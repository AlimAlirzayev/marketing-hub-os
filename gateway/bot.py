"""Telegram front-end: receive tasks from chat, enqueue them, reply instantly.

Separation of concerns: this process ONLY handles intake. The worker executes
jobs and pushes results back to the chat. So you message a task from your
phone, get an immediate "queued" ack, and the finished result arrives later --
exactly the Manus/Hermes experience, self-hosted.

Setup (one time):
  1. Open Telegram, talk to @BotFather, send /newbot, follow prompts.
  2. Put the token it gives you into .env as TELEGRAM_BOT_TOKEN=...
  3. Run this:   python -m gateway.bot
  4. In another terminal run the worker:   python -m gateway.worker
  5. Message your bot any task.

Long-polling = outbound HTTPS only, so no port/webhook/public IP is needed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ._bootstrap import load_env
from . import queue, telegram

load_env()

_ROOT = Path(__file__).resolve().parent.parent
_SYNC = _ROOT / "scripts" / "sync_engine.py"

_HELP = (
    "Xalq Insurance Digital OS background agent.\n"
    "Send me any task and I'll run it in the background, then send the result.\n\n"
    "Commands:\n"
    "  /jobs    - list recent jobs\n"
    "  /update  - pull the latest engine from GitHub (owner only)\n"
    "  /help    - this message"
)


def _owner_id() -> str | None:
    """The single chat allowed to run privileged ops commands (e.g. /update)."""
    val = (os.getenv("TELEGRAM_OWNER_CHAT_ID") or "").strip()
    return val or None


def _is_owner(chat_id) -> bool:
    """True if this chat may run ops commands. If no owner is configured we allow
    it (single-user private bot) but the reply nudges you to lock it down."""
    owner = _owner_id()
    return owner is None or str(chat_id) == owner


def _run_sync() -> str:
    """Run the shared sync brain and return its one-line summary for the reply."""
    try:
        proc = subprocess.run(
            [sys.executable, str(_SYNC)],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return out or "sync finished (no changes)."
    except subprocess.TimeoutExpired:
        return "sync timed out reaching GitHub — try again shortly."
    except Exception as exc:  # never crash the bot on an ops command
        return f"sync could not run: {exc.__class__.__name__}"


def _handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text:
        telegram.send_message(chat_id, "Send me a text task (voice support coming next).")
        return

    if text in ("/start", "/help"):
        telegram.send_message(chat_id, _HELP + f"\n\nYour chat id: {chat_id}")
        return

    if text.split()[0] in ("/update", "/pull", "/sync"):
        if not _is_owner(chat_id):
            telegram.send_message(chat_id, "Not authorized for ops commands.")
            return
        telegram.send_message(chat_id, "🔄 Pulling the latest engine from GitHub...")
        summary = _run_sync()
        note = "" if _owner_id() else "\n\n(Tip: set TELEGRAM_OWNER_CHAT_ID in .env to lock this to you.)"
        telegram.send_message(chat_id, f"✅ {summary}{note}")
        return

    if text == "/jobs":
        jobs = queue.list_jobs(limit=10)
        if not jobs:
            telegram.send_message(chat_id, "No jobs yet.")
        else:
            lines = [f"#{j.id} [{j.status}] {j.task[:50]}" for j in jobs]
            telegram.send_message(chat_id, "\n".join(lines))
        return

    job_id = queue.submit(text, source="telegram", chat_id=str(chat_id))
    telegram.send_message(chat_id, f"📥 Queued as job #{job_id}. Working on it...")


def main() -> None:
    if not telegram.is_configured():
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN not set in .env. Create a bot via @BotFather first."
        )
    queue.init_db()
    print("[bot] started. Long-polling for messages... (Ctrl+C to stop)")
    offset = None
    while True:
        try:
            updates = telegram.get_updates(offset=offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    _handle_message(msg)
        except KeyboardInterrupt:
            print("\n[bot] stopped.")
            break
        except Exception as exc:  # transient network errors -> back off, retry
            print(f"[bot] error: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    main()
