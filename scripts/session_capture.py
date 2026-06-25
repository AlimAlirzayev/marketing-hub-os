"""Autonomous session capture: the interactive (VSC/CLI) counterpart to the
gateway worker's post-job reflection.

Wired as a Claude Code **SessionEnd** hook so that when a session with the
assistant ends gracefully, the durable lessons of that session are distilled and
**auto-committed straight into the trusted store** (``data/memory/*.md``) --
WITHOUT the operator having to say "remember this" OR having to go approve a queue.
The operator is a bottleneck we removed on purpose: a strong lesson must not wait
on a human who might forget. Safety comes from a QUALITY gate instead of a human
gate (see capture_session).

SessionEnd only fires reliably on a clean exit (/clear, /exit, logout, idle). When
a window is just closed, it may not flush -- so ``capture_sweep.py`` is the safety
net that catches idle, not-yet-captured transcripts on the next SessionStart. Both
share ``capture_session()`` below and the same marker dir, so nothing is captured
twice.

Design rules (mirroring brain/ + gateway/knowledge.py):
  - Never raise. A capture failure must never disrupt the user's session.
  - Zero-cost without a key: brain.distill() no-ops when no Gemini key / offline.
  - Quality gate, not human gate: only high/medium-confidence lessons are
    committed; everything is plain markdown (reversible) and tagged
    ``source: reflect-auto`` so auto-captured entries stay distinguishable.
  - Idempotent: a per-session marker (keyed by session id = transcript stem in
    real runs) avoids double-capturing the same session.

Claude Code passes the hook payload as JSON on stdin, including ``transcript_path``
and ``session_id``. We parse the transcript defensively (its shape can vary).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAPTURE_LOG = ROOT / "data" / "memory" / "_session_capture.log"
CAPTURED_DIR = ROOT / "data" / "memory" / ".captured"  # markers live OUTSIDE _pending
MAX_TASK_CHARS = 2000
MAX_RESULT_CHARS = 6000


def _load_env() -> None:
    """Load .env into os.environ so brain.reflect can see the Gemini key.

    Hooks run with a bare environment (the key lives in .env, not exported), and
    brain.reflect reads os.getenv directly. Without this the hook would silently
    no-op. Dependency-free fallback parser mirrors gateway/_bootstrap.load_env.
    """
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def _log(msg: str) -> None:
    try:
        CAPTURE_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().isoformat(timespec="seconds")
        with CAPTURE_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{stamp}  {msg}\n")
    except Exception:
        pass


def _marker(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in session_id)
    return CAPTURED_DIR / f"{safe}.done"


def is_captured(session_id: str) -> bool:
    return _marker(session_id).exists()


def mark_captured(session_id: str) -> None:
    try:
        CAPTURED_DIR.mkdir(parents=True, exist_ok=True)
        _marker(session_id).write_text(_dt.datetime.now().isoformat(), encoding="utf-8")
    except Exception:
        pass


def _text_of(content) -> str:
    """Flatten a message 'content' (str or list of blocks) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("type") == "tool_result" and block.get("content"):
                    parts.append(_text_of(block["content"])[:300])  # tool results are noisy
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def _parse_transcript(path: Path) -> tuple[str, str]:
    """Return (task, result): user asks vs assistant outputs, both truncated."""
    user_msgs: list[str] = []
    asst_msgs: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return "", ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        msg = evt.get("message") if isinstance(evt, dict) else None
        if not isinstance(msg, dict):
            continue
        role = msg.get("role") or evt.get("type")
        text = _text_of(msg.get("content", "")).strip()
        if not text:
            continue
        if role == "user":
            user_msgs.append(text)
        elif role == "assistant":
            asst_msgs.append(text)

    # Task = what the operator asked (first + last carry the intent).
    task_bits = user_msgs[:1] + (user_msgs[-2:] if len(user_msgs) > 2 else user_msgs[1:])
    task = "\n---\n".join(task_bits)[:MAX_TASK_CHARS]
    # Result = what the assistant concluded/built (the tail matters most).
    result = "\n\n".join(asst_msgs[-6:])[-MAX_RESULT_CHARS:]
    return task, result


def capture_session(transcript_path: str | Path, session_id: str) -> int:
    """Distill one session's transcript into pending lessons. Returns count.

    Shared by the SessionEnd hook (main) and the SessionStart sweep. Never raises;
    idempotent via the per-session marker.
    """
    session_id = session_id or "unknown"
    if is_captured(session_id):
        _log(f"skip: session {session_id} already captured")
        return 0

    task, result = _parse_transcript(Path(transcript_path))
    if not task and not result:
        _log(f"skip: empty transcript for session {session_id}")
        return 0

    try:
        _load_env()
        import brain

        entries = brain.distill(task, result, source="reflect-auto")
        # Safety is a QUALITY gate, not a human gate: only durable, confident
        # lessons land in the trusted store; low-confidence noise is dropped.
        # Dedup is automatic (same title -> same slug -> overwrite), and the
        # "reflect-auto" source tag keeps these distinguishable and prunable.
        keep = [e for e in entries if e.confidence in ("high", "medium")]
        for e in keep:
            brain.save(e, rebuild_index=False)
        if keep:
            brain.rebuild_index_file()
    except Exception as exc:
        _log(f"capture skipped for session {session_id}: {exc}")
        return 0

    mark_captured(session_id)
    n = len(keep)
    dropped = len(entries) - n
    titles = "; ".join(f"[{e.type}] {e.title}" for e in keep) or "(nothing durable)"
    extra = f" (+{dropped} low-confidence dropped)" if dropped else ""
    _log(f"session {session_id}: committed {n} lesson(s){extra}: {titles}")
    return n


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    tpath = payload.get("transcript_path")
    if not tpath:
        _log("skip: no transcript_path in hook payload")
        return 0
    capture_session(tpath, str(payload.get("session_id") or "unknown"))
    return 0


if __name__ == "__main__":
    # Hooks must exit cleanly; we never propagate a non-zero status.
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
