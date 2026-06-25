"""FastAPI backend for Influencer Hunter.

Run:
    .venv/Scripts/python -m uvicorn server:app --port 8840
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import decision
import score
from hunt import hunt

config.ensure_dirs()

app = FastAPI(title="Influencer Hunter", docs_url="/api/docs")
_STATIC = os.path.join(config.BASE, "static")
os.makedirs(_STATIC, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


class HuntRequest(BaseModel):
    query: str
    source: str = "instagram"
    top_n: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.0, ge=0.0, le=10.0)
    min_followers: int = Field(default=config.DEFAULT_MIN_FOLLOWERS, ge=0)
    allow_unknown_followers: bool = False
    seed_handles: list[str] = Field(default_factory=list)
    deep_comments: bool = True
    verdict: bool = True


def _evidence_dict(e) -> dict:
    return {
        "kind": e.kind,
        "url": e.url,
        "source": e.source,
        "title": e.title,
        "text": e.text,
        "author": e.author,
        "created_at": e.created_at,
        "metrics": e.metrics,
        "sentiment": round(e.sentiment, 3),
        "relevance": round(e.relevance, 2),
        "reason": e.reason,
    }


def _candidate_dict(c) -> dict:
    idx = getattr(c, "_decision_index", 99)
    return {
        "handle": c.handle,
        "name": c.name,
        "platform": c.platform,
        "url": c.url or f"https://www.instagram.com/{c.handle}/",
        "avatar": c.avatar,
        "bio": c.bio,
        "followers": c.followers,
        "following": c.following,
        "posts_count": c.posts_count,
        "avg_likes": round(c.avg_likes, 1),
        "avg_comments": round(c.avg_comments, 1),
        "avg_views": round(c.avg_views, 1),
        "engagement_rate": round(c.engagement_rate, 4),
        "engagement_band": score.engagement_band(c.followers, c.engagement_rate),
        "categories": c.categories,
        "country": c.country,
        "contact": c.contact,
        "audience_summary": c.audience_summary,
        "flags": c.flags,
        "scores": {
            "audience_fit": c.audience_fit,
            "content_fit": c.content_fit,
            "engagement_quality": c.engagement_quality,
            "feedback_sentiment": c.feedback_sentiment,
            "brand_safety": c.brand_safety,
            "authenticity": c.authenticity,
            "proof_density": c.proof_density,
            "influence_power": c.influence_power,
            "market_fit": c.market_fit,
            "ai_fit": c.ai_fit,
            "total": c.total_score,
        },
        "market_reasons": c.market_reasons,
        "ai_reasons": c.ai_reasons,
        "ai_verdict": c.ai_verdict,
        "decision": decision.candidate_decision(c, idx),
        "proof_summary": c.proof_summary,
        "evidence": [_evidence_dict(e) for e in c.evidence],
    }


def _payload(res) -> dict:
    for i, c in enumerate(res.shortlist):
        setattr(c, "_decision_index", i)
    shortlist_handles = {c.handle for c in res.shortlist}
    for i, c in enumerate([x for x in res.candidates if x.handle not in shortlist_handles], len(res.shortlist)):
        setattr(c, "_decision_index", i)
    return {
        "query": res.query,
        "brief": res.brief.to_dict(),
        "filters": res.filters.to_dict(),
        "decision": decision.result_decision(res),
        "verdict": res.verdict,
        "shortlist": [_candidate_dict(c) for c in res.shortlist],
        "candidates": [_candidate_dict(c) for c in res.candidates],
        "filtered_out": [_candidate_dict(c) for c in res.filtered_out],
        "coverage": [s.to_dict() for s in res.source_status],
        "totals": {
            "seen": res.total_seen,
            "ranked": len(res.candidates),
            "filtered_out": len(res.filtered_out),
            "shortlisted": len(res.shortlist),
            "rejected": res.rejected,
        },
        "engines": config.engine_status(),
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/api/health")
def health():
    return {"ok": True, **config.engine_status()}


@app.post("/api/hunt")
async def api_hunt(req: HuntRequest):
    if not req.query.strip():
        return JSONResponse({"error": "empty query"}, status_code=400)
    res = await hunt(
        req.query.strip(),
        source=req.source,
        top_n=req.top_n,
        min_score=req.min_score,
        min_followers=req.min_followers,
        allow_unknown_followers=req.allow_unknown_followers,
        seed_handles=req.seed_handles,
        deep_comments=req.deep_comments,
        do_verdict=req.verdict,
    )
    return _payload(res)


@app.get("/api/hunt")
async def api_hunt_get(
    q: str,
    source: str = "instagram",
    top_n: int = 3,
    min_score: float = 0.0,
    min_followers: int = config.DEFAULT_MIN_FOLLOWERS,
    allow_unknown_followers: bool = False,
    deep_comments: bool = True,
    verdict: bool = True,
):
    return await api_hunt(HuntRequest(
        query=q,
        source=source,
        top_n=top_n,
        min_score=min_score,
        min_followers=min_followers,
        allow_unknown_followers=allow_unknown_followers,
        deep_comments=deep_comments,
        verdict=verdict,
    ))
