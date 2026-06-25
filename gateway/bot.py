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

import time

from ._bootstrap import load_env
from . import queue, telegram

load_env()

_HELP = (
    "Xalq Insurance Digital OS background agent.\n"
    "Send me any task and I'll run it in the background, then send the result.\n\n"
    "Commands:\n"
    "  /jobs  - list recent jobs\n"
    "  /help  - this message"
)


def _handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text:
        telegram.send_message(chat_id, "Send me a text task (voice support coming next).")
        return

    if text in ("/start", "/help"):
        telegram.send_message(chat_id, _HELP)
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
