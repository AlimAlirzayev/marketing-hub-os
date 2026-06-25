"""Deterministic demo data engine for GA4 Studio.

Produces a fully-formed website-analytics report — the exact shape the live GA4
connector returns — so the dashboard, analytics and AI layers work end-to-end
with zero credentials. Numbers are seeded by the date range, so a given window
always renders identically (stable screenshots, stable trends).

Shaped like a real Azerbaijani insurance site: organic-search-led, mobile-heavy,
Baku-dominant, with KASKO / icbari / ipoteka pages and a quote→lead funnel.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import config

# Channel mix typical of an insurance brand with SEO + social + some paid.
_CHANNEL_MIX = [
    ("Organic Search", 0.42, 0.075),
    ("Direct", 0.21, 0.060),
    ("Organic Social", 0.14, 0.045),
    ("Paid Social", 0.10, 0.110),     # Meta ads — highest conversion intent
    ("Paid Search", 0.07, 0.130),     # Google Ads
    ("Referral", 0.045, 0.050),
    ("Email", 0.015, 0.090),
]

# Top pages: (path, title, view weight, engagement seconds, conversion-ish)
_PAGES = [
    ("/", "Ana səhifə", 0.26, 42, False),
    ("/kasko", "KASKO sığortası", 0.18, 98, True),
    ("/icbari-sigorta", "İcbari sığorta (OMTPL)", 0.13, 86, True),
    ("/ipoteka-sigortasi", "İpoteka sığortası", 0.09, 79, True),
    ("/qiymet-hesabla", "Qiymət hesabla", 0.08, 120, True),
    ("/saglamliq-sigortasi", "Sağlamlıq sığortası", 0.07, 74, True),
    ("/seyahet-sigortasi", "Səyahət sığortası", 0.06, 71, True),
    ("/elaqe", "Əlaqə", 0.05, 38, False),
    ("/haqqimizda", "Haqqımızda", 0.04, 33, False),
    ("/xeberler", "Xəbərlər", 0.04, 51, False),
]

_DEVICES = [("mobile", 0.68), ("desktop", 0.28), ("tablet", 0.04)]
_GEO = [("Baku", 0.71), ("Ganja", 0.07), ("Sumqayit", 0.06), ("Khirdalan", 0.035),
        ("Mingachevir", 0.025), ("(other)", 0.10)]
_EVENTS = [("page_view", 1.0), ("session_start", 0.46), ("scroll", 0.38),
           ("user_engagement", 0.55), ("qiymet_hesabla", 0.06),
           ("form_start", 0.045), ("generate_lead", 0.022),
           ("phone_click", 0.018), ("file_download", 0.009)]


def _seed(tag: str) -> random.Random:
    return random.Random(f"{tag}:ramin-ga4")


def _daily_sessions(d: date, rng: random.Random, base: float) -> int:
    # Weekday rhythm: quieter weekends, slight Mon/Tue peak for insurance research.
    wk = [1.08, 1.10, 1.05, 1.02, 0.98, 0.80, 0.78][d.weekday()]
    return max(1, int(base * wk * (1 + rng.uniform(-0.08, 0.08))))


def _period_totals(start: str, end: str) -> tuple[dict, list[dict]]:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days = (e - s).days + 1
    rng = _seed(start)
    # ~1,950 sessions/day baseline with a gentle trend by absolute date.
    drift = 1.0 + (s.toordinal() % 90) / 1500.0
    base = 1950 * drift

    trend, total_sessions = [], 0
    cur = s
    while cur <= e:
        ses = _daily_sessions(cur, rng, base)
        users = int(ses * 0.86)
        conv = int(ses * 0.041 * (1 + rng.uniform(-0.12, 0.12)))
        trend.append({"date": cur.isoformat(), "users": users,
                      "sessions": ses, "conversions": conv})
        total_sessions += ses
        cur += timedelta(days=1)

    sessions = total_sessions
    users = int(sessions * 0.86)
    new_users = int(users * 0.63)
    engaged = int(sessions * 0.611)
    conversions = sum(t["conversions"] for t in trend)
    views = int(sessions * 2.34)
    avg_eng = int(78 * (1 + rng.uniform(-0.05, 0.05)))
    totals = {
        "users": users, "new_users": new_users, "sessions": sessions,
        "engaged_sessions": engaged,
        "engagement_rate": round(engaged / sessions, 4),
        "bounce_rate": round(1 - engaged / sessions, 4),
        "avg_engagement_sec": avg_eng,
        "conversions": conversions,
        "conversion_rate": round(conversions / sessions, 4),
        "views": views,
        "views_per_session": round(views / sessions, 2),
        "event_count": int(views + sessions * 1.9),
    }
    return totals, trend


def _split(total: int, weights: list[float], rng: random.Random,
           noise: float = 0.06) -> list[int]:
    """Distribute ``total`` across ``weights`` with a little per-bucket noise."""
    raw = [w * (1 + rng.uniform(-noise, noise)) for w in weights]
    s = sum(raw) or 1
    return [int(total * r / s) for r in raw]


def get_report(start: str, end: str) -> dict:
    totals, trend = _period_totals(start, end)

    # Previous period (same length, immediately before) for deltas.
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days = (e - s).days + 1
    p_end = s - timedelta(days=1)
    p_start = p_end - timedelta(days=days - 1)
    prev_totals, _ = _period_totals(p_start.isoformat(), p_end.isoformat())

    rng = _seed(start + ":dim")
    ses = totals["sessions"]

    # Channels
    counts = _split(ses, [w for _, w, _cr in _CHANNEL_MIX], rng)
    channels = []
    for (name, _w, cr), c in zip(_CHANNEL_MIX, counts):
        conv = int(c * cr * (1 + rng.uniform(-0.1, 0.1)))
        channels.append({
            "channel": name, "channel_az": config.CHANNEL_AZ.get(name, name),
            "sessions": c, "users": int(c * 0.87), "conversions": conv,
            "conversion_rate": round(conv / c, 4) if c else 0,
            "share": round(c / ses, 4),
        })
    channels.sort(key=lambda x: x["sessions"], reverse=True)

    # Top pages
    pv = totals["views"]
    pcounts = _split(pv, [w for _p, _t, w, _e, _c in _PAGES], rng)
    top_pages = []
    for (path, title, _w, eng, conv_page), v in zip(_PAGES, pcounts):
        top_pages.append({
            "page": path, "title": title, "views": v,
            "users": int(v * 0.78),
            "avg_engagement_sec": int(eng * (1 + rng.uniform(-0.06, 0.06))),
            "is_conversion_page": conv_page,
        })
    top_pages.sort(key=lambda x: x["views"], reverse=True)

    devices = [{"device": d, "sessions": c, "share": round(c / ses, 4)}
               for (d, _w), c in zip(_DEVICES, _split(ses, [w for _d, w in _DEVICES], rng, 0.03))]
    geo = [{"city": c, "sessions": n}
           for (c, _w), n in zip(_GEO, _split(ses, [w for _c, w in _GEO], rng, 0.05))]

    ev_base = totals["event_count"]
    events = [{"event": name, "count": int(ev_base * w * (1 + rng.uniform(-0.05, 0.05)))}
              for name, w in _EVENTS]
    events.sort(key=lambda x: x["count"], reverse=True)

    return {
        "mode": "demo",
        "property": f"DEMO · {config.SITE_DOMAIN}",
        "range": {"start": start, "end": end, "days": days,
                  "label": config.range_label(start, end)},
        "totals": totals,
        "prev_totals": prev_totals,
        "trend": trend,
        "channels": channels,
        "top_pages": top_pages,
        "devices": devices,
        "geo": geo,
        "events": events,
    }
