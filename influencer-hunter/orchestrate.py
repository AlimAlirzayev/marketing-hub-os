"""Multi-source acquisition orchestrator.

Turns individual source connectors into one resilient acquisition layer:

  * a formal Connector contract + registry,
  * fan-out across platforms (run in parallel),
  * a fallback chain within a platform (try by priority, stop at first data — so
    we never double-spend a paid provider when a free one already answered),
  * within-platform dedup/merge by handle,
  * honest aggregated source status (no silent drops).

Cross-platform identities are deliberately NOT auto-merged: the same handle on
Instagram and YouTube can be different people, so a wrong merge would corrupt the
shortlist. Candidates from different platforms stay distinct (each keeps its
`platform`); only same-(platform, handle) records are merged.

hunt.py calls ``collect()``; connectors normalize to the shared models, so
scoring / analysis / filters / UI remain source-agnostic.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

import config
import sources
import sources_rapidapi
import sources_telegram
import sources_web
import sources_youtube
from models import CampaignBrief, InfluencerCandidate, SourceStatus

CollectFn = Callable[..., "tuple[list[InfluencerCandidate], list[SourceStatus], int]"]


@dataclass(frozen=True)
class Connector:
    name: str
    platform: str
    collect: CollectFn
    available: Callable[[], bool]
    cost: str = "free"      # free | freemium | paid
    priority: int = 100     # lower runs first within a platform (fallback order)


# Late-bound lambdas so monkeypatching the underlying module functions (tests,
# or a swapped implementation) takes effect without rebuilding the registry.
REGISTRY: list[Connector] = [
    Connector(
        "instagram-apify", "instagram",
        lambda brief, **kw: sources.collect(brief, **kw),
        lambda: bool(config.APIFY_API_TOKEN),
        cost="paid", priority=10,
    ),
    # RapidAPI revives Instagram without Apify; priority 20 = fallback, so it only
    # runs when Apify is unavailable or returns nothing (no double-spend).
    Connector(
        "instagram-rapidapi", "instagram",
        lambda brief, **kw: sources_rapidapi.collect(brief, platform="instagram", **kw),
        lambda: sources_rapidapi.available(),
        cost="freemium", priority=20,
    ),
    Connector(
        "tiktok-rapidapi", "tiktok",
        lambda brief, **kw: sources_rapidapi.collect(brief, platform="tiktok", **kw),
        lambda: sources_rapidapi.available(),
        cost="freemium", priority=10,
    ),
    Connector(
        "youtube", "youtube",
        lambda brief, **kw: sources_youtube.collect(brief, **kw),
        lambda: sources_youtube.available(),
        cost="free", priority=10,
    ),
    Connector(
        "web", "web",
        lambda brief, **kw: sources_web.collect(brief, **kw),
        lambda: sources_web.available(),
        cost="free", priority=10,
    ),
    Connector(
        "telegram", "telegram",
        lambda brief, **kw: sources_telegram.collect(brief, **kw),
        lambda: sources_telegram.available(),
        cost="free", priority=10,
    ),
]

_ALL_TOKENS = {"all", "*", "hamısı", "hamisi", "hamı", "hami"}


def platforms() -> list[str]:
    return list(dict.fromkeys(c.platform for c in REGISTRY))


def resolve_platforms(source: str | None) -> list[str]:
    """Map a source string to platform names. Accepts a single name, a
    comma-separated list, or 'all'. Unknown names fall back to instagram."""
    s = (source or "instagram").strip().lower()
    valid = platforms()
    if s in _ALL_TOKENS:
        return valid
    requested = [p.strip() for p in s.split(",") if p.strip()]
    out = [p for p in requested if p in valid]
    return out or ["instagram"]


def _merge_by_handle(candidates: list[InfluencerCandidate]) -> list[InfluencerCandidate]:
    """Merge records that are the same creator on the same platform."""
    merged: dict[tuple[str, str], InfluencerCandidate] = {}
    for c in candidates:
        key = (c.platform, c.handle)
        existing = merged.get(key)
        if existing is None:
            merged[key] = c
            continue
        existing.evidence.extend(c.evidence)
        existing.followers = existing.followers or c.followers
        existing.bio = existing.bio or c.bio
        existing.avatar = existing.avatar or c.avatar
        existing.country = existing.country or c.country
        existing.name = existing.name or c.name
        existing.categories = list(dict.fromkeys([*existing.categories, *c.categories]))
    return list(merged.values())


def _run_platform(
    platform: str,
    brief: CampaignBrief,
    seed_handles: list[str] | None,
    deep_comments: bool,
) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    """Fallback chain for one platform: try connectors by priority, stop at the
    first that returns candidates. If none are 'available', still call the
    primary once so it can report its gap honestly (no silent drop)."""
    conns = sorted([c for c in REGISTRY if c.platform == platform], key=lambda c: c.priority)
    if not conns:
        return [], [SourceStatus(platform, "skipped", "uyğun connector yoxdur")], 0

    statuses: list[SourceStatus] = []
    seen = 0
    used_available = False
    for conn in conns:
        if not conn.available():
            continue
        used_available = True
        try:
            cands, st, n = conn.collect(brief, seed_handles=seed_handles, deep_comments=deep_comments)
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(conn.name, f"error:{type(exc).__name__}", str(exc)[:140]))
            continue
        statuses.extend(st)
        seen += n
        if cands:
            return cands, statuses, seen  # fallback satisfied; don't try cheaper-priority providers
    if not used_available:
        primary = conns[0]
        try:
            cands, st, n = primary.collect(brief, seed_handles=seed_handles, deep_comments=deep_comments)
            statuses.extend(st)
            seen += n
            return cands, statuses, seen
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(primary.name, f"error:{type(exc).__name__}", str(exc)[:140]))
    return [], statuses, seen


def collect(
    brief: CampaignBrief,
    *,
    source: str = "instagram",
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    plats = resolve_platforms(source)

    if len(plats) == 1:
        results = [_run_platform(plats[0], brief, seed_handles, deep_comments)]
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(plats))) as pool:
            futures = [pool.submit(_run_platform, p, brief, seed_handles, deep_comments) for p in plats]
            results = [f.result() for f in futures]

    all_candidates: list[InfluencerCandidate] = []
    all_statuses: list[SourceStatus] = []
    total_seen = 0
    for cands, statuses, seen in results:
        all_candidates.extend(cands)
        all_statuses.extend(statuses)
        total_seen += seen

    all_candidates = _merge_by_handle(all_candidates)
    if len(plats) > 1:
        all_statuses.append(SourceStatus(
            "orkestrator", "ok",
            f"{len(plats)} platforma birləşdirildi ({', '.join(plats)}); {len(all_candidates)} unikal namizəd",
        ))
    return all_candidates, all_statuses, total_seen
