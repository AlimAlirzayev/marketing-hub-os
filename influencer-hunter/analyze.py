"""Platform-agnostic audience analysis layer.

This is the "engineering answer" to deep sentiment: once comment text exists
(from any connector — YouTube, owned Meta media, web), pandas does the objective
aggregation and an optional LLM adds nuanced Azerbaijani sentiment + themes. It
never fetches data; it only makes collected text valuable, so it works identically
across every source.
"""

from __future__ import annotations

import json

import pandas as pd

import llm
import score as score_mod
from models import CampaignBrief, InfluencerCandidate

_SYSTEM = """You are an audience-sentiment analyst for influencer marketing in Azerbaijan.
Given each creator's real audience comments (mixed Azerbaijani/English), assess how the
audience actually reacts. Return strict JSON:
{"results":[{"handle":"...","sentiment":-1..1,"positive_ratio":0..1,
"authenticity_flag":true/false,"themes":["..."],"summary_az":"..."}]}
sentiment: overall tone. authenticity_flag: true if the comments look bot-like,
spammy, repetitive or purchased. themes: 2-4 short topic tags. summary_az: ONE
Azerbaijani sentence describing the audience reaction. Do not invent comments."""


def _clip10(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


def _comments_df(candidates: list[InfluencerCandidate]) -> pd.DataFrame:
    rows = []
    for c in candidates:
        for e in c.evidence:
            if (e.kind == "comment" or e.metrics.get("is_comment")) and e.text:
                rows.append({
                    "handle": c.handle,
                    "text": e.text[:500],
                    "likes": e.metrics.get("likes", 0) or 0,
                    "author": e.author or "",
                })
    return pd.DataFrame(rows, columns=["handle", "text", "likes", "author"])


def _deterministic(group: pd.DataFrame) -> dict:
    """Objective, LLM-free stats — the deterministic backbone of the analysis."""
    n = len(group)
    sentiments = group["text"].map(score_mod.sentiment)
    norm = group["text"].str.lower().str.strip()
    dup_ratio = 1.0 - (norm.nunique() / n) if n else 0.0
    return {
        "count": n,
        "mean_sentiment": float(sentiments.mean()) if n else 0.0,
        "positive_ratio": float((sentiments > 0).mean()) if n else 0.0,
        "dup_ratio": float(dup_ratio),
        "avg_likes": float(group["likes"].mean()) if n else 0.0,
    }


def _llm_results(df: pd.DataFrame) -> dict:
    if not llm.available():
        return {}
    payload = {h: g["text"].tolist()[:25] for h, g in df.groupby("handle")}
    data = llm.complete_json(json.dumps(payload, ensure_ascii=False), system=_SYSTEM, temperature=0.1, default=None)
    out: dict = {}
    if isinstance(data, dict):
        for item in data.get("results", []):
            if isinstance(item, dict) and item.get("handle"):
                out[str(item["handle"]).lstrip("@").lower()] = item
    return out


def enrich(brief: CampaignBrief, candidates: list[InfluencerCandidate]) -> list[InfluencerCandidate]:
    df = _comments_df(candidates)
    if df.empty:
        return candidates
    by_handle = {c.handle: c for c in candidates}
    llm_map = _llm_results(df)

    for handle, group in df.groupby("handle"):
        c = by_handle.get(handle)
        if not c:
            continue
        stats = _deterministic(group)
        item = llm_map.get(str(handle).lower())
        if item:
            sentiment = max(-1.0, min(1.0, float(item.get("sentiment", stats["mean_sentiment"]))))
            summary = str(item.get("summary_az") or "")
            themes = [str(t) for t in (item.get("themes") or [])][:4]
            auth_flag = bool(item.get("authenticity_flag"))
            pos_ratio = float(item.get("positive_ratio", stats["positive_ratio"]))
        else:
            sentiment = stats["mean_sentiment"]
            summary, themes = "", []
            auth_flag = stats["dup_ratio"] > 0.4
            pos_ratio = stats["positive_ratio"]

        c.feedback_sentiment = _clip10(5.0 + 5.0 * sentiment)
        bits = []
        if summary:
            bits.append(summary)
        bits.append(f"{stats['count']} rəy · müsbət {pos_ratio * 100:.0f}%")
        if themes:
            bits.append("mövzular: " + ", ".join(themes))
        c.audience_summary = " · ".join(bits)
        if auth_flag or stats["dup_ratio"] > 0.5:
            c.flags.append("rəylərdə bot/təkrar şübhəsi (analiz qatı)")
            c.flags = list(dict.fromkeys(c.flags))
    return candidates
