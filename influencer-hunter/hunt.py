"""Pipeline orchestrator for Influencer Hunter."""

from __future__ import annotations

import asyncio

import config
import ai_eval
import analyze
import filters as filters_mod
import llm
import orchestrate
import resolve as resolve_mod
import score as score_mod
from models import CampaignBrief, HuntResult, InfluencerCandidate, SelectionFilters, SourceStatus

_VERDICT_SYSTEM = """You are a sharp Azerbaijani influencer marketing strategist.
Given a campaign brief and ranked candidates, write a short Azerbaijani verdict.
Explain the best 3 choices with concrete proof: audience fit, content/reels
evidence, feedback signal, brand safety, and the one risk to verify.
Do not invent evidence, follower numbers, posts, comments, or URLs.
Do not use Markdown formatting. Keep it under 180 words."""


def _candidate_line(c: InfluencerCandidate) -> str:
    ev = []
    for e in sorted(c.evidence, key=lambda x: (x.relevance, x.metrics.get("video_views", 0), x.metrics.get("likes", 0)), reverse=True)[:3]:
        metric = e.metrics or {}
        ev.append(
            f"{e.kind} url={e.url or '-'} likes={metric.get('likes', 0)} "
            f"comments={metric.get('comments', 0)} views={metric.get('video_views', 0)} "
            f"text={e.text[:180]!r}"
        )
    return (
        f"@{c.handle} | name={c.name} | followers={c.followers} | "
        f"score={c.total_score}/10 | audience={c.audience_fit} content={c.content_fit} "
        f"engagement={c.engagement_quality} feedback={c.feedback_sentiment} "
        f"safety={c.brand_safety} authenticity={c.authenticity} | "
        f"summary={c.proof_summary} | evidence: " + " || ".join(ev)
    )


def _verdict(brief: CampaignBrief, shortlist: list[InfluencerCandidate]) -> str:
    if not shortlist or not llm.available():
        return ""
    prompt = (
        f"BRIEF:\n{brief.to_dict()}\n\n"
        "RANKED CANDIDATES:\n"
        + "\n".join(f"{i+1}. {_candidate_line(c)}" for i, c in enumerate(shortlist))
    )
    try:
        return llm.complete(prompt, system=_VERDICT_SYSTEM, temperature=0.25)
    except Exception:
        return ""


def _run_pipeline(
    query: str,
    *,
    source: str = "instagram",
    top_n: int = 3,
    min_score: float = 0.0,
    min_followers: int | None = None,
    allow_unknown_followers: bool = False,
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
    do_verdict: bool = True,
) -> HuntResult:
    config.ensure_dirs()
    brief = resolve_mod.resolve(query)
    if seed_handles:
        brief.seed_handles = list(dict.fromkeys([*brief.seed_handles, *seed_handles]))

    candidates, statuses, seen = orchestrate.collect(
        brief, source=source, seed_handles=seed_handles, deep_comments=deep_comments,
    )
    rejected = len([c for c in candidates if not c.evidence and not c.followers])
    ranked = score_mod.score_candidates(candidates, brief)
    # Audience-analysis layer: pandas + LLM Azerbaijani sentiment on real comment
    # text (any source). It revises feedback_sentiment, so recompute the total.
    if deep_comments:
        ranked = analyze.enrich(brief, ranked)
        for c in ranked:
            c.total_score = score_mod.weighted_total(c)
        ranked.sort(key=lambda x: (x.total_score, x.proof_density, x.engagement_quality), reverse=True)
    ranked = ai_eval.apply_ai_evaluation(brief, ranked)
    selection_filters = SelectionFilters(
        min_followers=max(0, int(config.DEFAULT_MIN_FOLLOWERS if min_followers is None else min_followers)),
        min_score=max(0.0, float(min_score or 0.0)),
        allow_unknown_followers=allow_unknown_followers,
    )
    eligible, filtered_out = filters_mod.apply_eligibility(ranked, selection_filters)
    min_pick_score = max(selection_filters.min_score, selection_filters.min_recommendation_score)
    picks = score_mod.shortlist(eligible, n=top_n, min_score=min_pick_score)
    if filtered_out:
        statuses.append(SourceStatus(
            "seçim filteri",
            "ok",
            f"{len(filtered_out)} namizəd filterdən kənar qaldı; minimum izləyici={selection_filters.min_followers:,}",
        ))
    if ai_eval.ENABLE_AI_EVAL and llm.available() and ranked:
        statuses.append(SourceStatus(
            "LLM adjudication",
            "ok",
            f"top {min(len(ranked), ai_eval.MAX_AI_CANDIDATES)} namizəd sübut əsasında yenidən qiymətləndirildi",
        ))
    if not picks and ranked:
        statuses.append(SourceStatus("seçim siyahısı", "empty", "Aktiv filterlərdən keçən namizəd yoxdur; filterdən kənar hesablara baxın və ya filterləri yumşaldın"))
    verdict = _verdict(brief, picks) if do_verdict else ""
    return HuntResult(
        query=query,
        brief=brief,
        filters=selection_filters,
        candidates=eligible,
        filtered_out=filtered_out,
        shortlist=picks,
        verdict=verdict,
        source_status=statuses,
        total_seen=seen,
        rejected=rejected,
    )


async def hunt(
    query: str,
    *,
    source: str = "instagram",
    top_n: int = 3,
    min_score: float = 0.0,
    min_followers: int | None = None,
    allow_unknown_followers: bool = False,
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
    do_verdict: bool = True,
) -> HuntResult:
    """Run the (synchronous, I/O-heavy) pipeline off the event loop.

    Apify/YouTube scraping and LLM calls are blocking; offloading to a worker
    thread keeps the FastAPI server responsive (e.g. /api/health) while a hunt runs.
    """
    return await asyncio.to_thread(
        _run_pipeline,
        query,
        source=source,
        top_n=top_n,
        min_score=min_score,
        min_followers=min_followers,
        allow_unknown_followers=allow_unknown_followers,
        seed_handles=seed_handles,
        deep_comments=deep_comments,
        do_verdict=do_verdict,
    )
