"""Turn a natural-language campaign request into a CampaignBrief."""

from __future__ import annotations

import re

import llm
from models import CampaignBrief

_SYSTEM = """You are a senior influencer marketing strategist for Azerbaijan.
Extract a precise campaign brief from the user request. Return only JSON with:
brand, product, objective, audience, market, language, content_format,
selling_angle, tone, must_have_topics, avoid_topics, creator_archetypes,
hashtags, seed_handles.
Prefer Azerbaijani market cues and Instagram/Reels creators when relevant.
The hashtags must be for finding human creators/bloggers, not the brand or
insurance company accounts. Avoid brand hashtags, competitor names, and generic
insurance-company tags unless the user explicitly asks for them.
Do not invent specific influencer names."""

_TRAVEL_WORDS = {
    "səyahət", "seyahat", "travel", "trip", "tourism", "turizm", "georgia",
    "gürcüstan", "gurcustan", "airport", "uçuş", "ucus", "visa", "otel",
    "baqaj", "xaric", "abroad", "tətil", "tetil",
}

_LOCAL_DISCOVERY_HASHTAGS = [
    "azerbaijanblogger", "bakublogger", "travelbloggeraz", "aztravelblogger",
    "azerbaijaninfluencer", "azblogger", "azeriinfluencer",
    "bakutravelblogger", "azerbaijantravel", "bakutravel",
    # extra breadth for the AZ travel/lifestyle creator pool (kept after the
    # core 10 so the fallback brief's first-10 slice is unchanged)
    "azerbaijanlifestyle", "bakulifestyle", "azvlogger", "azlifestyle",
]

_LOCAL_HASHTAG_HINTS = {
    "az", "azerbaijan", "azerbaycan", "azərbaycan", "baku", "bakı", "baki",
    "azeri", "azəri",
}


def _clean_words(text: str) -> list[str]:
    words = re.findall(r"[\wəğıöşüçƏĞIİÖŞÜÇ]+", text.lower(), re.UNICODE)
    return [w for w in words if len(w) > 2]


def _fallback(query: str) -> CampaignBrief:
    low = query.lower()
    brand = "Xalq Sigorta" if "xalq" in low else ""
    product = "səyahət sığortası" if ("səyahət" in low or "seyahat" in low or "travel" in low) else ""
    angle = "emotional selling proposition" if "emosional" in low or "emotional" in low else ""
    topics = sorted(_TRAVEL_WORDS.intersection(set(_clean_words(query))))
    if product and "sığorta" not in topics:
        topics.extend(["sığorta", "risk", "təhlükəsizlik", "ailə", "xaric"])
    archetypes = ["travel blogger", "lifestyle creator", "family travel creator"]
    hashtags = list(_LOCAL_DISCOVERY_HASHTAGS)
    handles = []
    for token in re.findall(r"@([A-Za-z0-9._]{2,30})", query):
        if token not in handles:
            handles.append(token)
    return CampaignBrief(
        query=query,
        brand=brand,
        product=product or "campaign product",
        objective="Find 3 evidence-backed influencers for an Instagram Reel",
        audience="Azerbaijani Instagram users likely to buy the product",
        market="Azerbaijan",
        language="az",
        content_format="Instagram Reel",
        selling_angle=angle or "credible emotional story",
        tone="natural, emotional, useful warning from a real creator",
        must_have_topics=topics[:12],
        avoid_topics=[
            "gambling", "political scandal", "fake giveaways", "unsafe claims",
            "corporate brand account", "insurance competitor account",
        ],
        creator_archetypes=archetypes,
        hashtags=list(dict.fromkeys(hashtags))[:10],
        seed_handles=handles,
    )


def _normalize_list(value) -> list[str]:
    if isinstance(value, list):
        out = [str(x).strip().lstrip("#@") for x in value if str(x).strip()]
    elif isinstance(value, str) and value.strip():
        out = [x.strip().lstrip("#@") for x in re.split(r"[,;\n]+", value) if x.strip()]
    else:
        out = []
    return list(dict.fromkeys(out))


def _norm_hashtag(value: str) -> str:
    value = value.strip().lstrip("#@").replace(" ", "")
    repl = {
        "ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c",
        "Ə": "e", "I": "i", "İ": "i", "Ö": "o", "Ü": "u", "Ğ": "g", "Ş": "s", "Ç": "c",
    }
    text = value.lower()
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return text


def _has_local_hashtag_hint(tag: str) -> bool:
    norm = _norm_hashtag(tag)
    return any(hint in norm for hint in _LOCAL_HASHTAG_HINTS)


def _localize_hashtags(tags: list[str]) -> list[str]:
    # Keep the strongest core discovery tags, weave in any local-signal tags the
    # LLM proposed, then top up from the rest of the curated pool.
    local = [h for h in tags if _has_local_hashtag_hint(h)]
    merged = [*_LOCAL_DISCOVERY_HASHTAGS[:8], *local, *_LOCAL_DISCOVERY_HASHTAGS[8:]]
    return list(dict.fromkeys(merged))[:12]


def resolve(query: str) -> CampaignBrief:
    brief = _fallback(query)
    if not llm.available():
        return brief
    data = llm.complete_json(
        f"USER REQUEST:\n{query}",
        system=_SYSTEM,
        temperature=0.1,
        default=None,
    )
    if not isinstance(data, dict):
        return brief
    return CampaignBrief(
        query=query,
        brand=str(data.get("brand") or brief.brand),
        product=str(data.get("product") or brief.product),
        objective=str(data.get("objective") or brief.objective),
        audience=str(data.get("audience") or brief.audience),
        market=str(data.get("market") or brief.market),
        language=str(data.get("language") or brief.language),
        content_format=str(data.get("content_format") or brief.content_format),
        selling_angle=str(data.get("selling_angle") or brief.selling_angle),
        tone=str(data.get("tone") or brief.tone),
        must_have_topics=_normalize_list(data.get("must_have_topics")) or brief.must_have_topics,
        avoid_topics=_normalize_list(data.get("avoid_topics")) or brief.avoid_topics,
        creator_archetypes=_normalize_list(data.get("creator_archetypes")) or brief.creator_archetypes,
        hashtags=_localize_hashtags(_normalize_list(data.get("hashtags")) or brief.hashtags),
        seed_handles=_normalize_list(data.get("seed_handles")) or brief.seed_handles,
    )
