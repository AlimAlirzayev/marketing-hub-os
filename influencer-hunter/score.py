"""Evidence-backed scoring for influencer discovery.

The scoring layer is intentionally domain-neutral. Campaign-specific meaning
comes from the resolved brief: product, objective, audience, topics, tone, and
creator archetypes. We use lexical/semantic evidence first, then an optional
LLM layer can adjudicate the strongest candidates.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from models import CampaignBrief, EvidenceItem, InfluencerCandidate

_POSITIVE = {
    "super", "ela", "əla", "cox", "çox", "gozel", "gözəl", "sevdim",
    "faydali", "faydalı", "tesekkur", "təşəkkür", "thanks", "love",
    "trusted", "real", "dogru", "doğru", "xeyirli", "möhtəşəm",
}
_NEGATIVE = {
    "fake", "reklam", "aldatma", "pis", "biabir", "şikayət", "sikayet",
    "scam", "spam", "yalan", "bahali", "bahalı", "blok", "ayıb",
}
_RISKY = {
    "bet", "casino", "kazino", "mərc", "merc", "18+", "erotik", "escort",
    "qalmaqal", "scandal", "politika", "siyasət", "giveaway spam",
}
_SEMANTIC_EXPANDERS = {
    "sığorta": ["sigorta", "insurance", "risk", "təhlükəsizlik", "tehlukesizlik", "polis", "güvən", "guven"],
    "insurance": ["sigorta", "sığorta", "risk", "safety", "security", "claim", "policy"],
    "səyahət": ["seyahat", "travel", "trip", "turizm", "otel", "uçuş", "ucus", "visa", "baqaj"],
    "travel": ["səyahət", "seyahat", "trip", "tourism", "hotel", "flight", "visa", "airport"],
    "food": ["yemek", "yemək", "restaurant", "restoran", "cafe", "recipe", "resept", "dad"],
    "beauty": ["makeup", "skin", "skincare", "cosmetic", "gözəllik", "gozellik", "baxım"],
    "fashion": ["style", "outfit", "geyim", "moda", "dress", "look"],
    "fitness": ["gym", "workout", "idman", "sağlamlıq", "saglamliq", "nutrition"],
    "finance": ["bank", "kart", "kredit", "pul", "invest", "ödəniş", "odenis"],
    "education": ["təhsil", "tehsil", "course", "kurs", "öyrən", "oyren", "student"],
    "tech": ["app", "software", "ai", "startup", "device", "telefon", "digital"],
    "auto": ["car", "avto", "auto", "maşın", "masin", "kasko", "sürücü", "surucu"],
    "real estate": ["ev", "mənzil", "menzil", "home", "property", "kirayə", "kiraye"],
    "emotional": ["story", "hekaye", "hekayə", "ailə", "real", "təcrübə", "tecrube", "hiss"],
    "trust": ["etibar", "güvən", "guven", "real", "dürüst", "durust", "təcrübə"],
}

_GENERIC_STOPWORDS = {
    "instagram", "reel", "reels", "post", "creator", "influencer", "blogger",
    "content", "campaign", "brand", "product", "azerbaijan", "baku",
}


def _norm(text: str) -> str:
    text = (text or "").lower()
    repl = {"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c"}
    for k, v in repl.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", _norm(text)))


def _has_word(text: str, word: str) -> bool:
    """Whole-word match for single tokens; substring for multiword phrases.

    Prevents false positives like 'bet' inside 'alphabet' or 'merc' in 'commerce'
    that would otherwise wrongly trip brand-safety on innocent content.
    """
    w = _norm(word)
    if not w:
        return False
    if " " in w:
        return w in text
    return re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) is not None


def _weighted_tokens(text: str) -> Counter:
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", _norm(text)) if t not in _GENERIC_STOPWORDS]
    counts = Counter(toks)
    words = toks
    for a, b in zip(words, words[1:]):
        counts[f"{a}_{b}"] += 2
    return counts


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / max(na * nb, 1e-9)


def _keyword_set(brief: CampaignBrief) -> set[str]:
    words = set()
    for chunk in [
        brief.query,
        brief.brand,
        brief.product,
        brief.objective,
        brief.selling_angle,
        brief.audience,
        brief.tone,
        *brief.must_have_topics,
        *brief.creator_archetypes,
        *brief.hashtags,
    ]:
        words.update(_tokens(chunk))
    text = _norm(" ".join([
        brief.query,
        brief.product,
        brief.objective,
        brief.selling_angle,
        brief.audience,
        " ".join(brief.must_have_topics),
        " ".join(brief.creator_archetypes),
    ]))
    for key, vals in _SEMANTIC_EXPANDERS.items():
        if _norm(key) in text or _norm(key) in words:
            words.update(_tokens(" ".join(vals)))
    return {w for w in words if w not in _GENERIC_STOPWORDS}


def _brief_text(brief: CampaignBrief) -> str:
    return " ".join([
        brief.query,
        brief.brand,
        brief.product,
        brief.objective,
        brief.audience,
        brief.content_format,
        brief.selling_angle,
        brief.tone,
        " ".join(brief.must_have_topics),
        " ".join(brief.creator_archetypes),
        " ".join(brief.hashtags),
    ])


def _clip10(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


def sentiment(text: str) -> float:
    toks = _tokens(text)
    if not toks:
        return 0.0
    pos = len(toks & {_norm(x) for x in _POSITIVE})
    neg = len(toks & {_norm(x) for x in _NEGATIVE})
    if pos == neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(1, pos + neg)))


def _evidence_text(c: InfluencerCandidate) -> str:
    return " ".join([c.bio, c.name, " ".join(c.categories), *[e.text for e in c.evidence], *[e.title for e in c.evidence]])


def _relevance(c: InfluencerCandidate, brief: CampaignBrief) -> float:
    keys = _keyword_set(brief)
    if not keys:
        return 0.0
    toks = _tokens(_evidence_text(c))
    overlap = len(keys & toks)
    # Normalise overlap against an absolute "strong match" target, not the total
    # key count. Semantic expansion can inflate the brief to 60+ keys, so dividing
    # by len(keys) silently dilutes a creator who genuinely hits 8 campaign terms.
    # We still respect sparse briefs by lowering the target when few keys exist.
    target = max(4, min(8, len(keys)))
    lexical = min(1.0, overlap / target) * 7.0
    semantic = _cosine(_weighted_tokens(_brief_text(brief)), _weighted_tokens(_evidence_text(c))) * 12.0
    return _clip10(lexical + semantic)


def _format_fit(c: InfluencerCandidate) -> float:
    posts = [e for e in c.evidence if e.kind in {"post", "reel"}]
    if not posts:
        return 2.0
    reelish = 0
    for e in posts:
        url = e.url.lower()
        metrics = e.metrics or {}
        text = _norm(e.text + " " + e.title)
        if "/reel" in url or metrics.get("video_views") or metrics.get("plays") or "reel" in text:
            reelish += 1
    return _clip10(3.0 + 7.0 * (reelish / max(1, len(posts))))


def expected_engagement_rate(followers: int | None) -> float:
    """Typical Instagram engagement-rate band for a follower tier.

    Shared by the engagement score and the UI so the dashboard can label a
    creator's ER as weak/normal/strong against the same benchmark the engine
    ranks on, instead of duplicating the thresholds in the frontend.
    """
    f = followers or 0
    if f < 20_000:
        return 0.055
    if f < 100_000:
        return 0.04
    if f < 500_000:
        return 0.025
    return 0.015


def engagement_band(followers: int | None, engagement_rate: float | None) -> str:
    """Qualitative ER label relative to the follower-tier benchmark."""
    if not engagement_rate or not followers:
        return "naməlum"
    ratio = engagement_rate / expected_engagement_rate(followers)
    if ratio >= 1.25:
        return "güclü"
    if ratio >= 0.75:
        return "normal"
    return "zəif"


def _engagement_quality(c: InfluencerCandidate) -> float:
    followers = c.followers or 0
    er = c.engagement_rate
    if not er and followers:
        er = (c.avg_likes + c.avg_comments) / followers
        c.engagement_rate = er
    if not followers:
        return 3.0 if (c.avg_likes or c.avg_comments or c.avg_views) else 1.0
    expected = expected_engagement_rate(followers)
    score = 6.0 * min(1.4, er / expected) / 1.4
    if c.avg_views and followers:
        score += 2.0 * min(1.5, c.avg_views / followers) / 1.5
    if c.avg_comments:
        score += 2.0 * min(1.0, c.avg_comments / max(10.0, c.avg_likes * 0.025))
    return _clip10(score)


def _feedback(c: InfluencerCandidate) -> float:
    comments = [e for e in c.evidence if e.kind == "comment" or e.metrics.get("is_comment")]
    if not comments:
        texts = [e.text for e in c.evidence if e.text]
    else:
        texts = [e.text for e in comments]
    vals = [sentiment(t) for t in texts if t]
    if not vals:
        return 5.0
    avg = sum(vals) / len(vals)
    return _clip10(5.0 + 5.0 * avg)


def _brand_safety(c: InfluencerCandidate, brief: CampaignBrief) -> float:
    text = _norm(_evidence_text(c))
    risky = sum(1 for w in _RISKY if _has_word(text, w))
    avoid = sum(1 for w in brief.avoid_topics if _has_word(text, w))
    score = 10.0 - 2.2 * risky - 1.6 * avoid
    if risky:
        c.flags.append("brend təhlükəsizliyi üçün riskli sözlər tapıldı")
    return _clip10(score)


def _authenticity(c: InfluencerCandidate) -> float:
    followers = c.followers or 0
    score = 7.0
    if followers and c.engagement_rate:
        if followers > 100_000 and c.engagement_rate < 0.004:
            score -= 3.0
            c.flags.append("böyük auditoriya fonunda engagement çox aşağıdır")
        if c.engagement_rate > 0.20:
            score -= 1.5
            c.flags.append("engagement qeyri-adi yüksəkdir; auditoriya keyfiyyətini yoxlayın")
        else:
            score += 1.0
    if c.avg_likes and c.avg_comments / max(1.0, c.avg_likes) < 0.004:
        score -= 1.0
        c.flags.append("rəy siqnalı zəifdir")
    bot_words = Counter()
    for e in c.evidence:
        if e.kind == "comment":
            bot_words.update(_tokens(e.text))
    generic = {"ela", "super", "gozel", "wow", "nice", "like"}
    if bot_words and sum(bot_words[w] for w in generic if w in bot_words) > max(6, sum(bot_words.values()) * 0.35):
        score -= 1.0
        c.flags.append("ümumi və təkrarlanan rəy klasteri var")
    return _clip10(score)


def _proof_density(c: InfluencerCandidate) -> float:
    score = 0.0
    score += min(4.0, len([e for e in c.evidence if e.kind in {"post", "reel"}]) * 0.8)
    score += min(3.0, len([e for e in c.evidence if e.kind == "comment"]) * 0.25)
    if c.bio:
        score += 1.0
    if c.followers:
        score += 1.0
    if any(e.url for e in c.evidence):
        score += 1.0
    return _clip10(score)


def _audience_fit(c: InfluencerCandidate, brief: CampaignBrief) -> float:
    base = _relevance(c, brief)
    market_words = {"azerbaijan", "baku", "azeri", "azərbaycan", "azerbaycan", "az"}
    text = _tokens(_evidence_text(c) + " " + c.handle)
    if text & {_norm(w) for w in market_words}:
        base += 1.5
    if c.followers:
        if 8_000 <= c.followers <= 250_000:
            base += 1.0
        elif c.followers > 1_000_000:
            base -= 0.6
    return _clip10(base)


def _summarize(c: InfluencerCandidate, brief: CampaignBrief) -> str:
    top = sorted(c.evidence, key=lambda e: (e.relevance, e.metrics.get("video_views", 0) or e.metrics.get("likes", 0) or 0), reverse=True)[:3]
    bits = []
    if c.audience_fit >= 7:
        bits.append("auditoriya uyğunluğu güclüdür")
    if c.content_fit >= 7:
        bits.append("Reels/video sübutu var")
    if c.feedback_sentiment >= 6.5:
        bits.append("izləyici reaksiyası müsbətdir")
    if c.brand_safety >= 8:
        bits.append("brend təhlükəsizliyi riski aşağıdır")
    if top:
        bits.append(f"{len(top)} uyğun sübut bu seçimi dəstəkləyir")
    if not bits:
        bits.append("uyğunluq məhdud sübuta əsaslanır")
    return "; ".join(bits) + "."


def weighted_total(c: InfluencerCandidate) -> float:
    """Single source of truth for the 0..10 weighted score.

    Exposed so later stages (e.g. the audience-analysis layer that revises
    feedback_sentiment) can recompute the total without duplicating weights.
    """
    return _clip10(
        c.audience_fit * 0.21
        + c.content_fit * 0.23
        + c.engagement_quality * 0.16
        + c.feedback_sentiment * 0.14
        + c.brand_safety * 0.14
        + c.authenticity * 0.09
        + c.proof_density * 0.03
    )


def score_candidates(candidates: list[InfluencerCandidate], brief: CampaignBrief) -> list[InfluencerCandidate]:
    for c in candidates:
        for e in c.evidence:
            e.sentiment = sentiment(e.text)
            e.relevance = _clip10((len(_keyword_set(brief) & _tokens(e.text + " " + e.title)) / 8.0) * 10)
        c.audience_fit = _audience_fit(c, brief)
        c.content_fit = _clip10((_relevance(c, brief) * 0.55) + (_format_fit(c) * 0.45))
        c.engagement_quality = _engagement_quality(c)
        c.feedback_sentiment = _feedback(c)
        c.brand_safety = _brand_safety(c, brief)
        c.authenticity = _authenticity(c)
        c.proof_density = _proof_density(c)
        c.influence_power = _clip10(math.sqrt(max(c.followers or 0, 1)) / math.sqrt(250_000) * 5 + c.engagement_quality * 0.5)
        c.total_score = weighted_total(c)
        c.flags = list(dict.fromkeys(c.flags))
        c.proof_summary = _summarize(c, brief)
    candidates.sort(key=lambda x: (x.total_score, x.proof_density, x.engagement_quality), reverse=True)
    return candidates


def shortlist(candidates: list[InfluencerCandidate], n: int = 3, min_score: float = 0.0) -> list[InfluencerCandidate]:
    return [c for c in candidates if c.total_score >= min_score][:n]
