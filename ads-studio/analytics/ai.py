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


# --------------------------------------------------------------------------
# Leadership narrative — paid + organic + product-line, written as a story,
# not a table. This is the thing a generic BI tool (Ads Manager, Looker, GA4)
# structurally cannot produce: it needs business-specific grouping (product
# line) blended with a synthesized write-up, not just numbers.
# --------------------------------------------------------------------------
def narrative_report(report: dict, analytics: dict, organic: dict | None,
                      product_breakdown: list[dict]) -> dict:
    lines = [build_context(report, analytics), ""]
    if organic:
        fb, ig = organic.get("facebook") or {}, organic.get("instagram") or {}
        if fb.get("fan_count") is not None:
            lines.append(f"Facebook Page izləyici: {fb['fan_count']}.")
        if ig.get("followers_count") is not None:
            lines.append(f"Instagram izləyici: {ig['followers_count']} (@{ig.get('username','')}).")
    if product_breakdown:
        lines.append("Məhsul xətti üzrə bölgü (bu ay, reklam səviyyəsində):")
        for p in product_breakdown[:8]:
            cpl_txt = _money(p["cpl"]) if p.get("cpl") is not None else "—"
            lines.append(f"- {p['product']} / {p['format']}: xərc {_money(p['spend'])}, "
                         f"{p['leads']} lead, CPL {cpl_txt}, CTR {p['ctr']}%.")
    ctx = "\n".join(lines)
    prompt = (
        "Aşağıdakı rəqəmlərə əsasən rəhbərlik üçün HƏFTƏLİK/AYLIQ HEKAYƏ HESABATI yaz. "
        "Struktur: (1) bu dövrdə nə baş verdi — 2-3 cümlə; (2) nə yaxşı işlədi, konkret "
        "rəqəmlə; (3) nəyə diqqət lazımdır, konkret rəqəmlə; (4) 2-3 konkret, tətbiq edilə "
        "bilən tövsiyə. Cədvəl və başlıq işarələri yox — axıcı, rəhbərlik səviyyəsində, "
        "Azərbaycan dilində yaz. Marketinq jarqonu işlətmə, rəqəm uydurma.\n\n" + ctx
    )
    try:
        text = _gemini(prompt, max_retries=2)
        if text:
            return {"text": text, "source": "gemini"}
    except Exception:
        pass
    return {"text": _fallback_summary(report, analytics), "source": "rule-based"}


# --------------------------------------------------------------------------
# Trend + Performance bridge — cross-references live campaign weak spots with
# the research lab's open external radar findings. No generic tool can do
# this: it needs both live account access AND the lab's trend feed.
# --------------------------------------------------------------------------
def trend_bridge(analytics: dict, findings: list[dict]) -> dict:
    flags = [a for a in analytics.get("anomalies", []) if a.get("severity") in ("warn", "high")]
    flags_txt = ("\n".join(f"- {a['title']}: {a['detail']}" for a in flags)
                 if flags else "Hazırda ciddi performans problemi qeydə alınmayıb.")
    top = sorted(findings, key=lambda f: -f.get("score", 0))[:12]
    findings_txt = "\n".join(f"- ({f['score']}/10) {f['title']}: {f.get('idea','')}" for f in top)
    prompt = (
        "Sən Xalq Sığorta-nın rəqəmsal marketinq strateqisən. Aşağıda (A) hazırkı "
        "kampaniyalardakı performans siqnalları, (B) xarici bazarda aşkarlanmış "
        "trend/imkan siyahısı var. Yalnız KONKRET, tətbiq edilə bilən 2-4 tövsiyə yaz — "
        "hansı trend hansı problemi necə həll edə bilər, NECƏ tətbiq olunacağı ilə birgə. "
        "Uydurma, yalnız verilən məlumata əsaslan.\n\n"
        f"(A) Performans siqnalları:\n{flags_txt}\n\n(B) Xarici trendlər:\n{findings_txt}"
    )
    try:
        text = _gemini(prompt, max_retries=2)
        if text:
            return {"text": text, "source": "gemini"}
    except Exception:
        pass
    return {"text": "Hazırda AI məsləhətçi əlçatan deyil — tapıntıları Trendlər tabında "
                    "(İdarəetmə Mərkəzi, port 8890) nəzərdən keçirin.", "source": "fallback"}
