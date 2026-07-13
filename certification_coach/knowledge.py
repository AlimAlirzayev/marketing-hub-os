"""Knowledge, vector recall, and learner memory for Certification Coach.

This module is deliberately inspectable and low-dependency:

- source-of-truth knowledge lives in JSON/Markdown files;
- the local vector store is a sparse TF-IDF index written to disk;
- optional semantic rerank uses the existing Brain embedding adapter only when
  `BRAIN_EMBEDDINGS=1`;
- learner memory is local runtime JSONL under root `data/`, which is gitignored.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from . import coach


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"
RUNTIME_DIR = PROJECT_ROOT / "data" / "certification_coach"
INDEX_PATH = RUNTIME_DIR / "vector_index.json"
MEMORY_PATH = RUNTIME_DIR / "learner_memory.jsonl"

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_.'-]+", re.UNICODE)
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "be", "this", "that", "it", "as", "at", "by", "from",
    "you", "your", "we", "our", "what", "why", "how", "which", "bir",
    "bu", "ve", "ya", "ile", "ucun", "lazim", "need", "want",
}


@dataclasses.dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    title: str
    text: str
    source: str
    kind: str
    tags: tuple[str, ...] = ()
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "source": self.source,
            "kind": self.kind,
            "tags": list(self.tags),
            "url": self.url,
        }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for token in _TOKEN_RE.findall((text or "").casefold()):
        token = token.strip("._-'")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        out.append(token)
    return out


def _read_markdown_chunks() -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    if not KNOWLEDGE_DIR.exists():
        return chunks
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ").title()
        sections = re.split(r"\n(?=## )", text)
        for index, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            first = section.splitlines()[0].lstrip("# ").strip()
            chunks.append(
                KnowledgeChunk(
                    id=f"kb:{path.stem}:{index}",
                    title=first or title,
                    text=section,
                    source=str(path.relative_to(PROJECT_ROOT)),
                    kind="playbook",
                    tags=("mentor", "certification", path.stem),
                )
            )
    return chunks


def _catalog_chunks() -> list[KnowledgeChunk]:
    data = coach.catalog()
    chunks: list[KnowledgeChunk] = []
    chunks.append(
        KnowledgeChunk(
            id="policy:ethics",
            title="Exam integrity policy",
            text=(
                "Allowed: "
                + "; ".join(data["ethics_policy"]["allowed"])
                + "\nBlocked: "
                + "; ".join(data["ethics_policy"]["blocked"])
            ),
            source="certification_coach/data/certifications.json",
            kind="policy",
            tags=("ethics", "approval", "exam_integrity"),
        )
    )
    for checkpoint in data.get("approval_checkpoints", []):
        chunks.append(
            KnowledgeChunk(
                id=f"checkpoint:{checkpoint['id']}",
                title=f"Approval checkpoint: {checkpoint['label']}",
                text=f"Risk: {checkpoint['risk']}. Rule: {checkpoint['agent_rule']}",
                source="certification_coach/data/certifications.json",
                kind="checkpoint",
                tags=("approval", checkpoint["id"]),
            )
        )

    for cert in data["certifications"]:
        tags = tuple(str(tag) for tag in cert.get("focus_tags", []))
        chunks.append(
            KnowledgeChunk(
                id=f"cert:{cert['id']}:profile",
                title=cert["title"],
                text=(
                    f"Provider: {cert['provider']}. Track: {cert['track']}. "
                    f"Level: {cert['level']}. Difficulty: {cert['difficulty']}/5. "
                    f"Proof power: {cert['proof_power']}/100. Estimated hours: "
                    f"{cert['estimated_hours']}. Cost: {cert['cost']}. "
                    f"Proctored: {cert['proctored']}. Source note: {cert['source_note']}"
                ),
                source="certification_coach/data/certifications.json",
                kind="certification",
                tags=tags + (cert["track"], cert["provider"]),
                url=cert["source_url"],
            )
        )
        chunks.append(
            KnowledgeChunk(
                id=f"cert:{cert['id']}:prep",
                title=f"{cert['title']} prep and proof",
                text=(
                    "Best for: "
                    + "; ".join(cert.get("best_for", []))
                    + "\nPrep topics: "
                    + "; ".join(cert.get("prep_topics", []))
                    + f"\nPortfolio task: {cert['portfolio_task']}"
                    + f"\nMentor move: {cert['mentor_move']}"
                ),
                source="certification_coach/data/certifications.json",
                kind="prep",
                tags=tags + ("portfolio", "prep"),
                url=cert["source_url"],
            )
        )
    return chunks


def knowledge_chunks(*, include_brain: bool = False, query: str = "") -> list[KnowledgeChunk]:
    chunks = _catalog_chunks() + _read_markdown_chunks()
    if include_brain and query:
        chunks.extend(_brain_chunks(query))
    return chunks


def _brain_chunks(query: str) -> list[KnowledgeChunk]:
    try:
        from brain import retrieval
    except Exception:
        return []
    out: list[KnowledgeChunk] = []
    try:
        for hit in retrieval.recall(query, k=4, floor=0.05):
            entry = hit.entry
            out.append(
                KnowledgeChunk(
                    id=f"brain:{entry.id}",
                    title=entry.title,
                    text=entry.body,
                    source=f"brain:{entry.id}",
                    kind=f"brain_{entry.type}",
                    tags=tuple(entry.tags),
                )
            )
    except Exception:
        return []
    return out


def _doc_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    if not counts:
        return {}
    total = sum(counts.values())
    vec = {term: (count / total) * idf.get(term, 1.0) for term, count in counts.items()}
    norm = math.sqrt(sum(weight * weight for weight in vec.values())) or 1.0
    return {term: weight / norm for term, weight in vec.items()}


def rebuild_index(*, include_brain: bool = False, query: str = "") -> dict[str, Any]:
    """Build the local sparse vector index and persist it to disk."""
    docs = knowledge_chunks(include_brain=include_brain, query=query)
    tokenized = {doc.id: _tokens(f"{doc.title} {' '.join(doc.tags)} {doc.text}") for doc in docs}
    df: Counter[str] = Counter()
    for toks in tokenized.values():
        df.update(set(toks))
    n_docs = max(len(docs), 1)
    idf = {term: math.log(1 + n_docs / (1 + freq)) + 1.0 for term, freq in df.items()}
    index = {
        "schema_version": 1,
        "built_at": _now(),
        "engine": "local_sparse_tfidf",
        "semantic_rerank": _embedding_info(),
        "documents": [
            {
                **doc.as_dict(),
                "vector": _doc_vector(tokenized[doc.id], idf),
            }
            for doc in docs
        ],
        "idf": idf,
    }
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _load_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        return rebuild_index()
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return rebuild_index()


def _cosine_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b.get(term, 0.0) for term, weight in a.items())


def _embedding_info() -> dict[str, Any]:
    try:
        from brain import embeddings

        return embeddings.provider_info()
    except Exception:
        return {
            "enabled": False,
            "provider": "unavailable",
            "model": "",
            "endpoint": "",
            "endpoint_private": None,
            "external_allowed": False,
        }


def _semantic_rerank(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from brain import embeddings
    except Exception:
        return hits
    if not embeddings.enabled():
        return hits
    qvec = embeddings.embed(query)
    if qvec is None:
        return hits
    reranked: list[dict[str, Any]] = []
    for hit in hits:
        doc_text = f"{hit['title']}\n{hit['text']}"
        dvec = embeddings.embed(doc_text)
        semantic = embeddings.cosine(qvec, dvec) if dvec is not None else 0.0
        item = dict(hit)
        item["semantic_score"] = round(semantic, 4)
        item["score"] = round((0.65 * hit["score"]) + (0.35 * semantic), 4)
        reranked.append(item)
    reranked.sort(key=lambda item: item["score"], reverse=True)
    return reranked


def search(query: str, *, k: int = 6, include_brain: bool = True) -> list[dict[str, Any]]:
    """Search the coach knowledge base with local vector recall."""
    if not query.strip():
        return []
    index = _load_index()
    if include_brain:
        # Brain entries are query-dependent; rebuild in memory for this search.
        docs = knowledge_chunks(include_brain=True, query=query)
        index = _temporary_index(docs)
    idf = index.get("idf", {})
    qvec = _doc_vector(_tokens(query), idf)
    hits: list[dict[str, Any]] = []
    for doc in index.get("documents", []):
        score = _cosine_sparse(qvec, doc.get("vector", {}))
        if score <= 0:
            continue
        text = doc.get("text", "")
        hits.append(
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "source": doc.get("source"),
                "kind": doc.get("kind"),
                "tags": doc.get("tags", []),
                "url": doc.get("url", ""),
                "score": round(score, 4),
                "text": text,
                "snippet": text[:420].strip(),
            }
        )
    hits.sort(key=lambda item: item["score"], reverse=True)
    return _semantic_rerank(query, hits[: max(k * 2, k)])[:k]


def _temporary_index(docs: list[KnowledgeChunk]) -> dict[str, Any]:
    tokenized = {doc.id: _tokens(f"{doc.title} {' '.join(doc.tags)} {doc.text}") for doc in docs}
    df: Counter[str] = Counter()
    for toks in tokenized.values():
        df.update(set(toks))
    n_docs = max(len(docs), 1)
    idf = {term: math.log(1 + n_docs / (1 + freq)) + 1.0 for term, freq in df.items()}
    return {
        "documents": [
            {
                **doc.as_dict(),
                "vector": _doc_vector(tokenized[doc.id], idf),
            }
            for doc in docs
        ],
        "idf": idf,
    }


def stats() -> dict[str, Any]:
    index = _load_index()
    memory = learner_summary()
    brain_stats: dict[str, Any]
    try:
        from brain import store

        brain_stats = store.stats()
    except Exception:
        brain_stats = {"total": 0, "pending": 0, "store_dir": ""}
    return {
        "knowledge_chunks": len(knowledge_chunks()),
        "index_documents": len(index.get("documents", [])),
        "index_engine": index.get("engine", "local_sparse_tfidf"),
        "index_built_at": index.get("built_at", ""),
        "index_path": str(INDEX_PATH),
        "learner_memory_records": memory["records"],
        "learner_memory_path": str(MEMORY_PATH),
        "brain_entries": brain_stats.get("total", 0),
        "brain_pending": brain_stats.get("pending", 0),
        "semantic_rerank": _embedding_info(),
    }


def record_event(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append a private local learning event. Never store secrets or raw exam content."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": _now(),
        "kind": kind,
        "payload": payload,
    }
    with MEMORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def record_plan(profile: dict[str, Any], plan: dict[str, Any]) -> None:
    def _as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [item for item in value.replace(",", " ").split() if item]
        return []

    record_event(
        "plan_created",
        {
            "role": profile.get("role"),
            "level": profile.get("level"),
            "weekly_hours": profile.get("weekly_hours"),
            "focus_tags": _as_list(profile.get("focus_tags", [])),
            "recommended": [item["id"] for item in plan.get("recommended_stack", [])],
        },
    )


def record_mock_grade(grade: dict[str, Any]) -> None:
    weak = [item["id"] for item in grade.get("review", []) if not item.get("correct")]
    record_event(
        "mock_graded",
        {
            "cert_id": grade.get("cert_id"),
            "score": grade.get("score"),
            "correct": grade.get("correct"),
            "total": grade.get("total"),
            "verdict": grade.get("verdict"),
            "weak_question_ids": weak[:12],
        },
    )


def _memory_events(limit: int = 200) -> list[dict[str, Any]]:
    if not MEMORY_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in MEMORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-limit:]


def learner_summary() -> dict[str, Any]:
    events = _memory_events()
    attempts = [e for e in events if e.get("kind") == "mock_graded"]
    by_cert: dict[str, list[float]] = {}
    weak: Counter[str] = Counter()
    for event in attempts:
        payload = event.get("payload", {})
        cert_id = str(payload.get("cert_id") or "")
        if cert_id:
            by_cert.setdefault(cert_id, []).append(float(payload.get("score") or 0))
        weak.update(str(item) for item in payload.get("weak_question_ids", []))
    return {
        "records": len(events),
        "mock_attempts": len(attempts),
        "scores_by_cert": {
            cert_id: {
                "attempts": len(scores),
                "latest": scores[-1],
                "best": max(scores),
                "average": round(sum(scores) / len(scores), 1),
            }
            for cert_id, scores in by_cert.items()
        },
        "weak_question_ids": [item for item, _count in weak.most_common(8)],
        "recent": events[-6:],
    }


def enrich_plan(plan: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Attach evidence, vector/memory status, and institutional recall to a plan."""
    query_parts = [
        str(profile.get("role") or ""),
        str(profile.get("goals") or ""),
        " ".join(str(item) for item in profile.get("focus_tags", [])),
        " ".join(item["title"] for item in plan.get("recommended_stack", [])[:3]),
    ]
    query = " ".join(part for part in query_parts if part.strip())
    evidence = search(query or "marketing certification mentor", k=8, include_brain=True)
    plan = dict(plan)
    plan["knowledge"] = {
        "status": stats(),
        "evidence": evidence,
        "learner_memory": learner_summary(),
        "architecture": {
            "source_of_truth": [
                "certification_coach/data/certifications.json",
                "certification_coach/data/knowledge/*.md",
                "brain/data memory via brain.retrieval when relevant",
            ],
            "vector_store": str(INDEX_PATH),
            "memory_store": str(MEMORY_PATH),
            "retrieval": "local sparse TF-IDF vectors, optional Brain embeddings rerank",
            "fallback": "extractive evidence snippets when LLM synthesis is unavailable",
        },
    }
    return plan


def answer_question(question: str, profile: dict[str, Any] | None = None, *, use_llm: bool = True) -> dict[str, Any]:
    """Answer a learner question from retrieved knowledge, with optional LLM synthesis."""
    profile = profile or {}
    query = f"{question} {profile.get('role','')} {profile.get('goals','')} {' '.join(profile.get('focus_tags', []))}"
    hits = search(query, k=6, include_brain=True)
    if not hits:
        return {
            "answer": "Bu suala cavab vermək üçün hələ uyğun bilik chunk-u tapılmadı. Kataloqu yeniləmək və ya rəsmi mənbəni yoxlamaq lazımdır.",
            "mode": "no_hits",
            "evidence": [],
        }

    llm_answer = _synthesise_with_llm(question, profile, hits) if use_llm else ""
    if llm_answer:
        return {"answer": llm_answer, "mode": "rag_llm", "evidence": hits}

    lines = [
        "Retrieved evidence əsasında cavab:",
        "",
    ]
    for hit in hits[:3]:
        lines.append(f"- {hit['title']}: {hit['snippet']}")
    lines.append("")
    lines.append("Qeyd: bu fallback cavabıdır; LLM sintezi aktiv deyilsə və ya alınmayıbsa, sistem yalnız tapdığı mənbə fraqmentlərini göstərir.")
    return {"answer": "\n".join(lines), "mode": "extractive_fallback", "evidence": hits}


def _synthesise_with_llm(question: str, profile: dict[str, Any], hits: list[dict[str, Any]]) -> str:
    try:
        import llm_router
    except Exception:
        return ""
    context = "\n\n".join(
        f"[{hit['id']}] {hit['title']}\nSource: {hit['source']}\n{hit['text'][:900]}"
        for hit in hits[:6]
    )
    prompt = f"""You are the Ramin-OS Marketing Certification Coach.
Answer only from the retrieved context. Be candid about uncertainty.
Never suggest taking an exam for the learner or answering live exam questions.

Learner profile:
{json.dumps(profile, ensure_ascii=False)[:1200]}

Question:
{question}

Retrieved context:
{context}

Return a concise Azerbaijani answer with 2-4 bullets and cite chunk ids in brackets.
"""
    try:
        text, _model = llm_router.complete(prompt, tier="cheap", temperature=0.2)
        return (text or "").strip()
    except Exception:
        return ""
