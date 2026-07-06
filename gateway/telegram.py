"""Minimal Telegram client over the HTTP Bot API using `requests`.

No third-party Telegram library: long-polling makes only OUTBOUND HTTPS calls
to api.telegram.org, so it needs no open port and works behind a corporate
firewall and on any host. That property is the whole reason we chose it.
"""

from __future__ import annotations

import os

import requests

from ._bootstrap import load_env

load_env()

_API = "https://api.telegram.org/bot{token}/{method}"
_FILE_API = "https://api.telegram.org/file/bot{token}/{path}"
_TIMEOUT = 60  # long-poll holds the connection open up to this long


def _token() -> str | None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    return tok or None


def is_configured() -> bool:
    return _token() is not None


def _call(method: str, **params):
    tok = _token()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    url = _API.format(token=tok, method=method)
    resp = requests.post(url, json=params, timeout=_TIMEOUT + 10)
    resp.raise_for_status()
    return resp.json()


def send_message(chat_id: str | int, text: str) -> None:
    """Send a message, chunked to Telegram's 4096-char limit."""
    for i in range(0, len(text), 4000):
        _call("sendMessage", chat_id=chat_id, text=text[i : i + 4000])


def get_updates(offset: int | None = None) -> list[dict]:
    """Long-poll for new updates. Returns the raw 'result' list."""
    data = _call("getUpdates", offset=offset, timeout=_TIMEOUT)
    return data.get("result", [])


# --- file download (for voice notes -> STT) -------------------------------

def get_file_path(file_id: str) -> str | None:
    """Resolve a Telegram file_id to its server file_path via getFile."""
    data = _call("getFile", file_id=file_id)
    return (data.get("result") or {}).get("file_path")


def download_file_by_id(file_id: str) -> bytes | None:
    """Download a file's raw bytes given its file_id (voice/audio/document)."""
    tok = _token()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    file_path = get_file_path(file_id)
    if not file_path:
        return None
    url = _FILE_API.format(token=tok, path=file_path)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content
