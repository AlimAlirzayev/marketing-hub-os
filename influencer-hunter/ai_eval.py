"""LLM adjudication for shortlisted influencer candidates.

The deterministic/vector layer is fast and explainable. This layer adds the
more human judgment the user asked for: does the collected proof actually show
that this person fits the campaign intent?
"""

from __future__ import annotations

import json
import os

import llm
from models import CampaignBrief, InfluencerCandidate

MAX_AI_CANDIDATES = int(os.getenv("IH_AI_EVAL_LIMIT", "8"))
ENABLE_AI_EVAL = os.getenv("IH_ENABLE_AI_EVAL", "1").lower() not in {"0", "false", "no", "off"}

_SYSTEM = """You are an Azerbaijani influencer intelligence analyst.
Evaluate influencer candidates for the exact campaign brief using only supplied
profile, metric, post/Reels, and comment evidence. Return strict JSON:
{"candidates":[{"handle":"...","campaign_fit":0-10,"market_fit":0-10,
"audience_fit":0-10,"content_fit":0-10,"feedback_quality":0-10,
"brand_safety":0-10,"authenticity":0-10,"influence_power":0-10,
"is_local_market":true/false,"is_human_creator":true/false,
"recommend":true/false,"reasons":["..."],"risks":["..."],"verdict":"..."}]}
Do not invent facts. Penalize off-topic creators, foreign-market creators,
corporate/brand pages, aggregators, competitors, and weak evidence. If evidence
is insufficient, recommend=false.
IMPORTANT: write every "reasons", "risks" and "verdict" string in Azerbaijani
(Azərbaycan dilində), because they are shown directly to an Azerbaijani user.
The numeric scores and boolean fields stay as specified."""


def _evidence_pack(c: InfluencerCandidate) -> list[dict]:
    out = []
    for e in sorted(
        c.evidence,
        key=lambda x: (x.relevance, x.metrics.get("video_views", 0), x.metrics.get("likes", 0)),
        reverse=True,
    )[:8]:
        out.append({
            "kind": e.kind,
            "url": e.url,
            "text": e.text[:600],
            "metrics": {
                "likes": e.metrics.get("likes", 0),
                "comments": e.metrics.get("comments", 0),
                "views": e.metrics.get("video_views", 0),
            },
            "relevance": e.relevance,
            "sentiment": e.sentiment,
        })
    return out


def _candidate_pack(c: InfluencerCandidate) -> dict:
    return {
        "handle": c.handle,
        "name": c.name,
        "bio": c.bio,
        "categories": c.categories,
        "contact": c.contact,
        "followers": c.followers,
        "posts_count": c.posts_count,
        "engagement_rate": c.engagement_rate,
        "avg_likes": c.avg_likes,
        "avg_comments": c.avg_comments,
        "avg_views": c.avg_views,
        "deterministic_scores": {
            "market_fit": c.market_fit,
            "audience_fit": c.audience_fit,
            "content_fit": c.content_fit,
            "engagement_quality": c.engagement_quality,
            "feedback_sentiment": c.feedback_sentiment,
            "brand_safety": c.brand_safety,
            "authenticity": c.authenticity,
            "proof_density": c.proof_density,
            "influence_power": c.influence_power,
            "total": c.total_score,
        },
        "market_reasons": c.market_reasons,
        "flags": c.flags,
        "evidence": _evidence_pack(c),
    }


def _clip(value, default: float = 0.0) -> float:
    try:
        return round(max(0.0, min(10.0, float(value))), 2)
    except Exception:
        return default


def apply_ai_evaluation(brief: CampaignBrief, candidates: list[InfluencerCandidate]) -> list[InfluencerCandidate]:
    if not ENABLE_AI_EVAL or not llm.available() or not candidates:
        return candidates
    scoped = candidates[:MAX_AI_CANDIDATES]
    payload = {
        "brief": brief.to_dict(),
        "candidates": [_candidate_pack(c) for c in scoped],
    }
    data = llm.complete_json(
        json.dumps(payload, ensure_ascii=False),
        system=_SYSTEM,
        temperature=0.05,
        default=None,
    )
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return candidates
    by_handle = {c.handle: c for c in scoped}
    for item in data.get("candidates", []):
        if not isinstance(item, dict):
            continue
        handle = str(item.get("handle") or "").lstrip("@").lower()
        c = by_handle.get(handle)
        if not c:
            continue
        c.ai_fit = _clip(item.get("campaign_fit"))
        c.ai_reasons = [str(x)[:180] for x in item.get("reasons", []) if str(x).strip()][:5]
        risks = [str(x)[:180] for x in item.get("risks", []) if str(x).strip()]
        c.ai_verdict = str(item.get("verdict") or "")[:500]
        c.market_fit = max(c.market_fit, _clip(item.get("market_fit"), c.market_fit))
        c.audience_fit = round((c.audience_fit * 0.55) + (_clip(item.get("audience_fit"), c.audience_fit) * 0.45), 2)
        c.content_fit = round((c.content_fit * 0.55) + (_clip(item.get("content_fit"), c.content_fit) * 0.45), 2)
        c.feedback_sentiment = round((c.feedback_sentiment * 0.65) + (_clip(item.get("feedback_quality"), c.feedback_sentiment) * 0.35), 2)
        c.brand_safety = round((c.brand_safety * 0.65) + (_clip(item.get("brand_safety"), c.brand_safety) * 0.35), 2)
        c.authenticity = round((c.authenticity * 0.65) + (_clip(item.get("authenticity"), c.authenticity) * 0.35), 2)
        c.influence_power = round((c.influence_power * 0.7) + (_clip(item.get("influence_power"), c.influence_power) * 0.3), 2)
        if item.get("is_local_market") is False:
            c.flags.append("LLM: Azərbaycan/local bazar uyğunluğu zəifdir")
        if item.get("is_human_creator") is False:
            c.flags.append("LLM: fərdi creator deyil")
        if item.get("recommend") is False:
            c.flags.append("LLM: final tövsiyə üçün sübut yetərsizdir")
        for risk in risks[:3]:
            c.flags.append(f"LLM risk: {risk}")
        c.total_score = round(
            c.total_score * 0.70
            + c.ai_fit * 0.30,
            2,
        )
        c.flags = list(dict.fromkeys(c.flags))
    candidates.sort(key=lambda x: (x.total_score, x.ai_fit, x.proof_density, x.engagement_quality), reverse=True)
    return candidates
