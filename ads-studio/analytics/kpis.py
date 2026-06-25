"""Derived KPIs: the conversion funnel and month-over-month deltas.

Kept source-agnostic - operates purely on the report dict that connectors
return, so it works identically for demo and live data.
"""

from __future__ import annotations


def prev_month(ym: str) -> str:
    y, m = (int(x) for x in ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _sum_first_days(daily: list[dict], n: int) -> dict:
    keys = ("spend", "impressions", "clicks", "reach", "leads", "messages")
    out = {k: 0 for k in keys}
    for row in daily[:n]:
        for k in keys:
            out[k] += row[k]
    out["spend"] = round(out["spend"], 2)
    return out


def _pct_change(curr: float, base: float) -> float | None:
    if base == 0:
        return None
    return round((curr - base) / base * 100, 1)


def funnel(totals: dict) -> list[dict]:
    """Impressions -> reach -> clicks -> leads -> messages, with step rates."""
    stages = [
        ("Göstərilmə", totals["impressions"]),
        ("Əhatə", totals["reach"]),
        ("Klik", totals["clicks"]),
        ("Lead", totals["leads"]),
        ("Mesaj", totals["messages"]),
    ]
    out = []
    top = max(stages[0][1], 1)
    for i, (name, value) in enumerate(stages):
        prev_value = stages[i - 1][1] if i else value
        out.append({
            "stage": name,
            "value": value,
            "width_pct": round(value / top * 100, 1),
            "step_rate": round(value / prev_value * 100, 1) if prev_value else 0.0,
        })
    return out


# Metrics where a *lower* value is better (cost efficiency): green when down.
_LOWER_IS_BETTER = {"cpl", "cpm", "cpc", "cost_per_message", "frequency"}


def deltas(curr_totals: dict, prev_report: dict | None, days_elapsed: int) -> dict:
    """MoM deltas, comparing same elapsed window of the previous month.

    For a complete month this is a full-vs-full comparison; for the current
    (partial) month it compares the first ``days_elapsed`` days of each month -
    an apples-to-apples pace comparison rather than partial-vs-complete.
    """
    if not prev_report:
        return {}
    base = _sum_first_days(prev_report["daily"], days_elapsed)
    # Recompute the same ratio metrics on the baseline window.
    impr = max(base["impressions"], 1)
    clicks = max(base["clicks"], 1)
    leads = max(base["leads"], 1)
    base_ratios = {
        "ctr": base["clicks"] / impr * 100,
        "cpm": base["spend"] / impr * 1000,
        "cpc": base["spend"] / clicks,
        "cpl": base["spend"] / leads,
        "cost_per_message": base["spend"] / max(base["messages"], 1),
        "frequency": impr / max(base["reach"], 1),
    }

    out = {}
    for key in ("spend", "leads", "messages", "clicks", "impressions", "reach"):
        change = _pct_change(curr_totals[key], base[key])
        out[key] = {"change": change, "good": (change or 0) >= 0}
    for key, base_val in base_ratios.items():
        change = _pct_change(curr_totals[key], base_val)
        good = (change or 0) <= 0 if key in _LOWER_IS_BETTER else (change or 0) >= 0
        out[key] = {"change": change, "good": good}
    return out
