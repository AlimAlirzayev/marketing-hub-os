"""Rule-based anomaly detection (pro feature).

Flags the things a performance marketer would catch by eye: creative fatigue
(CTR drop / high frequency), cost spikes (CPM/CPL), lead slow-down, and budget
burn. Messages are user-facing, so they are written in Azerbaijani.

Severity: "high" (act now) | "warn" (watch) | "info" (FYI). If nothing fires,
returns a single "ok" item so the panel never looks broken.
"""

from __future__ import annotations

from config import CURRENCY_SYMBOL


def _money(x: float) -> str:
    return f"{CURRENCY_SYMBOL}{x:,.2f}"


def detect(report: dict, deltas: dict, pacing: dict) -> list[dict]:
    totals = report["combined_totals"]
    out: list[dict] = []

    def d(key: str) -> float | None:
        return (deltas.get(key) or {}).get("change")

    # --- Creative fatigue: frequency too high ---
    if totals["frequency"] >= 4.0:
        out.append({
            "severity": "high",
            "icon": "refresh",
            "title": "Tezlik həddən yüksəkdir",
            "detail": f"Orta tezlik {totals['frequency']}x — auditoriya doyub. "
                      "Kreativi yeniləyin və ya auditoriyanı genişləndirin.",
        })
    elif totals["frequency"] >= 3.5:
        out.append({
            "severity": "warn",
            "icon": "refresh",
            "title": "Tezlik artır",
            "detail": f"Orta tezlik {totals['frequency']}x. CPM-in qalxmasından "
                      "əvvəl kreativ yeniləməyi planlayın.",
        })

    # --- CTR drop = creative fatigue ---
    ctr_change = d("ctr")
    if ctr_change is not None and ctr_change <= -25:
        out.append({
            "severity": "high",
            "icon": "click",
            "title": "CTR kəskin düşüb",
            "detail": f"CTR keçən aya görə {ctr_change}% azalıb ({totals['ctr']}%). "
                      "Kreativ yorğunluğunun klassik əlaməti.",
        })

    # --- CPM spike ---
    cpm_change = d("cpm")
    if cpm_change is not None and cpm_change >= 25:
        out.append({
            "severity": "warn",
            "icon": "trend",
            "title": "CPM sıçrayışı",
            "detail": f"CPM keçən aya görə {cpm_change}% bahalaşıb "
                      f"({_money(totals['cpm'])}/1000 göstərilmə).",
        })

    # --- CPL above ceiling ---
    if pacing.get("cpl_status") == "over":
        out.append({
            "severity": "high",
            "icon": "money",
            "title": "Lead maliyyəti hədəfdən yuxarı",
            "detail": f"Proqnoz CPL {_money(pacing['projected_cpl'])} > limit "
                      f"{_money(pacing['max_cpl'])}. Büdcəni effektiv ad set-lərə yönləndirin.",
        })

    # --- Lead slow-down vs same period last month ---
    leads_change = d("leads")
    if leads_change is not None and leads_change <= -15:
        out.append({
            "severity": "warn",
            "icon": "lead",
            "title": "Lead axını yavaşlayıb",
            "detail": f"Lead-lər ötən ayın eyni dövrünə görə {leads_change}% aşağıdır.",
        })

    # --- Budget burn ---
    if pacing.get("budget_status") == "over":
        out.append({
            "severity": "high",
            "icon": "money",
            "title": "Büdcə aşımı riski",
            "detail": f"Bu sürətlə ay sonu xərc {_money(pacing['projected_spend'])} olacaq — "
                      f"plan {_money(pacing['budget'])}.",
        })
    elif pacing.get("budget_status") == "warn":
        out.append({
            "severity": "warn",
            "icon": "money",
            "title": "Büdcə plana yaxın",
            "detail": f"Proqnoz xərc {_money(pacing['projected_spend'])}, plan "
                      f"{_money(pacing['budget'])}. İzləyin.",
        })

    if not out:
        out.append({
            "severity": "ok",
            "icon": "check",
            "title": "Anomaliya aşkarlanmadı",
            "detail": "Bütün əsas göstəricilər normal diapazondadır.",
        })
    return out
