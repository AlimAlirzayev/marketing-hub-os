"""Read-only YTD reporting for the travel-insurance product line.

There is deliberately no demo fallback: leadership must never mistake
synthetic numbers for real travel performance. CRM exports are analysed in the
browser; this module only reads aggregated Meta Insights.
"""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone


TRAVEL_TERMS = (
    "travel", "seyah", "seyahet", "sefer", "safar", "xaric",
    "schengen", "shengen", "gurcustan", "georgia",
)
PURCHASE_ACTIONS = {
    "purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase",
    "onsite_web_purchase", "offline_conversion.purchase",
}


def _fold(value: str) -> str:
    value = (value or "").casefold().replace("ə", "e").replace("ı", "i")
    for source, target in (("ş", "s"), ("ğ", "g"), ("ç", "c"), ("ö", "o"), ("ü", "u")):
        value = value.replace(source, target)
    return "".join(c for c in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(c))


def is_travel(name: str) -> bool:
    folded = _fold(name)
    return any(term in folded for term in TRAVEL_TERMS)


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _actions(rows, allowed: set[str]) -> float:
    return sum(_number(item.get("value")) for item in (rows or [])
               if item.get("action_type") in allowed)


def _metrics(row: dict) -> dict:
    return {
        "spend": round(_number(row.get("spend")), 2),
        "impressions": int(_number(row.get("impressions"))),
        "clicks": int(_number(row.get("clicks"))),
        "reach": int(_number(row.get("reach"))),
        "purchases": int(_actions(row.get("actions"), PURCHASE_ACTIONS)),
        "revenue": round(_actions(row.get("action_values"), PURCHASE_ACTIONS), 2),
    }


def _sum_metrics(rows: list[dict]) -> dict:
    total = {k: 0 for k in ("spend", "impressions", "clicks", "reach", "purchases", "revenue")}
    for row in rows:
        for key in total:
            total[key] += row.get(key, 0) or 0
    total["spend"] = round(total["spend"], 2)
    total["revenue"] = round(total["revenue"], 2)
    total["ctr"] = round(total["clicks"] / total["impressions"] * 100, 2) if total["impressions"] else 0
    total["cpc"] = round(total["spend"] / total["clicks"], 2) if total["clicks"] else None
    total["cpa"] = round(total["spend"] / total["purchases"], 2) if total["purchases"] else None
    total["roas"] = round(total["revenue"] / total["spend"], 2) if total["spend"] and total["revenue"] else None
    return total


def _query(meta, since: str, until: str, *, breakdowns: str | None = None,
           time_increment: str | int | None = None) -> list[dict]:
    account = meta._acc(None)
    params = {
        "fields": "campaign_id,campaign_name,spend,impressions,clicks,reach,actions,action_values",
        "time_range": json.dumps({"since": since, "until": until}, separators=(",", ":")),
        "level": "campaign", "limit": 500,
    }
    if breakdowns:
        params["breakdowns"] = breakdowns
    if time_increment:
        params["time_increment"] = time_increment
    return meta._paged(f"{account}/insights", params)


def _segment(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not is_travel(row.get("campaign_name", "")):
            continue
        label = " · ".join(str(row.get(key) or "—").replace("_", " ").title() for key in keys)
        groups[label].append(_metrics(row))
    result = [{"label": label, **_sum_metrics(values)} for label, values in groups.items()]
    return sorted(result, key=lambda item: (item["purchases"], item["spend"]), reverse=True)


def build_ytd_report(today: date | None = None) -> dict:
    today = today or date.today()
    since, until = f"{today.year}-01-01", today.isoformat()
    base = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"since": since, "until": until, "label": f"{today.year} YTD"},
        "scope": "Səyahət sığortası",
        "crm": {"status": "upload_required", "note": "Real polis satışı CRM ixracından brauzerdə lokal hesablanır."},
        "ga4": {"status": "unavailable", "note": "GA4 hazırda demo rejimindədir; demo rəqəmlər daxil edilməyib."},
    }
    try:
        from connectors import meta

        campaign_rows = _query(meta, since, until)
        travel_rows = [row for row in campaign_rows if is_travel(row.get("campaign_name", ""))]
        campaigns = [{"campaign_id": row.get("campaign_id"),
                      "campaign_name": row.get("campaign_name") or "(adsız)",
                      **_sum_metrics([_metrics(row)])} for row in travel_rows]
        campaigns.sort(key=lambda row: row["spend"], reverse=True)
        trend_rows = _query(meta, since, until, time_increment="monthly")
        monthly: dict[str, list[dict]] = defaultdict(list)
        for row in trend_rows:
            if is_travel(row.get("campaign_name", "")):
                monthly[(row.get("date_start") or "")[:7]].append(_metrics(row))

        segments, segment_errors = {}, {}
        for name, breakdown, keys in (
            ("demographics", "age,gender", ("age", "gender")),
            ("regions", "region", ("region",)),
            ("placements", "publisher_platform,platform_position", ("publisher_platform", "platform_position")),
            ("devices", "impression_device", ("impression_device",)),
        ):
            try:
                segments[name] = _segment(_query(meta, since, until, breakdowns=breakdown), keys)
            except Exception as exc:
                segment_errors[name] = type(exc).__name__
                segments[name] = []

        base["meta"] = {
            "status": "live", "source": "Meta Marketing API",
            "campaigns_found": len(campaigns),
            "totals": _sum_metrics([_metrics(r) for r in travel_rows]),
            "campaigns": campaigns,
            "monthly": [{"month": month, **_sum_metrics(rows)} for month, rows in sorted(monthly.items())],
            "segments": segments, "segment_errors": segment_errors,
            "purchase_note": "Purchase və gəlir yalnız Meta tərəfindən bu kampaniyalara atribusiya edildikdə görünür; CRM polis sayı əsas satış mənbəyidir.",
        }
    except Exception as exc:
        msg = str(exc).lower()
        code = "token_invalid" if "code=190" in msg or "access token" in msg else "source_error"
        base["meta"] = {
            "status": "unavailable", "code": code, "error_type": type(exc).__name__,
            "note": "Meta sessiyası etibarsızdır; token yenilənənədək real reklam rəqəmi göstərilmir.",
            "totals": None, "campaigns": [], "monthly": [], "segments": {},
        }
    return base
