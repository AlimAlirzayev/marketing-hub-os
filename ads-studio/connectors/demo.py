"""Deterministic demo data engine.

Produces a fully-formed monthly report dict - the exact same shape the live Meta
+ Gmail connectors return - so the dashboard, analytics and AI layer can be built
and demoed end-to-end with zero credentials. Numbers are seeded per month, so a
given month always renders identically (stable screenshots, stable trends).

April 2026 is pinned to the reference figures the user shared, so the demo feels
familiar; other months are derived with realistic, internally-consistent drift
(CTR/CPM/frequency wander the way real accounts do).
"""

from __future__ import annotations

import calendar
import random
from datetime import date

from config import (
    ACCOUNT_NAME,
    CURRENCY,
    DEFAULT_ACCOUNT_ID,
    month_label,
    today,
)

# Reference month the user shared (internally consistent figures).
_REF = {
    "spend": 1984.52,
    "impressions": 820388,
    "clicks": 16878,
    "reach": 234330,
    "leads": 1514,
    "messages": 767,
}
# Stable per-funnel-step rates derived from the reference month.
_CTR = _REF["clicks"] / _REF["impressions"]            # ~0.0206
_FREQ = _REF["impressions"] / _REF["reach"]            # ~3.50
_LEAD_RATE = _REF["leads"] / _REF["clicks"]            # ~0.0897
_MSG_RATE = _REF["messages"] / _REF["leads"]           # ~0.5066

# Facebook vs Instagram split (Instagram leads this account).
_FB_SHARE = 0.40
_IG_SHARE = 0.60


def _seed(ym: str, salt: str = "") -> random.Random:
    return random.Random(f"{ym}:{salt}:ramin-ads")


def _months_from_ref(ym: str) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return (y - 2026) * 12 + (m - 4)


def _full_month_targets(ym: str) -> dict:
    """Full-month total targets for a month (what a complete month would reach)."""
    if ym == "2026-04":
        return dict(_REF)  # pin reference exactly

    rng = _seed(ym, "targets")
    # Gentle upward trend over time + per-metric noise => realistic drift.
    factor = 1.045 ** _months_from_ref(ym)

    def n(spread: float) -> float:
        return 1 + rng.uniform(-spread, spread)

    spend = _REF["spend"] * factor * n(0.10)
    impressions = _REF["impressions"] * factor * n(0.12)
    clicks = impressions * _CTR * n(0.10)
    reach = impressions / (_FREQ * n(0.06))
    leads = clicks * _LEAD_RATE * n(0.12)
    messages = leads * _MSG_RATE * n(0.10)
    return {
        "spend": round(spend, 2),
        "impressions": int(impressions),
        "clicks": int(clicks),
        "reach": int(reach),
        "leads": int(leads),
        "messages": int(messages),
    }


def _day_weights(ym: str) -> list[float]:
    """Per-day distribution weights for a whole month (weekends dip + noise)."""
    y, m = (int(x) for x in ym.split("-"))
    days = calendar.monthrange(y, m)[1]
    rng = _seed(ym, "daily")
    weights = []
    for d in range(1, days + 1):
        weekday = date(y, m, d).weekday()  # 0=Mon
        base = 0.82 if weekday >= 5 else 1.0
        weights.append(base * (1 + rng.uniform(-0.15, 0.15)))
    return weights


def _derive(t: dict) -> dict:
    """Add ratio metrics to a raw totals dict."""
    spend = t["spend"]
    impr = max(t["impressions"], 1)
    clicks = max(t["clicks"], 1)
    reach = max(t["reach"], 1)
    leads = max(t["leads"], 0)
    messages = max(t["messages"], 0)
    return {
        **t,
        "ctr": round(clicks / impr * 100, 2),
        "cpm": round(spend / impr * 1000, 2),
        "cpc": round(spend / clicks, 2),
        "frequency": round(impr / reach, 2),
        "cpl": round(spend / leads, 2) if leads else 0.0,
        "cost_per_message": round(spend / messages, 2) if messages else 0.0,
    }


def _split(value, share: float, integer: bool):
    out = value * share
    return int(round(out)) if integer else round(out, 2)


def _platform_totals(totals: dict, share: float, eff: float) -> dict:
    """Carve a platform slice out of the combined totals.

    ``eff`` nudges this platform's efficiency so the FB/IG filter is meaningful
    (e.g. Instagram converts a touch better here).
    """
    raw = {
        "spend": _split(totals["spend"], share, False),
        "impressions": _split(totals["impressions"], share, True),
        "clicks": _split(totals["clicks"], share, True),
        "reach": _split(totals["reach"], share, True),
        "leads": _split(totals["leads"], share * eff, True),
        "messages": _split(totals["messages"], share * eff, True),
    }
    return _derive(raw)


def _daily_series(ym: str, targets: dict, days_to_emit: int) -> list[dict]:
    weights = _day_weights(ym)
    total_w = sum(weights)
    y, m = (int(x) for x in ym.split("-"))
    series = []
    for i in range(days_to_emit):
        w = weights[i] / total_w
        series.append({
            "date": date(y, m, i + 1).isoformat(),
            "spend": round(targets["spend"] * w, 2),
            "impressions": int(round(targets["impressions"] * w)),
            "clicks": int(round(targets["clicks"] * w)),
            "reach": int(round(targets["reach"] * w)),
            "leads": int(round(targets["leads"] * w)),
            "messages": int(round(targets["messages"] * w)),
        })
    return series


def _sum_daily(series: list[dict]) -> dict:
    keys = ("spend", "impressions", "clicks", "reach", "leads", "messages")
    out = {k: 0 for k in keys}
    for row in series:
        for k in keys:
            out[k] += row[k]
    out["spend"] = round(out["spend"], 2)
    return out


def _invoices(ym: str, spend: float, days_to_emit: int) -> dict:
    """Synthesize Gmail->Meta payment receipts that track spend in $100 charges.

    Mirrors how Meta bills: a stream of fixed-threshold charges, with the tail of
    current spend not yet invoiced (the reconciliation gap finance cares about).
    """
    rng = _seed(ym, "invoices")
    y, m = (int(x) for x in ym.split("-"))
    n_full = int(spend // 100)
    rows = []
    for k in range(n_full):
        day = min(days_to_emit, max(1, int((k + 1) / max(n_full, 1) * days_to_emit)))
        ref = "".join(rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(11))
        rows.append({
            "date": date(y, m, day).isoformat(),
            "amount": 100.00,
            "ref": ref,
            "detail": f"Visa ****{rng.randint(1000, 9999)} · Meta Platforms · Ref {ref}",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    invoiced = round(sum(r["amount"] for r in rows), 2)
    return {
        "rows": rows,
        "count": len(rows),
        "total": invoiced,
        "unbilled": round(spend - invoiced, 2),  # spend not yet on a receipt
    }


def _sales(ym: str) -> dict:
    """Placeholder sales mix (CRM intentionally deferred - flagged as demo).

    Kept so the Sales tab renders a complete picture; wire a real CRM later.
    """
    rng = _seed(ym, "sales")
    total = rng.randint(18, 30)
    mix = [
        ("Instagram", 0.45),
        ("Facebook", 0.23),
        ("Instagram Inbox", 0.18),
        ("Vebsayt", 0.14),
    ]
    by_channel, running = [], 0
    for i, (name, share) in enumerate(mix):
        count = total - running if i == len(mix) - 1 else int(round(total * share))
        running += count
        by_channel.append({"channel": name, "count": count,
                            "pct": round(count / total * 100)})
    return {"total": total, "by_channel": by_channel, "is_demo": True}


def build_report(ym: str, platform: str = "all", account_id: str | None = None) -> dict:
    """Build the full monthly report dict for ``ym`` (e.g. '2026-04')."""
    acc = account_id or DEFAULT_ACCOUNT_ID
    y, m = (int(x) for x in ym.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]
    now = today()
    is_current = (y == now.year and m == now.month)
    days_elapsed = now.day if is_current else days_in_month

    targets = _full_month_targets(ym)
    series = _daily_series(ym, targets, days_elapsed)
    totals = _derive(_sum_daily(series))

    by_platform = {
        "facebook": _platform_totals(totals, _FB_SHARE, 0.92),
        "instagram": _platform_totals(totals, _IG_SHARE, 1.05),
    }
    if platform in ("facebook", "instagram"):
        shown, daily_share = by_platform[platform], (
            _FB_SHARE if platform == "facebook" else _IG_SHARE)
        series = [{**r,
                   "spend": round(r["spend"] * daily_share, 2),
                   "impressions": int(r["impressions"] * daily_share),
                   "clicks": int(r["clicks"] * daily_share),
                   "leads": int(r["leads"] * daily_share),
                   "messages": int(r["messages"] * daily_share),
                   "reach": int(r["reach"] * daily_share)} for r in series]
    else:
        shown = totals

    invoices = _invoices(ym, totals["spend"], days_elapsed)

    return {
        "account": {
            "id": acc,
            "name": ACCOUNT_NAME,
            "currency": CURRENCY,
            "ad_account_id": acc,
            "source": "demo",
        },
        "period": {
            "month": ym,
            "label": month_label(ym),
            "start": date(y, m, 1).isoformat(),
            "end": date(y, m, days_in_month).isoformat(),
            "days_total": days_in_month,
            "days_elapsed": days_elapsed,
            "is_current": is_current,
        },
        "platform": platform,
        "totals": shown,
        "combined_totals": totals,
        "full_month_targets": _derive(targets),
        "by_platform": by_platform,
        "daily": series,
        "invoices": invoices,
        "sales": _sales(ym),
    }


# ============================================================================
# Demo segment generators (mirror the live meta.py output shape)
# ============================================================================
def _split_metrics(totals: dict, share: float, eff: float = 1.0) -> dict:
    raw = {
        "spend": round(totals["spend"] * share, 2),
        "impressions": int(totals["impressions"] * share),
        "clicks": int(totals["clicks"] * share),
        "reach": int(totals["reach"] * share),
        "leads": int(totals["leads"] * share * eff),
        "messages": int(totals["messages"] * share * eff),
    }
    return _derive(raw)


def segments(ym: str, account_id: str | None = None) -> dict:
    """Synthetic segment breakdowns, plausible for an insurance/messaging account."""
    r = build_report(ym, "all", account_id)
    t = r["combined_totals"]
    rng = _seed(ym, "segments")

    def split(mix):
        return [{"key": k, **_split_metrics(t, share * rng.uniform(0.92, 1.08), eff)}
                for k, share, eff in mix]

    out = {
        "publisher_platform": split([
            ("instagram", 0.60, 1.05), ("facebook", 0.35, 0.95),
            ("messenger", 0.04, 1.0), ("audience_network", 0.01, 0.7),
        ]),
        # Combined publisher+position breakdown (mirrors the real Meta combined call)
        "placement": split([
            ("Instagram · Feed", 0.28, 1.0),
            ("Instagram · Stories", 0.20, 1.05),
            ("Instagram · Reels", 0.24, 1.10),
            ("Facebook · Feed", 0.14, 0.95),
            ("Facebook · Stories", 0.05, 0.90),
            ("Facebook · Reels", 0.04, 0.92),
            ("Messenger · Stories", 0.03, 0.95),
            ("Search", 0.02, 0.80),
        ]),
        "impression_device": split([
            ("android_smartphone", 0.62, 1.0), ("iphone", 0.34, 1.05),
            ("desktop", 0.03, 0.7), ("ipad", 0.01, 0.9),
        ]),
        "age": split([
            ("18-24", 0.16, 0.85), ("25-34", 0.35, 1.1), ("35-44", 0.25, 1.05),
            ("45-54", 0.15, 1.0), ("55-64", 0.07, 0.85), ("65+", 0.02, 0.7),
        ]),
        "gender": split([
            ("female", 0.55, 1.05), ("male", 0.43, 0.95), ("unknown", 0.02, 0.8),
        ]),
        "region": split([
            ("Baku", 0.62, 1.0), ("Sumqayit", 0.10, 0.95),
            ("Ganja", 0.08, 0.92), ("Lankaran", 0.05, 0.9),
            ("Mingachevir", 0.04, 0.9), ("Other", 0.11, 0.85),
        ]),
    }

    # Combined age × gender (mirror of the live combined Meta breakdown)
    ages = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    age_shares = [0.16, 0.35, 0.25, 0.15, 0.07, 0.02]
    gender_mix = [("female", 0.55, 1.05), ("male", 0.43, 0.95), ("unknown", 0.02, 0.6)]
    ag = []
    for a, ash in zip(ages, age_shares):
        for g, gsh, eff in gender_mix:
            ag.append({"age": a, "gender": g,
                       **_split_metrics(t, ash * gsh * rng.uniform(0.85, 1.15), eff)})
    out["age_gender"] = ag

    # Hourly: heavier 18:00–22:00, lighter early morning.
    weights = []
    for h in range(24):
        if 0 <= h < 6:
            w = 0.25
        elif 6 <= h < 9:
            w = 0.6
        elif 9 <= h < 17:
            w = 0.9
        elif 17 <= h < 23:
            w = 1.6
        else:
            w = 0.7
        weights.append(w * rng.uniform(0.88, 1.12))
    total_w = sum(weights)
    hourly = []
    for h in range(24):
        share = weights[h] / total_w
        hourly.append({
            "hour": h,
            "spend": round(t["spend"] * share, 2),
            "impressions": int(t["impressions"] * share),
            "clicks": int(t["clicks"] * share),
            "leads": int(t["leads"] * share),
            "messages": int(t["messages"] * share),
        })
    out["hourly"] = hourly
    return out


def top_campaigns(ym: str, account_id: str | None = None, limit: int = 10) -> list[dict]:
    r = build_report(ym, "all", account_id)
    t = r["combined_totals"]
    rng = _seed(ym, "campaigns")
    names = [
        ("KASKO Bayram Push", 0.32),
        ("Səyahət sığortası — Gürcüstan", 0.22),
        ("İcbari sığorta retargeting", 0.16),
        ("Avto KASKO — broad", 0.12),
        ("İpoteka sığortası awareness", 0.09),
        ("Sağlamlıq sığortası lead-gen", 0.06),
        ("Brand always-on", 0.03),
    ]
    out = []
    for i, (name, share) in enumerate(names):
        s = share * rng.uniform(0.88, 1.12)
        m = _split_metrics(t, s)
        out.append({"campaign_id": f"demo_{i}", "campaign_name": name, **m})
    out.sort(key=lambda r: r["spend"], reverse=True)
    return out[:limit]


_RANKS = ["ABOVE_AVERAGE", "AVERAGE", "BELOW_AVERAGE_35",
          "BELOW_AVERAGE_20", "BELOW_AVERAGE_10"]


def creative_diagnostics(ym: str, account_id: str | None = None,
                          limit: int = 10) -> list[dict]:
    r = build_report(ym, "all", account_id)
    t = r["combined_totals"]
    rng = _seed(ym, "creatives")
    creatives = [
        "KASKO_video_15s_v3", "KASKO_carousel_5cards", "KASKO_static_red",
        "Travel_reel_30s", "Travel_static_mountain", "Retarget_dynamic_v2",
        "Awareness_brand_film_30s",
    ]
    out = []
    for i, name in enumerate(creatives[:limit]):
        share = rng.uniform(0.05, 0.20)
        m = _split_metrics(t, share)
        out.append({
            "ad_id": f"demo_ad_{i}",
            "ad_name": name,
            "quality_ranking": rng.choice(_RANKS[:3]),
            "engagement_rate_ranking": rng.choice(_RANKS[:3]),
            "conversion_rate_ranking": rng.choice(_RANKS),
            **m,
        })
    return out


def video_metrics(ym: str, account_id: str | None = None) -> dict:
    r = build_report(ym, "all", account_id)
    t = r["combined_totals"]
    rng = _seed(ym, "video")
    impr = t["impressions"]
    v3 = int(impr * rng.uniform(0.18, 0.32))      # hook 18-32%
    thru = int(v3 * rng.uniform(0.12, 0.28))       # hold 12-28%
    plays = int(impr * rng.uniform(0.40, 0.55))
    return {
        "has_video": True,
        "impressions": impr,
        "plays": plays,
        "three_sec_views": v3,
        "thruplays": thru,
        "avg_watch_seconds": round(rng.uniform(3.2, 7.5), 1),
        "hook_rate": round(v3 / impr * 100, 2),
        "hold_rate": round(thru / v3 * 100, 2),
    }
