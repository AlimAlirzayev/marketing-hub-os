"""Build one local context card for every Ramin-OS builder entry point.

The bridge does not merge or overwrite agent-owned memory stores. It reads only
their curated Markdown indexes, combines them with authoritative repository
decisions and a live masked system pulse, and writes a machine-local card under
``data/``. Current code/state always outranks memory-derived hints.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "builder_context.md"
DECISIONS_PATH = ROOT / "memory" / "decisions.jsonl"

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
    r"\s*([:=])\s*([^\s,;]+)"
)
_SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
)


def _redact(text: str) -> str:
    clean = _SECRET_ASSIGNMENT.sub(
        lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text
    )
    for pattern in _SECRET_SHAPES:
        clean = pattern.sub("<redacted-secret>", clean)
    return clean


def _excerpt(text: str, limit: int) -> str:
    clean = _redact(text.strip())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit("\n", 1)[0]
    return cut + "\n\n[excerpt truncated]"


def _read(path: Path | None, limit: int) -> str:
    if not path or not path.is_file():
        return "(not available on this machine)"
    try:
        return _excerpt(path.read_text(encoding="utf-8", errors="replace"), limit)
    except OSError as exc:
        return f"(unavailable: {exc.__class__.__name__})"


def _project_slug(path: Path) -> str:
    return str(path.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")


def find_claude_memory() -> Path | None:
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    slug = _project_slug(ROOT)
    wanted = {slug.lower(), slug[:1].lower() + slug[1:]}
    for child in projects.iterdir():
        candidate = child / "memory" / "MEMORY.md"
        if child.name.lower() in wanted and candidate.is_file():
            return candidate
    candidates = list(projects.glob("*/memory/MEMORY.md"))
    candidates.sort(
        key=lambda p: (
            "ramin-os" in p.parent.parent.name.lower(),
            p.stat().st_mtime,
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def find_codex_memory() -> Path | None:
    base = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    path = base / "memories" / "memory_summary.md"
    return path if path.is_file() else None


def latest_decisions(limit: int = 8) -> list[dict[str, str]]:
    if not DECISIONS_PATH.is_file():
        return []
    rows: list[dict[str, str]] = []
    for raw in DECISIONS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "ts": str(item.get("ts") or ""),
                "kind": str(item.get("kind") or "note"),
                "summary": _redact(str(item.get("summary") or "")).strip(),
            }
        )
    return rows[-limit:]


def live_state() -> str:
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from gateway import sense

        return _redact(sense.pulse())
    except Exception as exc:
        return f"(live pulse unavailable: {exc.__class__.__name__})"


def render_context(
    *,
    claude_memory: str,
    codex_memory: str,
    decisions: Iterable[dict[str, str]],
    state: str,
    claude_path: Path | None = None,
    codex_path: Path | None = None,
) -> str:
    decision_lines = [
        f"- `{d.get('ts', '')}` **{d.get('kind', 'note')}** — {d.get('summary', '')}"
        for d in decisions
        if d.get("summary")
    ]
    if not decision_lines:
        decision_lines = ["- No shared decisions were available."]
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return "\n".join(
        [
            "# Ramin-OS Builder Context",
            "",
            f"Generated UTC: {generated}",
            "",
            "This is the common cold-start card for Codex, Claude Code, Gemini,",
            "OpenCode, Copilot, and other governed builders in this checkout.",
            "",
            "## Authority Order",
            "",
            "1. Live repository code, `services.json`, and the masked live state below.",
            "2. `AGENTS.md`, `SECURITY.md`, `docs/RAMIN_OS_CONTEXT.md`, and module docs.",
            "3. Latest shared decisions in `memory/decisions.jsonl`.",
            "4. Agent-specific memory excerpts below, used only as potentially stale hints.",
            "",
            "Never let a private agent memory override newer code or a superseding shared decision.",
            "Never copy credentials, private transcripts, customer data, or raw `.env` content into",
            "this card or into another agent's memory.",
            "",
            "## Mandatory Builder Contract",
            "",
            "- Ramin-OS is one product; builders are interchangeable entry points, not silos.",
            "- User-visible delivery follows `docs/USER_VISIBLE_DELIVERY_STANDARD.md`.",
            "- New system shape ships with governance, Hub discovery, `_SELF_FACTS`, docs, and tests.",
            "- Construction without applicable UI/Hub proof is **partial**, never complete.",
            "- Outward, destructive, credentialed, paid, or production actions keep human checkpoints.",
            "",
            "## Live Local State",
            "",
            "```text",
            _excerpt(state, 9000),
            "```",
            "",
            "## Latest Shared Decisions",
            "",
            *decision_lines,
            "",
            "## Claude Code Curated Memory Index",
            "",
            f"Source: `{claude_path}`" if claude_path else "Source: unavailable",
            "",
            _excerpt(claude_memory, 14000),
            "",
            "## Codex Curated Memory Summary",
            "",
            f"Source: `{codex_path}`" if codex_path else "Source: unavailable",
            "",
            _excerpt(codex_memory, 12000),
            "",
            "## Retrieval Rule",
            "",
            "Use these indexes to locate relevant history, then verify drift-prone facts against",
            "the current repo/runtime. Durable cross-builder decisions belong in",
            "`memory/decisions.jsonl` and the Brain workflow—not in a new agent-only silo.",
            "",
        ]
    )


def build() -> tuple[str, Path | None, Path | None]:
    claude_path = find_claude_memory()
    codex_path = find_codex_memory()
    text = render_context(
        claude_memory=_read(claude_path, 14000),
        codex_memory=_read(codex_path, 12000),
        decisions=latest_decisions(),
        state=live_state(),
        claude_path=claude_path,
        codex_path=codex_path,
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.is_file() else ""
    if old != text:
        OUT_PATH.write_text(text, encoding="utf-8")
    return text, claude_path, codex_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_context",
        help="refresh and print the full context for a session-start hook",
    )
    args = parser.parse_args(argv)
    text, claude_path, codex_path = build()
    if args.print_context:
        print(text)
    else:
        print(
            f"[builder-context] refreshed {OUT_PATH} "
            f"(claude={'yes' if claude_path else 'no'}, "
            f"codex={'yes' if codex_path else 'no'})"
        )
    return 0


if __name__ == "__main__":
    if os.getenv("RAMIN_NO_HOOKS"):
        raise SystemExit(0)
    raise SystemExit(main())
