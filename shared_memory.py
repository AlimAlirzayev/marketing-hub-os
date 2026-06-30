"""Memory with a hard boundary: SHARED engine context vs PRIVATE business context.

Two systems run this codebase — a corporate (xalq) build and a personal (global)
build — and they must share the ENGINE (code, tools, capabilities, engineering
decisions) but NEVER share business data (customers, brand content, strategy,
conversations). This module enforces that split:

  SHARED  (git-tracked → travels via push/pull):  memory/decisions.jsonl
          + memory/SHARED_CONTEXT.md         → engine/capability decisions only.
  PRIVATE (git-ignored → stays on this machine): data/private_context/decisions.jsonl
                                             → customer/brand/strategy/conversation.

SAFETY DEFAULT: `remember()` writes PRIVATE unless you pass scope="shared". So
business context never leaks into the traveling layer by accident — you must opt in
to share, and only for engine/capability facts. NEVER put secrets/keys anywhere here.

CLI:
    python shared_memory.py show                          # full local context
    python shared_memory.py add "summary" [kind] [scope]  # scope: private|shared
    python shared_memory.py recall "query"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Shared (git-tracked) — engine/capability only, travels between machines.
MEM_DIR = ROOT / "memory"
SHARED_LOG = MEM_DIR / "decisions.jsonl"
CONTEXT_FILE = MEM_DIR / "SHARED_CONTEXT.md"

# Private (git-ignored) — business/customer/brand/strategy, never travels.
PRIVATE_DIR = ROOT / "data" / "private_context"
PRIVATE_LOG = PRIVATE_DIR / "decisions.jsonl"

MAX_CONTEXT_CHARS = 4000  # keep injected context bounded for (free) LLM prompts


def _log_path(scope: str) -> Path:
    return SHARED_LOG if scope == "shared" else PRIVATE_LOG


def remember(
    summary: str,
    *,
    scope: str = "private",
    kind: str = "note",
    detail: str = "",
    source: str = "chat",
    tags: list[str] | None = None,
) -> dict:
    """Append a durable entry.

    scope="private" (DEFAULT) -> stays on this machine, never committed.
    scope="shared"            -> git-tracked, travels. Use ONLY for engine/
                                 capability decisions, never business/customer data.
    """
    scope = "shared" if scope == "shared" else "private"
    path = _log_path(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scope": scope,
        "kind": kind,
        "summary": summary.strip(),
        "detail": (detail or "").strip()[:2000],
        "source": source,
        "tags": tags or [],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001 — skip a corrupt line, never crash recall
            continue
    return out


def entries(limit: int = 20, scope: str | None = None) -> list[dict]:
    """Recent entries. scope=None merges shared+private (local full view)."""
    rows: list[dict] = []
    if scope in (None, "shared"):
        rows += [{**e, "scope": e.get("scope", "shared")} for e in _read(SHARED_LOG)]
    if scope in (None, "private"):
        rows += [{**e, "scope": e.get("scope", "private")} for e in _read(PRIVATE_LOG)]
    rows.sort(key=lambda e: e.get("ts", ""))
    return rows[-limit:]


def recall(query: str, limit: int = 8) -> list[dict]:
    """Cheap keyword recall across both stores (no embeddings needed)."""
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
    """Compact LOCAL context for a session/agent run: the shared canonical state +
    recent shared decisions + recent private decisions (this machine only)."""
    parts: list[str] = []
    if CONTEXT_FILE.exists():
        # Cap the static doc but reserve room so the (short) decision lines from
        # BOTH shared and private always survive — never let the cap drop the
        # private/local context.
        doc = CONTEXT_FILE.read_text(encoding="utf-8").strip()
        doc_cap = max(1500, MAX_CONTEXT_CHARS - 1500)
        if len(doc) > doc_cap:
            doc = doc[:doc_cap].rstrip() + "\n[... see memory/SHARED_CONTEXT.md]"
        parts.append(doc)

    shared = entries(limit, scope="shared")
    if shared:
        lines = ["## Recent SHARED engine decisions (travel via git)"]
        lines += [f"- [{e['ts']}] ({e['kind']}) {e['summary']}" for e in shared]
        parts.append("\n".join(lines))

    private = entries(limit, scope="private")
    if private:
        lines = ["## Recent PRIVATE context (this machine only — never shared)"]
        lines += [f"- [{e['ts']}] ({e['kind']}) {e['summary']}" for e in private]
        parts.append("\n".join(lines))

    return "\n\n".join(p for p in parts if p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    args = sys.argv[1:]
    if not args or args[0] == "show":
        print(context())
    elif args[0] == "add" and len(args) >= 2:
        kind = args[2] if len(args) >= 3 else "note"
        scope = args[3] if len(args) >= 4 else "private"
        rec = remember(args[1], scope=scope, kind=kind, source="cli")
        print(f"saved ({rec['scope']}):", rec["summary"])
    elif args[0] == "recall" and len(args) >= 2:
        for e in recall(args[1]):
            print(f"- [{e['ts']}] ({e.get('scope','?')}/{e['kind']}) {e['summary']}")
    else:
        print(__doc__)
