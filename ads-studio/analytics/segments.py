"""Higher-level analysis on top of raw Meta segment / creative data.

Adds the interpretation a marketer would do by eye:
  - day-of-week pattern (computed locally from daily series — Meta has no
    native day-of-week breakdown, but we already have daily totals)
  - best / worst hour and placement (actionable callouts)
  - creative-health summary from diagnostic rankings (Meta's relevance scores)
  - hook / hold rate interpretation against 2026 industry benchmarks
"""

from __future__ import annotations

from datetime import date

# ----------------------------------------------------------------------------
# Day-of-week — computed from the daily series we already have
# ----------------------------------------------------------------------------
_AZ_WEEKDAYS = ["B.E.", "Ç.A.", "Çər.", "C.A.", "Cüm.", "Şən.", "Baz."]


def day_of_week(daily: list[dict]) -> list[dict]:
    """Aggregate the daily series by weekday (0=Mon … 6=Sun)."""
    bins: list[dict] = [{"weekday": i, "label": _AZ_WEEKDAYS[i],
                         "spend": 0.0, "impressions": 0, "clicks": 0,
                         "leads": 0, "messages": 0, "days": 0} for i in range(7)]
    for row in daily:
        wd = date.fromisoformat(row["date"]).weekday()
        b = bins[wd]
        b["spend"] += row["spend"]
        b["impressions"] += row["impressions"]
        b["clicks"] += row["clicks"]
        b["leads"] += row["leads"]
        b["messages"] += row["messages"]
        b["days"] += 1
    for b in bins:
        b["spend"] = round(b["spend"], 2)
        b["cpl"] = round(b["spend"] / b["leads"], 2) if b["leads"] else 0.0
    return bins


def best_worst(rows: list[dict], metric: str = "leads",
                label_key: str = "key") -> dict:
    """Return the highest- and lowest-performing slice by ``metric``."""
    if not rows:
        return {"best": None, "worst": None}
    rows = [r for r in rows if r.get(metric, 0) is not None]
    if not rows:
        return {"best": None, "worst": None}
    best = max(rows, key=lambda r: r.get(metric, 0))
    worst = min(rows, key=lambda r: r.get(metric, 0))
    return {
        "best": {"label": best.get(label_key), "value": best.get(metric)},
        "worst": {"label": worst.get(label_key), "value": worst.get(metric)},
    }


# ----------------------------------------------------------------------------
# Creative-health summary from ad-level rankings
# ----------------------------------------------------------------------------
_RANK_SCORE = {
    "ABOVE_AVERAGE": 2,
    "AVERAGE": 1,
    "BELOW_AVERAGE_35": 0,
    "BELOW_AVERAGE_20": -1,
    "BELOW_AVERAGE_10": -2,
}
_RANK_LABEL = {
    "ABOVE_AVERAGE": "Yuxarı orta",
    "AVERAGE": "Orta",
    "BELOW_AVERAGE_35": "Aşağı 35%",
    "BELOW_AVERAGE_20": "Aşağı 20%",
    "BELOW_AVERAGE_10": "Aşağı 10%",
}


def creative_health(ads: list[dict]) -> dict:
    """Roll-up of Meta's three relevance rankings into a single health score."""
    if not ads:
        return {"score": None, "summary": "Diagnostik göstərici üçün kifayət qədər data yoxdur."}

    keys = ("quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking")
    totals = {k: {"above_average": 0, "average": 0, "below": 0, "missing": 0} for k in keys}
    score_sum, score_n = 0, 0
    for ad in ads:
        for k in keys:
            v = ad.get(k)
            if not v:
                totals[k]["missing"] += 1
                continue
            if v == "ABOVE_AVERAGE":
                totals[k]["above_average"] += 1
            elif v == "AVERAGE":
                totals[k]["average"] += 1
            else:
                totals[k]["below"] += 1
            score_sum += _RANK_SCORE.get(v, 0)
            score_n += 1
    avg = score_sum / score_n if score_n else None

    if avg is None:
        verdict = "Hələ data toplanır — kifayət qədər impressionu olan reklam yoxdur."
    elif avg >= 1.2:
        verdict = "Kreativlər güclüdür: əksər diagnostik göstəricilər orta və ya yuxarıdır."
    elif avg >= 0.4:
        verdict = "Orta səviyyə — bir neçə kreativ yenilənməyə ehtiyaclıdır."
    else:
        verdict = "Diqqət: kreativlərin böyük hissəsi aşağı diapazondadır, yeniləmə vacibdir."

    return {"score": avg, "ranking_breakdown": totals, "verdict": verdict,
            "labels": _RANK_LABEL, "ad_count": len(ads)}


# ----------------------------------------------------------------------------
# Video-creative interpretation (Hook / Hold against 2026 benchmarks)
# ----------------------------------------------------------------------------
def video_verdict(v: dict) -> dict:
    if not v or not v.get("has_video"):
        return {"summary": "Bu dövrdə video reklam aşkarlanmadı.", "has_video": False}

    h = v.get("hook_rate", 0)
    hd = v.get("hold_rate", 0)

    if h >= 30:
        hook = ("əla", "high")
    elif h >= 25:
        hook = ("yaxşı", "good")
    elif h >= 15:
        hook = ("orta", "warn")
    else:
        hook = ("zəif", "over")

    if hd >= 24:
        hold = ("top 10%", "high")
    elif hd >= 15:
        hold = ("yaxşı", "good")
    elif hd >= 10:
        hold = ("orta", "warn")
    else:
        hold = ("zəif", "over")

    summary = (
        f"Hook rate {h}% ({hook[0]}, benchmark 25%+), "
        f"Hold rate {hd}% ({hold[0]}, benchmark 15%+). "
        f"Orta baxış müddəti {v.get('avg_watch_seconds', 0)}san."
    )
    return {
        "has_video": True, "summary": summary,
        "hook": {"value": h, "label": hook[0], "status": hook[1]},
        "hold": {"value": hd, "label": hold[0], "status": hold[1]},
    }
