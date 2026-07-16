"""Live Meta Marketing API adapter (Graph API Insights).

Exposes the same report shape as the demo engine plus segment / creative /
campaign fetchers needed by the pro dashboard (placements, day-parting,
demographics, top campaigns, diagnostic rankings, video metrics).

Activate by setting in .env:
    META_ACCESS_TOKEN=...                # long-lived / system-user, ads_read
    META_AD_ACCOUNT_ID=act_123...        # single account
    META_AD_ACCOUNTS=act_1|Client A,...  # optional multi-account list

All public functions accept an optional ``account_id`` so the API can serve
multiple ad accounts side-by-side.
"""

from __future__ import annotations

import calendar
import json
import os
import random
import sys
import time
from datetime import date

import requests

from config import (
    ACCOUNT_NAME,
    CURRENCY,
    DEFAULT_ACCOUNT_ID,
    META_ACCESS_TOKEN,
    META_API_VERSION,
    month_label,
    today,
)

_BASE = "https://graph.facebook.com"
_TIMEOUT = 30
_ROOT_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")


def _access_token() -> str:
    """Read the current token without requiring a service restart.

    The encrypted-vault sync runs in a separate process, so its os.environ
    changes cannot reach this already-running API. Reading one named line from
    the local .env makes rotations effective on the next Meta request.
    """
    try:
        with open(_ROOT_ENV, encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith("META_ACCESS_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return META_ACCESS_TOKEN

# --- Resilience knobs (env-overridable) -------------------------------------
# A live report fires several Insights calls per dashboard load (report +
# baseline + segments + campaigns + diagnostics + video). It must ride out
# Meta's frequent throttles and 5xx blips instead of collapsing to demo data on
# the first hiccup, and it must not re-pull the same month on every endpoint.
_MAX_RETRIES = int(os.getenv("ADS_META_MAX_RETRIES", "3"))
_CACHE_TTL = int(os.getenv("ADS_META_CACHE_TTL", "300"))  # seconds; 0 disables

# One pooled connection for every Graph call (TLS reuse → faster pagination).
_session = requests.Session()

# Meta error codes worth retrying — rate limits + transient backend errors:
#   1,2 = transient/unknown API error   4   = app-level rate limit
#   17  = user request limit reached     32  = page-level rate limit
#   341 = application limit reached      613 = custom rate limit
#   80000-89999 = business-use-case (ads) throttling
_RETRYABLE_CODES = {1, 2, 4, 17, 32, 341, 613}
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}
# Never retry these — the message must reach the UI fast, retrying only stalls:
#   190 = token expired/invalid   102 = bad session   100 = bad parameter
#   10/200/272/278/294 = permission / access problems
_FATAL_CODES = {10, 100, 102, 190, 200, 272, 278, 294}

# Meta action_type tokens we treat as "lead" / "message".
_LEAD_ACTIONS = {"lead", "onsite_conversion.lead_grouped", "leadgen.other"}
_MSG_ACTIONS = {
    "onsite_conversion.messaging_conversation_started_7d",
    "onsite_conversion.total_messaging_connection",
}


class MetaNotConfigured(RuntimeError):
    """Raised when token is missing. Caller falls back to demo."""


def _acc(account_id: str | None) -> str:
    acc = account_id or DEFAULT_ACCOUNT_ID
    if not _access_token():
        raise MetaNotConfigured("META_ACCESS_TOKEN not set")
    if not acc:
        raise MetaNotConfigured("No ad account configured")
    return acc


def _sanitize(text: str) -> str:
    """Strip the access token out of anything we might surface (errors, logs)."""
    token = _access_token()
    if token and token in text:
        return text.replace(token, "<REDACTED>")
    return text


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter: ~0.5, 1, 2, 4 … capped at 30s."""
    return min(0.5 * (2 ** attempt) + random.uniform(0, 0.5), 30.0)


def _retry_after(resp: requests.Response, attempt: int) -> float:
    """Honor a Retry-After header if Meta sends one, else exponential backoff."""
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return min(float(ra), 60.0)
        except ValueError:
            pass
    return _backoff(attempt)


def _parse_error(resp: requests.Response) -> tuple[str, bool]:
    """Build a token-safe error message and decide whether it is retryable.

    Surfaces Meta's real type/code/message so the dispatcher and
    /api/meta live-health can detect "token expired" (code 190) etc.
    """
    code = None
    is_transient = False
    try:
        err = resp.json().get("error", {})
        code = err.get("code")
        is_transient = bool(err.get("is_transient"))
        detail = (f" type={err.get('type')} code={code}"
                  f" subcode={err.get('error_subcode')} msg={err.get('message')}")
    except Exception:
        detail = " body=" + (resp.text or "")[:200]
    retryable = (code not in _FATAL_CODES) and (
        resp.status_code in _RETRYABLE_HTTP
        or is_transient
        or code in _RETRYABLE_CODES
        or (isinstance(code, int) and 80000 <= code <= 89999)
    )
    msg = _sanitize(
        f"{resp.status_code} {resp.reason} for {resp.url.split('?')[0]}{detail}")
    return msg, retryable


def _request(url: str, params: dict | None = None) -> dict:
    """GET with bounded retry on rate limits / transient 5xx / network blips.

    Fatal errors (expired token, permissions, bad params) raise immediately so
    the failure surfaces in the UI instead of stalling behind useless retries.
    """
    last_msg = "Meta request failed"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _session.get(url, params=params, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            last_msg = _sanitize(str(exc))
            if attempt < _MAX_RETRIES:
                time.sleep(_backoff(attempt))
                continue
            raise type(exc)(last_msg) from None
        if resp.ok:
            return resp.json()
        msg, retryable = _parse_error(resp)
        last_msg = msg
        if retryable and attempt < _MAX_RETRIES:
            wait = _retry_after(resp, attempt)
            print(f"[meta] retry {attempt + 1}/{_MAX_RETRIES} in {wait:.1f}s — {msg}",
                  file=sys.stderr)
            time.sleep(wait)
            continue
        raise requests.HTTPError(msg) from None
    raise requests.HTTPError(last_msg) from None


# --- Tiny in-process TTL cache ----------------------------------------------
# Keyed by call + path + params (token excluded). One dashboard load fans out
# into many duplicate month fetches (report, baseline, segments all re-read the
# same month); within the TTL they collapse to a single Graph call.
_cache: dict[str, tuple[float, object]] = {}


def _cache_key(kind: str, path: str, params: dict) -> str:
    items = sorted((k, v) for k, v in params.items() if k != "access_token")
    return f"{kind}|{path}|{items}"


def _cache_get(key: str):
    if _CACHE_TTL <= 0:
        return None
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value) -> None:
    if _CACHE_TTL > 0:
        _cache[key] = (time.time(), value)


def clear_cache() -> None:
    """Drop all cached responses (tests / forced refresh)."""
    _cache.clear()


def _get(path: str, params: dict, use_cache: bool = True) -> dict:
    key = _cache_key("get", path, params) if use_cache else ""
    if key:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    data = _request(f"{_BASE}/{META_API_VERSION}/{path}",
                    {**params, "access_token": _access_token()})
    if key:
        _cache_put(key, data)
    return data


def _paged(path: str, params: dict, hard_limit: int = 2000) -> list[dict]:
    key = _cache_key("paged", path, params)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows: list[dict] = []
    page = _get(path, params, use_cache=False)  # cache the assembled list, not pages
    while True:
        rows.extend(page.get("data", []))
        if len(rows) >= hard_limit:
            break
        nxt = page.get("paging", {}).get("next")
        if not nxt:
            break
        page = _request(nxt)  # next URL already carries the token + cursor
    _cache_put(key, rows)
    return rows


def _tr_json(tr: dict) -> str:
    """Serialize a {"since","until"} time range to the JSON Meta expects."""
    return json.dumps(tr, separators=(",", ":"))


def _count_actions(actions: list[dict], wanted: set[str]) -> int:
    return int(sum(float(a.get("value", 0)) for a in actions or []
                   if a.get("action_type") in wanted))


def _value_for(actions: list[dict], action_type: str) -> int:
    for a in actions or []:
        if a.get("action_type") == action_type:
            return int(float(a.get("value", 0)))
    return 0


def _time_range(ym: str) -> tuple[dict, int, int, bool]:
    """Returns (time_range_dict, days_in_month, days_elapsed, is_current)."""
    y, m = (int(x) for x in ym.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]
    now = today()
    is_current = (y == now.year and m == now.month)
    end_day = now.day if is_current else days_in_month
    tr = {"since": date(y, m, 1).isoformat(),
          "until": date(y, m, end_day).isoformat()}
    return tr, days_in_month, end_day, is_current


def _row_to_metrics(row: dict) -> dict:
    actions = row.get("actions", [])
    return {
        "spend": round(float(row.get("spend", 0)), 2),
        "impressions": int(float(row.get("impressions", 0))),
        "clicks": int(float(row.get("clicks", 0))),
        "reach": int(float(row.get("reach", 0))),
        "leads": _count_actions(actions, _LEAD_ACTIONS),
        "messages": _count_actions(actions, _MSG_ACTIONS),
    }


def _derive(t: dict) -> dict:
    impr = max(t["impressions"], 1)
    clicks = max(t["clicks"], 1)
    reach = max(t["reach"], 1)
    leads = max(t["leads"], 0)
    messages = max(t["messages"], 0)
    return {
        **t,
        "ctr": round(clicks / impr * 100, 2),
        "cpm": round(t["spend"] / impr * 1000, 2),
        "cpc": round(t["spend"] / clicks, 2),
        "frequency": round(impr / reach, 2),
        "cpl": round(t["spend"] / leads, 2) if leads else 0.0,
        "cost_per_message": round(t["spend"] / messages, 2) if messages else 0.0,
    }


def _sum(rows: list[dict]) -> dict:
    keys = ("spend", "impressions", "clicks", "reach", "leads", "messages")
    out = {k: 0 for k in keys}
    for r in rows:
        for k in keys:
            out[k] += r[k]
    out["spend"] = round(out["spend"], 2)
    return out


_FIELDS = "spend,impressions,clicks,reach,frequency,ctr,cpm,actions"


# ============================================================================
# Public API
# ============================================================================

def account_info(account_id: str | None = None) -> dict:
    """Fetch the ad account's real name / currency / status / timezone."""
    acc = _acc(account_id)
    d = _get(acc, {"fields": "name,currency,account_status,timezone_name"})
    return {
        "id": acc,
        "name": d.get("name", ACCOUNT_NAME),
        "currency": d.get("currency", CURRENCY),
        "status": d.get("account_status"),
        "timezone": d.get("timezone_name"),
    }


def build_report(ym: str, platform: str = "all", account_id: str | None = None) -> dict:
    """Daily insights + platform split for a single month, real data."""
    acc = _acc(account_id)
    tr, days_in_month, end_day, is_current = _time_range(ym)
    y, m = (int(x) for x in ym.split("-"))
    tr_json = _tr_json(tr)

    # Daily rows for the trend.
    daily_raw = _paged(f"{acc}/insights", {
        "fields": _FIELDS, "time_range": tr_json,
        "time_increment": 1, "level": "account", "limit": 500,
    })
    series = [{"date": r.get("date_start"), **_row_to_metrics(r)} for r in daily_raw]
    totals = _derive(_sum([_row_to_metrics(r) for r in daily_raw]))

    # Per-publisher-platform breakdown for the FB/IG/Messenger filter.
    plat_raw = _paged(f"{acc}/insights", {
        "fields": _FIELDS, "time_range": tr_json,
        "breakdowns": "publisher_platform", "level": "account", "limit": 500,
    })
    zero = _derive({"spend": 0, "impressions": 0, "clicks": 0, "reach": 0, "leads": 0, "messages": 0})
    by_platform = {"facebook": zero, "instagram": zero, "messenger": zero, "audience_network": zero}
    for r in plat_raw:
        key = r.get("publisher_platform")
        if key in by_platform:
            by_platform[key] = _derive(_row_to_metrics(r))

    shown = by_platform.get(platform, totals) if platform in by_platform else totals

    try:
        info = account_info(acc)
    except Exception:
        info = {"id": acc, "name": ACCOUNT_NAME, "currency": CURRENCY}

    return {
        "account": {
            "id": info["id"], "name": info["name"], "currency": info["currency"],
            "ad_account_id": acc, "source": "meta-live",
        },
        "period": {
            "month": ym, "label": month_label(ym),
            "start": date(y, m, 1).isoformat(),
            "end": date(y, m, days_in_month).isoformat(),
            "days_total": days_in_month, "days_elapsed": end_day,
            "is_current": is_current,
        },
        "platform": platform,
        "totals": shown,
        "combined_totals": totals,
        "full_month_targets": totals,
        "by_platform": by_platform,
        "daily": series,
        "invoices": {"rows": [], "count": 0, "total": 0.0, "unbilled": 0.0},
        "sales": {"total": 0, "by_channel": [], "is_demo": True},
    }


# ----------------------------------------------------------------------------
# Segment fetchers — placements, time-of-day, demographics, regions
# ----------------------------------------------------------------------------
def insights_by(breakdown: str, ym: str, account_id: str | None = None,
                extra_fields: str = "") -> list[dict]:
    """Generic breakdown puller. Returns raw rows with metrics + breakdown key.

    Useful breakdowns: publisher_platform, platform_position,
    impression_device, hourly_stats_aggregated_by_advertiser_time_zone,
    age, gender, country, region.
    """
    acc = _acc(account_id)
    tr, *_ = _time_range(ym)
    # Hourly + reach/frequency are incompatible: drop reach when needed.
    fields = _FIELDS
    if breakdown.startswith("hourly_"):
        fields = "spend,impressions,clicks,ctr,cpm,actions"
    if extra_fields:
        fields = f"{fields},{extra_fields}"
    return _paged(f"{acc}/insights", {
        "fields": fields, "time_range": _tr_json(tr),
        "breakdowns": breakdown, "level": "account", "limit": 500,
    })


def segments(ym: str, account_id: str | None = None) -> dict:
    """One-shot bundle: placement, position, hourly, day-of-week, device,
    age, gender. Cached daily series powers the day-of-week chart locally
    so we don't burn a separate API call."""
    out: dict = {}

    def safe(name: str, breakdown: str, key_field: str | None = None):
        try:
            rows = insights_by(breakdown, ym, account_id)
            out[name] = [{
                "key": r.get(key_field or breakdown),
                **_derive(_row_to_metrics(r)),
            } for r in rows]
        except Exception as exc:
            out[name] = {"error": str(exc)}

    safe("publisher_platform", "publisher_platform")
    safe("impression_device", "impression_device")
    safe("age", "age")
    safe("gender", "gender")
    safe("region", "region")

    # Combined age × gender — drives the demographics heatmap.
    try:
        rows = insights_by("age,gender", ym, account_id)
        out["age_gender"] = [{
            "age": r.get("age"), "gender": r.get("gender"),
            **_derive(_row_to_metrics(r)),
        } for r in rows]
    except Exception as exc:
        out["age_gender"] = {"error": str(exc)}

    # Placement: Meta rejects `platform_position` alone on many accounts, but
    # accepts it combined with publisher_platform. The combined breakdown is
    # also more useful — gives "Instagram · Feed", "Instagram · Stories" etc.
    # Try combined first; fall back to the plain breakdown if combined fails.
    try:
        rows = insights_by("publisher_platform,platform_position", ym, account_id)
        out["placement"] = [{
            "key": f"{(r.get('publisher_platform') or '?').replace('_',' ').title()} · "
                    f"{(r.get('platform_position') or '?').replace('_',' ').title()}",
            "publisher_platform": r.get("publisher_platform"),
            "platform_position": r.get("platform_position"),
            **_derive(_row_to_metrics(r)),
        } for r in rows]
    except Exception as combined_exc:
        try:
            rows = insights_by("platform_position", ym, account_id)
            out["placement"] = [{
                "key": (r.get("platform_position") or "?").replace("_", " ").title(),
                **_derive(_row_to_metrics(r)),
            } for r in rows]
        except Exception as exc:
            out["placement"] = {"error": f"combined: {combined_exc} · alone: {exc}"}

    # Hourly: 24 rows of "HH:MM:SS - HH:MM:SS".
    try:
        rows = insights_by("hourly_stats_aggregated_by_advertiser_time_zone", ym, account_id)
        hourly = []
        for r in rows:
            label = r.get("hourly_stats_aggregated_by_advertiser_time_zone", "")
            hour = int(label.split(":")[0]) if label else 0
            hourly.append({
                "hour": hour,
                "spend": round(float(r.get("spend", 0)), 2),
                "impressions": int(float(r.get("impressions", 0))),
                "clicks": int(float(r.get("clicks", 0))),
                "leads": _count_actions(r.get("actions"), _LEAD_ACTIONS),
                "messages": _count_actions(r.get("actions"), _MSG_ACTIONS),
            })
        hourly.sort(key=lambda x: x["hour"])
        out["hourly"] = hourly
    except Exception as exc:
        out["hourly"] = {"error": str(exc)}

    return out


# ----------------------------------------------------------------------------
# Top campaigns leaderboard
# ----------------------------------------------------------------------------
def top_campaigns(ym: str, account_id: str | None = None, limit: int = 10) -> list[dict]:
    acc = _acc(account_id)
    tr, *_ = _time_range(ym)
    rows = _paged(f"{acc}/insights", {
        "fields": f"campaign_id,campaign_name,{_FIELDS}",
        "time_range": _tr_json(tr),
        "level": "campaign", "limit": 200,
    })
    enriched = []
    for r in rows:
        m = _row_to_metrics(r)
        d = _derive(m)
        enriched.append({
            "campaign_id": r.get("campaign_id"),
            "campaign_name": r.get("campaign_name") or "(adsız)",
            **d,
        })
    enriched.sort(key=lambda r: r["spend"], reverse=True)
    return enriched[:limit]


def top_adsets(ym: str, account_id: str | None = None, limit: int = 200) -> list[dict]:
    """Ad-set level spend/leads — needed for the budget simulator on accounts
    without Campaign Budget Optimization, where the real budget lever is the
    ad set, not the campaign (Meta silently returns null campaign.daily_budget
    in that case)."""
    acc = _acc(account_id)
    tr, *_ = _time_range(ym)
    rows = _paged(f"{acc}/insights", {
        "fields": f"adset_id,adset_name,campaign_id,{_FIELDS}",
        "time_range": _tr_json(tr),
        "level": "adset", "limit": 200,
    })
    enriched = []
    for r in rows:
        d = _derive(_row_to_metrics(r))
        enriched.append({
            "adset_id": r.get("adset_id"),
            "adset_name": r.get("adset_name") or "(adsız)",
            "campaign_id": r.get("campaign_id"),
            **d,
        })
    enriched.sort(key=lambda r: r["spend"], reverse=True)
    return enriched[:limit]


# ----------------------------------------------------------------------------
# Creative diagnostics — Meta's ad-level Quality / Engagement / Conversion rank
# ----------------------------------------------------------------------------
_RANK_FIELDS = "ad_id,ad_name,quality_ranking,engagement_rate_ranking,conversion_rate_ranking"


def _canon_rank(v: str | None) -> str | None:
    """Meta returns ABOVE_AVERAGE / AVERAGE / BELOW_AVERAGE_35[…] / UNKNOWN
    in mixed shorthand; collapse to a stable canonical key (or None)."""
    if not v:
        return None
    u = v.upper()
    if u in ("UNKNOWN", ""):
        return None
    if u.startswith("BELOW_AVERAGE_35"):
        return "BELOW_AVERAGE_35"
    if u.startswith("BELOW_AVERAGE_20"):
        return "BELOW_AVERAGE_20"
    if u.startswith("BELOW_AVERAGE_10"):
        return "BELOW_AVERAGE_10"
    if u == "ABOVE_AVERAGE":
        return "ABOVE_AVERAGE"
    if u == "AVERAGE":
        return "AVERAGE"
    return u


def creative_diagnostics(ym: str, account_id: str | None = None,
                          min_impressions: int = 500, limit: int = 20) -> list[dict]:
    """Per-ad creative health: Meta's three relevance rankings.
    Rankings only fill after enough impressions; we filter to meaningful ads.

    Note: ranking fields cannot be requested alongside reach/frequency at
    ad-level — Meta returns 400. We use a tighter field set here.
    """
    acc = _acc(account_id)
    tr, *_ = _time_range(ym)
    # No reach/frequency here — incompatible with ranking fields at ad level.
    fields = ("ad_id,ad_name,quality_ranking,engagement_rate_ranking,"
              "conversion_rate_ranking,spend,impressions,clicks,ctr,cpm,actions")
    rows = _paged(f"{acc}/insights", {
        "fields": fields,
        "time_range": _tr_json(tr),
        "level": "ad", "limit": 200,
    })
    out = []
    for r in rows:
        m = _row_to_metrics(r)
        if m["impressions"] < min_impressions:
            continue
        out.append({
            "ad_id": r.get("ad_id"),
            "ad_name": r.get("ad_name") or "(adsız)",
            "quality_ranking": _canon_rank(r.get("quality_ranking")),
            "engagement_rate_ranking": _canon_rank(r.get("engagement_rate_ranking")),
            "conversion_rate_ranking": _canon_rank(r.get("conversion_rate_ranking")),
            **_derive(m),
        })
    out.sort(key=lambda r: r["spend"], reverse=True)
    return out[:limit]


# ----------------------------------------------------------------------------
# Video metrics — Hook rate + Hold rate (2026 creative-health standard)
# ----------------------------------------------------------------------------
_VIDEO_EXTRA = ("video_play_actions,video_3_sec_watched_actions,"
                "video_thruplay_watched_actions,video_avg_time_watched_actions")


def video_metrics(ym: str, account_id: str | None = None) -> dict:
    acc = _acc(account_id)
    tr, *_ = _time_range(ym)
    rows = _paged(f"{acc}/insights", {
        "fields": f"impressions,spend,{_VIDEO_EXTRA}",
        "time_range": _tr_json(tr),
        "level": "account", "limit": 100,
    })
    if not rows:
        return {"has_video": False}
    r = rows[0]
    impr = int(float(r.get("impressions", 0))) or 1
    plays = _value_for(r.get("video_play_actions"), "video_view")
    v3 = _value_for(r.get("video_3_sec_watched_actions"), "video_view")
    thru = _value_for(r.get("video_thruplay_watched_actions"), "video_view")
    avg_time = 0
    for a in (r.get("video_avg_time_watched_actions") or []):
        if a.get("action_type") == "video_view":
            avg_time = float(a.get("value", 0))
            break
    hook = round(v3 / impr * 100, 2) if v3 else 0.0
    hold = round(thru / v3 * 100, 2) if v3 else 0.0
    return {
        "has_video": v3 > 0,
        "impressions": impr,
        "plays": plays,
        "three_sec_views": v3,
        "thruplays": thru,
        "avg_watch_seconds": round(avg_time, 1),
        "hook_rate": hook,         # benchmark: 25%+ good, 30%+ great
        "hold_rate": hold,         # benchmark: 15%+ good, 24%+ top 10%
    }
