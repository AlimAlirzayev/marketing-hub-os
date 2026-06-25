"""Generic RapidAPI connector — one key, many social hosts (free tiers).

Why this exists: RapidAPI issues a single ``X-RapidAPI-Key`` that unlocks *every*
host you subscribe to. That makes it the cheapest way off Apify — the same key
revives **Instagram** profile/post enrichment (what Apify did) and adds
**TikTok**, with no Docker, no account pool, and no ban risk on our side (the host
operator owns the scraping infrastructure).

Design — a declarative *host-adapter registry*. RapidAPI has hundreds of social
hosts and every one returns a slightly different JSON shape. Instead of hard-coding
one provider's schema (which breaks the moment the user subscribes to a different
host), each adapter is a small field-map and the extractor tries several key paths
per field. Add a host by appending one ``RapidAdapter`` — no new code path.

Role in the mesh: this is primarily an **enrichment** connector. Give it handles
(seed handles, or handles discovered by the web/telegram connectors) and it
returns a real profile + recent posts. Discovery stays with web/youtube/telegram;
enrichment turns their leads into ranked, evidence-backed candidates.

Without ``RAPIDAPI_KEY`` it degrades honestly (reports the gap), exactly like the
Apify connector does without credits — never a silent drop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

import config
from models import CampaignBrief, EvidenceItem, InfluencerCandidate, SourceStatus


@dataclass(frozen=True)
class RapidAdapter:
    """One RapidAPI host. Field paths are dotted (``data.user.stats.followerCount``);
    the first path that resolves to a value wins, so minor schema drift between
    similar hosts does not break extraction."""
    name: str
    host: str
    platform: str                      # instagram | tiktok
    profile_path: str                  # "{user}" placeholder, query string included
    posts_path: str = ""               # optional; "" disables post evidence
    profile_root: tuple[str, ...] = ()  # dig into this before reading profile fields
    p_username: tuple[str, ...] = ()
    p_name: tuple[str, ...] = ()
    p_bio: tuple[str, ...] = ()
    p_followers: tuple[str, ...] = ()
    p_posts_count: tuple[str, ...] = ()
    p_avatar: tuple[str, ...] = ()
    p_verified: tuple[str, ...] = ()
    posts_list: tuple[str, ...] = ()    # dig to the list of post objects
    pp_text: tuple[str, ...] = ()
    pp_likes: tuple[str, ...] = ()
    pp_comments: tuple[str, ...] = ()
    pp_views: tuple[str, ...] = ()
    pp_url: tuple[str, ...] = ()
    pp_code: tuple[str, ...] = ()       # shortcode/id -> build url via url_for
    post_kind: str = "post"


# --- Built-in adapters (real, documented host shapes; add more freely) ---
# Instagram primary: social-api's instagram-scraper-api2 (popular free tier).
_IG_SCRAPER_API2 = RapidAdapter(
    name="instagram-scraper-api2", host="instagram-scraper-api2.p.rapidapi.com",
    platform="instagram",
    profile_path="/v1/info?username_or_id_or_url={user}",
    posts_path="/v1.2/posts?username_or_id_or_url={user}",
    profile_root=("data",),
    p_username=("username",), p_name=("full_name",), p_bio=("biography",),
    p_followers=("follower_count",), p_posts_count=("media_count",),
    p_avatar=("profile_pic_url_hd", "profile_pic_url"), p_verified=("is_verified",),
    posts_list=("data.items",),
    pp_text=("caption.text", "caption_text"), pp_likes=("like_count",),
    pp_comments=("comment_count",), pp_views=("play_count", "view_count"),
    pp_code=("code", "shortcode"), post_kind="post",
)
# Instagram fallback: instagram-best-experience (GraphQL-shaped response).
_IG_BEST_EXPERIENCE = RapidAdapter(
    name="instagram-best-experience", host="instagram-best-experience.p.rapidapi.com",
    profile_path="/profile?username={user}", platform="instagram",
    p_username=("username",), p_name=("full_name",), p_bio=("biography",),
    p_followers=("edge_followed_by.count", "follower_count"),
    p_posts_count=("edge_owner_to_timeline_media.count", "media_count"),
    p_avatar=("profile_pic_url_hd", "profile_pic_url"), p_verified=("is_verified",),
)
# TikTok: tiktok-scraper7 (widely used free tier).
_TT_SCRAPER7 = RapidAdapter(
    name="tiktok-scraper7", host="tiktok-scraper7.p.rapidapi.com",
    platform="tiktok",
    profile_path="/user/info?unique_id={user}",
    posts_path="/user/posts?unique_id={user}&count={count}",
    p_username=("data.user.uniqueId",), p_name=("data.user.nickname",),
    p_bio=("data.user.signature",),
    p_followers=("data.stats.followerCount",), p_posts_count=("data.stats.videoCount",),
    p_avatar=("data.user.avatarLarger", "data.user.avatarMedium"),
    p_verified=("data.user.verified",),
    posts_list=("data.videos",),
    pp_text=("title", "desc"), pp_likes=("digg_count",), pp_comments=("comment_count",),
    pp_views=("play_count",), pp_code=("video_id", "id", "aweme_id"), post_kind="video",
)

ADAPTERS: list[RapidAdapter] = [_IG_SCRAPER_API2, _IG_BEST_EXPERIENCE, _TT_SCRAPER7]


def available() -> bool:
    return bool(config.RAPIDAPI_KEY) and not config.DISABLE_RAPIDAPI


def adapters_for(platform: str) -> list[RapidAdapter]:
    """Adapters for a platform. An explicit host override (env) is tried first so a
    user who subscribed to a specific host gets it preferred."""
    override = {"instagram": config.RAPIDAPI_IG_HOST, "tiktok": config.RAPIDAPI_TT_HOST}.get(platform, "")
    pool = [a for a in ADAPTERS if a.platform == platform]
    if override:
        pool.sort(key=lambda a: a.host != override)
    return pool


def url_for(platform: str, user: str, code: str = "") -> str:
    user = user.lstrip("@")
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{user}/video/{code}" if code else f"https://www.tiktok.com/@{user}"
    return f"https://www.instagram.com/p/{code}/" if code else f"https://www.instagram.com/{user}/"


# --- tolerant extraction helpers ---

def _dig(obj, path: str):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _first(obj, paths: tuple[str, ...]):
    for p in paths:
        val = _dig(obj, p)
        if val not in (None, ""):
            return val
    return None


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    t = str(value or "").strip().lower().replace(",", "").replace("\xa0", "")
    mult = 1
    if t.endswith("k"):
        mult, t = 1_000, t[:-1]
    elif t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    elif t.endswith("b"):
        mult, t = 1_000_000_000, t[:-1]
    try:
        return int(float(re.sub(r"[^0-9.]", "", t)) * mult)
    except (ValueError, TypeError):
        return None


def _headers(adapter: RapidAdapter) -> dict:
    return {"X-RapidAPI-Key": config.RAPIDAPI_KEY, "X-RapidAPI-Host": adapter.host}


def _get(adapter: RapidAdapter, path: str) -> dict | None:
    url = f"https://{adapter.host}{path}"
    r = httpx.get(url, headers=_headers(adapter), timeout=config.RAPIDAPI_TIMEOUT)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return None


def build_profile(adapter: RapidAdapter, user: str, raw: dict) -> InfluencerCandidate | None:
    """Pure parser (no network) — the unit-tested contract."""
    root = raw
    for part in adapter.profile_root:
        root = _dig(raw, part) if part else raw
        if root is None:
            root = raw
            break
    username = (_first(root, adapter.p_username) or user).lstrip("@").lower()
    return InfluencerCandidate(
        handle=username,
        name=str(_first(root, adapter.p_name) or username),
        platform=adapter.platform,
        url=url_for(adapter.platform, username),
        avatar=str(_first(root, adapter.p_avatar) or ""),
        bio=str(_first(root, adapter.p_bio) or "")[:1500],
        followers=_as_int(_first(root, adapter.p_followers)),
        posts_count=_as_int(_first(root, adapter.p_posts_count)),
        categories=(["verified"] if _first(root, adapter.p_verified) else []),
    )


def attach_posts(adapter: RapidAdapter, c: InfluencerCandidate, raw: dict) -> int:
    """Pure parser for the posts payload — unit-tested contract."""
    items = _first(raw, adapter.posts_list)
    if not isinstance(items, list):
        return 0
    added = 0
    for item in items[: config.RAPIDAPI_MAX_POSTS]:
        text = str(_first(item, adapter.pp_text) or "").strip()
        code = str(_first(item, adapter.pp_code) or "")
        c.evidence.append(EvidenceItem(
            kind=adapter.post_kind, source=adapter.name,
            url=url_for(adapter.platform, c.handle, code),
            text=text[:2000], author=c.handle,
            metrics={
                "likes": _as_int(_first(item, adapter.pp_likes)) or 0,
                "comments": _as_int(_first(item, adapter.pp_comments)) or 0,
                "video_views": _as_int(_first(item, adapter.pp_views)) or 0,
            },
            reason=f"{adapter.platform} son paylaşım",
        ))
        added += 1
    return added


def _merge_metrics(c: InfluencerCandidate) -> None:
    posts = [e for e in c.evidence if e.kind in ("post", "video")]
    if not posts:
        return
    c.avg_likes = sum(e.metrics.get("likes", 0) for e in posts) / len(posts)
    c.avg_comments = sum(e.metrics.get("comments", 0) for e in posts) / len(posts)
    c.avg_views = sum(e.metrics.get("video_views", 0) for e in posts) / len(posts)
    if c.followers:
        c.engagement_rate = (c.avg_likes + c.avg_comments) / c.followers
    elif c.avg_views:
        c.engagement_rate = (c.avg_likes + c.avg_comments) / c.avg_views


def _enrich_one(user: str, platform: str, deep_comments: bool, statuses: list[SourceStatus]) -> InfluencerCandidate | None:
    for adapter in adapters_for(platform):
        try:
            raw = _get(adapter, adapter.profile_path.format(user=user))
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (401, 403):
                statuses.append(SourceStatus(
                    f"rapidapi/{adapter.name}", "error:not-subscribed",
                    f"Açar bu host-a abunə deyil ({adapter.host}); RapidAPI-də pulsuz plana abunə ol",
                ))
                continue
            if code == 429:
                statuses.append(SourceStatus(f"rapidapi/{adapter.name}", "error:rate-limit", "Aylıq/dəqiqəlik limit doldu"))
                continue
            statuses.append(SourceStatus(f"rapidapi/{adapter.name}", f"error:HTTP{code}", user))
            continue
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(f"rapidapi/{adapter.name}", f"error:{type(exc).__name__}", str(exc)[:120]))
            continue
        if not raw:
            continue
        c = build_profile(adapter, user, raw)
        if not c or c.followers is None:
            continue
        if deep_comments and adapter.posts_path:
            try:
                praw = _get(adapter, adapter.posts_path.format(user=user, count=config.RAPIDAPI_MAX_POSTS))
                if praw:
                    attach_posts(adapter, c, praw)
            except Exception:  # noqa: BLE001
                pass
        _merge_metrics(c)
        return c
    return None


def collect(
    brief: CampaignBrief,
    *,
    platform: str = "instagram",
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    statuses: list[SourceStatus] = []
    if not available():
        statuses.append(SourceStatus(f"rapidapi/{platform}", "skipped", "RAPIDAPI_KEY yoxdur (.env-ə əlavə et)"))
        return [], statuses, 0

    handles: list[str] = []
    for raw in [*(seed_handles or []), *(brief.seed_handles or [])]:
        h = (raw or "").strip().lstrip("@").lower()
        if h and h not in handles:
            handles.append(h)
    handles = handles[: config.RAPIDAPI_MAX_HANDLES]

    if not handles:
        statuses.append(SourceStatus(
            f"rapidapi/{platform}", "empty",
            "Zənginləşdirmə üçün handle lazımdır — web/telegram kəşfi və ya seed handle ver",
        ))
        return [], statuses, 0

    candidates: list[InfluencerCandidate] = []
    seen = 0
    for user in handles:
        c = _enrich_one(user, platform, deep_comments, statuses)
        if c:
            candidates.append(c)
            seen += 1 + len([e for e in c.evidence if e.kind in ("post", "video")])
    statuses.append(SourceStatus(
        f"rapidapi/{platform}", "ok" if candidates else "empty",
        f"{len(candidates)}/{len(handles)} profil zənginləşdirildi",
    ))
    return candidates, statuses, seen
