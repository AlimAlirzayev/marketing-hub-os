"""Unified hierarchical memory — the shared blackboard (L1–L4).

Implements the production memory architecture the project decided on, grounded in
the user's NVIDIA NCP AAI lessons: ONE shared, persistent, hierarchical memory
that every agent/channel reads from and writes to (not per-session silos).

  L1 working buffer  — recent turns per ``thread_id`` (this module, SQLite)
  L2 semantic recall — institutional knowledge (delegated to brain.recall)
  L3 entity memory   — people / brands / campaigns / handles seen in a thread
  L4 summary         — rolling compaction of older turns per thread

``assemble_context()`` fuses them in priority order (summary → recent turns →
entities → semantic knowledge) into one prompt block — the "priority-based context
assembly" from the lessons. Everything is dependency-light, has deterministic
fallbacks (works with the LLM free tier down), and shares the gateway SQLite DB so
it is genuinely one blackboard, not another silo.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "xidigitalos.db"

L1_MAX_TURNS = int(os.getenv("MEM_L1_MAX_TURNS", "12"))
L1_MAX_CHARS = int(os.getenv("MEM_L1_MAX_CHARS", "4000"))
SUMMARIZE_AFTER = int(os.getenv("MEM_SUMMARIZE_AFTER", "20"))  # keep buffer bounded
ASSEMBLE_MAX_CHARS = int(os.getenv("MEM_ASSEMBLE_MAX_CHARS", "6000"))


def _db_path() -> Path:
    # Env override keeps tests isolated from the live gateway DB.
    return Path(os.getenv("MEM_DB_PATH", str(_DEFAULT_DB)))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _db():
    """Connection that both commits/rolls-back AND closes (no leaked handles)."""
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init() -> None:
    """Create the blackboard tables if absent (idempotent, additive to the DB)."""
    with _db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS memory_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL, role TEXT, content TEXT,
                ts REAL DEFAULT (strftime('%s','now')))"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS ix_turns_thread ON memory_turns(thread_id, id)")
        c.execute(
            """CREATE TABLE IF NOT EXISTS memory_entities (
                thread_id TEXT NOT NULL, name TEXT, etype TEXT, note TEXT,
                mentions INTEGER DEFAULT 1, updated REAL,
                PRIMARY KEY (thread_id, name))"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS memory_summaries (
                thread_id TEXT PRIMARY KEY, summary TEXT, turns_at INTEGER, updated REAL)"""
        )
        c.commit()


# --------------------------------------------------------------------------
# L3 — entity extraction (deterministic; LLM-free so it always works)
# --------------------------------------------------------------------------

_HANDLE_RE = re.compile(r"@([A-Za-z0-9_.]{3,30})")
_MONEY_RE = re.compile(r"\b(\d+[.,]?\d*)\s?(azn|usd|eur|man|manat|₼|\$|€)\b", re.I)
_CAP_RE = re.compile(r"\b([A-ZƏÜÖĞİIŞÇ][\wƏəÜüÖöĞğİıŞşÇç]+(?:\s+[A-ZƏÜÖĞİIŞÇ][\wƏəÜüÖöĞğİıŞşÇç]+){0,2})\b")
_BRANDS = (
    "xalq sığorta", "xalq sigorta", "kasko", "azal", "azpetrol", "ateşgah",
    "ateshgah", "pasha", "rapidapi", "instagram", "tiktok", "telegram",
)
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "task", "user",
    "assistant", "instagram", "azərbaycan", "azerbaijan", "baku", "bakı",
}


def extract_entities(text: str) -> list[tuple[str, str]]:
    """Return [(name, etype)] found in text. Deterministic, dedup-preserving order."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(name: str, etype: str) -> None:
        key = name.casefold()
        if key and key not in seen:
            seen.add(key)
            found.append((name, etype))

    low = (text or "").casefold()
    for m in _HANDLE_RE.findall(text or ""):
        _add("@" + m, "handle")
    for brand in _BRANDS:
        if brand in low:
            _add(brand, "brand")
    for amount, unit in _MONEY_RE.findall(text or ""):
        _add(f"{amount} {unit.upper()}", "money")
    for m in _CAP_RE.findall(text or ""):
        name = m.strip()
        if len(name) < 3 or name.casefold() in _STOP:
            continue
        # Skip single very-common capitalized words; keep multiword or distinctive.
        if " " not in name and name.casefold() in _STOP:
            continue
        _add(name, "name")
    return found


def _upsert_entities(conn: sqlite3.Connection, thread_id: str, text: str) -> None:
    for name, etype in extract_entities(text):
        row = conn.execute(
            "SELECT mentions FROM memory_entities WHERE thread_id=? AND name=?",
            (thread_id, name),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE memory_entities SET mentions=mentions+1, updated=? WHERE thread_id=? AND name=?",
                (time.time(), thread_id, name),
            )
        else:
            conn.execute(
                "INSERT INTO memory_entities (thread_id, name, etype, note, mentions, updated) "
                "VALUES (?,?,?,?,1,?)",
                (thread_id, name, etype, "", time.time()),
            )


def entities_for(thread_id: str, query: str = "", limit: int = 8) -> list[dict]:
    init()
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT name, etype, mentions FROM memory_entities WHERE thread_id=? "
            "ORDER BY mentions DESC, updated DESC", (thread_id,)
        ).fetchall()]
    if query:
        q = query.casefold()
        # Light relevance boost: entities whose name overlaps the query first.
        rows.sort(key=lambda r: (r["name"].casefold() not in q, -r["mentions"]))
    return rows[:limit]


# --------------------------------------------------------------------------
# L1 — working buffer  +  L4 — rolling summary
# --------------------------------------------------------------------------

def observe(thread_id: str, role: str, content: str) -> None:
    """Record one turn (L1), update entities (L3), and roll up a summary (L4)
    when the buffer grows. Never raises — memory must not break execution."""
    if not thread_id or not (content or "").strip():
        return
    try:
        init()
        with _db() as c:
            c.execute(
                "INSERT INTO memory_turns (thread_id, role, content, ts) VALUES (?,?,?,?)",
                (str(thread_id), role or "user", content.strip(), time.time()),
            )
            _upsert_entities(c, str(thread_id), content)
            c.commit()
        _maybe_summarize(str(thread_id))
    except Exception:
        return


def working_buffer(thread_id: str, max_turns: int | None = None, max_chars: int | None = None) -> list[dict]:
    """Most recent turns for a thread, oldest→newest, char-capped (L1)."""
    init()
    max_turns = max_turns or L1_MAX_TURNS
    max_chars = max_chars or L1_MAX_CHARS
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT role, content FROM (SELECT * FROM memory_turns WHERE thread_id=? "
            "ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (thread_id, max_turns)
        ).fetchall()]
    # Trim from the front until under the char budget.
    total = sum(len(r["content"]) for r in rows)
    while rows and total > max_chars:
        total -= len(rows.pop(0)["content"])
    return rows


def _turn_count(conn: sqlite3.Connection, thread_id: str) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM memory_turns WHERE thread_id=?", (thread_id,)).fetchone()["n"]


def _maybe_summarize(thread_id: str) -> None:
    """Compact older turns into the rolling summary once the buffer exceeds the
    threshold, so the working window stays bounded without losing the gist."""
    with _db() as c:
        n = _turn_count(c, thread_id)
        if n < SUMMARIZE_AFTER:
            return
        row = c.execute("SELECT turns_at FROM memory_summaries WHERE thread_id=?", (thread_id,)).fetchone()
        last_at = row["turns_at"] if row else 0
        if n - last_at < SUMMARIZE_AFTER // 2:
            return  # don't re-summarize too often
        # Older turns = everything except the live working window.
        older = c.execute(
            "SELECT role, content FROM memory_turns WHERE thread_id=? ORDER BY id ASC LIMIT ?",
            (thread_id, max(0, n - L1_MAX_TURNS)),
        ).fetchall()
        prev = c.execute("SELECT summary FROM memory_summaries WHERE thread_id=?", (thread_id,)).fetchone()
        base = prev["summary"] if prev else ""
        summary = _summarize_text(base, [dict(r) for r in older])
        c.execute(
            "INSERT INTO memory_summaries (thread_id, summary, turns_at, updated) VALUES (?,?,?,?) "
            "ON CONFLICT(thread_id) DO UPDATE SET summary=excluded.summary, turns_at=excluded.turns_at, updated=excluded.updated",
            (thread_id, summary, n, time.time()),
        )
        c.commit()


def _summarize_text(base: str, turns: list[dict]) -> str:
    """LLM summary if available, else a deterministic compaction (always works)."""
    joined = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
    text = (base + "\n" + joined).strip() if base else joined
    llm_summary = _llm_summary(text)
    if llm_summary:
        return llm_summary[:1500]
    # Deterministic fallback: keep the first sentence of each distinct turn,
    # newest-biased, capped — a lossy-but-honest gist, no fabrication.
    bullets: list[str] = []
    seen: set[str] = set()
    for t in turns:
        head = re.split(r"(?<=[.!?])\s", t["content"].strip(), maxsplit=1)[0][:160]
        key = head.casefold()
        if head and key not in seen:
            seen.add(key)
            bullets.append(f"- {t['role']}: {head}")
    gist = "\n".join(bullets[-12:])
    return ((base + "\n" if base else "") + gist).strip()[:1500]


def _llm_summary(text: str) -> str:
    """Optional LLM compaction. Guarded: any failure → '' (deterministic fallback)."""
    if os.getenv("MEM_SUMMARY_LLM", "0").lower() not in {"1", "true", "yes", "on"}:
        return ""
    try:
        from . import capture  # brain's existing LLM access
        fn = getattr(capture, "_complete", None) or getattr(capture, "complete", None)
        if not fn:
            return ""
        prompt = ("Aşağıdakı söhbəti 4-6 qısa Azərbaycanca bənddə xülasə et "
                  "(faktları uydurma, yalnız mətndən):\n\n" + text[:6000])
        return (fn(prompt) or "").strip()
    except Exception:
        return ""


def summary(thread_id: str) -> str:
    init()
    with _db() as c:
        row = c.execute("SELECT summary FROM memory_summaries WHERE thread_id=?", (thread_id,)).fetchone()
    return row["summary"] if row and row["summary"] else ""


# --------------------------------------------------------------------------
# Blackboard assembly — fuse L4 + L1 + L3 + L2 into one prompt block
# --------------------------------------------------------------------------

def _recall_block(query: str, k: int) -> str:
    try:
        from .retrieval import recall_block  # L2 semantic, same package
        return recall_block(query, k=k) or ""
    except Exception:
        return ""


def assemble_context(query: str, thread_id: str | None = None, *, k: int = 4,
                     include_recall: bool = True) -> str:
    """One prompt-ready memory block fusing all available layers, priority-ordered."""
    sections: list[str] = []

    if thread_id:
        s = summary(thread_id)
        if s:
            sections.append("### Söhbət xülasəsi (L4)\n" + s)

        buf = working_buffer(thread_id)
        if buf:
            lines = "\n".join(f"- {t['role']}: {t['content'][:300]}" for t in buf)
            sections.append("### Son danışıq (L1)\n" + lines)

        ents = entities_for(thread_id, query)
        if ents:
            lines = "\n".join(f"- {e['name']} ({e['etype']}, {e['mentions']}x)" for e in ents)
            sections.append("### Əlaqəli obyektlər (L3)\n" + lines)

    if include_recall:
        rb = _recall_block(query, k)
        if rb:
            sections.append("### Bildiklərimiz (L2)\n" + rb)

    if not sections:
        return ""
    block = "## Yaddaş konteksti\n\n" + "\n\n".join(sections)
    return block[:ASSEMBLE_MAX_CHARS]


def thread_stats(thread_id: str) -> dict:
    init()
    with _db() as c:
        turns = _turn_count(c, thread_id)
        ents = c.execute("SELECT COUNT(*) AS n FROM memory_entities WHERE thread_id=?", (thread_id,)).fetchone()["n"]
        has_summary = bool(c.execute("SELECT 1 FROM memory_summaries WHERE thread_id=?", (thread_id,)).fetchone())
    return {"thread_id": thread_id, "turns": turns, "entities": ents, "has_summary": has_summary}
