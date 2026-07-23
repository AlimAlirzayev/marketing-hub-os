"""gateway/knowledge_graph.py — a dependency-free knowledge graph over the
system's OWN accumulated memory (GraphRAG, first slice, 2026-07-23).

WHY. The operator asked (jobs 180/181) whether we use vector databases and
knowledge graphs. We already have vector RAG (the Knowledge Base, port 8895) —
it finds SIMILAR text. A knowledge graph finds CONNECTED knowledge: which
decisions/lessons share a capability, a tag, a client, a trend. This module
builds that graph from what we already own — memory/decisions.jsonl (the shared
engine decisions), data/memory/*.md (learned lessons/patterns/playbooks) and
data/skills/*.md — with ZERO fabricated data and ZERO new dependencies (a plain
adjacency graph + BFS, persisted nowhere; the corpus is small so a rebuild is
cheap and never stale).

vector RAG answers "what is like this?"; this answers "what is connected to this,
and how?". `related(query)` seeds on matching tags/terms, walks the graph, and
returns the connected neighbourhood of real memory entries with the path that
connects them — so the brain can reason over relationships, not just similarity.
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DECISIONS = _ROOT / "memory" / "decisions.jsonl"
_MEM_DIR = _ROOT / "data" / "memory"
_SKILLS_DIR = _ROOT / "data" / "skills"

# Curated lexicon of core system capabilities/concepts. A term links two entries
# that both mention the same capability even when they carry no shared tag. Kept
# small and real (things the system actually has), not an open NER.
_LEXICON = [
    "claude", "gemini", "gpt-oss", "groq", "opencode", "codex", "ollama",
    "instagram", "tiktok", "youtube", "meta ads", "google ads", "rapidapi",
    "yt-dlp", "voice", "tts", "stt", "elevenlabs", "edge-tts", "whisper",
    "crew", "council", "social", "radar", "champion", "curator", "rag",
    "knowledge graph", "vector", "seo", "ga4", "capi", "brain", "floor",
    "telegram", "supervisor", "queue", "summon", "approval", "checkpoint",
    "cookies", "browser", "sync", "memory", "skills", "lyria", "veo", "imagen",
    "call agent", "phone", "kasko", "xalq sığorta", "flora", "higgsfield",
]

_WORD = re.compile(r"[0-9A-Za-zƏəÜüÖöĞğİıŞşÇç]+")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_CACHE: dict | None = None
_CACHE_AT = 0.0
_TTL = 300  # rebuild at most every 5 min; the corpus changes rarely


def _norm(text: str) -> str:
    return (text or "").lower()


def _terms_in(text: str) -> set[str]:
    low = _norm(text)
    found = {t for t in _LEXICON if t in low}
    found |= {m.group(1).strip().lower() for m in _WIKILINK.finditer(text or "")}
    return found


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.adj: dict[str, set[tuple[str, str]]] = {}

    def add_node(self, nid: str, **meta) -> None:
        if nid not in self.nodes:
            self.nodes[nid] = meta
            self.adj[nid] = set()

    def link(self, a: str, b: str, rel: str) -> None:
        self.adj.setdefault(a, set()).add((b, rel))
        self.adj.setdefault(b, set()).add((a, rel))

    def add_entry(self, nid: str, label: str, text: str, kind: str,
                  ts: float, tags: list[str]) -> None:
        self.add_node(nid, type="entry", label=label[:120], kind=kind,
                      ts=ts, text=text[:1200])
        for tag in tags:
            t = tag.strip().lower()
            if not t:
                continue
            tid = f"tag:{t}"
            self.add_node(tid, type="tag", label=t)
            self.link(nid, tid, "HAS_TAG")
        for term in _terms_in(text):
            mid = f"term:{term}"
            self.add_node(mid, type="term", label=term)
            self.link(nid, mid, "MENTIONS")

    def entry_count(self) -> int:
        return sum(1 for n in self.nodes.values() if n.get("type") == "entry")


def _load_decisions(g: Graph) -> None:
    if not _DECISIONS.exists():
        return
    for i, line in enumerate(_DECISIONS.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        summary = d.get("summary", "")
        text = f"{summary} {d.get('detail', '')}".strip()
        if not text:
            continue
        g.add_entry(f"dec:{i}", summary or f"decision {i}", text,
                    kind=d.get("kind", "decision"),
                    ts=_parse_ts(d.get("ts")), tags=list(d.get("tags") or []))


def _load_md_dir(g: Graph, directory: Path, prefix: str) -> None:
    if not directory.exists():
        return
    for f in sorted(directory.glob("*.md")):
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        label = (m.group(1).strip() if m else f.stem.replace("-", " "))
        # kind from the lesson-/pattern-/playbook- filename convention
        kind = f.stem.split("-", 1)[0] if "-" in f.stem else "note"
        g.add_entry(f"{prefix}:{f.stem}", label, body, kind=kind,
                    ts=f.stat().st_mtime, tags=[])


def _parse_ts(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        return time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0.0


def build(force: bool = False) -> Graph:
    """Build (and briefly cache) the graph from the live memory corpus."""
    global _CACHE, _CACHE_AT
    if not force and _CACHE is not None and (time.time() - _CACHE_AT) < _TTL:
        return _CACHE
    g = Graph()
    _load_decisions(g)
    _load_md_dir(g, _MEM_DIR, "mem")
    _load_md_dir(g, _SKILLS_DIR, "skill")
    _CACHE, _CACHE_AT = g, time.time()
    return g


def stats() -> dict:
    g = build()
    tags = sum(1 for n in g.nodes.values() if n.get("type") == "tag")
    terms = sum(1 for n in g.nodes.values() if n.get("type") == "term")
    edges = sum(len(v) for v in g.adj.values()) // 2
    return {"entries": g.entry_count(), "tags": tags, "terms": terms, "edges": edges}


def _seed_nodes(g: Graph, query: str) -> list[str]:
    toks = {t for t in (_WORD.findall(_norm(query))) if len(t) > 2}
    ql = _norm(query)
    seeds: list[str] = []
    # exact-ish tag/term hits first (the strongest connectors)
    for nid, n in g.nodes.items():
        if n.get("type") in ("tag", "term"):
            label = n["label"]
            if label in ql or any(tok in label or label in tok for tok in toks):
                seeds.append(nid)
    # then entries whose text directly matches query tokens
    if not seeds:
        for nid, n in g.nodes.items():
            if n.get("type") == "entry" and toks & set(_WORD.findall(_norm(n["text"]))):
                seeds.append(nid)
    return seeds


def related(query: str, depth: int = 2, limit: int = 10) -> list[dict]:
    """Connected memory entries for a query, via graph proximity. Each result:
    {label, kind, ts, distance, via} — 'via' names the tag/term that connects it."""
    g = build()
    seeds = _seed_nodes(g, query)
    if not seeds:
        return []
    # BFS distances from the seed frontier
    dist: dict[str, int] = {s: 0 for s in seeds}
    via: dict[str, str] = {}
    dq = deque(seeds)
    while dq:
        cur = dq.popleft()
        if dist[cur] >= depth:
            continue
        for nb, _rel in g.adj.get(cur, ()):  # noqa: perf fine at this scale
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                # remember a connector label (the tag/term we passed through)
                connector = g.nodes[cur].get("label") if g.nodes[cur]["type"] in ("tag", "term") else via.get(cur, "")
                via[nb] = connector or via.get(cur, "")
                dq.append(nb)
    entries = [(nid, n) for nid, n in ((i, g.nodes[i]) for i in dist)
               if n.get("type") == "entry"]
    entries.sort(key=lambda x: (dist[x[0]], -x[1].get("ts", 0)))
    out = []
    for nid, n in entries[:limit]:
        out.append({"label": n["label"], "kind": n.get("kind", ""),
                    "ts": n.get("ts", 0), "distance": dist[nid],
                    "via": via.get(nid, "seed")})
    return out


def graph_recall(query: str, limit: int = 8) -> str:
    """A formatted 'connected knowledge' block for the brain / the operator."""
    g = build()
    hits = related(query, limit=limit)
    if not hits:
        s = stats()
        return (f"🕸 Bilik qrafında «{query}» üçün əlaqə tapılmadı "
                f"(qraf: {s['entries']} giriş, {s['tags']} tag, {s['terms']} termin).")
    lines = [f"🕸 **Bilik qrafı — «{query}» ilə əlaqəli** ({len(hits)} nəticə):"]
    for h in hits:
        when = time.strftime("%Y-%m-%d", time.localtime(h["ts"])) if h["ts"] else "—"
        conn = f" · bağlantı: {h['via']}" if h["via"] and h["via"] != "seed" else ""
        lines.append(f"• [{when}] {h['label']}{conn}")
    return "\n".join(lines)
