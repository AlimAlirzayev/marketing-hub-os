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
_TIMEOUT = 60  # long-poll holds the connection open up to this long


def _token() -> str | None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    return tok or None


def is_configured() -> bool:
    return _token() is not None


class ConflictError(RuntimeError):
    """Telegram 409: ANOTHER process is long-polling this same bot token.
    Almost always means both friend-systems are running a bot with one shared
    token — each machine must have its OWN bot (@BotFather), which is exactly
    why TELEGRAM_BOT_TOKEN is excluded from key syncing."""


def _call(method: str, **params):
    tok = _token()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    url = _API.format(token=tok, method=method)
    resp = requests.post(url, json=params, timeout=_TIMEOUT + 10)
    if resp.status_code == 409:
        raise ConflictError("another poller is using this bot token")
    resp.raise_for_status()
    return resp.json()


def send_message(chat_id: str | int, text: str) -> None:
    """Send a message, chunked to Telegram's 4096-char limit."""
    for i in range(0, len(text), 4000):
        _call("sendMessage", chat_id=chat_id, text=text[i : i + 4000])


def delete_message(chat_id: str | int, message_id: int) -> None:
    """Delete a message from the chat (e.g. one that carried a secret)."""
    _call("deleteMessage", chat_id=chat_id, message_id=message_id)


def get_updates(offset: int | None = None) -> list[dict]:
    """Long-poll for new updates. Returns the raw 'result' list."""
    data = _call("getUpdates", offset=offset, timeout=_TIMEOUT)
    return data.get("result", [])
