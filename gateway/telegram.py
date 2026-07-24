"""Minimal Telegram client over the HTTP Bot API using `requests`.

No third-party Telegram library: long-polling makes only OUTBOUND HTTPS calls
to api.telegram.org, so it needs no open port and works behind a corporate
firewall and on any host. That property is the whole reason we chose it.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from ._bootstrap import load_env

load_env()

_API = "https://api.telegram.org/bot{token}/{method}"
_FILE_API = "https://api.telegram.org/file/bot{token}/{path}"
_TIMEOUT = 60  # long-poll holds the connection open up to this long
_MAX_ATTEMPTS = 4
_ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Ramin-OS-Telegram/1"})
_HEALTH: dict[str, Any] = {
    "last_ok_at": None,
    "last_error_at": None,
    "last_error": None,
    "last_retry_after": None,
    "retries": 0,
    "last_poll_started_at": None,
    "last_poll_completed_at": None,
}


def _token() -> str | None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    return tok or None


def is_configured() -> bool:
    return _token() is not None


class TelegramError(RuntimeError):
    """Base transport error with a safe, secret-free description."""


class AuthenticationError(TelegramError):
    """Telegram rejected the bot identity (401)."""


class ForbiddenError(TelegramError):
    """The bot cannot access the target chat/action (403)."""


class RateLimitError(TelegramError):
    """Telegram asked the caller to wait before retrying."""

    def __init__(self, retry_after: int):
        self.retry_after = max(1, int(retry_after))
        super().__init__(f"Telegram rate limited; retry after {self.retry_after}s")


class TransientError(TelegramError):
    """Retry budget was exhausted for a network or Telegram 5xx failure."""


class ConflictError(TelegramError):
    """Telegram 409: ANOTHER process is long-polling this same bot token.
    Almost always means both friend-systems are running a bot with one shared
    token — each machine must have its OWN bot (@BotFather), which is exactly
    why TELEGRAM_BOT_TOKEN is excluded from key syncing."""


def _safe_description(payload: dict | None, status: int) -> str:
    description = str((payload or {}).get("description") or "").strip()
    return description[:240] or f"Telegram HTTP {status}"


def _retry_after(payload: dict | None, response) -> int:
    value = ((payload or {}).get("parameters") or {}).get("retry_after")
    if value is None:
        value = getattr(response, "headers", {}).get("Retry-After", 1)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _rewind_files(files: dict | None) -> None:
    for value in (files or {}).values():
        candidate = value[1] if isinstance(value, tuple) and len(value) > 1 else value
        if hasattr(candidate, "seek"):
            candidate.seek(0)


def _request(
    method: str,
    *,
    json_params: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    http_timeout: int | None = None,
    max_attempts: int = _MAX_ATTEMPTS,
):
    tok = _token()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    url = _API.format(token=tok, method=method)
    timeout = http_timeout or _TIMEOUT + 10
    last_error: Exception | None = None

    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            _rewind_files(files)
            resp = _SESSION.post(
                url,
                json=json_params,
                data=data,
                files=files,
                timeout=timeout,
            )
            try:
                payload = resp.json()
            except (ValueError, TypeError):
                payload = {}
            code = int(payload.get("error_code") or resp.status_code)
            ok = bool(payload.get("ok", 200 <= resp.status_code < 300))

            if code == 409:
                raise ConflictError("another poller is using this bot token")
            if code == 401:
                raise AuthenticationError("Telegram rejected the bot token")
            if code == 403:
                raise ForbiddenError(_safe_description(payload, code))
            if code == 429:
                wait = _retry_after(payload, resp)
                _HEALTH["last_retry_after"] = wait
                if attempt < attempts:
                    _HEALTH["retries"] += 1
                    time.sleep(min(wait, 60))
                    continue
                raise RateLimitError(wait)
            if code >= 500:
                raise requests.exceptions.HTTPError(_safe_description(payload, code))
            if not ok:
                raise TelegramError(_safe_description(payload, code))

            resp.raise_for_status()
            _HEALTH["last_ok_at"] = time.time()
            _HEALTH["last_error"] = None
            return payload
        except (ConflictError, AuthenticationError, ForbiddenError, RateLimitError, TelegramError) as exc:
            _HEALTH["last_error_at"] = time.time()
            _HEALTH["last_error"] = exc.__class__.__name__
            raise
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as exc:
            last_error = exc
            if attempt < attempts:
                _HEALTH["retries"] += 1
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            break

    _HEALTH["last_error_at"] = time.time()
    _HEALTH["last_error"] = (last_error or RuntimeError("unknown")).__class__.__name__
    raise TransientError(
        f"Telegram transport failed after {attempts} attempts "
        f"({_HEALTH['last_error']})"
    ) from last_error


def _call(method: str, **params):
    """Typed JSON Bot API call with bounded retry and 429 compliance."""
    max_attempts = int(params.pop("_max_attempts", _MAX_ATTEMPTS))
    poll_timeout = int(params.get("timeout") or 0)
    return _request(
        method,
        json_params=params,
        http_timeout=max(_TIMEOUT + 10, poll_timeout + 10),
        max_attempts=max_attempts,
    )


def status() -> dict[str, Any]:
    """Secret-free transport state for the existing Hub/pulse surface."""
    durable: dict[str, Any] = {}
    try:
        from . import queue
        durable = queue.channel_health("telegram")
    except Exception:
        pass
    health = {**_HEALTH}
    for key in (
        "last_poll_started_at",
        "last_poll_completed_at",
        "last_error_at",
        "last_error",
    ):
        if durable.get(key) is not None:
            health[key] = durable[key]
    now = time.time()
    last_poll = health.get("last_poll_completed_at")
    poll_started = health.get("last_poll_started_at")
    if not is_configured():
        poll_healthy = None
    elif last_poll is not None:
        poll_healthy = now - float(last_poll) <= 120
    elif poll_started is not None:
        poll_healthy = now - float(poll_started) <= _TIMEOUT + 30
    else:
        poll_healthy = None
    return {
        "configured": is_configured(),
        "mode": "long_poll",
        "allowed_updates": list(_ALLOWED_UPDATES),
        "max_attempts": _MAX_ATTEMPTS,
        "poll_stale_after_seconds": 120,
        "polling_healthy": poll_healthy,
        **health,
    }


def send_message(chat_id: str | int, text: str) -> None:
    """Send a message, chunked to Telegram's 4096-char limit."""
    for i in range(0, len(text), 4000):
        _call("sendMessage", chat_id=chat_id, text=text[i : i + 4000])


def _inline_keyboard(buttons: list[list[tuple[str, str]]] | None) -> dict | None:
    """Build a Telegram inline keyboard without embedding task or secret text."""
    if not buttons:
        return None
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data} for text, data in row]
            for row in buttons
        ]
    }


def send_status(
    chat_id: str | int,
    text: str,
    *,
    buttons: list[list[tuple[str, str]]] | None = None,
) -> int | None:
    """Create one editable progress/approval message and return its message id."""
    params: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000]}
    markup = _inline_keyboard(buttons)
    if markup:
        params["reply_markup"] = markup
    result = (_call("sendMessage", **params).get("result") or {})
    value = result.get("message_id")
    return int(value) if value is not None else None


def edit_status(
    chat_id: str | int,
    message_id: int,
    text: str,
    *,
    buttons: list[list[tuple[str, str]]] | None = None,
) -> None:
    """Edit a progress message; omitting buttons removes any old controls."""
    _call(
        "editMessageText",
        chat_id=chat_id,
        message_id=int(message_id),
        text=text[:4000],
        reply_markup=_inline_keyboard(buttons) or {"inline_keyboard": []},
    )


def answer_callback(callback_query_id: str, text: str = "") -> None:
    """Stop Telegram's button spinner with a short, non-sensitive result."""
    params: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        params["text"] = text[:200]
    _call("answerCallbackQuery", **params)


def send_chat_action(chat_id: str | int, action: str = "typing") -> None:
    """Show a status indicator ("typing…") in the chat — the lightweight
    acknowledgment for conversational turns, instead of a noisy service
    message. Telegram shows it ~5s or until the next message arrives."""
    _call("sendChatAction", chat_id=chat_id, action=action)


def delete_message(chat_id: str | int, message_id: int) -> None:
    """Delete a message from the chat (e.g. one that carried a secret)."""
    _call("deleteMessage", chat_id=chat_id, message_id=message_id)


def send_document(chat_id: str | int, file_path: str, caption: str = "") -> None:
    """Deliver a built file (zip/image/pdf/…) to the chat as a real document.

    This is the 'hand it to me' half: a background job builds a deliverable and
    it arrives in Telegram as a downloadable file, not just a path in text.
    Uses multipart upload (not the JSON _call path)."""
    tok = _token()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    url = _API.format(token=tok, method="sendDocument")
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    with open(file_path, "rb") as fh:
        _request(
            "sendDocument",
            data=data,
            files={"document": fh},
            http_timeout=180,
        )


def send_voice(chat_id: str | int, audio: bytes, *, caption: str = "") -> None:
    """Send a voice note (the system talking back). OGG/Opus shows as a real
    voice bubble; mp3 falls back to an audio file. Multipart upload."""
    tok = _token()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    is_ogg = audio[:4] == b"OggS"
    method = "sendVoice" if is_ogg else "sendAudio"
    field = "voice" if is_ogg else "audio"
    fname = "reply.ogg" if is_ogg else "reply.mp3"
    mime = "audio/ogg" if is_ogg else "audio/mpeg"
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    _request(
        method,
        data=data,
        files={field: (fname, audio, mime)},
        http_timeout=120,
    )


def get_updates(offset: int | None = None) -> list[dict]:
    """Long-poll for new updates. Returns the raw 'result' list."""
    params: dict[str, Any] = {
        "timeout": _TIMEOUT,
        "allowed_updates": _ALLOWED_UPDATES,
    }
    if offset is not None:
        params["offset"] = offset
    started = time.time()
    _HEALTH["last_poll_started_at"] = started
    try:
        from . import queue
        queue.update_channel_health("telegram", last_poll_started_at=started)
    except Exception:
        pass
    # One long-poll attempt per outer bot loop. Retrying four 70-second polls
    # inside the transport can make a dead channel look alive for ~5 minutes;
    # the supervised bot loop is the retry/restart boundary for ingress.
    try:
        data = _call("getUpdates", _max_attempts=1, **params)
    except Exception as exc:
        failed = time.time()
        try:
            from . import queue
            queue.update_channel_health(
                "telegram",
                last_error_at=failed,
                last_error=exc.__class__.__name__,
            )
        except Exception:
            pass
        raise
    completed = time.time()
    _HEALTH["last_poll_completed_at"] = completed
    try:
        from . import queue
        queue.update_channel_health(
            "telegram",
            last_poll_completed_at=completed,
            last_error=None,
        )
    except Exception:
        pass
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
