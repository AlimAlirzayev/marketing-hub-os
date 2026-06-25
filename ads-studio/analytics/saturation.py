"""Audience saturation curve + creative fatigue early-warning indicators.

Saturation: when frequency climbs while incremental reach flatlines, the
audience is saturated and CPMs will bloat. We surface the trend so a marketer
sees this *before* it inflates costs.

Fatigue: a rule-based summary using the existing daily data — frequency,
CTR, and trend slopes — that matches what marketers eyeball in Ads Manager.
"""

from __future__ import annotations


def _linreg_slope(series: list[float]) -> float:
    """Tiny linear-regression slope (no numpy dep). Returns 0 if too short."""
    n = len(series)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(series) / n
    num = sum((xs[i] - mx) * (series[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n)) or 1
    return num / den


def saturation(daily: list[dict]) -> dict:
    """Per-day reach and frequency, plus a verdict on saturation health."""
    if not daily:
        return {"points": [], "verdict": "Data yoxdur."}

    points = []
    for row in daily:
        reach = row.get("reach", 0)
        impr = row.get("impressions", 0)
        freq = impr / reach if reach else 0
        points.append({"date": row["date"], "reach": reach,
                        "impressions": impr, "frequency": round(freq, 2)})

    # Slopes over the period: reach trending down + freq trending up = saturation.
    reach_slope = _linreg_slope([p["reach"] for p in points])
    freq_slope = _linreg_slope([p["frequency"] for p in points])
    avg_reach = sum(p["reach"] for p in points) / len(points)
    avg_freq = sum(p["frequency"] for p in points) / len(points)
    # Normalise slope to a per-day % of average so they're comparable.
    reach_pct = (reach_slope / avg_reach * 100) if avg_reach else 0
    freq_pct = (freq_slope / avg_freq * 100) if avg_freq else 0

    if avg_freq >= 4 and freq_pct > 0:
        verdict = "Auditoriya doyub. Frequency həm yüksək, həm artır. Auditoriyanı genişləndirin."
        status = "over"
    elif freq_pct > 5 and reach_pct < 0:
        verdict = "Saturasiya siqnalı: frequency artır, gündəlik reach düşür. Kreativi yeniləyin."
        status = "warn"
    elif avg_freq >= 3:
        verdict = "Frequency hələ qəbul edilən diapazonda, amma izləyin."
        status = "warn"
    else:
        verdict = "Saturasiya yoxdur — reach sağlam böyüyür."
        status = "good"

    return {
        "points": points,
        "avg_reach": int(avg_reach),
        "avg_frequency": round(avg_freq, 2),
        "reach_trend_pct": round(reach_pct, 2),
        "freq_trend_pct": round(freq_pct, 2),
        "verdict": verdict,
        "status": status,
    }


def fatigue_indicators(daily: list[dict], totals: dict, deltas: dict) -> dict:
    """Rule-based creative fatigue early warning at the account level."""
    if not daily:
        return {"signals": [], "verdict": "Data yoxdur."}

    sig = []
    freq = totals.get("frequency", 0)
    ctr = totals.get("ctr", 0)
    ctr_delta = (deltas.get("ctr") or {}).get("change")

    # 1) Frequency level
    if freq >= 4:
        sig.append({"name": "Çox yüksək tezlik", "value": f"{freq}x",
                    "severity": "high",
                    "detail": "Eyni şəxsə 4+ dəfə göstərilir. Kreativi dərhal yeniləyin."})
    elif freq >= 3:
        sig.append({"name": "Yüksək tezlik", "value": f"{freq}x", "severity": "warn",
                    "detail": "Yorğunluq başlanğıcı. 3.5x-ə yaxınlaşır."})

    # 2) CTR decline vs baseline
    if ctr_delta is not None and ctr_delta <= -25:
        sig.append({"name": "CTR kəskin düşüb", "value": f"{ctr_delta}%",
                    "severity": "high",
                    "detail": "Klassik kreativ yorğunluğu əlaməti — yeni hooks lazım."})
    elif ctr_delta is not None and ctr_delta <= -10:
        sig.append({"name": "CTR azalır", "value": f"{ctr_delta}%", "severity": "warn",
                    "detail": "Trend mənfiyə dönüb, izləyin."})

    # 3) Daily frequency slope
    freqs = [d.get("impressions", 0) / max(d.get("reach", 1), 1) for d in daily]
    slope = _linreg_slope(freqs)
    if slope > 0.05:
        sig.append({"name": "Tezlik gündən-günə artır", "value": f"+{round(slope,2)}/gün",
                    "severity": "warn",
                    "detail": "Reach plato verir, eyni adamlara daha çox göstərilir."})

    if not sig:
        verdict = "Fatigue siqnalı yoxdur — kreativ sağlam görünür."
        status = "good"
    elif any(s["severity"] == "high" for s in sig):
        verdict = "Kreativ yorğunluğu aşkarlandı — yenilənmə vacibdir."
        status = "over"
    else:
        verdict = "Erkən fatigue siqnalları var — yaxın günlərdə yeni kreativ planlayın."
        status = "warn"

    return {"signals": sig, "verdict": verdict, "status": status}
