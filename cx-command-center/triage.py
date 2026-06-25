"""AI-assisted complaint triage.

The first pass is deterministic so the command center keeps working without an
LLM key. When Gemini is configured, it can refine the classification and draft a
more nuanced reply, but the rule layer remains the safety net.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from typing import Any

import config

_AI_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _via_router_json(prompt: str, system: str) -> str | None:
    """Prefer the unified router (free-first cascade + one spend log) for the
    refine call; None if it can't serve, so we fall back to direct Gemini. The
    whole refine step already degrades to the deterministic baseline on failure."""
    if os.getenv("CX_DISABLE_LLM_ROUTER", "0").lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        import llm_router
    except Exception:  # noqa: BLE001
        return None
    try:
        text, _model = llm_router.complete(prompt, system=system or None,
                                           tier="cheap", want_json=True, temperature=0.2)
        return text or None
    except Exception:  # noqa: BLE001
        return None

NEGATIVE_TERMS = {
    "az": [
        "şikayət", "narazı", "naraziyam", "pis", "bərbad", "gecikmə", "gecikir",
        "cavab vermirsiniz", "aldat", "problem", "qaytarmırsınız", "ödəmirsiniz",
        "imtina", "haqsız", "rüsvay", "biabır", "məhkəmə", "şikayət edəcəm",
        "narazi", "naraziyam", "cavab yoxdur", "cavab yoxdu", "paylasacam",
        "paylaşacam", "cox narazi", "çox narazı",
    ],
    "tr": ["şikayet", "kötü", "berbat", "gecikti", "cevap yok", "mahkeme"],
    "ru": ["жалоба", "плохо", "ужас", "задерж", "не отвеч", "обман"],
    "en": ["complaint", "bad", "terrible", "delay", "no response", "scam", "fraud"],
}

CATEGORY_TERMS = {
    "claims": ["ödəniş", "kompensasiya", "zərər", "hadisə", "sığorta hadisəsi", "claim", "выплата"],
    "price": ["bahalı", "qiymət", "endirim", "premium", "price", "цена"],
    "service_quality": ["xidmət", "operator", "cavab", "support", "service", "обслуживание"],
    "delay": ["gecik", "gözləyirəm", "gozleyirem", "gundur", "gündür", "nə vaxt", "ne vaxt", "delay", "late", "задерж"],
    "staff_behavior": ["kobud", "hörmətsiz", "işçi", "menecer", "rude", "хам"],
    "digital_issue": ["sayt", "app", "tətbiq", "login", "ödəniş keçmir", "site", "bug"],
    "policy_terms": ["müqavilə", "şərt", "istisna", "polis", "contract", "terms"],
    "branch_experience": ["filial", "ofis", "növbə", "branch", "office"],
    "sales_followup": ["zəng etmədiniz", "təklif", "müraciət", "sales", "lead"],
    "reputation_risk": ["məhkəmə", "mehkeme", "media", "paylaşacam", "paylasacam", "viral", "jurnalist", "şikayət edəcəm", "sikayet edecem"],
}


def _contains_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


def _detect_language(text: str) -> str:
    if re.search(r"[А-Яа-я]", text):
        return "ru"
    if any(ch in text.lower() for ch in "əıöüçğş"):
        return "az"
    return "az"


def _category(text: str) -> str:
    low = text.lower()
    if any(term in low for term in CATEGORY_TERMS["reputation_risk"]):
        return "reputation_risk"
    matches = []
    for category, terms in CATEGORY_TERMS.items():
        score = sum(1 for term in terms if term in low)
        if score:
            matches.append((score, category))
    if not matches:
        return "other"
    return sorted(matches, reverse=True)[0][1]


def _sentiment_and_score(text: str, rating: float | None) -> tuple[str, int]:
    score = 0
    low = text.lower()
    for terms in NEGATIVE_TERMS.values():
        score += sum(12 for term in terms if term in low)
    if rating is not None:
        if rating <= 1:
            score += 50
        elif rating <= 2:
            score += 38
        elif rating <= 3:
            score += 18
    if re.search(r"!{2,}|[A-ZƏÜÖĞŞÇİ]{5,}", text):
        score += 8
    if any(word in low for word in ["məhkəmə", "mehkeme", "media", "viral", "fraud", "scam", "aldat", "paylasacam", "paylaşacam"]):
        score += 22
    if score >= 55:
        return "very_negative", min(score, 100)
    if score >= 25:
        return "negative", min(score, 100)
    if rating and rating >= 4:
        return "positive", 8
    return "neutral", min(score, 100)


def _severity(channel: str, sentiment: str, urgency_score: int, category: str, rating: float | None) -> str:
    public_channel = channel in {
        "instagram_comment",
        "tiktok_comment",
        "facebook_comment",
        "google_review",
        "web_mention",
    }
    if category == "reputation_risk" or urgency_score >= 75:
        return "critical"
    if public_channel and sentiment in {"very_negative", "negative"}:
        return "high"
    if rating is not None and rating <= 2:
        return "high"
    if urgency_score >= 35:
        return "medium"
    return "low"


def _intent(sentiment: str, category: str) -> str:
    if category == "reputation_risk":
        return "reputation_escalation"
    if sentiment in {"very_negative", "negative"}:
        return "complaint"
    return "support_question"


def _summary(text: str, category: str, severity: str) -> str:
    clean = " ".join(text.split())
    if len(clean) > 150:
        clean = clean[:147].rstrip() + "..."
    return f"{severity.title()} {category.replace('_', ' ')} issue: {clean}"


def _reply(text: str, channel: str, category: str, severity: str) -> str:
    if channel in {"google_review", "instagram_comment", "tiktok_comment", "facebook_comment", "web_mention"}:
        return (
            "Salam. Narahatlığınız üçün üzr istəyirik. Məsələni dərhal yoxlamaq "
            "istəyirik. Zəhmət olmasa əlaqə nömrənizi və müraciət detalını şəxsi mesajla göndərin."
        )
    if severity in {"critical", "high"}:
        return (
            "Salam. Yaşadığınız narahatlığa görə üzr istəyirik. Müraciətinizi prioritet "
            "kimi qeydə aldıq və məsul komandaya yönləndiririk. Qısa zamanda sizə geri dönüş ediləcək."
        )
    return (
        "Salam. Mesajınız üçün təşəkkür edirik. Müraciətinizi qeydə aldıq və məsələni "
        "yoxlayıb sizə cavab verəcəyik."
    )


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        return None
    return None


def _rating(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    mapping = {
        "ONE": 1,
        "TWO": 2,
        "THREE": 3,
        "FOUR": 4,
        "FIVE": 5,
        "STAR_RATING_UNSPECIFIED": None,
    }
    text = str(value).strip().upper()
    if text in mapping:
        mapped = mapping[text]
        return float(mapped) if mapped is not None else None
    try:
        return float(text)
    except ValueError:
        return None


def _gemini_refine(message: dict, baseline: dict) -> dict:
    if message.get("_skip_ai") or not config.AI_ENABLED or not config.GEMINI_API_KEY:
        return baseline
    future = _AI_EXECUTOR.submit(_gemini_refine_inner, message, baseline)
    try:
        return future.result(timeout=config.AI_TIMEOUT_SECONDS)
    except TimeoutError:
        return baseline
    except Exception:
        return baseline


def _gemini_refine_inner(message: dict, baseline: dict) -> dict:
    try:
        from google import genai
        from google.genai import types

        # Xalq Insurance Digital OS: Korporativ Bilik Bazasından (RAG) müvafiq sənədlərin axtarışı
        rag_context = ""
        try:
            import sys
            from pathlib import Path
            _ROOT = Path(__file__).resolve().parent.parent
            if str(_ROOT) not in sys.path:
                sys.path.append(str(_ROOT))
            from gateway import rag
            rag_results = rag.search(message.get("text") or "", top_k=1, threshold=0.35)
            if rag_results:
                rag_context = "\n\n".join([f"Mənbə: {r['metadata'].get('title')}\nŞərt: {r['text']}" for r in rag_results])
        except Exception:
            pass

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        system = (
            "You are an Azerbaijani customer experience incident triage engine. "
            "Return only compact JSON. Do not invent facts. Keep public replies empathetic, short and compliant."
        )
        if rag_context:
            system += " Base your recommended_reply strictly on the 'internal_knowledge_base' if it matches the complaint context."

        prompt = {
            "task": "Refine complaint triage for a customer message.",
            "allowed_categories": config.CATEGORIES,
            "allowed_severities": ["critical", "high", "medium", "low"],
            "allowed_sentiments": ["very_negative", "negative", "neutral", "positive"],
            "baseline": baseline,
            "message": {
                "channel": message.get("channel"),
                "rating": message.get("rating"),
                "text": message.get("text"),
            },
            "return_schema": {
                "sentiment": "string",
                "severity": "string",
                "urgency_score": "integer 0-100",
                "category": "string",
                "intent": "string",
                "summary": "one sentence",
                "recommended_reply": "Azerbaijani reply draft",
                "tags": ["short tags"],
            },
        }
        if rag_context:
            prompt["internal_knowledge_base"] = rag_context

        contents = json.dumps(prompt, ensure_ascii=False)
        text = _via_router_json(contents, system)  # unified router first
        if text is None:                            # fall back to direct Gemini
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0.2),
            )
            text = resp.text or ""
        parsed = _safe_json(text)
        if not parsed:
            return baseline
        refined = {**baseline}
        for key in [
            "sentiment",
            "severity",
            "urgency_score",
            "category",
            "intent",
            "summary",
            "recommended_reply",
            "tags",
        ]:
            if key in parsed and parsed[key]:
                refined[key] = parsed[key]
        if refined["category"] not in config.CATEGORIES:
            refined["category"] = baseline["category"]
        if refined["severity"] not in config.SLA_BY_SEVERITY:
            refined["severity"] = baseline["severity"]
        refined["urgency_score"] = max(0, min(int(refined["urgency_score"]), 100))
        refined["assigned_team"] = config.TEAMS.get(refined["category"], "Customer Care")
        refined["sla_due_at"] = _sla_due(refined["severity"])
        refined["ai_source"] = "gemini"
        return refined
    except Exception:
        return baseline


def _sla_due(severity: str) -> str:
    delta = config.SLA_BY_SEVERITY.get(severity, config.SLA_BY_SEVERITY["low"])
    return (datetime.now(timezone.utc) + delta).replace(microsecond=0).isoformat()


def triage_message(message: dict) -> dict:
    text = message.get("text") or ""
    rating = _rating(message.get("rating"))
    if rating is not None:
        message["rating"] = rating
    channel = message.get("channel") or "manual"
    language = message.get("language") or _detect_language(text)
    sentiment, urgency_score = _sentiment_and_score(text, rating)
    category = _category(text)
    severity = _severity(channel, sentiment, urgency_score, category, rating)
    baseline = {
        "language": language,
        "sentiment": sentiment,
        "severity": severity,
        "urgency_score": urgency_score,
        "category": category,
        "intent": _intent(sentiment, category),
        "assigned_team": config.TEAMS.get(category, "Customer Care"),
        "sla_due_at": _sla_due(severity),
        "summary": _summary(text, category, severity),
        "recommended_reply": _reply(text, channel, category, severity),
        "tags": [category, severity, channel],
        "ai_source": "rules",
    }
    return _gemini_refine(message, baseline)
