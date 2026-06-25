"""Operational alerts for critical complaint events."""

from __future__ import annotations

import requests

import config


def maybe_alert(complaint: dict) -> dict:
    if complaint.get("severity") not in {"critical", "high"}:
        return {"sent": False, "reason": "not_high_priority"}
    if not complaint.get("_is_new") and complaint.get("_previous_severity") == complaint.get("severity"):
        return {"sent": False, "reason": "already_alerted"}
    if not config.TELEGRAM_BOT_TOKEN or not config.CX_ALERT_CHAT_ID:
        return {"sent": False, "reason": "telegram_not_configured"}
    text = _telegram_text(complaint)
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": config.CX_ALERT_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=8,
        )
        return {"sent": resp.ok, "status_code": resp.status_code}
    except requests.RequestException as exc:
        return {"sent": False, "reason": type(exc).__name__}


def _telegram_text(c: dict) -> str:
    source = c.get("url") or c.get("channel")
    return (
        f"<b>Customer Relations {c.get('severity', '').upper()} ALERT</b>\n"
        f"#{c.get('id')} | {c.get('channel')} | {c.get('assigned_team')}\n"
        f"<b>{_escape(c.get('category'))}</b>: {_escape(c.get('ai_summary'))}\n"
        f"SLA: {_escape(c.get('sla_due_at'))}\n"
        f"Source: {_escape(source)}"
    )


def _escape(value: object) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
