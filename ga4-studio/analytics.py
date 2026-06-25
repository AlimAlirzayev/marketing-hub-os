"""Analytics layer for GA4 Studio.

Turns a raw report dict (from demo or live) into decision-ready signals:
period-over-period deltas, an engagement funnel, and honest rule-based insights
(no fabricated numbers — every insight points at a figure already in the report).
An optional Gemini narrative is generated on demand via ``ai_narrative``.
"""

from __future__ import annotations

import config


def pct_delta(cur: float, prev: float) -> float | None:
    if not prev:
        return None
    return round((cur - prev) / prev * 100, 1)


# Metrics where "up" is good vs. where "up" is bad (bounce rate).
_GOOD_UP = {"users", "new_users", "sessions", "engaged_sessions", "engagement_rate",
            "avg_engagement_sec", "conversions", "conversion_rate", "views"}


def deltas(report: dict) -> dict:
    cur, prev = report["totals"], report.get("prev_totals", {})
    out = {}
    for k, v in cur.items():
        d = pct_delta(v, prev.get(k))
        good = None
        if d is not None:
            good = (d >= 0) if k in _GOOD_UP else (d <= 0)
        out[k] = {"value": v, "prev": prev.get(k), "delta_pct": d, "good": good}
    return out


def funnel(report: dict) -> list[dict]:
    """Engagement funnel from the period totals: every site has these three."""
    t = report["totals"]
    sessions = t["sessions"] or 1
    steps = [
        ("Sessiyalar", t["sessions"], "Sayta gələn bütün ziyarətlər"),
        ("Cəlb olunmuş", t["engaged_sessions"], "10 san+ / 2 səhifə+ / konversiya"),
        ("Konversiyalar", t["conversions"], "Açar hadisə (lead, zəng, qiymət)"),
    ]
    out = []
    for i, (name, val, desc) in enumerate(steps):
        out.append({
            "step": name, "value": val, "desc": desc,
            "of_top": round(val / sessions * 100, 1),
            "drop_from_prev": (round((steps[i - 1][1] - val) / steps[i - 1][1] * 100, 1)
                               if i and steps[i - 1][1] else 0),
        })
    return out


def insights(report: dict, d: dict | None = None) -> list[dict]:
    """Rule-based, source-honest insights. Each ties to a number in the report."""
    d = d or deltas(report)
    t = report["totals"]
    out: list[dict] = []

    # 1) Traffic direction
    su = d["sessions"]["delta_pct"]
    if su is not None:
        tone = "good" if su >= 0 else "warn"
        out.append({"tone": tone, "icon": "📈" if su >= 0 else "📉",
                    "text": f"Sessiyalar əvvəlki dövrə görə {su:+.1f}% "
                            f"({t['sessions']:,} ziyarət)."})

    # 2) Conversion rate movement
    cr = d["conversion_rate"]["delta_pct"]
    if cr is not None:
        tone = "good" if cr >= 0 else "warn"
        out.append({"tone": tone, "icon": "🎯",
                    "text": f"Konversiya nisbəti {t['conversion_rate']*100:.2f}% "
                            f"({cr:+.1f}% dəyişib) — {t['conversions']:,} konversiya."})

    # 3) Leading channel
    if report["channels"]:
        top = report["channels"][0]
        out.append({"tone": "info", "icon": "🚦",
                    "text": f"Ən böyük kanal: {top['channel_az']} — "
                            f"trafikin {top['share']*100:.0f}%-i "
                            f"({top['conversion_rate']*100:.2f}% konversiya)."})
        # Best-converting channel (min 5% of sessions) — where to push budget.
        elig = [c for c in report["channels"] if c["share"] >= 0.05]
        if elig:
            best = max(elig, key=lambda c: c["conversion_rate"])
            if best["channel"] != top["channel"]:
                out.append({"tone": "good", "icon": "💡",
                            "text": f"Ən yüksək konversiyalı kanal: {best['channel_az']} "
                                    f"({best['conversion_rate']*100:.2f}%) — büdcəni bura "
                                    f"yönəltmək səmərəli ola bilər."})

    # 4) Leaking page: lots of views but low engagement, and not a known convert page
    pages = [p for p in report["top_pages"] if p["views"] >= t["views"] * 0.04]
    if pages:
        leak = min(pages, key=lambda p: p["avg_engagement_sec"])
        if leak["avg_engagement_sec"] < 30 and not leak.get("is_conversion_page"):
            out.append({"tone": "warn", "icon": "🕳️",
                        "text": f"“{leak['title']}” ({leak['page']}) çox baxılır, amma "
                                f"orta cəlb {leak['avg_engagement_sec']} san — sızdıra bilər."})

    # 5) Mobile reality check
    mob = next((x for x in report["devices"] if x["device"] == "mobile"), None)
    if mob and mob["share"] >= 0.55:
        out.append({"tone": "info", "icon": "📱",
                    "text": f"Trafikin {mob['share']*100:.0f}%-i mobil — mobil sürət/forma "
                            f"təcrübəsi prioritet olmalıdır."})
    return out


def enrich(report: dict) -> dict:
    d = deltas(report)
    report["deltas"] = d
    report["funnel"] = funnel(report)
    report["insights"] = insights(report, d)
    return report


# --------------------------------------------------------------------------
# Optional AI narrative (on demand) — reuses the free Gemini key. Never required;
# fails soft so the dashboard always works without it.
# --------------------------------------------------------------------------
def ai_narrative(report: dict) -> dict:
    if not config.GEMINI_API_KEY:
        return {"ok": False, "error": "Gemini açarı yoxdur (GEMINI_API_KEY)."}
    import json

    import requests
    t = report["totals"]
    facts = {
        "dövr": report["range"]["label"],
        "sessiyalar": t["sessions"], "istifadəçilər": t["users"],
        "konversiyalar": t["conversions"],
        "konversiya_nisbəti_%": round(t["conversion_rate"] * 100, 2),
        "cəlb_nisbəti_%": round(t["engagement_rate"] * 100, 1),
        "kanallar": [{"ad": c["channel_az"], "pay_%": round(c["share"] * 100, 1),
                      "konv_%": round(c["conversion_rate"] * 100, 2)}
                     for c in report["channels"][:6]],
        "ən_çox_baxılan": [{"səhifə": p["page"], "baxış": p["views"],
                            "cəlb_san": p["avg_engagement_sec"]}
                           for p in report["top_pages"][:6]],
        "dəyişmələr": {k: report["deltas"][k]["delta_pct"]
                       for k in ("sessions", "conversions", "conversion_rate")},
    }
    prompt = (
        "Sən Xalq Sigorta üçün rəqəmsal marketinq analitikisənsə. Aşağıdakı GA4 "
        "vebsayt datasına əsasən QISA, konkret Azərbaycanca icmal ver: 3 əsas "
        "müşahidə + 2 tövsiyə. Yalnız verilən rəqəmlərə istinad et, heç nə uydurma. "
        "Maddələrlə yaz.\n\nDATA:\n" + json.dumps(facts, ensure_ascii=False))
    import time
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{config.GEMINI_MODEL}:generateContent")
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    def _scrub(msg: str) -> str:
        # Never let the API key (it travels as a query param) reach a UI/log.
        return msg.replace(config.GEMINI_API_KEY, "<KEY>") if config.GEMINI_API_KEY else msg

    last = ""
    for attempt in range(3):
        try:
            r = requests.post(url, params={"key": config.GEMINI_API_KEY},
                              json=payload, timeout=40)
            if r.status_code in (429, 500, 503) and attempt < 2:
                last = f"{r.status_code} (model məşğuldur)"
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return {"ok": True, "text": text.strip(), "model": config.GEMINI_MODEL}
        except Exception as exc:
            last = _scrub(str(exc))
            if attempt < 2:
                time.sleep(1.0)
    return {"ok": False, "error": f"AI icmal alınmadı: {last}"}
