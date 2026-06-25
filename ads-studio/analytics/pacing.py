"""Budget pacing + month-end forecast (pro feature).

For the current month it projects where spend/leads land at month-end based on
the run-rate so far, and grades that against the plan in config (MONTHLY_BUDGET,
TARGET_LEADS, MAX_CPL). For completed months it reports final vs target.

Status vocabulary (used by the UI to colour the card):
    "good"  on plan / better
    "warn"  drifting, watch it
    "over"  projected to blow the budget / target ceiling
"""

from __future__ import annotations

from config import MAX_CPL, MONTHLY_BUDGET, TARGET_LEADS, TARGET_MESSAGES


def _project(value: float, days_elapsed: int, days_total: int) -> float:
    if days_elapsed <= 0:
        return 0.0
    return value / days_elapsed * days_total


def build(report: dict) -> dict:
    period = report["period"]
    totals = report["combined_totals"]
    days_elapsed = max(period["days_elapsed"], 1)
    days_total = period["days_total"]
    is_current = period["is_current"]

    proj_spend = round(_project(totals["spend"], days_elapsed, days_total), 2)
    proj_leads = int(round(_project(totals["leads"], days_elapsed, days_total)))
    proj_messages = int(round(_project(totals["messages"], days_elapsed, days_total)))
    proj_cpl = round(proj_spend / proj_leads, 2) if proj_leads else 0.0

    # Budget status.
    if proj_spend > MONTHLY_BUDGET * 1.05:
        budget_status = "over"
    elif proj_spend > MONTHLY_BUDGET:
        budget_status = "warn"
    else:
        budget_status = "good"

    # Lead-target status (more leads = good).
    lead_attain = round(proj_leads / TARGET_LEADS * 100) if TARGET_LEADS else 0
    if lead_attain >= 100:
        leads_status = "good"
    elif lead_attain >= 85:
        leads_status = "warn"
    else:
        leads_status = "over"  # well short of target

    cpl_status = "over" if proj_cpl > MAX_CPL else (
        "warn" if proj_cpl > MAX_CPL * 0.9 else "good")

    return {
        "is_current": is_current,
        "days_elapsed": days_elapsed,
        "days_total": days_total,
        "pace_pct": round(days_elapsed / days_total * 100),
        "budget": MONTHLY_BUDGET,
        "spend_so_far": totals["spend"],
        "projected_spend": proj_spend,
        "budget_used_pct": round(totals["spend"] / MONTHLY_BUDGET * 100) if MONTHLY_BUDGET else 0,
        "budget_status": budget_status,
        "target_leads": TARGET_LEADS,
        "leads_so_far": totals["leads"],
        "projected_leads": proj_leads,
        "lead_attainment_pct": lead_attain,
        "leads_status": leads_status,
        "target_messages": TARGET_MESSAGES,
        "projected_messages": proj_messages,
        "projected_cpl": proj_cpl,
        "max_cpl": MAX_CPL,
        "cpl_status": cpl_status,
    }
