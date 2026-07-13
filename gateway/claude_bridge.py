"""Headless Claude Code bridge — put THIS chat on any microphone.

The operator's ask: make Telegram (and every other mic) answer like talking to
Claude Code here, on the subscription plan — not a free-model approximation.
Claude Code ships a headless mode (`claude -p --output-format json`) that is the
REAL thing: same model, same repo context, same subscription auth. This module
drives it so a Telegram/panel/CLI turn can be answered by actual Claude Code.

  ask("...") -> runs `claude -p` in the repo, returns (text, meta)

Session continuity: the single conversation (mic.MIC_THREAD) maps to one Claude
Code session id, persisted in data/claude_session.json (git-ignored) and resumed
each turn — so the Telegram thread is continuous, exactly like this chat.

HONEST COST: each call runs a full Claude Code turn and consumes subscription
quota (the first turn re-creates ~25k tokens of context cache → the ~$0.16 seen
in testing; --resume makes later turns cheaper). So this is OPT-IN: the default
brain stays free (Gemini via the router); flip MIC_BRAIN=claude to route the
conversational path here. Requires the `claude` CLI installed AND authenticated
(subscription login) on whatever machine runs the bot.

SAFETY: runs with permission-mode "default" (headless auto-declines tools that
need approval → read/answer freely, no unsupervised writes). The queue's outward-
action checkpoint still applies on top. Power users on a trusted box can widen it
with CLAUDE_BRIDGE_PERMISSION_MODE=acceptEdits.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SESSION_FILE = ROOT / "data" / "claude_session.json"
_TIMEOUT = int(os.getenv("CLAUDE_BRIDGE_TIMEOUT", "240"))

_FRAMING = (
    "You are answering the operator through a microphone (Telegram/panel/CLI), "
    "not the terminal. Reply in the operator's language (Azerbaijani), concise and "
    "direct — no preamble. Do not make outward/irreversible changes."
)


def is_available() -> bool:
    """True only if the Claude CLI is installed AND actually authenticated —
    checking install alone made every turn fire a `claude -p` that came back
    'Not logged in', wasting a call before falling back. We now require real
    credentials, so an un-logged-in box skips straight to the free brain."""
    if shutil.which("claude") is None:
        return False
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
        return True
    # subscription login writes a credentials file under the home config dir
    for p in (Path.home() / ".claude" / ".credentials.json",
              Path.home() / ".config" / "claude" / ".credentials.json"):
        if p.exists():
            return True
    return False


def _load_session(thread: str) -> str | None:
    try:
        return json.loads(_SESSION_FILE.read_text(encoding="utf-8")).get(thread)
    except Exception:
        return None


def _save_session(thread: str, session_id: str) -> None:
    try:
        data = {}
        if _SESSION_FILE.exists():
            data = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
        data[thread] = session_id
        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def ask(prompt: str, *, thread: str = "main", cwd: Path | None = None,
        timeout: int | None = None) -> tuple[str, dict]:
    """Answer one turn with real headless Claude Code. Continues the thread's
    session when there is one. Returns (text, meta). Raises on failure so the
    caller can fall back to the free brain."""
    if not is_available():
        raise RuntimeError("claude CLI not found on PATH")

    perm = os.getenv("CLAUDE_BRIDGE_PERMISSION_MODE", "default")
    cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", perm]
    sid = _load_session(thread)
    if sid:
        cmd += ["--resume", sid]

    full_prompt = f"{_FRAMING}\n\n{prompt}"
    proc = subprocess.run(
        cmd, input=full_prompt, cwd=str(cwd or ROOT),
        capture_output=True, text=True, timeout=timeout or _TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {(proc.stderr or '').strip()[:200]}")

    data = json.loads(proc.stdout)
    text = (data.get("result") or "").strip()
    if not text or data.get("is_error"):
        raise RuntimeError(f"claude -p returned no usable result: {str(data)[:200]}")

    new_sid = data.get("session_id")
    if new_sid:
        _save_session(thread, new_sid)
    meta = {
        "session_id": new_sid,
        "cost_usd": data.get("total_cost_usd"),
        "num_turns": data.get("num_turns"),
    }
    return text, meta
