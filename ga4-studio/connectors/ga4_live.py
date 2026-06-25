"""Live GA4 connector — Google Analytics Data API (v1beta) over REST.

Auth: a Google **service account** (JSON key) granted *Viewer* on the GA4
property. We lazily import google-auth (needed only here), mint an access token
with the analytics.readonly scope, then POST ``runReport`` with plain
``requests`` — no grpc, no google-analytics-data SDK — so it installs cleanly on
the locked-down corporate machine.

Returns the identical dict shape as connectors/demo.py, so nothing downstream
knows or cares which source is live.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import requests

import config

_creds = None            # cached google-auth Credentials
_session = requests.Session()
# GA4 renamed "conversions" → "keyEvents" (2024). Try the new name, fall back to
# the old one once and remember which the property accepts.
_KEY_METRIC = "keyEvents"
_KEY_RESOLVED = False


class GA4NotConfigured(RuntimeError):
    pass


def _token() -> str:
    """A valid OAuth access token for the service account (auto-refreshed)."""
    global _creds
    if not (config.PROPERTY_ID and config.SERVICE_ACCOUNT_FILE):
        raise GA4NotConfigured("GA4_PROPERTY_ID və service-account faylı lazımdır.")
    if _creds is None:
        try:
            from google.oauth2 import service_account
        except ImportError as exc:
            raise GA4NotConfigured(
                "Canlı rejim üçün 'google-auth' lazımdır: "
                ".venv\\Scripts\\python.exe -m pip install google-auth") from exc
        _creds = service_account.Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_FILE, scopes=[config.GA4_SCOPE])
    if not _creds.valid:
        from google.auth.transport.requests import Request
        _creds.refresh(Request())
    return _creds.token


def _num(s: str) -> float:
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _run_report(*, dimensions=None, metrics, limit=10000, order_metric=None,
                start=None, end=None, retry_key=True) -> list[dict]:
    """One runReport call → list of {dims:[...], metrics:{name:value}} rows."""
    global _KEY_METRIC, _KEY_RESOLVED
    body: dict = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
        "keepEmptyRows": False,
    }
    if dimensions:
        body["dimensions"] = [{"name": d} for d in dimensions]
    if order_metric:
        body["orderBys"] = [{"metric": {"metricName": order_metric}, "desc": True}]

    url = f"{config.GA4_API}/properties/{config.PROPERTY_ID}:runReport"
    r = _session.post(url, headers={"Authorization": f"Bearer {_token()}"},
                      json=body, timeout=config.TIMEOUT)
    if not r.ok:
        msg = ""
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:
            msg = (r.text or "")[:300]
        # One-time fallback for the conversions/keyEvents rename.
        if (retry_key and not _KEY_RESOLVED and _KEY_METRIC in metrics
                and "keyEvents" in msg):
            _KEY_METRIC, _KEY_RESOLVED = "conversions", True
            metrics = ["conversions" if m == "keyEvents" else m for m in metrics]
            return _run_report(dimensions=dimensions, metrics=metrics, limit=limit,
                               order_metric=("conversions" if order_metric == "keyEvents"
                                             else order_metric),
                               start=start, end=end, retry_key=False)
        raise requests.HTTPError(f"GA4 runReport {r.status_code}: {msg}")
    _KEY_RESOLVED = True

    data = r.json()
    mh = [m["name"] for m in data.get("metricHeaders", [])]
    rows = []
    for row in data.get("rows", []):
        dvals = [d["value"] for d in row.get("dimensionValues", [])]
        mvals = {mh[i]: _num(v["value"]) for i, v in enumerate(row.get("metricValues", []))}
        rows.append({"dims": dvals, "metrics": mvals})
    return rows


def _totals(start: str, end: str) -> dict:
    m = ["activeUsers", "newUsers", "sessions", "engagedSessions",
         "engagementRate", "bounceRate", "userEngagementDuration",
         "screenPageViews", "eventCount", _KEY_METRIC]
    rows = _run_report(metrics=m, start=start, end=end)
    g = rows[0]["metrics"] if rows else {}
    sessions = g.get("sessions", 0) or 0
    users = g.get("activeUsers", 0) or 0
    conv = g.get(_KEY_METRIC, 0) or g.get("conversions", 0) or 0
    views = g.get("screenPageViews", 0) or 0
    return {
        "users": int(users), "new_users": int(g.get("newUsers", 0)),
        "sessions": int(sessions), "engaged_sessions": int(g.get("engagedSessions", 0)),
        "engagement_rate": round(g.get("engagementRate", 0), 4),
        "bounce_rate": round(g.get("bounceRate", 0), 4),
        "avg_engagement_sec": int(g.get("userEngagementDuration", 0) / users) if users else 0,
        "conversions": int(conv),
        "conversion_rate": round(conv / sessions, 4) if sessions else 0,
        "views": int(views),
        "views_per_session": round(views / sessions, 2) if sessions else 0,
        "event_count": int(g.get("eventCount", 0)),
    }


def get_report(start: str, end: str) -> dict:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days = (e - s).days + 1
    p_end = s - timedelta(days=1)
    p_start = p_end - timedelta(days=days - 1)

    totals = _totals(start, end)
    prev_totals = _totals(p_start.isoformat(), p_end.isoformat())

    # Daily trend
    trend = []
    for row in sorted(_run_report(dimensions=["date"],
                                  metrics=["activeUsers", "sessions", _KEY_METRIC],
                                  start=start, end=end), key=lambda r: r["dims"][0]):
        d = row["dims"][0]
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d
        m = row["metrics"]
        trend.append({"date": iso, "users": int(m.get("activeUsers", 0)),
                      "sessions": int(m.get("sessions", 0)),
                      "conversions": int(m.get(_KEY_METRIC, m.get("conversions", 0)))})

    # Channels
    ses = totals["sessions"] or 1
    channels = []
    for row in _run_report(dimensions=["sessionDefaultChannelGroup"],
                           metrics=["sessions", "activeUsers", _KEY_METRIC],
                           order_metric="sessions", start=start, end=end):
        name = row["dims"][0] or "Unassigned"
        c = int(row["metrics"].get("sessions", 0))
        conv = int(row["metrics"].get(_KEY_METRIC, row["metrics"].get("conversions", 0)))
        channels.append({
            "channel": name, "channel_az": config.CHANNEL_AZ.get(name, name),
            "sessions": c, "users": int(row["metrics"].get("activeUsers", 0)),
            "conversions": conv, "conversion_rate": round(conv / c, 4) if c else 0,
            "share": round(c / ses, 4)})

    # Top pages
    top_pages = []
    for row in _run_report(dimensions=["pagePath", "pageTitle"],
                           metrics=["screenPageViews", "activeUsers", "userEngagementDuration"],
                           order_metric="screenPageViews", limit=12, start=start, end=end):
        u = int(row["metrics"].get("activeUsers", 0))
        top_pages.append({
            "page": row["dims"][0], "title": row["dims"][1] if len(row["dims"]) > 1 else "",
            "views": int(row["metrics"].get("screenPageViews", 0)), "users": u,
            "avg_engagement_sec": int(row["metrics"].get("userEngagementDuration", 0) / u) if u else 0,
            "is_conversion_page": False})

    devices = [{"device": r["dims"][0], "sessions": int(r["metrics"].get("sessions", 0)),
                "share": round(int(r["metrics"].get("sessions", 0)) / ses, 4)}
               for r in _run_report(dimensions=["deviceCategory"], metrics=["sessions"],
                                    order_metric="sessions", start=start, end=end)]
    geo = [{"city": r["dims"][0] or "(other)", "sessions": int(r["metrics"].get("sessions", 0))}
           for r in _run_report(dimensions=["city"], metrics=["sessions"],
                                order_metric="sessions", limit=6, start=start, end=end)]
    events = [{"event": r["dims"][0], "count": int(r["metrics"].get("eventCount", 0))}
              for r in _run_report(dimensions=["eventName"], metrics=["eventCount"],
                                   order_metric="eventCount", limit=10, start=start, end=end)]

    return {
        "mode": "live", "property": str(config.PROPERTY_ID),
        "range": {"start": start, "end": end, "days": days,
                  "label": config.range_label(start, end)},
        "totals": totals, "prev_totals": prev_totals, "trend": trend,
        "channels": channels, "top_pages": top_pages, "devices": devices,
        "geo": geo, "events": events,
    }
