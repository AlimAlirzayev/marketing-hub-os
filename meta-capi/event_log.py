"""Durable event journal for the CAPI senders — the missing history layer.

2026-07-21 crew audit finding: this module family is a live production SENDER
(gateway /collect + web.py CRM batches) with only volatile in-memory counters
(STATS dict + a 50-item deque) — so "custom conversions over time" could not be
charted at all. This journal closes that gap: every dispatch outcome is
appended, one JSON object per line, to ``data/events.jsonl``.

Design rules (this file must never endanger sending):
  * Append-only JSONL — no locks needed for a single-process writer per app;
    two apps (gateway :8812, web :8811) write to the same file via O_APPEND
    line writes, which POSIX/Windows keep atomic for small lines.
  * ``log_event`` NEVER raises — a broken disk must not break a Meta send.
  * Reading tolerates corrupt/partial lines (skips them, counts them).
  * Pure aggregation (``aggregate``) is separated from IO (``read_events``)
    so tests run offline — the impact_ledger pattern.

Record shape (all optional but ``t`` and ``event``):
    {"t": 1732200000, "event": "Step_FormStart", "event_id": "…",
     "status": "ok|error|dry_run", "detail": "fbtrace or error",
     "test": false, "dry_run": false, "kind": "collect|crm_batch",
     "value": 120.0, "currency": "AZN", "count": 1, "dataset": "…"}
``count`` lets one CRM batch line stand for N accepted events.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Iterator

_BASE = os.path.dirname(os.path.abspath(__file__))


def _log_path() -> str:
    # Env override first (tests point this at a tmp dir), else data/events.jsonl.
    p = os.getenv("CAPI_EVENT_LOG")
    if p:
        return p
    return os.path.join(_BASE, "data", "events.jsonl")


def log_event(record: dict[str, Any]) -> bool:
    """Append one journal line. Returns False (and stays silent) on any failure —
    journalling is observability, sending is the job."""
    try:
        rec = dict(record)
        rec.setdefault("t", int(_dt.datetime.now(_dt.timezone.utc).timestamp()))
        rec.setdefault("count", 1)
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True
    except Exception:
        return False


def read_events(since_ts: float | None = None,
                until_ts: float | None = None) -> Iterator[dict]:
    """Yield journal records in file order; skip corrupt lines silently."""
    path = _log_path()
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            t = rec.get("t")
            if not isinstance(t, (int, float)):
                continue
            if since_ts is not None and t < since_ts:
                continue
            if until_ts is not None and t >= until_ts:
                continue
            yield rec


def aggregate(records: Iterator[dict] | list[dict], *,
              include_test: bool = False) -> dict:
    """Pure: fold journal records into the chart-ready summary.

    Returns {total, sent_ok, failed, dry_run, value_sum, currency,
             by_event: [{event, count, value_sum}...] desc,
             daily: [{date, count, by_event:{name:count}}...] asc}.
    Test-mode events are excluded by default — an exec chart must show real
    traffic, not our own wiring smoke-tests (include_test=True for debugging).
    """
    total = sent_ok = failed = dry = 0
    value_sum = 0.0
    currency: str | None = None
    by_event: dict[str, dict] = {}
    daily: dict[str, dict] = {}

    for rec in records:
        if rec.get("test") and not include_test:
            continue
        n = rec.get("count")
        n = int(n) if isinstance(n, (int, float)) and n > 0 else 1
        status = str(rec.get("status") or "")
        name = str(rec.get("event") or "?")
        total += n
        if status == "ok":
            sent_ok += n
        elif status == "error":
            failed += n
        elif status == "dry_run":
            dry += n
        v = rec.get("value")
        if isinstance(v, (int, float)):
            value_sum += float(v)
            currency = rec.get("currency") or currency
        be = by_event.setdefault(name, {"event": name, "count": 0, "value_sum": 0.0})
        be["count"] += n
        if isinstance(v, (int, float)):
            be["value_sum"] += float(v)
        day = _dt.datetime.fromtimestamp(rec["t"], _dt.timezone.utc).strftime("%Y-%m-%d")
        d = daily.setdefault(day, {"date": day, "count": 0, "by_event": {}})
        d["count"] += n
        d["by_event"][name] = d["by_event"].get(name, 0) + n

    return {
        "total": total, "sent_ok": sent_ok, "failed": failed, "dry_run": dry,
        "value_sum": round(value_sum, 2), "currency": currency,
        "by_event": sorted(by_event.values(), key=lambda x: -x["count"]),
        "daily": sorted(daily.values(), key=lambda x: x["date"]),
    }


def report(days: int = 30, *, include_test: bool = False) -> dict:
    """IO + pure: the /api/events payload for the last N days."""
    now = _dt.datetime.now(_dt.timezone.utc)
    since = (now - _dt.timedelta(days=days)).timestamp()
    agg = aggregate(read_events(since_ts=since), include_test=include_test)
    return {"ok": True, "days": days, "include_test": include_test,
            "source": "jurnal (events.jsonl)", **agg}
