"""Ads morning pulse — the proactive Meta Ads rail.

Every morning the scheduler enqueues "reklam nəbzi"; this rail pulls the live
sales block from Ads Studio (127.0.0.1:8800 /api/briefing — the same in-house
seam the panel uses), compares YESTERDAY against the trailing week, and delivers
a compact Azerbaijani digest with explicit anomaly flags:

  * delivery stop  — yesterday spent ~nothing while the week was live
  * spend spike    — yesterday >= 2x the trailing average
  * CPR spike      — cost per result (leads+messages) >= 2x the trailing average
  * CTR collapse   — yesterday CTR < half the trailing average

Deterministic on purpose: pure arithmetic over numbers Ads Studio already
aggregated — zero LLM tokens, nothing to hallucinate, and the thresholds are
tunable via env. The schedule row is created with source='telegram' +
the owner chat id, so the worker delivers it like any operator-visible job.
Analysis is a pure function (``analyze``) so it is unit-testable offline.
"""

from __future__ import annotations

import datetime as _dt
import os

import requests

_ADS_STUDIO = os.getenv("ADS_STUDIO_URL", "http://127.0.0.1:8800")
# Thresholds: ratio vs the trailing baseline that counts as an anomaly.
_SPIKE_X = float(os.getenv("ADS_WATCH_SPIKE_X", "2.0"))
_COLLAPSE_X = float(os.getenv("ADS_WATCH_COLLAPSE_X", "0.5"))
# Volume floors below which ratios are noise, not signal.
_MIN_BASE_SPEND = 1.0     # USD/day average before "stopped/spiked" means anything
_MIN_BASE_RESULTS = 3     # trailing results before a CPR ratio is trusted
_MIN_IMPRESSIONS = 1000   # impressions on both sides before a CTR ratio is trusted


def _f(row: dict, key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def analyze(daily: list[dict], today: str | None = None) -> dict:
    """Compare the last COMPLETE day against the trailing week before it.

    daily: [{date, spend, impressions, clicks, leads, messages}, ...] ascending.
    today: ISO date treated as "now" (today's partial row is excluded).
    Returns {yesterday, baseline, anomalies:[{kind, text}], enough_history}.
    """
    today = today or _dt.date.today().isoformat()
    complete = [r for r in daily if (r.get("date") or "") < today]
    if not complete:
        return {"yesterday": None, "baseline": {}, "anomalies": [], "enough_history": False}
    complete.sort(key=lambda r: r.get("date") or "")
    y = complete[-1]
    base_rows = complete[-8:-1]  # up to 7 days before yesterday
    enough = len(base_rows) >= 3

    y_spend, b_spend = _f(y, "spend"), _avg([_f(r, "spend") for r in base_rows])
    y_res = _f(y, "leads") + _f(y, "messages")
    b_res = _avg([_f(r, "leads") + _f(r, "messages") for r in base_rows])
    y_imp, b_imp = _f(y, "impressions"), _avg([_f(r, "impressions") for r in base_rows])
    y_ctr = (_f(y, "clicks") / y_imp * 100) if y_imp else 0.0
    b_ctrs = [(_f(r, "clicks") / _f(r, "impressions") * 100)
              for r in base_rows if _f(r, "impressions")]
    b_ctr = _avg(b_ctrs)

    anomalies: list[dict] = []
    if enough and b_spend >= _MIN_BASE_SPEND:
        if y_spend < 0.1:
            anomalies.append({"kind": "delivery_stop", "text": (
                f"Çatdırılma DAYANIB: dünən xərc $0.00, halbuki 7 günlük orta "
                f"${b_spend:.2f} idi — kampaniyalar yoxlanmalıdır.")})
        elif y_spend >= _SPIKE_X * b_spend:
            anomalies.append({"kind": "spend_spike", "text": (
                f"Xərc sıçrayışı: dünən ${y_spend:.2f} — 7 günlük ortadan "
                f"({b_spend:.2f}) {y_spend / b_spend:.1f}× çox.")})
    if enough and b_res >= _MIN_BASE_RESULTS and y_spend >= 2.0:
        b_cpr = (b_spend / b_res) if b_res else 0.0
        y_cpr = (y_spend / y_res) if y_res else float("inf")
        if b_cpr and y_cpr >= _SPIKE_X * b_cpr:
            shown = "∞ (nəticə yoxdur)" if y_cpr == float("inf") else f"${y_cpr:.2f}"
            anomalies.append({"kind": "cpr_spike", "text": (
                f"CPA sıçrayışı: dünən nəticə başına {shown} — 7 günlük orta "
                f"${b_cpr:.2f} idi.")})
    if enough and y_imp >= _MIN_IMPRESSIONS and b_imp >= _MIN_IMPRESSIONS and b_ctr:
        if y_ctr <= _COLLAPSE_X * b_ctr:
            anomalies.append({"kind": "ctr_collapse", "text": (
                f"CTR çöküşü: dünən {y_ctr:.2f}% — 7 günlük orta {b_ctr:.2f}% "
                f"idi (kreativ yorğunluğu ehtimalı).")})

    return {
        "yesterday": {"date": y.get("date"), "spend": y_spend, "results": y_res,
                      "ctr": y_ctr, "impressions": y_imp, "clicks": _f(y, "clicks")},
        "baseline": {"spend": b_spend, "results": b_res, "ctr": b_ctr,
                     "days": len(base_rows)},
        "anomalies": anomalies,
        "enough_history": enough,
    }


def _fetch_sales(refresh: bool = True) -> dict | None:
    try:
        r = requests.get(f"{_ADS_STUDIO}/api/briefing",
                         params={"refresh": 1} if refresh else {}, timeout=180)
        if r.status_code != 200:
            return None
        sales = (r.json() or {}).get("sales") or {}
        return sales if sales.get("status") == "live" else None
    except Exception:
        return None


def _az_date(iso: str | None) -> str:
    try:
        return _dt.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return iso or "?"


def report(refresh: bool = True) -> str:
    """Build the morning digest (Azerbaijani, operator-facing)."""
    sales = _fetch_sales(refresh=refresh)
    if not sales:
        return ("📊 Reklam səhər nəbzi\n\n⚠️ Meta Ads mənbəyi hazırda əlçatan "
                "deyil (Ads Studio 8800 cavab vermir və ya canlı data yoxdur). "
                "Rəqəm uydurmuram — sonra yenidən yoxlayacam.")
    a = analyze(sales.get("daily") or [])
    t = sales.get("totals") or {}
    cur = sales.get("currency") or "USD"
    lines = ["📊 Reklam səhər nəbzi — " + _az_date((a["yesterday"] or {}).get("date"))]
    y = a["yesterday"]
    if y:
        lines.append(
            f"Dünən: {y['spend']:.2f} {cur} xərc · {int(y['clicks'])} klik · "
            f"CTR {y['ctr']:.2f}% · {int(y['results'])} nəticə")
        b = a["baseline"]
        if a["enough_history"]:
            lines.append(
                f"7g orta: {b['spend']:.2f} {cur}/gün · {b['results']:.1f} nəticə/gün "
                f"· CTR {b['ctr']:.2f}%")
        else:
            lines.append("(Müqayisə üçün tarixçə hələ azdır — ratio yoxlamaları buraxıldı.)")
    lines.append(
        f"Ay (cəmi): {float(t.get('spend') or 0):.2f} {cur} · "
        f"{int(t.get('leads') or 0)} lead · {int(t.get('messages') or 0)} mesaj")
    if a["anomalies"]:
        lines.append("\n⚠️ Anomaliyalar:")
        lines += [f"- {x['text']}" for x in a["anomalies"]]
    else:
        lines.append("\n✅ Anomaliya yoxdur — göstəricilər normal axarındadır.")
    camps = sorted(sales.get("campaigns") or [],
                   key=lambda c: float(c.get("spend") or 0), reverse=True)[:3]
    if camps:
        lines.append("Top kampaniyalar (ay): " + " · ".join(
            f"{(c.get('name') or '?')[:28]} {float(c.get('spend') or 0):.2f} {cur}"
            for c in camps))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
