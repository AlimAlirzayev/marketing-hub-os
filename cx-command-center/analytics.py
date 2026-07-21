"""CX analytics and executive summary helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

import store

OPEN_STATUSES = {"new", "triaged", "in_progress", "waiting_customer"}
SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _is_overdue(item: dict) -> bool:
    if item["status"] not in OPEN_STATUSES:
        return False
    try:
        return _parse_dt(item["sla_due_at"]) < datetime.now(timezone.utc)
    except Exception:
        return False


def build_report(days: int = 30) -> dict:
    items = store.list_complaints(days=days, limit=2000)
    total = len(items)
    open_items = [i for i in items if i["status"] in OPEN_STATUSES]
    resolved = [i for i in items if i["status"] in {"resolved", "closed"}]
    overdue = [i for i in open_items if _is_overdue(i)]
    critical = [i for i in open_items if i["severity"] == "critical"]
    negative = [i for i in items if i["sentiment"] in {"negative", "very_negative"}]

    by_channel = Counter(i["channel"] for i in items)
    by_category = Counter(i["category"] for i in items)
    by_team = Counter(i["assigned_team"] for i in open_items)
    by_status = Counter(i["status"] for i in items)
    by_severity = Counter(i["severity"] for i in items)

    daily: dict[str, dict] = defaultdict(lambda: {"date": "", "total": 0, "negative": 0, "critical": 0})
    for item in items:
        date = (item["occurred_at"] or item["created_at"])[:10]
        daily[date]["date"] = date
        daily[date]["total"] += 1
        if item["sentiment"] in {"negative", "very_negative"}:
            daily[date]["negative"] += 1
        if item["severity"] == "critical":
            daily[date]["critical"] += 1

    rating_items = [i for i in items if i.get("rating") is not None]
    avg_rating = round(sum(float(i["rating"]) for i in rating_items) / len(rating_items), 2) if rating_items else None

    risk_score = 0
    if total:
        risk_score = min(
            100,
            round(
                sum(SEVERITY_WEIGHT.get(i["severity"], 1) * 7 for i in open_items)
                + len(overdue) * 6
                + len(critical) * 9
            ),
        )

    root_causes = [
        {"category": cat, "count": count, "team": _team_for_category(cat)}
        for cat, count in by_category.most_common(8)
    ]

    return {
        "period_days": days,
        "totals": {
            "messages": total,
            "open": len(open_items),
            "resolved": len(resolved),
            "negative": len(negative),
            "critical_open": len(critical),
            "overdue": len(overdue),
            "avg_rating": avg_rating,
            "risk_score": risk_score,
            "resolution_rate": round((len(resolved) / total) * 100, 1) if total else 0,
        },
        "breakdowns": {
            "channel": _counter_rows(by_channel),
            "category": _counter_rows(by_category),
            "team": _counter_rows(by_team),
            "status": _counter_rows(by_status),
            "severity": _counter_rows(by_severity),
        },
        "daily": sorted(daily.values(), key=lambda x: x["date"]),
        "root_causes": root_causes,
        "priority_queue": open_items[:20],
        "overdue_queue": overdue[:20],
    }


def _team_for_category(category: str) -> str:
    import config

    return config.TEAMS.get(category, "Customer Care")


def _counter_rows(counter: Counter) -> list[dict]:
    return [{"key": key, "count": count} for key, count in counter.most_common()]


def executive_brief(report: dict) -> dict:
    # User-facing strings are Azerbaijani (house language rule); keys stay EN.
    totals = report["totals"]
    root = report["root_causes"][:3]
    top = ", ".join(f"{r['category']} ({r['count']})" for r in root) or "dominant problem yoxdur"
    if totals["critical_open"] or totals["overdue"]:
        level = "red"
        title = "Təcili müdaxilə tələb olunur"
    elif totals["risk_score"] >= 55:
        level = "amber"
        title = "Şikayət təzyiqi yüksəlib"
    else:
        level = "green"
        title = "Şikayət sistemi nəzarət altındadır"
    text = (
        f"Son {report['period_days']} gün: {totals['messages']} siqnal, "
        f"{totals['open']} açıq, {totals['overdue']} gecikmiş, {totals['critical_open']} kritik. "
        f"Əsas səbəblər: {top}. Həll faizi: {totals['resolution_rate']}%."
    )
    return {"level": level, "title": title, "text": text}

