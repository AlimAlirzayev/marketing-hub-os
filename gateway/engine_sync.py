"""Canonical engine refresh — the ONE brain every entry point calls so the twins
equalize with GitHub BEFORE any work starts.

Callers (pull-first is the whole point — check GitHub, fast-forward the newest engine
+ shared memory + encrypted keys, THEN act):

  * supervisor timer          -> refresh(announce=True)                  every ENGINE_SYNC_MIN
  * Telegram WORK message      -> pull_if_stale()                        first thing before a task is queued
  * Telegram /update command   -> refresh(push=True, announce=False)     (the bot prints the summary itself)

Wraps scripts/sync_engine.py (the safe git brain: ff-pull, auto-checkpoint the
union-merge decisions log, guarded auto-merge) and adds the post-pull tripwire
(gateway.postpull) + the owner announcement, in ONE place so the callers never drift
(three copies drift — see docs/SYNC.md). Best-effort: never raises into a caller.

NOTE ON HOT CODE: a pull refreshes files / shared memory / encrypted keys on disk
immediately, but a long-running process keeps its already-imported code until its
next restart (the announcement says so). Every freshly-started session/hook and every
subprocess (the claude/codex CLIs, the sync brain itself) already reads the new files.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import sense, telegram

_ROOT = Path(__file__).resolve().parent.parent
_BRAIN = _ROOT / "scripts" / "sync_engine.py"
_STAMP = _ROOT / "data" / "last_sync.json"          # machine-local, git-ignored
_DEBOUNCE = float(os.getenv("ENGINE_PULL_DEBOUNCE", "90"))  # seconds


def _head() -> str:
    """Current HEAD sha (empty on any error) — lets us see the pull range."""
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                           capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _run_brain(pull: bool, push: bool) -> str:
    """Invoke the safe git brain as a subprocess; return its one-line summary."""
    flags: list[str] = []
    if pull and not push:
        flags.append("--pull-only")
    elif push and not pull:
        flags.append("--push-only")
    try:
        p = subprocess.run([sys.executable, str(_BRAIN), *flags], cwd=str(_ROOT),
                           capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        return (p.stdout or p.stderr or "").strip()
    except Exception as exc:  # a sync hiccup must never reach the caller
        return f"[sync] skipped ({exc.__class__.__name__})"


def _touch_stamp() -> None:
    try:
        _STAMP.parent.mkdir(parents=True, exist_ok=True)
        _STAMP.write_text(json.dumps({"ts": time.time()}))
    except Exception:
        pass


def seconds_since_sync() -> float:
    try:
        return time.time() - float(json.loads(_STAMP.read_text())["ts"])
    except Exception:
        return float("inf")


def announce_update(summary: str, report: str | None = None) -> bool:
    """When a real pull landed, tell the owner on Telegram ('dostum, yeniliklər gəldi')
    and fold in the post-pull tripwire verdict. Returns True on an update."""
    if "pulled new engine" not in summary:
        return False
    sense.emit("sync", "engine updated from origin",
               {"summary": summary[:120], "check": (report or "")[:160]})
    owner = (os.getenv("TELEGRAM_OWNER_CHAT_ID") or "").strip()
    if owner and telegram.is_configured():
        try:
            msg = ("🔄 Dostum, o biri sistemdən yeniliklər gəldi — GitHub-dan çəkib "
                   f"yerləşdirdim.\n{summary}\n")
            if report:
                msg += report + "\n"
            msg += "Qeyd: işləyən proseslər yeni kodu növbəti restartda tam götürür."
            telegram.send_message(owner, msg)
        except Exception as exc:  # an announcement must never hurt the caller
            print(f"[engine_sync] announce failed: {exc}")
    return True


def refresh(*, pull: bool = True, push: bool = True, announce: bool = True) -> str:
    """Pull-first (and optionally push), run the tripwire on any landed commits, and
    optionally announce to the owner. Returns the brain summary. Never raises."""
    prev = _head()
    summary = _run_brain(pull, push)
    _touch_stamp()
    try:  # hygiene watchdog: flag files the sync brain cannot carry (untracked)
        from . import untracked_watch
        untracked_watch.sweep()
    except Exception as exc:
        print(f'[engine_sync] untracked watch error: {exc}')
    if "pulled new engine" in summary:
        new = _head()
        report = None
        if prev and new and prev != new:
            try:
                from . import postpull
                report = postpull.verify(prev, new)
            except Exception as exc:  # tripwire must never break the sync
                print(f"[engine_sync] postpull error: {exc}")
        if announce:
            announce_update(summary, report)
    return summary


def pull_if_stale(*, max_age_s: float | None = None, announce: bool = True) -> str | None:
    """Entry-point guard: if we haven't synced within the debounce window, PULL first
    so the twin is equal before we act. Debounced so a burst of messages doesn't hammer
    git. Returns the summary if it synced, else None."""
    window = _DEBOUNCE if max_age_s is None else max_age_s
    if seconds_since_sync() < window:
        return None
    return refresh(pull=True, push=False, announce=announce)
