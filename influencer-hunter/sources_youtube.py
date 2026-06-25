"""YouTube Data API v3 connector — free, official, zero ban risk.

A drop-in alternative to the Apify Instagram path: same return contract as
``sources.collect`` and the same normalized models, so scoring/filters/UI need
no changes. YouTube's official API legally exposes the one thing Instagram makes
expensive — real comment text — which the analysis layer turns into audience
sentiment.

Cost note: ``search.list`` is 100 quota units; everything else is 1. The free
daily quota is 10,000 units, so discovery is capped deliberately.
"""

from __future__ import annotations

import re

import httpx

import config
from models import CampaignBrief, EvidenceItem, InfluencerCandidate, SourceStatus

_API = "https://www.googleapis.com/youtube/v3"

_LOCAL_HINTS = {
    "azerbaijan", "azerbaycan", "azərbaycan", "baku", "bakı", "baki", "azeri",
    "azəri", "az", "gəncə", "gence", "sumqayit",
}


def available() -> bool:
    return bool(config.YOUTUBE_API_KEY)


def _get(path: str, params: dict) -> dict:
    params = {**params, "key": config.YOUTUBE_API_KEY}
    r = httpx.get(f"{_API}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _thumb(snippet: dict) -> str:
    thumbs = snippet.get("thumbnails") or {}
    for size in ("high", "medium", "default"):
        if thumbs.get(size, {}).get("url"):
            return thumbs[size]["url"]
    return ""


def _handle_for(channel: dict) -> str:
    snippet = channel.get("snippet", {})
    custom = snippet.get("customUrl") or ""
    if custom:
        return custom.lstrip("@").lower()
    return channel.get("id", "")


def _search_terms(brief: CampaignBrief) -> list[str]:
    # Keep queries short and AZ-targeted. Never dump selling_angle (a sentence)
    # into search — it produces junk queries that return nothing.
    archetype = (brief.creator_archetypes or ["vlogger"])[0].strip()
    topic = (brief.must_have_topics or [""])[0].strip()
    product_kw = " ".join(re.findall(r"[\wəğıöşüçə]+", (brief.product or "").lower())[:2])
    queries = [
        f"Azərbaycan {archetype}",
        f"Azərbaycanlı {topic} vlog" if topic else "Azərbaycan səyahət vlog",
        f"Azərbaycan {product_kw}" if product_kw else "",
    ]
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:3]


def _channel_ids_from_search(brief: CampaignBrief, statuses: list[SourceStatus], budget: int) -> tuple[list[str], int]:
    ids: list[str] = []
    for q in _search_terms(brief):
        if budget <= 0:
            break
        try:
            data = _get("search", {
                "part": "snippet", "q": q, "type": "channel",
                "maxResults": min(config.YT_MAX_CHANNELS, 10),
                "regionCode": config.YT_REGION,
                "relevanceLanguage": config.YT_RELEVANCE_LANGUAGE,
            })
            found = [it["snippet"]["channelId"] for it in data.get("items", []) if it.get("snippet", {}).get("channelId")]
            ids.extend(found)
            budget -= 100
            statuses.append(SourceStatus("youtube/search", "ok" if found else "empty", f"{len(found)} kanal: {q}"))
        except httpx.HTTPStatusError as exc:
            return ids, _on_http_error(exc, statuses, "youtube/search", budget)
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus("youtube/search", f"error:{type(exc).__name__}", str(exc)[:140]))
    return list(dict.fromkeys(ids)), budget


def _on_http_error(exc: httpx.HTTPStatusError, statuses: list[SourceStatus], src: str, budget: int) -> int:
    code = exc.response.status_code if exc.response is not None else 0
    body = (exc.response.text if exc.response is not None else "")[:500]
    low = body.lower()
    if code == 403 and "quota" in low and "exceeded" in low:
        statuses.append(SourceStatus(src, "error:quota", "Gündəlik YouTube kvotası (10,000 vahid) bitib; sabah sıfırlanır"))
        return -1
    if code == 403 and ("are blocked" in low or "api_key_service_blocked" in low):
        # API is enabled, but the API KEY is restricted to other APIs only.
        statuses.append(SourceStatus(
            src, "error:key-restricted",
            "API enabled-dir, amma açar YouTube-a icazə vermir. Düzəliş: Cloud Console → "
            "APIs & Services → Credentials → açarı seç → API restrictions → 'YouTube Data API v3' əlavə et "
            "(və ya ayrıca açar yarat → .env-də YOUTUBE_API_KEY=...)",
        ))
        return -1
    if code == 403 and ("has not been used" in low or "service_disabled" in low or "accessnotconfigured" in low):
        statuses.append(SourceStatus(
            src, "error:disabled",
            "YouTube Data API v3 bu layihədə aktiv deyil — Cloud Console → APIs → 'YouTube Data API v3' → Enable",
        ))
        return -1
    statuses.append(SourceStatus(src, f"error:HTTP{code}", body[:140]))
    return budget


def _channels(ids: list[str], statuses: list[SourceStatus]) -> dict[str, InfluencerCandidate]:
    out: dict[str, InfluencerCandidate] = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        try:
            data = _get("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)})
        except httpx.HTTPStatusError as exc:
            _on_http_error(exc, statuses, "youtube/channels", 0)
            continue
        for ch in data.get("items", []):
            cid = ch.get("id", "")
            snippet = ch.get("snippet", {})
            stats = ch.get("statistics", {})
            uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
            handle = _handle_for(ch)
            subs = None if stats.get("hiddenSubscriberCount") else _as_int(stats.get("subscriberCount"))
            c = InfluencerCandidate(
                handle=handle or cid,
                name=snippet.get("title", ""),
                platform="youtube",
                url=f"https://www.youtube.com/channel/{cid}",
                avatar=_thumb(snippet),
                bio=snippet.get("description", "")[:1500],
                followers=subs,
                posts_count=_as_int(stats.get("videoCount")),
            )
            country = snippet.get("country")
            if country:
                c.country = country
                c.categories.append(f"country:{country}")
            c._yt_channel_id = cid  # type: ignore[attr-defined]
            c._yt_uploads = uploads  # type: ignore[attr-defined]
            c._yt_total_views = _as_int(stats.get("viewCount")) or 0  # type: ignore[attr-defined]
            out[c.handle] = c
        statuses.append(SourceStatus("youtube/channels", "ok", f"{len(batch)} kanal məlumatı"))
    return out


def _recent_video_ids(uploads_playlist: str, statuses: list[SourceStatus]) -> list[str]:
    if not uploads_playlist:
        return []
    try:
        data = _get("playlistItems", {
            "part": "contentDetails", "playlistId": uploads_playlist,
            "maxResults": config.YT_MAX_VIDEOS_PER_CHANNEL,
        })
    except Exception:  # noqa: BLE001
        return []
    return [it["contentDetails"]["videoId"] for it in data.get("items", []) if it.get("contentDetails", {}).get("videoId")]


def _attach_videos(candidates: dict[str, InfluencerCandidate], statuses: list[SourceStatus]) -> int:
    seen = 0
    vid_to_handle: dict[str, str] = {}
    all_vids: list[str] = []
    for c in candidates.values():
        for vid in _recent_video_ids(getattr(c, "_yt_uploads", ""), statuses):
            vid_to_handle[vid] = c.handle
            all_vids.append(vid)
    for i in range(0, len(all_vids), 50):
        batch = all_vids[i:i + 50]
        try:
            data = _get("videos", {"part": "snippet,statistics", "id": ",".join(batch)})
        except Exception as exc:  # noqa: BLE001
            statuses.append(SourceStatus("youtube/videos", f"error:{type(exc).__name__}", str(exc)[:120]))
            continue
        for v in data.get("items", []):
            vid = v.get("id", "")
            handle = vid_to_handle.get(vid)
            c = candidates.get(handle) if handle else None
            if not c:
                continue
            sn = v.get("snippet", {})
            st = v.get("statistics", {})
            c.evidence.append(EvidenceItem(
                kind="video",
                url=f"https://www.youtube.com/watch?v={vid}",
                source="youtube",
                title=sn.get("title", "")[:200],
                text=(sn.get("title", "") + " " + sn.get("description", ""))[:2000],
                author=c.handle,
                created_at=sn.get("publishedAt", ""),
                metrics={
                    "likes": _as_int(st.get("likeCount")) or 0,
                    "comments": _as_int(st.get("commentCount")) or 0,
                    "video_views": _as_int(st.get("viewCount")) or 0,
                },
                reason="YouTube son video",
            ))
            c._yt_video_ids = getattr(c, "_yt_video_ids", [])  # type: ignore[attr-defined]
            c._yt_video_ids.append(vid)
            seen += 1
        statuses.append(SourceStatus("youtube/videos", "ok", f"{len(batch)} video statistikası"))
    return seen


def _attach_comments(candidates: dict[str, InfluencerCandidate], statuses: list[SourceStatus]) -> int:
    seen = 0
    for c in candidates.values():
        # Comment the top 2 most-viewed recent videos per channel to stay cheap.
        vids = sorted(
            [e for e in c.evidence if e.kind == "video"],
            key=lambda e: e.metrics.get("video_views", 0), reverse=True,
        )[:2]
        for ev in vids:
            vid = ev.url.split("v=")[-1]
            try:
                data = _get("commentThreads", {
                    "part": "snippet", "videoId": vid, "order": "relevance",
                    "maxResults": config.YT_MAX_COMMENTS_PER_VIDEO, "textFormat": "plainText",
                })
            except httpx.HTTPStatusError as exc:
                # comments disabled on a video returns 403; not fatal
                if exc.response is not None and exc.response.status_code == 403:
                    continue
                statuses.append(SourceStatus("youtube/comments", f"error:HTTP{exc.response.status_code if exc.response else 0}", ev.url))
                continue
            except Exception:  # noqa: BLE001
                continue
            for it in data.get("items", []):
                top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = top.get("textDisplay") or top.get("textOriginal") or ""
                if not text:
                    continue
                c.evidence.append(EvidenceItem(
                    kind="comment", url=ev.url, source="youtube-comment",
                    text=text[:800], author=top.get("authorDisplayName", ""),
                    created_at=top.get("publishedAt", ""),
                    metrics={"is_comment": True, "likes": _as_int(top.get("likeCount")) or 0},
                    reason="YouTube video rəyi",
                ))
                seen += 1
        statuses.append(SourceStatus("youtube/comments", "ok", f"@{c.handle}: {len([e for e in c.evidence if e.kind=='comment'])} rəy"))
    return seen


def _merge_metrics(c: InfluencerCandidate) -> None:
    vids = [e for e in c.evidence if e.kind == "video"]
    if not vids:
        return
    c.avg_likes = sum(e.metrics.get("likes", 0) for e in vids) / len(vids)
    c.avg_comments = sum(e.metrics.get("comments", 0) for e in vids) / len(vids)
    c.avg_views = sum(e.metrics.get("video_views", 0) for e in vids) / len(vids)
    # YouTube engagement is conventionally measured against views, not subscribers.
    if c.avg_views:
        c.engagement_rate = (c.avg_likes + c.avg_comments) / c.avg_views


def collect(
    brief: CampaignBrief,
    *,
    seed_handles: list[str] | None = None,
    deep_comments: bool = True,
) -> tuple[list[InfluencerCandidate], list[SourceStatus], int]:
    statuses: list[SourceStatus] = []
    if not available():
        statuses.append(SourceStatus("youtube", "skipped", "YOUTUBE_API_KEY/GOOGLE_API_KEY yoxdur"))
        return [], statuses, 0

    budget = 9000  # leave headroom under the 10k daily quota
    ids: list[str] = []

    # seed handles first (cheap, 1 unit each)
    for raw in [*(brief.seed_handles or []), *(seed_handles or [])]:
        h = (raw or "").strip().lstrip("@")
        if not h:
            continue
        try:
            data = _get("channels", {"part": "id", "forHandle": h})
            for it in data.get("items", []):
                ids.append(it["id"])
        except httpx.HTTPStatusError as exc:
            if _on_http_error(exc, statuses, "youtube/seed", budget) == -1:
                return [], statuses, 0
        except Exception:  # noqa: BLE001
            pass

    found, budget = _channel_ids_from_search(brief, statuses, budget)
    if budget == -1:  # API disabled / quota -> stop honestly
        return [], statuses, 0
    ids.extend(found)
    ids = list(dict.fromkeys(ids))[: config.YT_MAX_CHANNELS]

    if not ids:
        statuses.append(SourceStatus("youtube", "empty", "Uyğun kanal tapılmadı"))
        return [], statuses, 0

    candidates = _channels(ids, statuses)
    seen = len(candidates)
    seen += _attach_videos(candidates, statuses)
    if deep_comments:
        seen += _attach_comments(candidates, statuses)

    for c in candidates.values():
        _merge_metrics(c)
    return list(candidates.values()), statuses, seen
