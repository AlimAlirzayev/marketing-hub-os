"""Impact Ledger — the monthly "what the OS did for Xalq" scorecard.

Pillar 2/3 of the 2026-07-20 roadmap ([[project_autonomy_money_roadmap]]): turn a
month of the system's work into the operator's indispensability argument. Operator
2026-07-21 choice = the BLENDED scorecard: business RESULTS (leads, CPA,
conversions, complaint SLA — live from the ads/ga4/cx studios) beside system WORK
(deliverables produced, requests answered, hours saved) on one page — "one person
does a whole team's work".

Two hard rules, both from existing house law:
  * No fabricated data (feedback_no_fabricated_data): every RESULTS figure carries
    a source label — CANLI (live), DEMO (studio in demo mode), or ƏLÇATMAZ (source
    down). A missing source is SAID, never invented.
  * The WORK side is computed from the OS's OWN durable job queue
    (gateway.queue.done_between) — real counts. Hours-saved is an explicitly
    labelled ESTIMATE (category × documented per-item minutes), never a hard claim.

Pure compute (activity_from_tasks / compute_scorecard) is separated from IO
(collect / report), so scoring is unit-testable offline — the ads_watch.analyze
pattern. Free: pure arithmetic + local HTTP reads, zero LLM tokens.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# --- work side: classify a finished job into a deliverable category ------------
# Per-category minutes = a conservative, documented estimate of the human time one
# such deliverable would take by hand. Tunable, but kept modest on purpose — the
# argument must survive scrutiny, so under-claim rather than over-claim.
_CATEGORY_MIN = {
    "content": 30,   # a brand post / creative / caption / clip
    "report": 40,    # a briefing / analysis / scorecard
    "research": 45,  # a radar / swipe / competitor scan
    "seo": 60,       # an audit / keyword+content pass
    "campaign": 50,  # a campaign / strategy / budget plan
    "other": 15,
}
_CATEGORY_AZ = {
    "content": "Kontent/kreativ", "report": "Hesabat/analiz",
    "research": "Araşdırma/radar", "seo": "SEO",
    "campaign": "Kampaniya/strategiya", "other": "Digər",
}
# Checked in priority order; first category with a keyword hit wins.
_CATEGORY_KEYWORDS = [
    ("seo", ("seo", "audit", "açar söz", "acar soz", "keyword")),
    ("campaign", ("kampaniya", "strategiya", "büdcə", "budce", "büdce")),
    ("research", ("radar", "swipe", "research", "araşdır", "arasdir", "scout",
                  "rəqib", "reqib", "trend", "kəşfiyyat", "kesfiyyat")),
    ("report", ("hesabat", "brifinq", "briefing", "analiz", "pulse", "nəbz",
                "nebz", "scorecard", "advisor", "təsir")),
    ("content", ("post", "kreativ", "idea", "sound", "clip", "video", "media",
                 "şəkil", "sekil", "kontent", "story", "reels", "copy", "mətn")),
]


def classify_task(task: str) -> str:
    t = (task or "").lower()
    for cat, keys in _CATEGORY_KEYWORDS:
        if any(k in t for k in keys):
            return cat
    return "other"


def activity_from_tasks(tasks: list[str]) -> dict:
    """Pure: turn finished-job task strings into the WORK block. Real counts +
    a labelled hours-saved estimate. Never raises on odd input."""
    by_cat = {c: 0 for c in _CATEGORY_MIN}
    for t in tasks or []:
        by_cat[classify_task(t)] += 1
    minutes = sum(by_cat[c] * _CATEGORY_MIN[c] for c in by_cat)
    return {
        "deliverables": sum(by_cat.values()),
        "requests_answered": len(tasks or []),
        "by_category": by_cat,
        "hours_saved_est": round(minutes / 60.0, 1),
    }


# --- results side --------------------------------------------------------------
def _source_label(data: dict | None) -> str:
    if data is None:
        return "ƏLÇATMAZ"
    mode = str(data.get("mode", "")).lower()
    return "DEMO" if mode == "demo" else "CANLI"


def _delta_pct(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100.0, 1)


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_scorecard(*, month: str, ads: dict | None, ads_prev: dict | None,
                      ga4: dict | None, cx: dict | None, activity: dict) -> dict:
    """Pure: assemble the blended scorecard from already-fetched raw inputs.

    ads / ads_prev: {mode, totals:{spend, leads, messages}} (ads-studio /api/report).
    ga4:            {mode, ...} — conversions/sessions pulled defensively.
    cx:             {mode, totals:{messages, resolution_rate}} (cx analytics).
    activity:       output of activity_from_tasks (the WORK block).
    """
    results: dict = {}

    # Leads = total inbound contacts (form leads + messaging), the number Xalq
    # marketing is judged on. CPA = ad spend per contact (lower is better).
    def _contacts(a: dict | None) -> float | None:
        if not a:
            return None
        t = a.get("totals") or {}
        lead, msg = _num(t.get("leads")), _num(t.get("messages"))
        if lead is None and msg is None:
            return None
        return (lead or 0) + (msg or 0)

    leads = _contacts(ads)
    leads_prev = _contacts(ads_prev)
    spend = _num((ads or {}).get("totals", {}).get("spend")) if ads else None
    spend_prev = _num((ads_prev or {}).get("totals", {}).get("spend")) if ads_prev else None
    cpa = (spend / leads) if (spend is not None and leads) else None
    cpa_prev = (spend_prev / leads_prev) if (spend_prev is not None and leads_prev) else None

    results["leads"] = {"value": None if leads is None else int(leads),
                        "prev": None if leads_prev is None else int(leads_prev),
                        "delta_pct": _delta_pct(leads, leads_prev),
                        "source": _source_label(ads)}
    results["cpa"] = {"value": None if cpa is None else round(cpa, 2),
                      "prev": None if cpa_prev is None else round(cpa_prev, 2),
                      "delta_pct": _delta_pct(cpa, cpa_prev),  # negative = improved
                      "lower_is_better": True, "source": _source_label(ads)}

    # GA4 conversions — pulled defensively (enrich() shape varies); ƏLÇATMAZ if absent.
    conv = None
    if ga4:
        totals = ga4.get("totals") or ga4
        for key in ("conversions", "conversion", "key_events", "conversions_total"):
            if totals.get(key) is not None:
                conv = _num(totals.get(key))
                break
    results["conversions"] = {"value": None if conv is None else int(conv),
                              "source": _source_label(ga4) if conv is not None else "ƏLÇATMAZ"}

    # CX — complaint signals handled + resolution rate (SLA proxy).
    cx_t = (cx or {}).get("totals") or {}
    sla = _num(cx_t.get("resolution_rate"))
    signals = _num(cx_t.get("messages"))
    results["sla"] = {"value": None if sla is None else round(sla, 1),
                      "signals": None if signals is None else int(signals),
                      "source": _source_label(cx)}

    live = [k for k, v in {"ads": ads, "ga4": ga4, "cx": cx}.items() if v is not None]
    return {
        "month": month,
        "results": results,
        "work": activity,
        "sources": {"ads": _source_label(ads), "ga4": _source_label(ga4),
                    "cx": _source_label(cx)},
        "live_sources": live,
        "headline": _headline(results, activity),
    }


def _headline(results: dict, activity: dict) -> str:
    """One-sentence indispensability line, grounded only in what we actually have."""
    bits = []
    lead = results.get("leads", {})
    if lead.get("value") is not None:
        d = lead.get("delta_pct")
        arrow = "" if d is None else (f" (↑{d:.0f}%)" if d > 0 else f" (↓{abs(d):.0f}%)")
        bits.append(f"{lead['value']} müraciət{arrow}")
    cpa = results.get("cpa", {})
    if cpa.get("value") is not None and cpa.get("delta_pct") is not None and cpa["delta_pct"] < 0:
        bits.append(f"CPA ↓{abs(cpa['delta_pct']):.0f}%")
    dl = activity.get("deliverables", 0)
    hs = activity.get("hours_saved_est", 0)
    if dl:
        bits.append(f"{dl} iş · ~{hs:g} saat qənaət")
    if not bits:
        return "Bu ay üçün canlı ölçü hələ toplanmayıb — mənbələri qoş, jurnal özü dolacaq."
    return " · ".join(bits) + " — bir adam, bir komandanın işi."


# --- IO: fetch live, assemble, format -----------------------------------------
_ADS = os.getenv("ADS_STUDIO_URL", "http://127.0.0.1:8800")
_GA4 = os.getenv("GA4_STUDIO_URL", "http://127.0.0.1:8850")
_CX = os.getenv("CX_URL", "http://127.0.0.1:8810")


def _get_json(url: str, params: dict | None = None):
    try:
        import requests
        r = requests.get(url, params=params or {}, timeout=60)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _prev_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _month_bounds(month: str) -> tuple[float, float]:
    y, m = (int(x) for x in month.split("-"))
    start = _dt.datetime(y, m, 1)
    last = calendar.monthrange(y, m)[1]
    end = _dt.datetime(y, m, last, 23, 59, 59) + _dt.timedelta(seconds=1)
    return start.timestamp(), end.timestamp()


def _fetch_ads(month: str) -> dict | None:
    rep = _get_json(f"{_ADS}/api/report", {"month": month})
    if not rep:
        return None
    r = rep.get("report") or rep
    return {"mode": rep.get("mode") or r.get("mode"), "totals": r.get("totals") or {}}


def _collect_activity(month: str) -> dict:
    try:
        from . import queue
        start, end = _month_bounds(month)
        tasks = [j.task for j in queue.done_between(start, end)]
        return activity_from_tasks(tasks)
    except Exception:
        return activity_from_tasks([])


def collect(month: str) -> dict:
    """Fetch every raw input for the scorecard. Best-effort — a down source comes
    back None and is labelled ƏLÇATMAZ, never invented."""
    ads = _fetch_ads(month)
    ads_prev = _fetch_ads(_prev_month(month))
    ga4 = _get_json(f"{_GA4}/api/report", {"days": 30})
    cx = _get_json(f"{_CX}/api/analytics", {"days": 30})
    activity = _collect_activity(month)
    return compute_scorecard(month=month, ads=ads, ads_prev=ads_prev,
                             ga4=ga4, cx=cx, activity=activity)


def _fmt_delta(d: float | None, *, lower_better: bool = False) -> str:
    if d is None:
        return ""
    good = (d < 0) if lower_better else (d > 0)
    arrow = "↓" if d < 0 else "↑"
    mark = "✅" if good else "⚠️"
    return f"  ({arrow}{abs(d):.0f}% {mark})"


def report(month: str | None = None) -> str:
    """The blended scorecard as operator-facing Azerbaijani text."""
    month = month or _dt.date.today().strftime("%Y-%m")
    sc = collect(month)
    r, w = sc["results"], sc["work"]
    lines = [f"📇 XALQ TƏSİR JURNALI — {month}", "=" * 34, "", "NƏTİCƏ (biznes):"]

    lead = r["leads"]
    if lead["value"] is not None:
        lines.append(f"  • Müraciət (lead+mesaj): {lead['value']}"
                     f"{_fmt_delta(lead['delta_pct'])}  [{lead['source']}]")
    else:
        lines.append(f"  • Müraciət: ölçü yoxdur  [{lead['source']}]")
    cpa = r["cpa"]
    if cpa["value"] is not None:
        lines.append(f"  • Reklam CPA: {cpa['value']} "
                     f"{_fmt_delta(cpa['delta_pct'], lower_better=True)}  [{cpa['source']}]")
    conv = r["conversions"]
    if conv["value"] is not None:
        lines.append(f"  • Konversiya (GA4): {conv['value']}  [{conv['source']}]")
    else:
        lines.append(f"  • Konversiya (GA4): ölçü yoxdur  [{conv['source']}]")
    sla = r["sla"]
    if sla["value"] is not None:
        extra = f" · {sla['signals']} siqnal" if sla.get("signals") is not None else ""
        lines.append(f"  • Şikayət həlli: {sla['value']}%{extra}  [{sla['source']}]")

    lines += ["", "İŞ (sistem nə etdi):",
              f"  • Deliverable: {w['deliverables']} · cavablanan iş: {w['requests_answered']}"]
    cats = [f"{_CATEGORY_AZ[c]} {n}" for c, n in w["by_category"].items() if n]
    if cats:
        lines.append("  • Bölgü: " + " · ".join(cats))
    lines.append(f"  • Qənaət (təxmini): ~{w['hours_saved_est']:g} saat")

    lines += ["", "─" * 34, "BİR CÜMLƏ: " + sc["headline"]]
    if "DEMO" in sc["sources"].values() or "ƏLÇATMAZ" in sc["sources"].values():
        lines.append("")
        lines.append("ⓘ Bəzi mənbələr DEMO/ƏLÇATMAZ — canlı konnektor qoşulanda rəqəmlər "
                     "avtomatik doğrulanır. Rəqəm uydurulmur.")
    return "\n".join(lines)


# --- monthly autonomy: deliver last month's ledger once, on its own -----------
# The scheduler speaks daily HH:MM only, so a MONTHLY report self-gates (the
# radar/signal_radar pattern): a supervisor thread calls run_if_due() on a slow
# tick; the first call on/after DELIVER_DAY of a new month emits the PREVIOUS
# month's ledger exactly once, then records it. State is machine-local.
_STATE = _ROOT / "data" / "impact_ledger_state.json"   # git-ignored
_DELIVER_DAY = int(os.getenv("IMPACT_LEDGER_DELIVER_DAY", "1"))


def _prev_month_of(d: _dt.date) -> str:
    return (d.replace(day=1) - _dt.timedelta(days=1)).strftime("%Y-%m")


def monthly_due(today: _dt.date, last_reported: str | None,
                deliver_day: int = 1) -> str | None:
    """Pure: the month to report if a monthly delivery is due, else None. On/after
    deliver_day, the PREVIOUS month is due once (last_reported guards the repeat;
    a never-reported prior month is caught up on first run)."""
    if today.day < deliver_day:
        return None
    target = _prev_month_of(today)
    return None if last_reported == target else target


def _load_state() -> dict:
    try:
        import json
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        import json
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def run_if_due(now: _dt.datetime | None = None) -> dict:
    """Deliver the previous month's ledger once when a new month has turned.
    Returns {"skipped": True} when not due, else {"skipped": False, "month",
    "text"}. Never raises — it rides the always-on supervisor."""
    try:
        now = now or _dt.datetime.now()
        state = _load_state()
        target = monthly_due(now.date(), state.get("last_month"), _DELIVER_DAY)
        if not target:
            return {"skipped": True}
        text = report(target)
        state["last_month"] = target
        _save_state(state)
        return {"skipped": False, "month": target, "text": text}
    except Exception as exc:  # noqa: BLE001
        print(f"[impact_ledger] run_if_due error: {exc}")
        return {"skipped": True}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    arg_month = sys.argv[1] if len(sys.argv) > 1 else None
    print(report(arg_month))
