"""Period comparison — fetch baselines (prev month, same month last year) and
compute deltas on an apples-to-apples (same-elapsed-window) basis.

Used by both the KPI cards (small comparison badge) and the "What changed"
analyzer that surfaces the biggest movers.
"""

from __future__ import annotations

from connectors import get_report

# Metrics where a *lower* value is the better outcome.
LOWER_IS_BETTER = {"cpl", "cpm", "cpc", "cost_per_message", "frequency"}

# Friendly Azerbaijani labels for movers narrative.
METRIC_LABEL = {
    "spend": "Xərc", "leads": "Lead", "messages": "Mesaj",
    "clicks": "Klik", "impressions": "Göstərilmə", "reach": "Əhatə",
    "ctr": "CTR", "cpm": "CPM", "cpl": "CPL", "cpc": "Klik başına",
    "cost_per_message": "Mesaj başına", "frequency": "Tezlik",
}


def prev_month(ym: str) -> str:
    y, m = (int(x) for x in ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def same_month_last_year(ym: str) -> str:
    y, m = (int(x) for x in ym.split("-"))
    return f"{y - 1}-{m:02d}"


def fetch_baseline(ym: str, mode: str, platform: str = "all",
                    account_id: str | None = None) -> dict | None:
    target = prev_month(ym) if mode == "prev_month" else (
        same_month_last_year(ym) if mode == "prev_year" else None)
    if not target:
        return None
    try:
        return get_report(target, platform, account_id)
    except Exception:
        return None


def _sum_first_days(daily: list[dict], n: int) -> dict:
    keys = ("spend", "impressions", "clicks", "reach", "leads", "messages")
    out = {k: 0 for k in keys}
    for row in daily[:n]:
        for k in keys:
            out[k] += row[k]
    out["spend"] = round(out["spend"], 2)
    return out


def _derive_ratios(t: dict) -> dict:
    impr = max(t["impressions"], 1)
    clicks = max(t["clicks"], 1)
    leads = max(t["leads"], 0)
    msg = max(t["messages"], 0)
    reach = max(t["reach"], 1)
    return {
        **t,
        "ctr": t["clicks"] / impr * 100,
        "cpm": t["spend"] / impr * 1000,
        "cpc": t["spend"] / clicks,
        "cpl": t["spend"] / leads if leads else 0,
        "cost_per_message": t["spend"] / msg if msg else 0,
        "frequency": impr / reach,
    }


def pct(curr: float, base: float) -> float | None:
    if base == 0:
        return None
    return round((curr - base) / base * 100, 1)


def is_good(metric: str, change: float | None) -> bool:
    if change is None:
        return True
    return change <= 0 if metric in LOWER_IS_BETTER else change >= 0


def compute_deltas(current_totals: dict, baseline_report: dict | None,
                    days_elapsed: int) -> dict:
    """Compare the current totals to the same elapsed window of the baseline."""
    if not baseline_report:
        return {}
    base_raw = _sum_first_days(baseline_report["daily"], days_elapsed)
    base = _derive_ratios(base_raw)
    out = {}
    for k in ("spend", "leads", "messages", "clicks", "impressions", "reach",
              "ctr", "cpm", "cpl", "frequency", "cpc", "cost_per_message"):
        change = pct(current_totals.get(k, 0), base.get(k, 0))
        out[k] = {"change": change, "good": is_good(k, change),
                  "current": current_totals.get(k, 0),
                  "base": round(base.get(k, 0), 2) if isinstance(base.get(k), float) else base.get(k, 0)}
    return out
