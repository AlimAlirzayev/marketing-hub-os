"""Eligibility gates for influencer selection.

Scoring ranks quality. Eligibility gates decide whether a creator is allowed to
enter the campaign shortlist at all.
"""

from __future__ import annotations

import re

from models import InfluencerCandidate, SelectionFilters

_CREATOR_WORDS = {
    "blogger", "influencer", "creator", "vlogger", "traveler", "traveller",
    "travelblog", "travelblogger", "lifestyle", "personal blog", "public figure",
    "digital creator", "content creator", "photographer", "videographer",
    "filmmaker", "family", "mom", "ana", "yemek", "seyahat", "gezgin",
    "səyahət", "sahəyat", "foodblogger",
}

_CORPORATE_WORDS = {
    "insurance", "sigorta", "sığorta", "airlines", "airline", "hava yollari",
    "hava yolları", "azal", "bank", "tour agency", "travel agency", "agency",
    "tourism", "official", "company", "mmc", "llc", "shop", "store", "hotel",
    "restaurant", "clinic", "media", "news", "rent", "auto", "avto",
}

_NON_CREATOR_PAGE_WORDS = {
    "places", "discover", "guide", "city", "cities", "tour", "tours", "trip",
    "trips", "travel", "tourism", "best_tour", "best tour", "official",
    "magazine", "portal", "community", "page",
}

_LOCAL_MARKET_WORDS = {
    "azerbaijan", "azerbaycan", "azərbaycan", "azərbaycanlı", "baku", "bakı",
    "baki", "ganja", "gəncə", "gence", "sumqayit", "sumqayıt", "qabala",
    "qəbələ", "sheki", "şəki", "azeri", "azəri", "bakublogger",
    "azerbaijanblogger", "azblogger", "travelbloggeraz", "aztravelblogger",
    "azerbaijaninfluencer", "azeriinfluencer", "🇦🇿",
}

_FOREIGN_MARKET_WORDS = {
    "from india", "india", "hindistan", "turkey", "turkiye", "türkiye",
    "istanbul", "ankara", "pakistan", "indonesia", "jakarta",
    "uae", "dubai", "emirates", "saudi", "kuwait", "qatar",
    "egypt", "russia", "moscow", "iran", "iraq", "kazakhstan", "qazaxstan",
    "kazakh", "simkent", "shymkent",
}

_STRONG_FOREIGN_PATTERNS = (
    r"\bfrom\s+(india|turkey|turkiye|türkiye|pakistan|indonesia|kazakhstan|qazaxstan|saudi|egypt)\b",
    r"\bbased\s+in\s+(india|turkey|turkiye|türkiye|istanbul|pakistan|indonesia|kazakhstan|qazaxstan|dubai|uae)\b",
    r"\b(traveller|traveler|influencer|creator|blogger)\s+in\s+(simkent|shymkent|istanbul|dubai|mumbai|delhi|jakarta|riyadh)\b",
)

_AZ_NAME_HINTS = {
    "mammad", "memmed", "mamed", "aliyev", "aliyeva", "hasanzade",
    "zadeh", "zade", "rasulova", "eminli", "mammadova", "huseyn",
    "hüseyn", "agalar", "ağalar", "nuray", "aysun", "ulvu", "ülvi",
}

_AZ_LANGUAGE_CHARS = {"ə", "Ə", "ı", "ğ", "Ğ"}

_AZ_WORDS = {
    "azerbaycan", "baki", "bakida", "men", "menim", "menimle", "bizim",
    "ucun", "ile", "ve", "cox", "deyil", "haqqinda", "melumat",
    "emekdasliq", "reklam", "seyahat", "yemek", "gezmek", "kesf", "rahatliq",
    "guven", "tehlukesizlik", "sual", "baxin", "gelin", "olaraq", "vacibdir",
    "dunyani", "ozun", "her", "seyi",
}

_COMPETITOR_WORDS = {
    "ateshgah", "atesgah", "atəşgah", "pasha", "paşa", "qalasigorta",
    "qala sigorta", "azsigorta", "az sigorta", "meqa sigorta", "meqasigorta",
    "gunes sigorta", "günəş sigorta", "xalg sigorta", "xalq sigorta",
}


def _reject(c: InfluencerCandidate, reason: str) -> None:
    c.flags = list(dict.fromkeys([*c.flags, reason]))


def _norm(text: str) -> str:
    text = (text or "").lower()
    repl = {
        "ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c",
        "Ə": "e", "I": "i", "İ": "i", "Ö": "o", "Ü": "u", "Ğ": "g", "Ş": "s", "Ç": "c",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text)


def _identity_text(c: InfluencerCandidate) -> str:
    return _norm(" ".join([
        c.handle,
        c.name,
        c.bio,
        " ".join(c.categories),
    ]))


def _evidence_text(c: InfluencerCandidate) -> str:
    return _norm(" ".join([
        " ".join(e.text[:300] for e in c.evidence[:8]),
    ]))


def _raw_text(c: InfluencerCandidate, include_evidence: bool = True) -> str:
    parts = [
        c.handle,
        c.name,
        c.bio,
        c.contact,
        " ".join(c.categories),
    ]
    if include_evidence:
        parts.append(" ".join(e.text[:300] for e in c.evidence[:8]))
    return " ".join(parts)


def _has_any(text: str, words: set[str]) -> bool:
    return any(_norm(w) in text for w in words)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _norm(text)))


def _az_language_hits(text: str) -> int:
    return len(_tokens(text) & {_norm(w) for w in _AZ_WORDS})


def _foreign_market_assessment(c: InfluencerCandidate) -> tuple[float, list[str]]:
    identity_raw = _raw_text(c, include_evidence=False)
    identity = _norm(identity_raw)
    score = 0.0
    reasons: list[str] = []
    # Explicit platform-provided country (e.g. YouTube channel country) is the
    # most reliable signal we get; a non-AZ country is strong foreign evidence.
    if c.country and c.country.upper() != "AZ":
        score += 5.0
        reasons.append(f"kanal ölkəsi: {c.country} (Azərbaycan deyil)")
    for pattern in _STRONG_FOREIGN_PATTERNS:
        if re.search(pattern, identity):
            score += 4.0
            reasons.append("profil özünü xarici bazara bağlayır")
            break
    for word in _FOREIGN_MARKET_WORDS:
        if _norm(word) in identity:
            score += 1.5
            reasons.append(f"xarici lokasiya siqnalı: {word}")
            break
    return score, list(dict.fromkeys(reasons))


def local_market_assessment(c: InfluencerCandidate) -> tuple[float, list[str]]:
    identity_raw = _raw_text(c, include_evidence=False)
    evidence_raw = " ".join(e.text[:500] for e in c.evidence[:10])
    identity = _norm(identity_raw)
    evidence = _norm(evidence_raw)
    all_raw = f"{identity_raw} {evidence_raw}"
    score = 0.0
    reasons: list[str] = []
    if c.country and c.country.upper() == "AZ":
        score += 4.0
        reasons.append("kanal ölkəsi rəsmi olaraq Azərbaycandır")
    if _has_any(identity, _LOCAL_MARKET_WORDS):
        score += 3.0
        reasons.append("profil bio/ad/handle-da Azərbaycan/Bakı siqnalı var")
    if _has_any(evidence, _LOCAL_MARKET_WORDS):
        score += 1.5
        reasons.append("son kontentdə Azərbaycan/Bakı siqnalı var")
    if c.handle.endswith("az") or ".az" in c.handle or "_az" in c.handle or "az_" in c.handle:
        score += 2.0
        reasons.append("handle lokal AZ siqnalı daşıyır")
    if ".az" in _norm(all_raw) or "+994" in all_raw or "azn" in _norm(all_raw) or "manat" in _norm(all_raw):
        score += 2.0
        reasons.append("lokal kontakt/domen/valyuta siqnalı var")
    if any(ch in identity_raw for ch in _AZ_LANGUAGE_CHARS):
        score += 2.0
        reasons.append("profil mətnində Azərbaycan dili hərfləri var")
    if any(ch in evidence_raw for ch in _AZ_LANGUAGE_CHARS):
        score += 2.5
        reasons.append("son kontent Azərbaycan dilində görünür")
    identity_lang_hits = _az_language_hits(identity_raw)
    evidence_lang_hits = _az_language_hits(evidence_raw)
    if identity_lang_hits >= 2:
        score += 2.0
        reasons.append("profil mətni Azərbaycan dili leksikasına uyğundur")
    if evidence_lang_hits >= 3:
        score += 2.5
        reasons.append("caption/rəy mətni Azərbaycan dili leksikasına uyğundur")
    if _has_any(identity, _AZ_NAME_HINTS):
        score += 1.0
        reasons.append("ad/soyad lokal bazar siqnalı verir")
    foreign_score, foreign_reasons = _foreign_market_assessment(c)
    if foreign_score:
        reasons.extend(foreign_reasons)
    # Foreign context is a blocker only when local proof is weak. Travel creators
    # often list visited countries, so strong Azerbaijani proof can still pass.
    adjusted = score - (foreign_score if score < 5.0 else min(1.0, foreign_score))
    return max(0.0, adjusted), list(dict.fromkeys(reasons))[:6]


def is_local_market(c: InfluencerCandidate) -> bool:
    score, reasons = local_market_assessment(c)
    c.market_fit = round(min(10.0, score), 2)
    c.market_reasons = reasons
    foreign_score, _foreign_reasons = _foreign_market_assessment(c)
    if foreign_score >= 3.0 and score < 4.0:
        return False
    return score >= 2.5


def local_market_score(c: InfluencerCandidate) -> float:
    return local_market_assessment(c)[0]


def is_human_creator(c: InfluencerCandidate) -> bool:
    identity = _identity_text(c)
    if _has_any(identity, _COMPETITOR_WORDS):
        return False
    corporate = _has_any(identity, _CORPORATE_WORDS)
    creator = _has_any(identity, _CREATOR_WORDS)
    # A handle such as aritravelblog is a creator signal; "best_tour" is not.
    if "travelblog" in identity or "blogger" in identity or "vlogger" in identity:
        creator = True
    if _has_any(identity, _NON_CREATOR_PAGE_WORDS) and not creator:
        return False
    if corporate and not creator:
        return False
    if corporate and any(x in identity for x in ("insurance", "sigorta", "airline", "airlines", "agency", "official")):
        return False
    return creator


def apply_eligibility(
    candidates: list[InfluencerCandidate],
    filters: SelectionFilters,
) -> tuple[list[InfluencerCandidate], list[InfluencerCandidate]]:
    eligible: list[InfluencerCandidate] = []
    filtered_out: list[InfluencerCandidate] = []
    for c in candidates:
        c.market_fit, c.market_reasons = local_market_assessment(c)
        identity = _identity_text(c)
        if filters.exclude_competitors and _has_any(identity, _COMPETITOR_WORDS):
            _reject(c, "birbaşa rəqib və ya Xalq Sığorta hesabı ola bilər")
            filtered_out.append(c)
            continue
        if filters.exclude_corporate_accounts and _has_any(identity, _CORPORATE_WORDS) and not is_human_creator(c):
            _reject(c, "korporativ/brend hesabıdır, fərdi influencer deyil")
            filtered_out.append(c)
            continue
        if filters.require_human_creator and not is_human_creator(c):
            _reject(c, "fərdi influencer/blogger siqnalı zəifdir")
            filtered_out.append(c)
            continue
        if filters.require_local_market and not is_local_market(c):
            _reject(c, "Azərbaycan/local auditoriya siqnalı zəifdir")
            filtered_out.append(c)
            continue
        if filters.require_campaign_fit:
            if c.audience_fit < filters.min_audience_fit:
                _reject(c, f"kampaniya auditoriyası ilə uyğunluq zəifdir ({c.audience_fit:.1f} < {filters.min_audience_fit:.1f})")
                filtered_out.append(c)
                continue
            if c.content_fit < filters.min_content_fit:
                _reject(c, f"kampaniya kontenti/Reels uyğunluğu zəifdir ({c.content_fit:.1f} < {filters.min_content_fit:.1f})")
                filtered_out.append(c)
                continue
            if c.proof_density < filters.min_proof_density:
                _reject(c, f"real kontent sübutu azdır ({c.proof_density:.1f} < {filters.min_proof_density:.1f})")
                filtered_out.append(c)
                continue
        if filters.min_followers > 0:
            if c.followers is None:
                if not filters.allow_unknown_followers:
                    _reject(c, f"izləyici sayı görünmür; {filters.min_followers:,}+ filterindən keçmədi")
                    filtered_out.append(c)
                    continue
            elif c.followers < filters.min_followers:
                _reject(c, f"minimum izləyici filterindən aşağıdır ({c.followers:,} < {filters.min_followers:,})")
                filtered_out.append(c)
                continue
        if c.total_score < filters.min_score:
            _reject(c, f"minimum bal filterindən aşağıdır ({c.total_score:.1f} < {filters.min_score:.1f})")
            filtered_out.append(c)
            continue
        eligible.append(c)
    return eligible, filtered_out
