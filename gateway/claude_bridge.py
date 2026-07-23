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
need approval → no unsupervised writes/edits/outward actions). On top of that the
chat turn is granted a READ/RESEARCH allowlist (Read/Grep/Glob + WebSearch/WebFetch,
all non-destructive) so it answers like Claude Code in the IDE — grounded in our
own repo/memory/lab and able to read the operator's links live. Kill switches:
CLAUDE_BRIDGE_RESEARCH=0 (research surface), CLAUDE_BRIDGE_HANDS=0 (studio/summon
door). The queue's outward-action checkpoint still applies on top. Power users on a
trusted box can widen writes with CLAUDE_BRIDGE_PERMISSION_MODE=acceptEdits.
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
# THE AZERBAIJANI LETTER THAT KILLED THE PREMIUM BRAIN (2026-07-14).
# `subprocess.run(text=True)` with no explicit encoding uses the LOCALE default,
# which on this Windows box is cp1252 — an alphabet with no 'ı' (U+0131). So every
# `claude -p` turn carrying Azerbaijani raised UnicodeEncodeError, the bridge was
# marked "unavailable", and the whole system silently fell back to the free Groq
# model. The premium brain was never down; it was never reachable.
# Pin UTF-8 on BOTH directions of the pipe. Never remove: the prompts are Azerbaijani.
_TEXT_IO = {"encoding": "utf-8", "errors": "replace"}
# Fallback bench when the cap message carries no parseable reset time. Kept
# SHORT (1h) on purpose: a capped Claude session usually resets well under an
# hour, and over-benching a recovered account is what dropped the mic to the
# weak free floor for hours (2026-07-20). _cooldown_until() prefers the real
# "resets 8:50pm (UTC)" time the CLI reports; this is only the no-parse floor.
_COOLDOWN_S = int(float(os.getenv("CLAUDE_LIMIT_COOLDOWN_HOURS", "1")) * 3600)
# Signatures in a claude -p result that mean "this account is capped", not a
# real failure — the cue to fail over to the next account.
_LIMIT_CUES = ("usage limit", "limit reached", "rate limit", "rate_limit",
               "quota", "exceeded your", "please try again later", "overloaded",
               # Claude Code session/5h caps: the CLI reports these as an
               # is_error result with api_error_status 429 and a "session
               # limit" message. Without these cues a capped account raised
               # HARD instead of rotating to the next account (and its
               # cooldown was never set, so account_status lied). 2026-07-19.
               "session limit", "hit your session", "api_error_status\":429",
               "api_error_status\": 429", "error_status\":429")


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


def _cooldown_until(msg: str) -> float:
    """Bench a capped account until it ACTUALLY resets. Claude reports the
    reset in the cap message ("... resets 8:50pm (UTC)"); honor that exact
    time (+2min buffer) so a recovered account comes straight back instead of
    sitting idle for a blind 5h while the mic falls to the free floor. Falls
    back to the short _COOLDOWN_S floor when no reset time is present."""
    import re
    from datetime import datetime, timezone, timedelta
    now = time.time()
    m = re.search(r"resets?\s+(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m",
                  (msg or "").lower())
    if m:
        hr = int(m.group(1)) % 12
        if m.group(3) == "p":
            hr += 12
        target = datetime.now(timezone.utc).replace(
            hour=hr, minute=int(m.group(2) or 0), second=0, microsecond=0)
        if target.timestamp() <= now:      # time already passed today -> tomorrow
            target += timedelta(days=1)
        return min(target.timestamp() + 120, now + 6 * 3600)  # +buffer, 6h safety cap
    return now + _COOLDOWN_S


# A model is GONE (not just the account capped): needs pay-as-you-go credits, or
# the id no longer exists. Distinct from _is_limit (a per-account usage cap) —
# gone means step DOWN the model ladder; capped means rotate the account.
_MODEL_GONE_CUES = ("usage credits are required", "out of usage credits",
                    "requires usage credits", "requires credits",
                    "no longer available", "not available", "model not found",
                    "does not exist", "invalid model", "unknown model")

# The chat model ladder MIRRORS the current Claude Code tier and auto-adapts: it
# tries Fable first (fast/cheap probe), then the strongest brain (Opus 4.8), then
# Sonnet, then Haiku — stepping down by ITSELF the moment a rung is capped, gone, or
# credit-gated (exactly "Fable runs out -> switch to Opus on its own"). A dead rung
# is skipped for a while then re-probed, so a funded Fable — or a model Anthropic
# renames/retires — is absorbed with no restart. Override the whole tier without a
# deploy via CLAUDE_CHAT_LADDER; pin one model via CLAUDE_BRIDGE_MODEL. So the lineup
# is never hardcoded-and-forgotten: it degrades gracefully and is data-tunable.
_MODEL_RETRY_S = int(os.getenv("CLAUDE_MODEL_RETRY_MIN", "30")) * 60
_model_cooldown: dict[str, float] = {}


def _is_model_gone(text: str) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in _MODEL_GONE_CUES)


def _full_ladder() -> list[str]:
    pin = os.getenv("CLAUDE_BRIDGE_MODEL")
    if pin:  # an explicit pin forces a single model, no laddering
        return [pin]
    raw = os.getenv("CLAUDE_CHAT_LADDER",
                    "claude-fable-5,claude-opus-4-8,claude-sonnet-5,claude-haiku-4-5-20251001")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _chat_ladder() -> list[str]:
    """Rungs to try now, best-first, skipping any recently found gone. If every
    rung is cooling down, try them all anyway (better a probe than no brain)."""
    now = time.time()
    full = _full_ladder()
    ready = [m for m in full if _model_cooldown.get(m, 0) <= now]
    return ready or full


def _mark_model_gone(model: str) -> None:
    _model_cooldown[model] = time.time() + _MODEL_RETRY_S


# ── The mic brain's tool surface (safety by permission model, not prompt-shackle).
# READ/RESEARCH — the non-destructive tools that turn the mic brain from a guesser
# into "Claude Code in the IDE" for ANSWERING: read our OWN repo + memory + lab to
# ground in what THIS system knows, and reach the live web to verify facts and to
# READ THE LINKS the operator sends (his recurring ask). All read-only — they can
# never write, delete, or act outward, so widening here buys ANSWER QUALITY, not
# risk: the envelope is unchanged (permission-mode "default" still auto-declines
# every write/edit/outward tool). A fetched page could carry a prompt injection, but
# a chat turn holds NO destructive hands, so the worst case is a wrong text reply to
# the owner-only operator — self-correcting. Kill switch: CLAUDE_BRIDGE_RESEARCH=0.
_RESEARCH_TOOLS = ("Read", "Grep", "Glob", "WebSearch", "WebFetch")
# SERVICE HANDS — the chat turn may USE the live studios through exactly one governed
# door (`python -m gateway.studio_api`: registered studios only, 127.0.0.1 only,
# risky POSTs blocked, responses token-scrubbed) and enqueue heavy work via
# gateway.summon ("the model is the router", 2026-07-20). Compound shell is
# permission-checked per segment, so the prefix cannot be chained past. Kill switch:
# CLAUDE_BRIDGE_HANDS=0.
_HANDS_TOOLS = ("Bash(python3 -m gateway.studio_api:*)",
                "Bash(python -m gateway.studio_api:*)",
                "Bash(python3 -m gateway.summon:*)",
                "Bash(python -m gateway.summon:*)")


def _allowed_tools(hands: bool, research: bool) -> list[str]:
    """Compose the chat turn's --allowedTools from the two governed surfaces, each
    independently kill-switchable. An empty list means the flag is dropped entirely
    and permission-mode 'default' alone governs every tool (read-only tools still
    work; everything needing approval auto-declines)."""
    tools: list[str] = []
    if research:
        tools += list(_RESEARCH_TOOLS)
    if hands:
        tools += list(_HANDS_TOOLS)
    return tools


_FRAMING = (
    "You are answering the operator through a microphone (Telegram/panel/CLI), "
    "not the terminal. Reply in the operator's language (Azerbaijani), concise and "
    "direct — no preamble. "
    "TOOLS — you are not a guesser: you HAVE real read/research tools, use them "
    "instead of hedging. Read/Grep our own repo, memory and lab to ground answers "
    "in what THIS system already knows; WebSearch and WebFetch to check current "
    "facts and to OPEN and read any link the operator sends, then evaluate it — "
    "never tell him you cannot open a link or that your knowledge is dated. Prefer "
    "a grounded, checked answer over a hedge. Do not make outward/irreversible "
    "changes (post/pay/send/delete) without a plain go-ahead. "
    "ROUTING: you are the router. If — and only if — the operator asks for a "
    "HEAVY multi-studio marketing deliverable (campaign strategy, full report, "
    "budget analysis, competitor research), do not grind it inline: run "
    "`python3 -m gateway.summon crew \"<goal in Azerbaijani>\"` once and relay "
    "its confirmation line to the operator. Never summon for greetings, "
    "follow-ups, system/status questions, or anything you can answer directly "
    "yourself; at most one summon per turn. "
    "VOICE — this is the most important rule: talk to the operator EXACTLY "
    "like Claude Code talks to him in the terminal — one natural conversation "
    "between two people, never a ticketing system. He writes an intention, you "
    "do it and report like a teammate. NEVER show internal job numbers (no "
    "\"İş #135\", no \"#138\"), NEVER tell him to type \"/approve N\", and NEVER "
    "narrate pipeline mechanics (\"növbəyə salındı\", \"build xəttinə verildi\", "
    "\"ayrıca mesajla gələcək\", \"icra mərhələsi\"). If you did something, just "
    "say it (\"düzəltdim\", \"baxdım\", \"tapdım\"). If it runs in the background, "
    "say it like a person (\"onu arxada hazırlayıram, hazır olanda özüm deyəcəm\") "
    "with no id. If an action needs his go-ahead, ask ONE plain question in this "
    "same turn (\"...edim?\") and act on \"hə\"/\"yox\" — never queue it silently "
    "and hand him a number to approve."
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


def _primary_index(accts: list[dict]) -> int | None:
    """The operator's DEFAULT account (alim.alirzayev) — always tried first when it
    isn't resting, so the system stays on his primary Claude subscription instead of
    drifting onto whichever account answered last. Marked by "primary": true in
    claude_accounts.json, or by name via CLAUDE_PRIMARY_ACCOUNT."""
    want = (os.getenv("CLAUDE_PRIMARY_ACCOUNT") or "").strip().lower()
    for i, a in enumerate(accts):
        if a.get("primary") or (want and a.get("name", "").strip().lower() == want):
            return i
    return None


def _account_order() -> list[tuple[int, dict]]:
    """Accounts to try this turn, best first: the operator's PRIMARY account, then
    the persisted 'active' one, then the rest — skipping any still cooling down after
    hitting its cap. Primary-first means we always return to his default subscription
    once its cap resets, rather than drifting onto a secondary account."""
    data = _load_accounts()
    accts = data.get("accounts", [])
    if not accts:
        return []
    now = time.time()
    active = data.get("active", 0)
    primary = _primary_index(accts)
    seq = ([primary] if primary is not None else []) \
        + list(range(active, len(accts))) + list(range(0, active))
    order: list[int] = []
    for i in seq:
        if i not in order:
            order.append(i)
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
    # The mic brain's governed tool surface (defined at module scope): read/research
    # by default (ground answers + read the operator's links) plus the studio/summon
    # hands. Each independently kill-switchable; permission-mode "default" still
    # auto-declines every write/edit/outward tool regardless.
    hands = os.getenv("CLAUDE_BRIDGE_HANDS", "1").strip().lower() not in ("0", "off", "false")
    research = os.getenv("CLAUDE_BRIDGE_RESEARCH", "1").strip().lower() not in ("0", "off", "false")
    allowed = _allowed_tools(hands, research)
    env = os.environ.copy()
    # The child claude -p session inherits this repo's SessionStart/SessionEnd
    # hooks (sync, capture, pulse). A headless brain turn must not fire them:
    # they add seconds of latency, can touch git under the operator's feet, and
    # their failure ("Hook cancelled") flips the exit code -> false free-fallback.
    env["RAMIN_NO_HOOKS"] = "1"
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
    ladder = _chat_ladder()
    for mi, model in enumerate(ladder):
        for attempt in range(2):
            cmd = ["claude", "-p", "--output-format", "json",
                   "--permission-mode", perm, "--model", model]
            if allowed:
                cmd += ["--allowedTools", ",".join(allowed)]
            # The FIRST attempt of EVERY rung resumes the thread; only a retry
            # (attempt 1, after a failure on the same rung) starts fresh. It used
            # to be rung 0 only — but with a credit-gated model on top (fable),
            # rung 0 always failed and the rung that actually answered began with
            # NO memory: every >30-min gap (fable re-probe) wiped the Telegram
            # thread (observed 2026-07-19). claude -p supports cross-model resume,
            # so continuity must survive a stepdown.
            if sid and attempt == 0:
                cmd += ["--resume", sid]
            proc = subprocess.run(
                cmd, input=f"{_FRAMING}\n\n{prompt}", cwd=str(cwd or ROOT),
                capture_output=True, text=True, timeout=timeout or _TIMEOUT, env=env,
                **_TEXT_IO,
            )
            out, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
            if proc.returncode != 0:
                last = err or out or "empty output"
                # A credit-gated / gone MODEL steps DOWN the ladder; only a real
                # account cap rotates accounts. Check model-gone FIRST: a 429 that
                # says "requires usage credits" is fable needing credits (step down
                # to sonnet on the SAME account), not this account being capped —
                # misreading it benched a HEALTHY account and dropped the whole
                # premium brain to the free floor (2026-07-23).
                if _is_model_gone(last):
                    _mark_model_gone(model)
                    break  # step down to the next model rung
                if _is_limit(last):
                    raise RuntimeError(f"claude -p capped: {last[:200]}")  # rotate account
                continue  # transient / bad-session -> retry fresh
            try:
                data = json.loads(out)
            except ValueError:
                last = f"unparseable output: {out[:150]}"
                continue
            text = (data.get("result") or "").strip()
            if data.get("is_error") or not text:
                detail = text or str(data)[:200]
                last = detail
                # model-gone before cap (see the returncode branch above): a
                # credit-gated model steps down on the same account, not a cap.
                if _is_model_gone(detail):
                    _mark_model_gone(model)
                    break  # step down
                if _is_limit(detail):
                    raise RuntimeError(f"claude -p capped: {detail[:200]}")
                raise RuntimeError(f"claude -p error: {detail[:200]}")
            new_sid = data.get("session_id")
            if new_sid:
                _save_session(thread, new_sid)
            return text, {"session_id": new_sid, "cost_usd": data.get("total_cost_usd"),
                          "num_turns": data.get("num_turns"),
                          "model": data.get("model") or model}
    raise RuntimeError(f"claude -p failed on all model rungs: {last[:200]}")


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
                accts[idx]["cooldown_until"] = _cooldown_until(str(exc))
                _save_accounts(data)
                continue  # capped -> try the next account
            raise  # a non-limit failure shouldn't burn the other account
    raise RuntimeError(f"all Claude accounts capped/failing: {last_exc}")


def _run_stateless(prompt: str, timeout: int | None, token: str | None) -> tuple[str, str]:
    """One fresh `claude -p` turn — NO session, NO conversational framing. This is
    the subscription's raw completion primitive for the router's smart tier, so it
    must not carry the mic persona or resume a chat thread. Returns (text, model)."""
    env = os.environ.copy()
    env["RAMIN_NO_HOOKS"] = "1"  # see _run_once: no repo hooks on headless turns
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)
    last = ""
    for model in _chat_ladder():  # best-first; steps down on a per-model failure
        cmd = ["claude", "-p", "--output-format", "json",
               "--permission-mode", "default", "--model", model]
        proc = subprocess.run(
            cmd, input=prompt, cwd=str(ROOT), capture_output=True, text=True,
            timeout=timeout or _TIMEOUT, env=env, **_TEXT_IO,
        )
        out, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
        if proc.returncode != 0:
            msg = err or out or "empty output"
            if _is_model_gone(msg):  # credit-gated/gone model -> step down, not a cap
                _mark_model_gone(model); last = msg; continue  # next rung
            if _is_limit(msg):
                raise RuntimeError(f"claude -p capped: {msg[:200]}")  # rotate account
            raise RuntimeError(f"claude -p failed: {msg[:200]}")
        try:
            data = json.loads(out)
        except ValueError:
            last = f"unparseable output: {out[:150]}"; continue
        text = (data.get("result") or "").strip()
        if data.get("is_error") or not text:
            detail = text or str(data)[:200]
            if _is_model_gone(detail):  # step down (same account), not a cap
                _mark_model_gone(model); last = detail; continue
            if _is_limit(detail):
                raise RuntimeError(f"claude -p capped: {detail[:200]}")
            raise RuntimeError(f"claude -p error: {detail[:200]}")
        return text, "claude-code/" + str(data.get("model") or model)
    raise RuntimeError(f"claude -p: all model rungs unavailable: {last[:150]}")


def complete(prompt: str, *, system: str | None = None,
             timeout: int | None = None) -> tuple[str, str]:
    """Stateless subscription completion for the router's smart tier — the premium
    brain wherever the system THINKS (planning, synthesis, digests, decisions).
    Rotates across the operator's Claude accounts; raises only when EVERY account
    is capped (the router then falls back to the free cascade). Returns (text, model).
    """
    if not is_available():
        raise RuntimeError("claude bridge not authenticated")
    full = f"{system}\n\n{prompt}" if system else prompt
    order = _account_order() or [(None, {})]  # (None, {}) = single ambient login
    data = _load_accounts()
    accts = data.get("accounts", [])
    last_exc: Exception | None = None
    for idx, acct in order:
        try:
            text, model = _run_stateless(full, timeout, acct.get("token") if acct else None)
            if idx is not None:
                data["active"] = idx
                _save_accounts(data)
            return text, model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_limit(str(exc)) and idx is not None and accts:
                accts[idx]["cooldown_until"] = _cooldown_until(str(exc))
                _save_accounts(data)
                continue  # capped -> next account
            raise  # non-limit failure: let the router fall back to free now
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
        env["RAMIN_NO_HOOKS"] = "1"  # see _run_once: no repo hooks on headless turns
        if acct.get("token"):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = acct["token"]
            for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
                env.pop(k, None)
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--permission-mode", perm],
            input=f"{_BUILD_FRAMING}\n\nTASK: {task}", cwd=str(workspace),
            capture_output=True, text=True, timeout=timeout, env=env,
            **_TEXT_IO,
        )
        out, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
        if proc.returncode != 0:
            last = err or out or "empty output"
            if _is_limit(last) and accts:
                accts[idx]["cooldown_until"] = _cooldown_until(last)
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
                accts[idx]["cooldown_until"] = _cooldown_until(last)
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
