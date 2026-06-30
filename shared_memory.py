"""Shared blackboard memory — the durable context that TRAVELS across machines.

Problem it solves: decisions/intentions/context made in one place (a chat here, the
autonomous graph, Telegram later) were invisible everywhere else — the brain
(`data/memory`, git-ignored) and chat context are machine-local, so the "me" on
another machine started with amnesia.

This store is git-TRACKED (under `memory/`), so a normal `git push`/`pull` carries
the shared context to every machine and channel. In the L1–L4 memory model it is the
**L4 "summary / blackboard"** tier: a small, human+agent-readable layer that any
session reads first and any channel can append to. The richer per-machine working
memory stays in `brain/`.

    memory/SHARED_CONTEXT.md  — canonical current state + direction (read this first)
    memory/decisions.jsonl    — append-only log of decisions / important outcomes

SECURITY: this is committed to git. NEVER write secrets/keys/PII here — decisions,
context, and learnings only.

CLI:
    python shared_memory.py show                 # print the shared context
    python shared_memory.py add "summary" [kind] # append a decision/log entry
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEM_DIR = ROOT / "memory"
LOG = MEM_DIR / "decisions.jsonl"
CONTEXT_FILE = MEM_DIR / "SHARED_CONTEXT.md"

# Keep injected context bounded so it never bloats a (free) LLM prompt.
MAX_CONTEXT_CHARS = 4000


def remember(
    summary: str,
    *,
    kind: str = "decision",
    detail: str = "",
    source: str = "chat",
    tags: list[str] | None = None,
) -> dict:
    """Append a durable entry to the shared (git-tracked) log. Returns the record."""
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": kind,
        "summary": summary.strip(),
        "detail": (detail or "").strip()[:2000],
        "source": source,
        "tags": tags or [],
    }
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def entries(limit: int = 20) -> list[dict]:
    """The most recent log entries (newest last)."""
    if not LOG.exists():
        return []
    out: list[dict] = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001 — skip a corrupt line, never crash recall
            continue
    return out[-limit:]


def recall(query: str, limit: int = 8) -> list[dict]:
    """Cheap keyword recall over the log (no embeddings needed)."""
    q = (query or "").lower().split()
    if not q:
        return entries(limit)
    scored = []
    for e in entries(10_000):
        hay = f"{e.get('summary','')} {e.get('detail','')} {' '.join(e.get('tags',[]))}".lower()
        score = sum(1 for w in q if w in hay)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [e for _s, e in scored[:limit]]


def context(limit: int = 12) -> str:
    """Compact shared context to inject into a new session or agent run.

    SHARED_CONTEXT.md (the canonical state) + the most recent log lines, capped.
    """
    parts: list[str] = []
    if CONTEXT_FILE.exists():
        parts.append(CONTEXT_FILE.read_text(encoding="utf-8").strip())
    recent = entries(limit)
    if recent:
        lines = ["## Recent shared decisions / log"]
        for e in recent:
            lines.append(f"- [{e['ts']}] ({e['kind']}) {e['summary']}")
        parts.append("\n".join(lines))
    blob = "\n\n".join(p for p in parts if p)
    if len(blob) > MAX_CONTEXT_CHARS:
        blob = blob[:MAX_CONTEXT_CHARS].rstrip() + "\n\n[context trimmed]"
    return blob


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    args = sys.argv[1:]
    if not args or args[0] == "show":
        print(context())
    elif args[0] == "add" and len(args) >= 2:
        kind = args[2] if len(args) >= 3 else "decision"
        rec = remember(args[1], kind=kind, source="cli")
        print("saved:", rec["summary"])
    elif args[0] == "recall" and len(args) >= 2:
        for e in recall(args[1]):
            print(f"- [{e['ts']}] ({e['kind']}) {e['summary']}")
    else:
        print(__doc__)
