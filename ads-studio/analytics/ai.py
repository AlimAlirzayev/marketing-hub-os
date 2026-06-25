"""AI layer: executive summary + grounded Q&A, in Azerbaijani.

Reuses the free, live Gemini key already in Xalq Insurance Digital OS. Every call is grounded on
a compact numeric context built from the report, so the model reports real
figures instead of inventing them. If Gemini is unavailable (no key / quota /
network), we fall back to a deterministic, data-driven answer so the assistant
never shows an error to management.
"""

from __future__ import annotations

import os
import re
import time

from config import ACCOUNT_NAME, CURRENCY_SYMBOL, GEMINI_API_KEY, GEMINI_MODEL

# Prefer the repo-wide unified router (free-first cascade + one spend log). Falls
# back transparently to direct Gemini if the router/litellm is unavailable in this
# studio's venv, so behavior is identical. Disable with ADS_DISABLE_LLM_ROUTER=1.
_USE_ROUTER = os.getenv("ADS_DISABLE_LLM_ROUTER", "0").lower() not in {"1", "true", "yes", "on"}
_ROUTER_TIER = os.getenv("ADS_LLM_TIER", "smart")


def _via_router(prompt: str, system: str, temperature: float) -> str | None:
    if not _USE_ROUTER:
        return None
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parent.parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        import llm_router
    except Exception:  # noqa: BLE001
        return None
    try:
        text, _model = llm_router.complete(prompt, system=system or None,
                                           tier=_ROUTER_TIER, temperature=temperature)
        return text or None
    except Exception:  # noqa: BLE001
        return None

_SYSTEM = (
    "Sən Xalq Sigorta-nın rəqəmsal marketinq analitikisən. Yalnız sənə verilən "
    "rəqəmlərə əsaslan, rəqəm uydurma. Qısa, aydın və rəhbərliyə uyğun "
    "Azərbaycan dilində cavab ver. Pul məbləğlərini verilən valyuta ilə yaz."
)

_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL", "overloaded")


def _money(x: float) -> str:
    return f"{CURRENCY_SYMBOL}{x:,.2f}"


def build_context(report: dict, analytics: dict) -> str:
    """Compact, model-friendly numeric context for grounding."""
    t = report["combined_totals"]
    p = report["period"]
    pac = analytics["pacing"]
    inv = report["invoices"]
    lines = [
        f"Hesab: {ACCOUNT_NAME}. Dövr: {p['label']} "
        f"({p['days_elapsed']}/{p['days_total']} gün keçib).",
        f"Platforma filtri: {report['platform']}.",
        f"Ümumi xərc: {_money(t['spend'])}.",
        f"Lead: {t['leads']} (lead başına {_money(t['cpl'])}).",
        f"Mesaj: {t['messages']} (mesaj başına {_money(t['cost_per_message'])}).",
        f"Klik: {t['clicks']} (CTR {t['ctr']}%, klik başına {_money(t['cpc'])}).",
        f"Göstərilmə: {t['impressions']}, Əhatə: {t['reach']}, Tezlik: {t['frequency']}x.",
        f"CPM: {_money(t['cpm'])}.",
        f"Facebook lead: {report['by_platform']['facebook']['leads']}, "
        f"Instagram lead: {report['by_platform']['instagram']['leads']}.",
        f"Ödəniş qəbzləri: {inv['count']} ədəd, cəmi {_money(inv['total'])}, "
        f"fakturalanmamış {_money(inv.get('unbilled', 0))}.",
    ]
    if pac["is_current"]:
        lines.append(
            f"Proqnoz (ay sonu): xərc {_money(pac['projected_spend'])} "
            f"(plan {_money(pac['budget'])}), lead {pac['projected_leads']} "
            f"(hədəf {pac['target_leads']}, {pac['lead_attainment_pct']}%).")
    flags = [a["title"] for a in analytics["anomalies"] if a["severity"] != "ok"]
    if flags:
        lines.append("Xəbərdarlıqlar: " + "; ".join(flags) + ".")
    return "\n".join(lines)


def _gemini(prompt: str, system: str = _SYSTEM, max_retries: int = 3) -> str:
    routed = _via_router(prompt, system, 0.5)
    if routed is not None:
        return routed
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(system_instruction=system, temperature=0.5)
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt, config=config)
            return (resp.text or "").strip()
        except Exception as exc:
            if not any(tok in str(exc) for tok in _RETRYABLE):
                raise
            last = exc
            m = re.search(r"retryDelay'?\s*[:=]\s*'?(\d+)", str(exc))
            time.sleep(min(float(m.group(1)) if m else 4 * (attempt + 1), 30))
    raise last  # type: ignore[misc]


# --------------------------------------------------------------------------
# Executive summary
# --------------------------------------------------------------------------
def exec_summary(report: dict, analytics: dict) -> dict:
    ctx = build_context(report, analytics)
    prompt = (
        f"Aşağıdakı kampaniya rəqəmlərinə əsasən rəhbərlik üçün 3-4 cümləlik "
        f"icra xülasəsi yaz. 'Bu dövrdə nə baş verdi, nə yaxşıdır, nəyə diqqət "
        f"lazımdır' məntiqi ilə. Marketinq jarqonu yox, biznes dili.\n\n{ctx}"
    )
    try:
        text = _gemini(prompt)
        if text:
            return {"text": text, "source": "gemini"}
    except Exception:
        pass
    return {"text": _fallback_summary(report, analytics), "source": "rule-based"}


def _fallback_summary(report: dict, analytics: dict) -> str:
    t = report["combined_totals"]
    pac = analytics["pacing"]
    parts = [
        f"{report['period']['label']} dövründə {_money(t['spend'])} xərclə "
        f"{t['leads']} lead və {t['messages']} mesaj əldə edilib "
        f"(lead başına {_money(t['cpl'])}, CTR {t['ctr']}%)."
    ]
    if pac["is_current"]:
        parts.append(
            f"Bu sürətlə ay sonu təxminən {pac['projected_leads']} lead gözlənilir "
            f"(hədəfin {pac['lead_attainment_pct']}%-i), proqnoz xərc "
            f"{_money(pac['projected_spend'])}.")
    flags = [a["title"] for a in analytics["anomalies"] if a["severity"] != "ok"]
    parts.append("Diqqət: " + ", ".join(flags) + "."
                 if flags else "Əsas göstəricilər normal diapazondadır.")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Grounded Q&A (the assistant panel)
# --------------------------------------------------------------------------
SUGGESTED_QUESTIONS = [
    "Bu ay neçə lead gəldi?",
    "Lead başına xərc nə qədərdir?",
    "CTR göstəricisi necədir?",
    "Ümumi büdcə necə xərcləndi?",
    "Facebook yoxsa Instagram daha effektivdir?",
    "Ay sonuna proqnoz nədir?",
]


def answer(question: str, report: dict, analytics: dict) -> dict:
    ctx = build_context(report, analytics)
    prompt = f"Kampaniya məlumatları:\n{ctx}\n\nSual: {question}\nCavab:"
    try:
        text = _gemini(prompt)
        if text:
            return {"text": text, "source": "gemini"}
    except Exception:
        pass
    return {"text": _fallback_answer(question, report, analytics), "source": "rule-based"}


def _fallback_answer(question: str, report: dict, analytics: dict) -> str:
    """Deterministic keyword responder for when Gemini is unavailable."""
    q = question.lower()
    t = report["combined_totals"]
    pac = analytics["pacing"]
    if "lead" in q and ("xərc" in q or "başına" in q or "cpl" in q):
        return f"Lead başına xərc {_money(t['cpl'])}-dır (cəmi {t['leads']} lead)."
    if "lead" in q:
        return f"Bu dövrdə {t['leads']} lead gəlib."
    if "ctr" in q:
        return f"CTR {t['ctr']}%-dir ({t['clicks']} klik / {t['impressions']} göstərilmə)."
    if "büdcə" in q or "xərc" in q:
        return f"Ümumi xərc {_money(t['spend'])}-dır. Proqnoz ay sonu: {_money(pac['projected_spend'])}."
    if "facebook" in q or "instagram" in q:
        fb = report["by_platform"]["facebook"]
        ig = report["by_platform"]["instagram"]
        return (f"Instagram {ig['leads']} lead (CPL {_money(ig['cpl'])}), "
                f"Facebook {fb['leads']} lead (CPL {_money(fb['cpl'])}).")
    if "proqnoz" in q or "sonu" in q:
        return (f"Ay sonu proqnozu: {pac['projected_leads']} lead, xərc "
                f"{_money(pac['projected_spend'])} (hədəfin {pac['lead_attainment_pct']}%-i).")
    if "mesaj" in q:
        return f"{t['messages']} mesaj başlanıb (mesaj başına {_money(t['cost_per_message'])})."
    return (f"Bu dövrdə {_money(t['spend'])} xərclə {t['leads']} lead və "
            f"{t['messages']} mesaj əldə edilib. Daha dəqiq sual verə bilərsiniz.")
