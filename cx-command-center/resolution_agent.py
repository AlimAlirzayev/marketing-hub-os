"""Draft-only CX resolution agent.

This module is the sandbox audition for a future customer-recovery agent. It
does not send replies, change statuses, call external APIs, or approve anything
for production. It only reads already-triaged complaint data and prepares an
operator plan with redacted evidence and reply drafts.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any


OPEN_STATUSES = {"new", "triaged", "in_progress", "waiting_customer"}
PUBLIC_CHANNELS = {"instagram_comment", "facebook_comment", "tiktok_comment", "google_review", "web_mention"}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{6,}\d)(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def redact_text(text: str) -> str:
    """Mask obvious PII before showing text in the agent plan."""
    value = text or ""
    value = _EMAIL_RE.sub("[redacted-email]", value)
    value = _CARD_RE.sub("[redacted-number]", value)
    value = _PHONE_RE.sub("[redacted-phone]", value)
    return value


def build_plan_from_store(days: int = 7, limit: int = 20) -> dict:
    """Build a draft resolution plan from the local CX Command Center store."""
    import analytics

    report = analytics.build_report(days=days)
    report["brief"] = analytics.executive_brief(report)
    return build_plan(report, days=days, limit=limit)


def build_plan(report: dict, *, days: int = 7, limit: int = 20) -> dict:
    """Build an operator-only recovery plan from a CX analytics report."""
    priority = _dedupe_items((report.get("overdue_queue") or []) + (report.get("priority_queue") or []))
    priority = sorted(priority, key=_priority_sort_key, reverse=True)[:limit]
    drafts = [_draft_for_item(item) for item in priority]
    totals = report.get("totals") or {}
    root_causes = report.get("root_causes") or []

    return {
        "mode": "sandbox_draft_only",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "period_days": days,
        "send_allowed": False,
        "status_write_allowed": False,
        "approval_required": True,
        "summary": _operator_summary(totals, root_causes, len(drafts)),
        "safety_controls": [
            "Draft-only: do not send replies from this agent.",
            "Human approval is required before any customer-facing message.",
            "PII is redacted in evidence previews.",
            "Verify policy, claim, payment, and customer identity details in source systems before replying.",
            "Public-channel replies require brand, legal, and tone review.",
        ],
        "clusters": _clusters(report, priority),
        "draft_queue": drafts,
        "next_actions": _next_actions(totals, root_causes, drafts),
    }


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[Any] = set()
    out: list[dict] = []
    for item in items:
        key = item.get("id") or (item.get("channel"), item.get("external_id"), item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _priority_sort_key(item: dict) -> tuple[int, int, int]:
    severity = SEVERITY_RANK.get(str(item.get("severity", "low")), 1)
    overdue = 1 if _is_overdue(item) else 0
    urgency = int(item.get("urgency_score") or 0)
    public = 1 if item.get("channel") in PUBLIC_CHANNELS else 0
    return (severity, overdue, urgency + public)


def _is_overdue(item: dict) -> bool:
    if item.get("status") not in OPEN_STATUSES:
        return False
    due = item.get("sla_due_at")
    if not due:
        return False
    try:
        if str(due).endswith("Z"):
            due = str(due)[:-1] + "+00:00"
        return datetime.fromisoformat(str(due)) < datetime.now(timezone.utc)
    except Exception:
        return False


def _draft_for_item(item: dict) -> dict:
    reply = (item.get("recommended_reply") or "").strip() or _fallback_reply(item)
    checklist = [
        "Confirm customer identity and case context.",
        "Check the underlying policy, claim, or service record.",
        "Approve tone and facts before sending.",
    ]
    if item.get("channel") in PUBLIC_CHANNELS:
        checklist.append("Keep the public reply brief and move personal details to private channel.")
    if item.get("severity") in {"critical", "high"}:
        checklist.append("Escalate to the assigned team owner before marking resolved.")

    return {
        "complaint_id": item.get("id"),
        "priority": _priority_label(item),
        "channel": item.get("channel"),
        "category": item.get("category"),
        "sentiment": item.get("sentiment"),
        "severity": item.get("severity"),
        "status": item.get("status"),
        "assigned_team": item.get("assigned_team"),
        "sla_due_at": item.get("sla_due_at"),
        "overdue": _is_overdue(item),
        "customer_text_redacted": redact_text(item.get("text", "")),
        "ai_summary": redact_text(item.get("ai_summary", "")),
        "draft_reply": redact_text(reply),
        "next_best_action": _next_best_action_for_item(item),
        "send_allowed": False,
        "approval_required": True,
        "approval_checklist": checklist,
    }


def _priority_label(item: dict) -> str:
    if _is_overdue(item) and item.get("severity") in {"critical", "high"}:
        return "urgent_recovery"
    if item.get("severity") == "critical":
        return "critical_review"
    if item.get("severity") == "high":
        return "high_priority"
    return "standard_followup"


def _next_best_action_for_item(item: dict) -> str:
    category = item.get("category")
    severity = item.get("severity")
    if _is_overdue(item):
        return "Assign owner now, verify facts, and prepare same-day recovery reply."
    if category == "claims":
        return "Verify claim status and give a clear next-step timeline."
    if category == "delay":
        return "Acknowledge the delay, explain the next checkpoint, and offer a direct follow-up path."
    if category == "digital_issue":
        return "Ask for safe troubleshooting details and route to Digital if repeated."
    if category == "reputation_risk" or severity in {"critical", "high"}:
        return "Escalate to PR and Customer Care before public response."
    return "Review context, personalize the draft, then request human approval."


def _fallback_reply(item: dict) -> str:
    return (
        "Hormetli musteri, muracietinizi qeyd etdik. Melumati yoxlayib size en qisa zamanda "
        "deqiq geri donus edeceyik. Sexsi melumatlari ictimai kanalda paylasmamaginizi xahis edirik."
    )


def _operator_summary(totals: dict, root_causes: list[dict], draft_count: int) -> str:
    top = root_causes[0]["category"] if root_causes else "no dominant root cause"
    return (
        f"{draft_count} draft recovery items prepared. Open={totals.get('open', 0)}, "
        f"overdue={totals.get('overdue', 0)}, critical={totals.get('critical_open', 0)}, "
        f"risk={totals.get('risk_score', 0)}/100. Top driver: {top}."
    )


def _clusters(report: dict, priority: list[dict]) -> list[dict]:
    root = report.get("root_causes") or []
    if root:
        return [
            {
                "category": row.get("category"),
                "count": row.get("count"),
                "team": row.get("team"),
                "recommended_workflow": _workflow_for_category(row.get("category")),
            }
            for row in root[:8]
        ]

    counts = Counter(item.get("category") or "other" for item in priority)
    return [
        {
            "category": category,
            "count": count,
            "team": None,
            "recommended_workflow": _workflow_for_category(category),
        }
        for category, count in counts.most_common(8)
    ]


def _workflow_for_category(category: str | None) -> str:
    if category == "claims":
        return "Claims verification -> timeline reply -> owner follow-up."
    if category == "delay":
        return "Delay acknowledgment -> cause check -> deadline commitment after approval."
    if category == "digital_issue":
        return "Troubleshooting evidence -> Digital routing -> customer update."
    if category == "price":
        return "Clarify product/coverage terms -> Sales callback."
    if category == "reputation_risk":
        return "PR review -> short public reply -> private recovery path."
    return "Customer Care review -> personalize draft -> approve before sending."


def _next_actions(totals: dict, root_causes: list[dict], drafts: list[dict]) -> list[str]:
    actions = []
    if totals.get("overdue", 0):
        actions.append("Clear overdue SLA items first; assign owners before drafting new public replies.")
    if totals.get("critical_open", 0):
        actions.append("Escalate critical open complaints to Customer Care lead and relevant business team.")
    if root_causes:
        actions.append(f"Open a root-cause workstream for {root_causes[0]['category']}.")
    if drafts:
        actions.append("Review the draft queue, approve safe replies, and keep this agent draft-only.")
    if not actions:
        actions.append("No urgent CX recovery work found; keep monitoring daily.")
    return actions
