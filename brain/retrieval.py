"""Recall: given a task/query, surface the most relevant past knowledge.

Two layers, by design:

  1. Keyword scoring -- always on, zero dependencies, instant, offline. Handles
     the common case and works even when the Gemini free tier is rate-limited.
  2. Embedding rerank -- optional (``BRAIN_EMBEDDINGS=1``); blends semantic
     similarity on top so "car insurance" can find a "KASKO" lesson. Degrades
     to layer 1 on any failure.

``recall()`` returns scored entries; ``recall_block()`` formats the top hits into
a compact markdown context block ready to prepend to an LLM prompt -- this is how
every autonomous job gets to stand on what we already learned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import embeddings
from .store import Entry, all_entries

# Function words that carry no retrieval signal (EN + AZ), kept short.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "be", "this", "that", "it", "as", "at", "by", "from", "we", "you",
    "i", "our", "your", "how", "what", "when", "do", "does", "make", "need",
    "ve", "ya", "ile", "ucun", "bir", "bu", "o", "da", "de", "ki", "ne", "var",
    "olan", "etmek", "et", "üçün", "ilə", "və", "necə", "nə", "olar", "lazim",
}

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    out = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if len(tok) < 2 or tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


_CONFIDENCE_BOOST = {"high": 1.15, "medium": 1.0, "low": 0.85}


@dataclass
class Hit:
    entry: Entry
    score: float
    keyword_score: float
    embed_score: float


def _document_frequency(entries: list[Entry]) -> dict[str, int]:
    df: dict[str, int] = {}
    for e in entries:
        seen = set(_tokens(e.text))
        for tok in seen:
            df[tok] = df.get(tok, 0) + 1
    return df


def _field_hit(term: str, field_tokens: set[str], field_text: str) -> float:
    """1.0 for an exact token match, 0.6 for a substring match (AZ morphology)."""
    if term in field_tokens:
        return 1.0
    # Substring catches suffixed/inflected forms ("kampaniya" vs "kampaniyani").
    if len(term) >= 4 and term in field_text:
        return 0.6
    return 0.0


def _keyword_score(query_terms: list[str], entry: Entry, df: dict[str, int], n_docs: int) -> float:
    import math

    title_text = entry.title.lower()
    tags_text = " ".join(entry.tags).lower()
    body_text = entry.body.lower()
    title_toks = set(_tokens(entry.title))
    tags_toks = set(_tokens(tags_text))
    body_toks = set(_tokens(entry.body))

    score = 0.0
    for term in query_terms:
        # IDF: rare terms across the corpus matter more.
        idf = math.log(1 + n_docs / (1 + df.get(term, 0)))
        field = (
            3.0 * _field_hit(term, title_toks, title_text)
            + 2.0 * _field_hit(term, tags_toks, tags_text)
            + 1.0 * _field_hit(term, body_toks, body_text)
        )
        score += idf * field
    # Normalize by query length so long queries don't dominate.
    if query_terms:
        score /= len(query_terms)
    return score * _CONFIDENCE_BOOST.get(entry.confidence, 1.0)


def recall(query: str, k: int = 5, *, floor: float = 0.15) -> list[Hit]:
    """Return up to ``k`` relevant entries, best first.

    ``floor`` filters out weak keyword matches. When embeddings are enabled the
    semantic layer can rescue cross-lingual matches that keywords miss.
    """
    entries = all_entries()
    if not entries:
        return []

    query_terms = _tokens(query)
    df = _document_frequency(entries)
    n_docs = len(entries)

    raw = [(e, _keyword_score(query_terms, e, df, n_docs)) for e in entries]
    max_kw = max((s for _, s in raw), default=0.0) or 1.0

    use_embed = embeddings.enabled()
    qvec = embeddings.embed(query) if use_embed else None

    hits: list[Hit] = []
    for entry, kw in raw:
        kw_norm = kw / max_kw
        emb = 0.0
        if qvec is not None:
            evec = embeddings.embed(entry.text)
            if evec is not None:
                emb = embeddings.cosine(qvec, evec)
        # Blend when we have a semantic signal; else pure keyword.
        if qvec is not None and emb > 0:
            final = 0.5 * kw_norm + 0.5 * emb
        else:
            final = kw_norm
        hits.append(Hit(entry=entry, score=final, keyword_score=kw_norm, embed_score=emb))

    hits = [h for h in hits if h.score >= floor]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]


def recall_block(
    query: str,
    *,
    k: int = 4,
    char_budget: int = 1600,
    header: str = "Institutional knowledge (what RAMIN OS already learned)",
) -> str:
    """Format top recall hits into a compact markdown block for prompt injection.

    Returns "" when there is nothing relevant, so callers can prepend it
    unconditionally without ever degrading an empty-store run.
    """
    hits = recall(query, k=k)
    if not hits:
        return ""

    lines = [f"## {header}", ""]
    used = 0
    for h in hits:
        e = h.entry
        body = e.body.strip()
        # Trim each entry's body to keep the whole block within budget.
        remaining = char_budget - used
        if remaining <= 120:
            break
        snippet = body if len(body) <= remaining else body[: remaining - 1].rstrip() + "…"
        block = f"- **[{e.type}] {e.title}** _(confidence: {e.confidence})_\n  {snippet}"
        lines.append(block)
        used += len(block)
    lines.append("")
    lines.append(
        "_Apply the above where relevant. If something here conflicts with the "
        "task, prefer the task and note the conflict._"
    )
    return "\n".join(lines)
