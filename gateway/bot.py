"""Telegram front-end: receive tasks (text OR voice) from the OWNER only,
enqueue them, reply instantly. The worker executes jobs and pushes results
back to the chat.

SECURITY (inbound hard shell):
  * Only GATEWAY_OWNER_ID may issue commands. Fail-closed: if the owner id is
    not configured, EVERY message is rejected.

Voice: a voice note is transcribed by Gemini (best for Azerbaijani), with the
local whisper-stt server (WHISPER_URL) as a fallback, before being queued.
"""

from __future__ import annotations

import os
import time

import requests

from ._bootstrap import load_env
from . import queue, sense, telegram

load_env()

_OWNER_ID = (os.getenv("GATEWAY_OWNER_ID") or "").strip()
_WHISPER_URL = os.getenv(
    "WHISPER_URL", "http://127.0.0.1:8787/v1/audio/transcriptions"
)
_STT_GEMINI_MODEL = os.getenv("STT_GEMINI_MODEL", "gemini-2.5-flash")
_STT_PROMPT = (
    "Transcribe this voice message verbatim. It is most likely in Azerbaijani "
    "(may also contain Russian, Turkish or English words). Return ONLY the exact "
    "transcript text — no quotes, no translation, no commentary."
)

_HELP = (
    "Ramin-OS background agent.\n"
    "Send me any task (text or voice) and I'll run it in the background, "
    "then send the result.\n\n"
    "Commands:\n"
    "  /jobs  - list recent jobs\n"
    "  /help  - this message"
)


def _is_owner(chat_id) -> bool:
    """Fail-closed owner check: no configured owner => reject everyone."""
    if not _OWNER_ID:
        return False
    return str(chat_id) == _OWNER_ID


def _transcribe_gemini(audio: bytes) -> str | None:
    """Transcribe via Gemini — far better than local whisper for Azerbaijani."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=_STT_GEMINI_MODEL,
        contents=[
            _STT_PROMPT,
            types.Part.from_bytes(data=audio, mime_type="audio/ogg"),
        ],
    )
    return (resp.text or "").strip() or None


def _transcribe_whisper(audio: bytes) -> str | None:
    """Fallback: local whisper-stt server."""
    resp = requests.post(
        _WHISPER_URL,
        files={"file": ("voice.ogg", audio, "audio/ogg")},
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json().get("text") or "").strip() or None


def _transcribe(file_id: str) -> str | None:
    """Download a Telegram voice file and transcribe it (Gemini -> whisper)."""
    try:
        audio = telegram.download_file_by_id(file_id)
    except Exception as exc:
        sense.emit("stt", f"voice download failed: {exc}")
        return None
    if not audio:
        return None
    # 1) Gemini (accurate for AZ)
    try:
        text = _transcribe_gemini(audio)
        if text:
            return text
    except Exception as exc:
        sense.emit("stt", f"gemini stt failed, falling back to whisper: {exc}")
    # 2) whisper fallback
    try:
        return _transcribe_whisper(audio)
    except Exception as exc:
        sense.emit("stt", f"whisper stt failed: {exc}")
        return None


def _extract_task(msg: dict) -> tuple[str | None, bool]:
    """Return (task_text, was_voice). Text wins; else transcribe voice/audio."""
    text = (msg.get("text") or "").strip()
    if text:
        return text, False
    media = msg.get("voice") or msg.get("audio") or msg.get("video_note")
    if media and media.get("file_id"):
        return _transcribe(media["file_id"]), True
    return None, False


def _handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]

    # ---- inbound hard shell: owner-only, fail-closed --------------------
    if not _is_owner(chat_id):
        sense.emit("security", f"rejected non-owner chat_id={chat_id}")
        try:
            telegram.send_message(chat_id, "⛔ Unauthorized.")
        except Exception:
            pass
        return

    task, was_voice = _extract_task(msg)

    if was_voice:
        if not task:
            telegram.send_message(chat_id, "\U0001f3a4 Səsi tanıya bilmədim, bir də cəhd et.")
            return
        telegram.send_message(chat_id, f"\U0001f3a4 Eşitdim: “{task[:300]}”")

    if not task:
        telegram.send_message(chat_id, "Mətn və ya səs tapşırığı göndər.")
        return

    if task in ("/start", "/help"):
        telegram.send_message(chat_id, _HELP)
        return

    if task == "/jobs":
        jobs = queue.list_jobs(limit=10)
        if not jobs:
            telegram.send_message(chat_id, "No jobs yet.")
        else:
            lines = [f"#{j.id} [{j.status}] {j.task[:50]}" for j in jobs]
            telegram.send_message(chat_id, "\n".join(lines))
        return

    job_id = queue.submit(task, source="telegram", chat_id=str(chat_id))
    telegram.send_message(chat_id, f"\U0001f4e5 Queued as job #{job_id}. Working on it...")


def main() -> None:
    if not telegram.is_configured():
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN not set in .env. Create a bot via @BotFather first."
        )
    if not _OWNER_ID:
        print("[bot] WARNING: GATEWAY_OWNER_ID not set -> rejecting ALL messages (fail-closed).")
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
