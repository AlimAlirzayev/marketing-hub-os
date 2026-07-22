"""YouTube brand-mention listening connector — free, official, read-only.

Fills the CX "Sosial dinləmə" gap: searches YouTube for recent Xalq Sigorta
mentions and pulls the public comments, normalized into the SAME message
contract as the Meta/Chatplace connectors, so triage / store / alerts / panel
need no changes. A video like "ən çox şikayət olunan sığorta şirkətləri" is a
genuine reputation signal, so it belongs in the CX risk picture.

Quota (YouTube Data API v3, free 10,000 units/day): search.list = 100 units,
commentThreads/videos = 1 each — so discovery is deliberately capped.
"""

from __future__ import annotations

import datetime as _dt

import requests

import config

_API = "https://www.googleapis.com/youtube/v3"


def configured() -> bool:
    return bool(config.YOUTUBE_API_KEY)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(path: str, params: dict) -> dict:
    resp = requests.get(f"{_API}/{path}",
                        params={**params, "key": config.YOUTUBE_API_KEY}, timeout=25)
    resp.raise_for_status()
    return resp.json()


def sync_mentions(max_videos: int = 5, comments_per_video: int = 12) -> list[dict]:
    """Return normalized brand-mention messages (videos + their comments)."""
    if not configured():
        raise RuntimeError("YouTube connector is not configured (YOUTUBE_API_KEY)")
    messages: list[dict] = []
    seen: set[str] = set()
    for query in config.YOUTUBE_QUERIES:
        data = _get("search", {
            "part": "snippet", "q": query, "type": "video",
            "order": "date", "maxResults": max_videos, "relevanceLanguage": "az"})
        for item in data.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            snippet = item.get("snippet") or {}
            messages.append(_video_message(vid, snippet))
            messages.extend(_comment_messages(vid, snippet, comments_per_video))
    return [m for m in messages if (m.get("text") or "").strip()]


def _video_message(vid: str, sn: dict) -> dict:
    title = sn.get("title") or ""
    desc = (sn.get("description") or "")[:280]
    return {
        "source": "youtube_pull",
        "channel": "youtube_mention",
        "account": sn.get("channelId"),
        "external_id": f"yt-video:{vid}",
        "author_name": sn.get("channelTitle"),
        "author_handle": sn.get("channelId"),
        "text": f"[Video] {title}" + (f" — {desc}" if desc else ""),
        "url": f"https://www.youtube.com/watch?v={vid}",
        "occurred_at": sn.get("publishedAt") or _now_iso(),
        "metadata": {"youtube_video": {"id": vid, **sn}},
        "raw_payload": {"video": sn},
    }


def _comment_messages(vid: str, video_sn: dict, limit: int) -> list[dict]:
    try:
        data = _get("commentThreads", {
            "part": "snippet", "videoId": vid, "maxResults": limit,
            "order": "relevance", "textFormat": "plainText"})
    except Exception:
        # Comments disabled / unavailable on a video must never fail the whole sync.
        return []
    out: list[dict] = []
    for thread in data.get("items", []):
        top = ((thread.get("snippet") or {}).get("topLevelComment") or {})
        cid = top.get("id")
        c = top.get("snippet") or {}
        if not cid:
            continue
        out.append({
            "source": "youtube_pull",
            "channel": "youtube_comment",
            "account": (c.get("authorChannelId") or {}).get("value"),
            "external_id": f"yt-comment:{cid}",
            "author_name": c.get("authorDisplayName"),
            "author_handle": (c.get("authorChannelId") or {}).get("value"),
            "text": c.get("textOriginal") or c.get("textDisplay") or "",
            "url": f"https://www.youtube.com/watch?v={vid}&lc={cid}",
            "occurred_at": c.get("publishedAt") or _now_iso(),
            "metadata": {"youtube_video_title": video_sn.get("title"),
                         "like_count": c.get("likeCount")},
            "raw_payload": {"comment": c},
        })
    return out
