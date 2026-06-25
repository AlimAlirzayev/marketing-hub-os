"""Shared dataclasses for Influencer Hunter.

The module keeps the whole pipeline speaking one vocabulary: campaign brief,
evidence, candidate profile, and final hunt result. Scores are normalized to a
0..10 scale because the user-facing question is "who deserves 10 stars?".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CampaignBrief:
    query: str
    brand: str = ""
    product: str = ""
    objective: str = ""
    audience: str = "Azerbaijan Instagram audience"
    market: str = "Azerbaijan"
    language: str = "az"
    content_format: str = "Instagram Reel"
    selling_angle: str = ""
    tone: str = "natural, emotional, credible"
    must_have_topics: list[str] = field(default_factory=list)
    avoid_topics: list[str] = field(default_factory=list)
    creator_archetypes: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    seed_handles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceItem:
    kind: str
    url: str = ""
    source: str = "instagram"
    title: str = ""
    text: str = ""
    author: str = ""
    created_at: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    sentiment: float = 0.0
    relevance: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InfluencerCandidate:
    handle: str
    name: str = ""
    platform: str = "instagram"
    url: str = ""
    avatar: str = ""
    bio: str = ""
    followers: int | None = None
    following: int | None = None
    posts_count: int | None = None
    avg_likes: float = 0.0
    avg_comments: float = 0.0
    avg_views: float = 0.0
    engagement_rate: float = 0.0
    categories: list[str] = field(default_factory=list)
    country: str = ""
    contact: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    audience_fit: float = 0.0
    content_fit: float = 0.0
    engagement_quality: float = 0.0
    feedback_sentiment: float = 0.0
    brand_safety: float = 0.0
    authenticity: float = 0.0
    proof_density: float = 0.0
    influence_power: float = 0.0
    market_fit: float = 0.0
    market_reasons: list[str] = field(default_factory=list)
    ai_fit: float = 0.0
    ai_reasons: list[str] = field(default_factory=list)
    ai_verdict: str = ""
    audience_summary: str = ""
    total_score: float = 0.0
    proof_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [e.to_dict() for e in self.evidence]
        return data


@dataclass
class SourceStatus:
    source: str
    status: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SelectionFilters:
    min_followers: int = 20_000
    min_score: float = 0.0
    min_recommendation_score: float = 6.0
    allow_unknown_followers: bool = False
    require_human_creator: bool = True
    require_local_market: bool = True
    require_campaign_fit: bool = True
    min_audience_fit: float = 5.0
    min_content_fit: float = 5.0
    min_proof_density: float = 3.0
    exclude_competitors: bool = True
    exclude_corporate_accounts: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HuntResult:
    query: str
    brief: CampaignBrief
    filters: SelectionFilters = field(default_factory=SelectionFilters)
    candidates: list[InfluencerCandidate] = field(default_factory=list)
    filtered_out: list[InfluencerCandidate] = field(default_factory=list)
    shortlist: list[InfluencerCandidate] = field(default_factory=list)
    verdict: str = ""
    source_status: list[SourceStatus] = field(default_factory=list)
    total_seen: int = 0
    rejected: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "brief": self.brief.to_dict(),
            "filters": self.filters.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "filtered_out": [c.to_dict() for c in self.filtered_out],
            "shortlist": [c.to_dict() for c in self.shortlist],
            "verdict": self.verdict,
            "source_status": [s.to_dict() for s in self.source_status],
            "totals": {
                "seen": self.total_seen,
                "ranked": len(self.candidates),
                "filtered_out": len(self.filtered_out),
                "shortlisted": len(self.shortlist),
                "rejected": self.rejected,
            },
        }
