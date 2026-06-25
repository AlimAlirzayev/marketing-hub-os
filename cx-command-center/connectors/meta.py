"""Meta webhook normalization for Instagram and Facebook events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_meta_payload(raw: dict[str, Any]) -> list[dict]:
    messages: list[dict] = []
    obj = raw.get("object") or "meta"
    for entry in raw.get("entry", []) or []:
        account_id = str(entry.get("id") or "")
        occurred_at = _entry_time(entry.get("time"))
        for event in entry.get("messaging", []) or []:
            msg = _message_event(obj, account_id, occurred_at, event, raw)
            if msg:
                messages.append(msg)
        for change in entry.get("changes", []) or []:
            msg = _change_event(obj, account_id, occurred_at, change, raw)
            if msg:
                messages.append(msg)
    return messages


def _message_event(obj: str, account_id: str, fallback_time: str, event: dict, raw: dict) -> dict | None:
    message = event.get("message") or {}
    if message.get("is_echo") or message.get("is_deleted"):
        return None
    text = message.get("text") or _attachment_text(message.get("attachments") or [])
    if not text:
        return None
    sender = event.get("sender") or {}
    timestamp = event.get("timestamp")
    channel = "instagram_dm" if obj == "instagram" else "facebook_message"
    return {
        "source": "meta_webhook",
        "channel": channel,
        "account": account_id,
        "external_id": message.get("mid") or f"{account_id}-{timestamp}-{sender.get('id')}",
        "author_name": None,
        "author_handle": sender.get("id"),
        "text": text,
        "url": _first_attachment_url(message.get("attachments") or []),
        "occurred_at": _ms_time(timestamp) or fallback_time,
        "metadata": {"meta_event": event, "object": obj},
        "raw_payload": raw,
    }


def _change_event(obj: str, account_id: str, occurred_at: str, change: dict, raw: dict) -> dict | None:
    field = change.get("field")
    value = change.get("value") or {}
    text = value.get("text") or value.get("message") or value.get("comment")
    if not text and field in {"mentions"}:
        text = "Instagram mention detected. Fetch mentioned comment/media text from Graph API for full context."
    if not text:
        return None
    from_user = value.get("from") or {}
    channel = "instagram_comment" if obj == "instagram" else "facebook_comment"
    external_id = (
        value.get("comment_id")
        or value.get("commentId")
        or value.get("post_id")
        or value.get("id")
        or f"{account_id}-{field}-{occurred_at}"
    )
    media = value.get("media") or {}
    return {
        "source": "meta_webhook",
        "channel": channel,
        "account": account_id,
        "external_id": external_id,
        "author_name": from_user.get("name"),
        "author_handle": from_user.get("username") or from_user.get("id"),
        "text": text,
        "url": value.get("permalink_url") or value.get("link"),
        "occurred_at": occurred_at,
        "metadata": {"field": field, "media": media, "meta_change": change, "object": obj},
        "raw_payload": raw,
    }


def _entry_time(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ms_time(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def _attachment_text(attachments: list[dict]) -> str:
    if not attachments:
        return ""
    types = ", ".join(a.get("type", "attachment") for a in attachments)
    return f"Customer sent attachment: {types}"


def _first_attachment_url(attachments: list[dict]) -> str | None:
    for attachment in attachments:
        payload = attachment.get("payload") or {}
        if payload.get("url"):
            return payload["url"]
    return None

