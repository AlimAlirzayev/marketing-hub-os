"""Instagram discovery and evidence collection.

Primary data path is Apify's official Instagram actors. The code is deliberately
configurable: actor names live in config/env, so switching a scraper does not
touch scoring or UI code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import quote_plus

import httpx

import config
from models import CampaignBrief, EvidenceItem, InfluencerCandidate, SourceStatus

# Per-run cache accounting. collect() runs inside a single worker thread, so a
# threadlocal counter lets us surface "N calls served from cache" honestly in
# the coverage table without changing the _run_actor return contract.
_cache_state = threading.local()

_RETRYABLE_STATUS = {500, 502, 503, 504, 408, 429}

_LOCAL_HINTS = {
    "azerbaijan", "azerbaycan", "azərbaycan", "baku", "bakı", "baki",
    "azblogger", "azerbaijanblogger", "bakublogger", "travelbloggeraz",
    "aztravelblogger", "azerbaijaninfluencer", "azeri", "azəri", "🇦🇿",
}


def _actor_slug(actor: str) -> str:
    return actor.replace("/", "~")


def _bump_cache_hit() -> None:
    _cache_state.hits = getattr(_cache_state, "hits", 0) + 1


def _cache_path(actor: str, payload: dict) -> str:
    raw = json.dumps({"actor": actor, "payload": payload}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return os.path.join(config.CACHE_DIR, f"actor-{_actor_slug(actor)}-{digest}.json")


def _cache_read(actor: str, payload: dict) -> list[dict] | None:
    if config.DISABLE_CACHE:
        return None
    path = _cache_path(actor, payload)
    try:
        if time.time() - os.path.getmtime(path) > config.CACHE_TTL:
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else None
    except (OSError, ValueError):
        return None


def _cache_write(actor: str, payload: dict, data: list[dict]) -> None:
    if config.DISABLE_CACHE:
        return
    try:
        config.ensure_dirs()
        with open(_cache_path(actor, payload), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def _run_actor(actor: str, payload: dict, timeout: int | None = None) -> list[dict]:
    if not config.APIFY_API_TOKEN:
        return []
    cached = _cache_read(actor, payload)
    if cached is not None:
        _bump_cache_hit()
        return cached
    eff_timeout = timeout or config.APIFY_TIMEOUT
    ep = (
        f"https://api.apify.com/v2/acts/{_actor_slug(actor)}/run-sync-get-dataset-items"
        f"?token={config.APIFY_API_TOKEN}&timeout={eff_timeout}"
    )
    attempts = max(1, config.APIFY_MAX_RETRIES + 1)
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            r = httpx.post(ep, json=payload, timeout=eff_timeout + 45)
            if r.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
                time.sleep(min(2 ** attempt * 1.5, 8))
                continue
            r.raise_for_status()
            data = r.json()
            data = data if isinstance(data, list) else []
            _cache_write(actor, payload, data)
            return data
        except httpx.HTTPStatusError as exc:
            # 4xx (e.g. 400 bad input) is deterministic; retrying wastes time/quota.
            if exc.response is not None and exc.response.status_code not in _RETRYABLE_STATUS:
                raise
            last_exc = exc
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
        if attempt < attempts - 1:
            time.sleep(min(2 ** attempt * 1.5, 8))
    if last_exc:
        raise last_exc
    return []


def _as_int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "").replace(" ", "")
    mult = 1
    if text.endswith("k"):
        mult = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        mult = 1_000_000
        text = text[:-1]
    try:
        return int(float(re.sub(r"[^0-9.]", "", text)) * mult)
    except Exception:
        return None


def _first(d: dict, *keys, default=None):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def _handle(value: str) -> str:
    value = (value or "").strip()
    value = value.removeprefix("@")
    value = re.sub(r"^https?://(?:www\.)?instagram\.com/", "", value, flags=re.I)
    value = value.split("/")[0].split("?")[0]
    return re.sub(r"[^A-Za-z0-9._]", "", value).lower()


def _norm_text(value: str) -> str:
    text = (value or "").lower()
    repl = {
        "ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c",
        "Ə": "e", "I": "i", "İ": "i", "Ö": "o", "Ü": "u", "Ğ": "g", "Ş": "s", "Ç": "c",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return text


def _handle_from_item(item: dict) -> str:
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    return _handle(
        _first(
            item,
            "ownerUsername",
            "username",
            "userName",
            default=owner.get("username") or owner.get("userName") or "",
        )
    )


_PERMALINK_RE = re.compile(r"instagram\.com/(?:p|reel|reels|tv)/[\w.-]+", re.I)


def _is_post_permalink(url: str) -> bool:
    return bool(_PERMALINK_RE.search(url or ""))


def _post_url(item: dict, handle: str = "") -> str:
    # Prefer a real post/reel permalink. Never fall back to displayUrl: that is a
    # CDN image link which both breaks the evidence link and is rejected (400) by
    # the comment scraper when passed as a directUrl.
    for key in ("url", "link", "postUrl"):
        val = str(_first(item, key, default="") or "")
        if _is_post_permalink(val):
            return val
    shortcode = _first(item, "shortCode", "shortcode", "code", default="")
    if shortcode:
        kind = "reel" if _is_reel(item) else "p"
        return f"https://www.instagram.com/{kind}/{shortcode}/"
    for key in ("url", "link"):
        val = str(_first(item, key, default="") or "")
        if "instagram.com" in val.lower():
            return val
    if handle:
        return f"https://www.instagram.com/{handle}/"
    return ""


def _is_reel(item: dict) -> bool:
    typename = str(_first(item, "type", "productType", "__typename", default="")).lower()
    url = str(_first(item, "url", default="")).lower()
    return "reel" in typename or "/reel/" in url or bool(_first(item, "videoViewCount", "videoPlayCount", "videoViews", "plays"))


def _metrics(item: dict) -> dict:
    likes = _as_int(_first(item, "likesCount", "likes", "likeCount", default=0)) or 0
    comments = _as_int(_first(item, "commentsCount", "comments", "commentCount", default=0)) or 0
    views = _as_int(_first(item, "videoViewCount", "videoPlayCount", "videoViews", "views", "plays", default=0)) or 0
    out = {
        "likes": likes,
        "comments": comments,
        "video_views": views,
    }
    for key in ("timestamp", "takenAtTimestamp", "date", "videoDuration", "hashtags", "mentions"):
        if key in item and item[key] not in (None, ""):
            out[key] = item[key]
    return out


def _post_evidence(item: dict, handle: str) -> EvidenceItem:
    caption = str(_first(item, "caption", "text", "description", "alt", default=""))
    title = "Reel" if _is_reel(item) else "Post"
    metrics = _metrics(item)
    return EvidenceItem(
        kind="reel" if _is_reel(item) else "post",
        url=_post_url(item, handle),
        source="instagram",
        title=title,
        text=caption[:2500],
        author=handle,
        created_at=str(_first(item, "timestamp", "takenAt", "date", default="")),
        metrics=metrics,
        reason="Instagram axtarışında tapıldı",
    )


def _profile_to_candidate(item: dict, existing: InfluencerCandidate | None = None) -> InfluencerCandidate | None:
    handle = _handle(_first(item, "username", "userName", "handle", default=""))
    if not handle:
        return existing
    c = existing or InfluencerCandidate(handle=handle)
    c.name = str(_first(item, "fullName", "name", "displayName", default=c.name or handle))
    c.url = str(_first(item, "url", default=c.url or f"https://www.instagram.com/{handle}/"))
    c.avatar = str(_first(item, "profilePicUrlHD", "profilePicUrl", "profile_pic_url", "profilePic", default=c.avatar))
    c.bio = str(_first(item, "biography", "bio", "description", default=c.bio))
    c.followers = _as_int(_first(item, "followersCount", "followers", "followedByCount", default=c.followers)) or c.followers
    c.following = _as_int(_first(item, "followsCount", "following", "followingCount", default=c.following)) or c.following
    c.posts_count = _as_int(_first(item, "postsCount", "mediaCount", "posts", default=c.posts_count)) or c.posts_count
    c.contact = str(_first(item, "externalUrl", "website", "businessEmail", "email", default=c.contact))
    cats = []
    for key in ("businessCategoryName", "categoryName", "category", "accountType"):
        val = item.get(key)
        if val:
            cats.append(str(val))
    c.categories = list(dict.fromkeys([*c.categories, *cats]))
    latest = item.get("latestPosts") or item.get("latestIgtvVideos") or []
    for post in latest if isinstance(latest, list) else []:
        if isinstance(post, dict):
            c.evidence.append(_post_evidence(post, handle))
    return c


def _merge_metrics(c: InfluencerCandidate) -> None:
    posts = [e for e in c.evidence if e.kind in {"post", "reel"}]
    if not posts:
        return
    c.avg_likes = sum((e.metrics.get("likes") or 0) for e in posts) / len(posts)
    c.avg_comments = sum((e.metrics.get("comments") or 0) for e in posts) / len(posts)
    c.avg_views = sum((e.metrics.get("video_views") or 0) for e in posts) / len(posts)
    if c.followers:
        c.engagement_rate = (c.avg_likes + c.avg_comments) / max(1, c.followers)


def _dedupe_evidence(c: InfluencerCandidate) -> None:
    seen = set()
    out = []
    for e in c.evidence:
        key = (e.kind, e.url or e.text[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    c.evidence = out


def _hashtag_payload(brief: CampaignBrief) -> dict:
    tags = [h.lstrip("#") for h in brief.hashtags if h.strip()]
    return {
        "hashtags": tags[:8],
        "resultsType": "posts",
        "resultsLimit": config.MAX_DISCOVERY_POSTS,
        "keywordSearch": True,
    }


def _fallback_scraper_payload(brief: CampaignBrief) -> dict:
    urls = [f"https://www.instagram.com/explore/tags/{quote_plus(h.lstrip('#'))}/" for h in brief.hashtags[:6]]
    return {
        "directUrls": urls,
        "resultsType": "posts",
        "resultsLimit": config.MAX_DISCOVERY_POSTS,
        "addParentData": False,
    }


def _search_queries(brief: CampaignBrief) -> list[str]:
    placeholder_words = {
        "name", "location", "date", "period", "highlights", "offers",
        "promotions", "details", "information", "if", "applicable",
    }
    text = _norm_text(" ".join([
        brief.query,
        brief.product,
        brief.objective,
        brief.audience,
        brief.selling_angle,
        " ".join(brief.must_have_topics),
        " ".join(brief.creator_archetypes),
    ]))
    stop = {
        "azerbaijan", "azerbaijani", "baku", "instagram", "reel", "reels",
        "creator", "influencer", "blogger", "content", "campaign", "brand",
        "product", "audience", "people", "users", "lazimdir",
    }
    priority_terms = []
    for phrase in [
        brief.query,
        brief.product,
        *brief.creator_archetypes[:4],
        *brief.must_have_topics[:5],
    ]:
        raw_tokens = re.findall(r"[a-z0-9]{3,}", _norm_text(phrase))
        if len(set(raw_tokens) & placeholder_words) >= 2:
            continue
        clean = " ".join([t for t in raw_tokens if t not in stop and t not in placeholder_words])
        if clean:
            priority_terms.append(clean[:60])
    for token in re.findall(r"[a-z0-9]{4,}", text):
        if token not in stop and token not in priority_terms:
            priority_terms.append(token)
        if len(priority_terms) >= 5:
            break
    if not priority_terms:
        priority_terms = ["lifestyle", "content"]
    queries = []
    for term in priority_terms[:4]:
        queries.extend([
            f"Azerbaijan {term} influencer",
            f"Baku {term} blogger",
            f"Azerbaijani {term} content creator",
        ])
    queries.extend(["Azerbaijan influencer", "Baku blogger"])
    return list(dict.fromkeys(q for q in queries if q.strip()))[:6]


def _search_payload(query: str) -> dict:
    return {
        "search": query,
        "searchType": "user",
        "searchLimit": min(config.MAX_PROFILE_HANDLES, 12),
        "resultsType": "details",
        "resultsLimit": min(config.MAX_PROFILE_HANDLES, 12),
        "addParentData": False,
    }


def _profile_priority(c: InfluencerCandidate) -> tuple[int, int, int]:
    text = _norm_text(" ".join([
        c.handle,
        c.name,
        c.bio,
        " ".join(c.categories),
        " ".join(e.text[:240] for e in c.evidence[:6]),
    ]))
    local_hits = sum(1 for h in _LOCAL_HINTS if _norm_text(h) in text)
    creator_hits = sum(1 for h in ("blogger", "creator", "influencer", "travelblog", "lifestyle") if h in text)
    proof = len(c.evidence)
    return (local_hits, creator_hits, proof)


def collect(brief: CampaignBrief, *, seed_handles: list[str] | None = None, deep_comments: bool = True) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    statuses: list[SourceStatus] = []
    candidates: dict[str, InfluencerCandidate] = {}
    total_seen = 0
    _cache_state.hits = 0

    for raw in [*(brief.seed_handles or []), *(seed_handles or [])]:
        h = _handle(raw)
        if h:
            candidates[h] = InfluencerCandidate(handle=h, url=f"https://www.instagram.com/{h}/")

    if not config.APIFY_API_TOKEN:
        statuses.append(SourceStatus("apify-instagram", "skipped", "APIFY_API_TOKEN yoxdur; canlı Instagram sübutu üçün Apify-ni aktiv edin və ya seed profil əlavə edin"))
        for c in candidates.values():
            c.flags.append("yalnız seed profil; canlı Instagram sübutu yoxdur")
        return list(candidates.values()), statuses, len(candidates)

    discovery_items: list[dict] = []
    try:
        if brief.hashtags:
            discovery_items = _run_actor(config.INSTAGRAM_HASHTAG_ACTOR, _hashtag_payload(brief))
            statuses.append(SourceStatus(config.INSTAGRAM_HASHTAG_ACTOR, "ok" if discovery_items else "empty", f"{len(discovery_items)} həştəq paylaşımı"))
    except Exception as exc:  # noqa: BLE001
        statuses.append(SourceStatus(config.INSTAGRAM_HASHTAG_ACTOR, f"error:{type(exc).__name__}", str(exc)[:140]))

    if not discovery_items and brief.hashtags:
        try:
            discovery_items = _run_actor(config.INSTAGRAM_SCRAPER_ACTOR, _fallback_scraper_payload(brief))
            statuses.append(SourceStatus(config.INSTAGRAM_SCRAPER_ACTOR, "ok" if discovery_items else "empty", f"{len(discovery_items)} əlavə həştəq paylaşımı"))
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(config.INSTAGRAM_SCRAPER_ACTOR, f"error:{type(exc).__name__}", str(exc)[:140]))

    search_items: list[dict] = []
    for q in _search_queries(brief):
        try:
            items = _run_actor(config.INSTAGRAM_SCRAPER_ACTOR, _search_payload(q))
            search_items.extend(items)
            statuses.append(SourceStatus(
                config.INSTAGRAM_SCRAPER_ACTOR + ":search",
                "ok" if items else "empty",
                f"{len(items)} profil axtarış nəticəsi: {q}",
            ))
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(config.INSTAGRAM_SCRAPER_ACTOR + ":search", f"error:{type(exc).__name__}", f"{q}: {str(exc)[:120]}"))

    total_seen += len(discovery_items) + len(search_items)
    for item in discovery_items:
        if not isinstance(item, dict):
            continue
        handle = _handle_from_item(item)
        if not handle:
            continue
        c = candidates.setdefault(handle, InfluencerCandidate(handle=handle, url=f"https://www.instagram.com/{handle}/"))
        c.evidence.append(_post_evidence(item, handle))

    for item in search_items:
        if not isinstance(item, dict):
            continue
        c = _profile_to_candidate(item, candidates.get(_handle_from_item(item)))
        if c and c.handle:
            candidates[c.handle] = c

    handles = [
        h for h, _c in sorted(
            candidates.items(),
            key=lambda item: _profile_priority(item[1]),
            reverse=True,
        )
    ][: config.MAX_PROFILE_HANDLES]
    if handles:
        try:
            profiles = _run_actor(config.INSTAGRAM_PROFILE_ACTOR, {"usernames": handles, "includeAboutSection": True})
            statuses.append(SourceStatus(config.INSTAGRAM_PROFILE_ACTOR, "ok" if profiles else "empty", f"{len(profiles)} profil"))
            total_seen += len(profiles)
            for item in profiles:
                if isinstance(item, dict):
                    c = _profile_to_candidate(item, candidates.get(_handle(_first(item, "username", default=""))))
                    if c and c.handle:
                        candidates[c.handle] = c
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(config.INSTAGRAM_PROFILE_ACTOR, f"error:{type(exc).__name__}", str(exc)[:140]))

        try:
            posts = _run_actor(
                config.INSTAGRAM_POST_ACTOR,
                {
                    "username": handles,
                    "resultsLimit": config.MAX_POSTS_PER_HANDLE,
                    "skipPinnedPosts": False,
                    "dataDetailLevel": "detailedData",
                },
                timeout=max(config.APIFY_TIMEOUT, 240),
            )
            statuses.append(SourceStatus(config.INSTAGRAM_POST_ACTOR, "ok" if posts else "empty", f"{len(posts)} son paylaşım"))
            total_seen += len(posts)
            for item in posts:
                if not isinstance(item, dict):
                    continue
                handle = _handle_from_item(item)
                if not handle:
                    continue
                c = candidates.setdefault(handle, InfluencerCandidate(handle=handle, url=f"https://www.instagram.com/{handle}/"))
                c.evidence.append(_post_evidence(item, handle))
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus(config.INSTAGRAM_POST_ACTOR, f"error:{type(exc).__name__}", str(exc)[:140]))

    if deep_comments:
        url_to_handle = {}
        comment_urls = []
        for c in candidates.values():
            for e in sorted(c.evidence, key=lambda ev: (ev.relevance, ev.metrics.get("comments", 0)), reverse=True):
                # Only real post/reel permalinks are valid comment-scraper inputs;
                # profile or CDN urls trigger a 400 and waste the whole call.
                if _is_post_permalink(e.url) and e.kind in {"post", "reel"} and len(comment_urls) < 18:
                    comment_urls.append(e.url)
                    url_to_handle[e.url] = c.handle
        if comment_urls:
            try:
                comments = _run_actor(
                    config.INSTAGRAM_COMMENT_ACTOR,
                    {
                        "directUrls": comment_urls,
                        "resultsLimit": config.MAX_COMMENTS_PER_POST,
                        "includeNestedComments": False,
                    },
                    timeout=max(config.APIFY_TIMEOUT, 240),
                )
                statuses.append(SourceStatus(config.INSTAGRAM_COMMENT_ACTOR, "ok" if comments else "empty", f"{len(comments)} rəy"))
                total_seen += len(comments)
                for item in comments:
                    if not isinstance(item, dict):
                        continue
                    post_url = str(_first(item, "postUrl", "url", "inputUrl", default=""))
                    handle = url_to_handle.get(post_url) or _handle_from_item(item)
                    if not handle or handle not in candidates:
                        continue
                    text = str(_first(item, "text", "comment", "caption", default=""))
                    if not text:
                        continue
                    candidates[handle].evidence.append(EvidenceItem(
                        kind="comment",
                        url=post_url,
                        source="instagram-comment",
                        text=text[:800],
                        author=str(_first(item, "ownerUsername", "username", default="")),
                        created_at=str(_first(item, "timestamp", "createdAt", default="")),
                        metrics={"is_comment": True},
                        reason="Namizəd paylaşımında izləyici rəyi",
                    ))
            except Exception as exc:  # noqa: BLE001
                statuses.append(SourceStatus(config.INSTAGRAM_COMMENT_ACTOR, f"error:{type(exc).__name__}", str(exc)[:140]))

    hits = getattr(_cache_state, "hits", 0)
    if hits:
        statuses.append(SourceStatus(
            "keş",
            "ok",
            f"{hits} Apify çağırışı keşdən gəldi; canlı təzələmə üçün IH_DISABLE_CACHE=1",
        ))

    out = []
    for c in candidates.values():
        _dedupe_evidence(c)
        _merge_metrics(c)
        out.append(c)
    return out, statuses, total_seen
