"""Analytics bundle: turn a raw report into everything the dashboard renders."""

from __future__ import annotations

from connectors import get_report

from . import ai, anomalies, comparison, kpis, pacing, saturation, whats_changed


def analyze(ym: str, platform: str = "all", account_id: str | None = None,
            with_ai_summary: bool = True,
            compare_mode: str = "prev_month") -> dict:
    """Build the full enriched payload for one month / platform / account.

    ``compare_mode`` selects the baseline used for deltas and 'what changed':
        - 'prev_month' (default) — apples-to-apples vs ötən ay
        - 'prev_year'             — vs keçən ilin eyni ayı (illik dinamika)
    """
    report = get_report(ym, platform, account_id)
    baseline = comparison.fetch_baseline(ym, compare_mode, platform, account_id)
    days_elapsed = report["period"]["days_elapsed"]

    delta = comparison.compute_deltas(report["combined_totals"], baseline, days_elapsed)
    pac = pacing.build(report)
    flags = anomalies.detect(report, delta, pac)

    mode_label = "ötən ay" if compare_mode == "prev_month" else "keçən ilin eyni ayı"
    insight = whats_changed.narrate(delta, mode_label, report, flags,
                                     use_ai=with_ai_summary)
    sat = saturation.saturation(report["daily"])
    fat = saturation.fatigue_indicators(report["daily"], report["combined_totals"], delta)

    analytics = {
        "funnel": kpis.funnel(report["combined_totals"]),
        "deltas": delta,
        "pacing": pac,
        "anomalies": flags,
        "insight": insight,
        "saturation": sat,
        "fatigue": fat,
        "comparison": {
            "mode": compare_mode,
            "label": mode_label,
            "baseline_period": baseline["period"]["label"] if baseline else None,
        },
    }
    if with_ai_summary:
        analytics["summary"] = ai.exec_summary(report, analytics)

    return {"report": report, "analytics": analytics}
