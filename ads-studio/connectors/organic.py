"""Live organic (owned-audience) social insights — Facebook Page + Instagram.

Distinct from meta.py (paid ad-account performance): this reads the Page's own
reach/engagement and the Instagram Business account's follower count, using
the Graph API token + Page/IG IDs already provisioned for CX comment sync
(cx-command-center). Nothing here spends money or writes anything — read-only.

Activate by setting in .env (same vars cx-command-center already uses):
    META_GRAPH_ACCESS_TOKEN=...       # or META_ACCESS_TOKEN as fallback
    META_FACEBOOK_PAGE_IDS=111,222    # first is the default/primary page
    META_INSTAGRAM_BUSINESS_IDS=333

Instagram reach/impressions additionally need the `instagram_manage_insights`
permission. When the app token lacks it, that one metric degrades to a
labelled "insufficient_permission" state — follower count still shows (it
only needs instagram_basic, already granted) and nothing is fabricated.
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta

import requests

from config import (
    META_API_VERSION,
    META_FACEBOOK_PAGE_IDS,
    META_GRAPH_ACCESS_TOKEN,
    META_INSTAGRAM_BUSINESS_IDS,
)

_BASE = "https://graph.facebook.com"
_TIMEOUT = 20
_MAX_RETRIES = 2
_session = requests.Session()

# Page Insights metrics still valid on v21+ (Meta deprecated page_fans,
# page_impressions*, page_engaged_users in the 2024 metrics cleanup).
_PAGE_METRICS = ["page_post_engagements", "page_views_total"]


class OrganicNotConfigured(RuntimeError):
    """Raised when no Page/IG id + token is configured."""


def _sanitize(text: str) -> str:
    if META_GRAPH_ACCESS_TOKEN and META_GRAPH_ACCESS_TOKEN in text:
        return text.replace(META_GRAPH_ACCESS_TOKEN, "<REDACTED>")
    return text


def _get(path: str, params: dict, token: str) -> dict:
    url = f"{_BASE}/{META_API_VERSION}/{path}"
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _session.get(url, params={**params, "access_token": token}, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            last_exc = _sanitize(str(exc))
            time.sleep(0.6 * (attempt + 1))
            continue
        if resp.ok:
            return resp.json()
        try:
            err = resp.json().get("error", {})
        except Exception:
            err = {}
        code = err.get("code")
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES:
            time.sleep(0.6 * (attempt + 1))
            continue
        raise requests.HTTPError(_sanitize(
            f"{resp.status_code} code={code} sub={err.get('error_subcode')} "
            f"msg={err.get('message', resp.text[:200])}"))
    raise requests.HTTPError(last_exc or "organic Graph request failed")


def _page_access_token(page_id: str) -> str:
    """Page-level insights require a Page Access Token, not the app/user token."""
    d = _get(page_id, {"fields": "access_token"}, META_GRAPH_ACCESS_TOKEN)
    return d.get("access_token") or META_GRAPH_ACCESS_TOKEN


def configured() -> dict:
    return {
        "facebook": bool(META_GRAPH_ACCESS_TOKEN and META_FACEBOOK_PAGE_IDS),
        "instagram": bool(META_GRAPH_ACCESS_TOKEN and META_INSTAGRAM_BUSINESS_IDS),
    }


def facebook_page(page_id: str | None = None, days: int = 30) -> dict:
    """Current fan count + a daily engagement/views series for the last N days."""
    pid = page_id or (META_FACEBOOK_PAGE_IDS[0] if META_FACEBOOK_PAGE_IDS else None)
    if not (META_GRAPH_ACCESS_TOKEN and pid):
        raise OrganicNotConfigured("META_FACEBOOK_PAGE_IDS / META_GRAPH_ACCESS_TOKEN not set")

    info = _get(pid, {"fields": "name,fan_count"}, META_GRAPH_ACCESS_TOKEN)
    out = {
        "page_id": pid, "name": info.get("name"), "fan_count": info.get("fan_count", 0),
        "daily": [], "insights_error": None,
    }
    try:
        page_tok = _page_access_token(pid)
        since = (date.today() - timedelta(days=days)).isoformat()
        until = date.today().isoformat()
        series: dict[str, dict[str, float]] = {}
        for metric in _PAGE_METRICS:
            d = _get(f"{pid}/insights", {
                "metric": metric, "period": "day", "since": since, "until": until,
            }, page_tok)
            for entry in d.get("data", []):
                for point in entry.get("values", []):
                    day = str(point.get("end_time", ""))[:10]
                    series.setdefault(day, {})[metric] = point.get("value", 0)
        out["daily"] = [
            {"date": day, **vals} for day, vals in sorted(series.items())
        ]
        # Meta silently returns an empty series (no error) when the token lacks
        # `read_insights` — never present that as "zero traffic" to the UI.
        if not out["daily"]:
            out["insights_error"] = (
                "insufficient_permission: Page views/engagement trend needs the "
                "'read_insights' scope, not yet granted on this token. Fan count "
                "above is live; re-authorize the app in Meta Business Suite to add "
                "the Page traffic trend."
            )
    except Exception as exc:
        out["insights_error"] = _sanitize(str(exc))
    return out


def instagram_business(ig_id: str | None = None) -> dict:
    """Current follower/media snapshot; reach/impressions trend when permitted."""
    iid = ig_id or (META_INSTAGRAM_BUSINESS_IDS[0] if META_INSTAGRAM_BUSINESS_IDS else None)
    if not (META_GRAPH_ACCESS_TOKEN and iid):
        raise OrganicNotConfigured("META_INSTAGRAM_BUSINESS_IDS / META_GRAPH_ACCESS_TOKEN not set")

    info = _get(iid, {"fields": "username,followers_count,media_count"}, META_GRAPH_ACCESS_TOKEN)
    out = {
        "ig_id": iid,
        "username": info.get("username"),
        "followers_count": info.get("followers_count", 0),
        "media_count": info.get("media_count", 0),
        "daily": [],
        "insights_error": None,
    }
    try:
        since = (date.today() - timedelta(days=30)).isoformat()
        until = date.today().isoformat()
        d = _get(f"{iid}/insights", {
            "metric": "reach", "period": "day", "since": since, "until": until,
        }, META_GRAPH_ACCESS_TOKEN)
        series = []
        for entry in d.get("data", []):
            for point in entry.get("values", []):
                series.append({"date": str(point.get("end_time", ""))[:10],
                                "reach": point.get("value", 0)})
        out["daily"] = series
    except Exception as exc:
        msg = _sanitize(str(exc))
        if "code=10" in msg or "does not have permission" in msg.lower():
            out["insights_error"] = (
                "insufficient_permission: Instagram reach/impressions needs the "
                "'instagram_manage_insights' scope, not yet granted on this token. "
                "Follower count above is live; re-authorize the app in Meta Business "
                "Suite to add reach/impressions history."
            )
        else:
            out["insights_error"] = msg
    return out


def organic_summary(days: int = 30) -> dict:
    """One-shot bundle for the dashboard's 'Sosial Performans' tab."""
    cfg = configured()
    out = {"facebook": {"configured": cfg["facebook"]}, "instagram": {"configured": cfg["instagram"]}}
    if cfg["facebook"]:
        try:
            out["facebook"] = {"configured": True, **facebook_page(days=days)}
        except Exception as exc:
            out["facebook"] = {"configured": True, "error": _sanitize(str(exc))}
    if cfg["instagram"]:
        try:
            out["instagram"] = {"configured": True, **instagram_business()}
        except Exception as exc:
            out["instagram"] = {"configured": True, "error": _sanitize(str(exc))}
    return out
