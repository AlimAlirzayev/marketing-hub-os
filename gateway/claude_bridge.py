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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SESSION_FILE = ROOT / "data" / "claude_session.json"
# Private (git-ignored) store of Claude subscription tokens — the operator runs
# two accounts to survive the 5-hour usage cap; we rotate between them.
_ACCOUNTS_FILE = ROOT / "data" / "private_context" / "claude_accounts.json"
_TIMEOUT = int(os.getenv("CLAUDE_BRIDGE_TIMEOUT", "240"))
# When an account hits its usage cap, rest it this long before trying it again
# (Claude's window is ~5h). The other account carries the load meanwhile.
_COOLDOWN_S = int(float(os.getenv("CLAUDE_LIMIT_COOLDOWN_HOURS", "5")) * 3600)
# Signatures in a claude -p result that mean "this account is capped", not a
# real failure — the cue to fail over to the next account.
_LIMIT_CUES = ("usage limit", "limit reached", "rate limit", "rate_limit",
               "quota", "exceeded your", "please try again later", "overloaded")


def _load_accounts() -> dict:
    try:
        return json.loads(_ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": 0, "accounts": []}


def _save_accounts(data: dict) -> None:
    try:
        _ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ACCOUNTS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _is_limit(text: str) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in _LIMIT_CUES)

_FRAMING = (
    "You are answering the operator through a microphone (Telegram/panel/CLI), "
    "not the terminal. Reply in the operator's language (Azerbaijani), concise and "
    "direct — no preamble. Do not make outward/irreversible changes."
)


def is_available() -> bool:
    """True only if the Claude CLI is installed AND we hold real credentials —
    a rotation token, an env token, or a login creds file. Checking install
    alone made every turn fire a `claude -p` that came back 'Not logged in'."""
    if shutil.which("claude") is None:
        return False
    if _load_accounts().get("accounts"):
        return True
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
        return True
    for p in (Path.home() / ".claude" / ".credentials.json",
              Path.home() / ".config" / "claude" / ".credentials.json"):
        if p.exists():
            return True
    return False


def _account_order() -> list[tuple[int, dict]]:
    """Accounts to try this turn, best first: the persisted 'active' one, then
    the rest, skipping any still cooling down after hitting its cap."""
    data = _load_accounts()
    accts = data.get("accounts", [])
    if not accts:
        return []
    now = time.time()
    active = data.get("active", 0)
    order = list(range(active, len(accts))) + list(range(0, active))
    ready = [(i, accts[i]) for i in order if accts[i].get("cooldown_until", 0) <= now]
    # if ALL are cooling down, still try the soonest-to-reset (better than nothing)
    return ready or [(order[0], accts[order[0]])]


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


def _run_once(prompt: str, thread: str, cwd: Path | None, timeout: int | None,
              token: str | None) -> tuple[str, dict]:
    """One `claude -p` turn against a specific account token (None = ambient
    login). Returns (text, meta). Raises on error; a usage-cap message trips
    _is_limit() so the caller fails over. `claude -p` occasionally exits non-
    zero with empty output (transient overload / cache-creation race) or fails
    to resume a stale session — both are retried once (the retry drops --resume),
    so a blip doesn't needlessly bounce the turn to the free brain."""
    perm = os.getenv("CLAUDE_BRIDGE_PERMISSION_MODE", "default")
    env = os.environ.copy()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        # CRITICAL: claude -p prefers ANTHROPIC_API_KEY over the OAuth token, and
        # .env carries a DEAD placeholder key that load_env() puts in the env —
        # leaving it makes every subscription turn 401 "Invalid API key". Strip
        # the API-key vars so the (valid) subscription token is what authenticates.
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)
    sid = _load_session(thread)

    last = ""
    for attempt in range(2):
        cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", perm]
        if sid and attempt == 0:  # only the first try resumes; retry is fresh
            cmd += ["--resume", sid]
        proc = subprocess.run(
            cmd, input=f"{_FRAMING}\n\n{prompt}", cwd=str(cwd or ROOT),
            capture_output=True, text=True, timeout=timeout or _TIMEOUT, env=env,
        )
        out, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
        if proc.returncode != 0:
            last = err or out or "empty output"
            if _is_limit(last):
                raise RuntimeError(f"claude -p capped: {last[:200]}")
            continue  # transient / bad-session -> retry fresh
        try:
            data = json.loads(out)
        except ValueError:
            last = f"unparseable output: {out[:150]}"
            continue
        text = (data.get("result") or "").strip()
        if data.get("is_error") or not text:
            raise RuntimeError(f"claude -p error: {text or str(data)[:200]}")
        new_sid = data.get("session_id")
        if new_sid:
            _save_session(thread, new_sid)
        return text, {"session_id": new_sid, "cost_usd": data.get("total_cost_usd"),
                      "num_turns": data.get("num_turns")}
    raise RuntimeError(f"claude -p failed after retry: {last[:200]}")


def ask(prompt: str, *, thread: str = "main", cwd: Path | None = None,
        timeout: int | None = None) -> tuple[str, dict]:
    """Answer one turn with real headless Claude Code, rotating across the
    operator's Claude accounts: when one hits its usage cap we rest it and fail
    over to the next, so the brain keeps working past a single account's 5-hour
    limit. Returns (text, meta); raises only if EVERY account is capped/failing
    (the caller then falls back to the free brain)."""
    if not is_available():
        raise RuntimeError("claude bridge not authenticated")

    order = _account_order()
    if not order:  # single ambient login (env token or creds file), no rotation
        return _run_once(prompt, thread, cwd, timeout, None)

    data = _load_accounts()
    accts = data["accounts"]
    last_exc: Exception | None = None
    for idx, acct in order:
        try:
            text, meta = _run_once(prompt, thread, cwd, timeout, acct.get("token"))
            data["active"] = idx  # stick with the account that just worked
            _save_accounts(data)
            meta["account"] = acct.get("name")
            return text, meta
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_limit(str(exc)):
                accts[idx]["cooldown_until"] = time.time() + _COOLDOWN_S
                _save_accounts(data)
                continue  # capped -> try the next account
            raise  # a non-limit failure shouldn't burn the other account
    raise RuntimeError(f"all Claude accounts capped/failing: {last_exc}")


_BUILD_FRAMING = (
    "You are an autonomous builder for the operator. Build the requested "
    "deliverable ENTIRELY inside the current working directory (your sandbox). "
    "Actually create the files; do not just describe them. When finished, "
    "summarise what you built in Azerbaijani, concise."
)


def build(task: str, workspace: Path, *, timeout: int = 900) -> str:
    """Agentic BUILD via real Claude Code (write access, in the job workspace),
    with the same account rotation as ask(). This is how 'build me X' work gets
    done now that the Gemini agent's keys are dead and Codex is rate-limited —
    Claude Code is a first-class building agent and we have rotation quota.
    Returns Claude's final text; raises only if every account is capped/failing."""
    if not is_available():
        raise RuntimeError("claude bridge not authenticated")
    perm = os.getenv("CLAUDE_BUILD_PERMISSION_MODE", "acceptEdits")
    order = _account_order() or [(0, {})]
    data = _load_accounts()
    accts = data.get("accounts", [])
    last = ""
    for idx, acct in order:
        env = os.environ.copy()
        if acct.get("token"):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = acct["token"]
            for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
                env.pop(k, None)
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--permission-mode", perm],
            input=f"{_BUILD_FRAMING}\n\nTASK: {task}", cwd=str(workspace),
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        out, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
        if proc.returncode != 0:
            last = err or out or "empty output"
            if _is_limit(last) and accts:
                accts[idx]["cooldown_until"] = time.time() + _COOLDOWN_S
                _save_accounts(data)
            continue
        try:
            d = json.loads(out)
        except ValueError:
            last = out[:150]
            continue
        text = (d.get("result") or "").strip()
        if d.get("is_error") or not text:
            last = text or str(d)[:150]
            if _is_limit(last) and accts:
                accts[idx]["cooldown_until"] = time.time() + _COOLDOWN_S
                _save_accounts(data)
            continue
        return text
    raise RuntimeError(f"claude build failed on all accounts: {last[:200]}")


def account_status() -> list[dict]:
    """Masked per-account view for the panel/advisor (never exposes a token)."""
    now = time.time()
    out = []
    for a in _load_accounts().get("accounts", []):
        cd = a.get("cooldown_until", 0)
        out.append({"name": a.get("name", "?"),
                    "resting": cd > now,
                    "resumes_in_min": max(0, round((cd - now) / 60)) if cd > now else 0})
    return out
