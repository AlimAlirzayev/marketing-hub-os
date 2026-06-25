"""Chatplace webhook and optional pull normalization."""

from __future__ import annotations

from typing import Any

import requests

import config


def configured_for_pull() -> bool:
    return bool(config.CHATPLACE_PULL_URL)


def sync_pull(limit: int | None = None) -> list[dict]:
    """Pull messages from a Chatplace-compatible JSON endpoint.

    Chatplace deployments differ by workspace, so this connector accepts a
    generic JSON feed URL. The response may be a list, or an object containing
    one of: items, messages, comments, conversations, data.
    """
    if not config.CHATPLACE_PULL_URL:
        raise RuntimeError("CHATPLACE_PULL_URL is not configured")
    headers = {"Accept": "application/json"}
    if config.CHATPLACE_API_TOKEN:
        headers["Authorization"] = f"Bearer {config.CHATPLACE_API_TOKEN}"
    params: dict[str, Any] = {}
    if limit:
        params["limit"] = limit
    resp = requests.get(config.CHATPLACE_PULL_URL, params=params, headers=headers, timeout=25)
    resp.raise_for_status()
    raw = resp.json()
    rows = _extract_rows(raw)
    return [normalize_payload(row) for row in rows if isinstance(row, dict)]


def normalize_payload(raw: dict[str, Any]) -> dict:
    text = _pick(raw, "message.text", "text", "last_message", "comment.text") or ""
    channel = _pick(raw, "channel", "platform", "message.channel") or "instagram_dm"
    if channel == "instagram":
        channel = "instagram_dm"
    return {
        "source": "chatplace",
        "channel": channel,
        "account": _pick(raw, "account.name", "account", "page.name"),
        "external_id": _pick(raw, "message.id", "id", "comment.id", "conversation.id"),
        "author_name": _pick(raw, "user.name", "contact.name", "author.name"),
        "author_handle": _pick(raw, "user.username", "contact.username", "author.username"),
        "text": text,
        "url": _pick(raw, "url", "message.url", "comment.url"),
        "occurred_at": _pick(raw, "created_at", "timestamp", "message.created_at"),
        "metadata": {"chatplace": raw},
        "raw_payload": raw,
    }


def _extract_rows(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    for key in ("items", "messages", "comments", "conversations", "data"):
        value = raw.get(key)
        if isinstance(value, list):
            return value
    return [raw]


def _pick(raw: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = raw
        ok = True
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                ok = False
                break
        if ok and value not in (None, ""):
            return value
    return None
