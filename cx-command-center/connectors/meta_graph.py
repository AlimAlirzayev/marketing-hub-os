"""Meta Graph API pull connector for owned Facebook and Instagram comments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

import config


GRAPH_BASE = f"https://graph.facebook.com/{config.META_GRAPH_API_VERSION}"
SESSION = requests.Session()
SESSION.trust_env = False


def configured() -> bool:
    return bool(
        config.META_GRAPH_ACCESS_TOKEN
        and (config.META_FACEBOOK_PAGE_IDS or config.META_INSTAGRAM_BUSINESS_IDS)
    )


def discover_assets() -> dict:
    """Return Pages and attached Instagram Business accounts visible to the token."""
    if not config.META_GRAPH_ACCESS_TOKEN:
        raise RuntimeError("META_GRAPH_ACCESS_TOKEN or META_ACCESS_TOKEN is not configured")
    pages = _paged(
        "me/accounts",
        {
            "fields": "id,name,instagram_business_account{id,username,name}",
            "limit": 100,
        },
        max_pages=3,
    )
    instagram_accounts = []
    for page in pages:
        ig = page.get("instagram_business_account")
        if isinstance(ig, dict) and ig.get("id"):
            instagram_accounts.append(ig)
    return {"pages": pages, "instagram_business_accounts": instagram_accounts}


def sync_comments(max_pages: int = 1) -> list[dict]:
    if not configured():
        raise RuntimeError("Meta Graph pull connector is not configured")
    messages: list[dict] = []
    for page_id in config.META_FACEBOOK_PAGE_IDS:
        messages.extend(_sync_facebook_page(page_id, max_pages=max_pages))
    for ig_id in config.META_INSTAGRAM_BUSINESS_IDS:
        messages.extend(_sync_instagram_business(ig_id, max_pages=max_pages))
    return messages


def _sync_facebook_page(page_id: str, *, max_pages: int) -> list[dict]:
    page_token = _page_access_token(page_id) or config.META_GRAPH_ACCESS_TOKEN
    posts = _paged(
        f"{page_id}/feed",
        {
            "fields": "id,message,permalink_url,created_time,from",
            "limit": config.META_SYNC_POST_LIMIT,
        },
        max_pages=max_pages,
        access_token=page_token,
    )
    out: list[dict] = []
    for post in posts:
        comments = _paged(
            f"{post['id']}/comments",
            {
                "fields": "id,message,created_time,from,permalink_url",
                "filter": "stream",
                "limit": config.META_SYNC_COMMENT_LIMIT,
            },
            max_pages=max_pages,
            access_token=page_token,
        )
        for comment in comments:
            text = comment.get("message")
            if not text:
                continue
            author = comment.get("from") or {}
            out.append(
                {
                    "source": "meta_graph_pull",
                    "channel": "facebook_comment",
                    "account": page_id,
                    "external_id": comment.get("id"),
                    "author_name": author.get("name"),
                    "author_handle": author.get("id"),
                    "text": text,
                    "url": comment.get("permalink_url") or post.get("permalink_url"),
                    "occurred_at": comment.get("created_time") or post.get("created_time"),
                    "metadata": {"facebook_post": post, "facebook_comment": comment},
                    "raw_payload": comment,
                }
            )
    return out


def _sync_instagram_business(ig_id: str, *, max_pages: int) -> list[dict]:
    media_items = _paged(
        f"{ig_id}/media",
        {
            "fields": "id,caption,permalink,timestamp,media_type",
            "limit": config.META_SYNC_MEDIA_LIMIT,
        },
        max_pages=max_pages,
    )
    out: list[dict] = []
    for media in media_items:
        comments = _paged(
            f"{media['id']}/comments",
            {
                "fields": "id,text,timestamp,username,like_count,replies{id,text,timestamp,username}",
                "limit": config.META_SYNC_COMMENT_LIMIT,
            },
            max_pages=max_pages,
        )
        for comment in comments:
            out.extend(_normalize_ig_comment_tree(ig_id, media, comment))
    return out


def _normalize_ig_comment_tree(ig_id: str, media: dict, comment: dict) -> list[dict]:
    rows = [_normalize_ig_comment(ig_id, media, comment, parent_id=None)]
    replies = ((comment.get("replies") or {}).get("data") or [])
    for reply in replies:
        rows.append(_normalize_ig_comment(ig_id, media, reply, parent_id=comment.get("id")))
    return [row for row in rows if row.get("text")]


def _normalize_ig_comment(ig_id: str, media: dict, comment: dict, parent_id: str | None) -> dict:
    return {
        "source": "meta_graph_pull",
        "channel": "instagram_comment",
        "account": ig_id,
        "external_id": comment.get("id"),
        "author_name": comment.get("username"),
        "author_handle": comment.get("username"),
        "text": comment.get("text") or "",
        "url": media.get("permalink"),
        "occurred_at": comment.get("timestamp") or _now_iso(),
        "metadata": {
            "instagram_media": media,
            "instagram_comment": comment,
            "parent_comment_id": parent_id,
        },
        "raw_payload": comment,
    }


def _page_access_token(page_id: str) -> str | None:
    payload = _graph_get(page_id, {"fields": "access_token"})
    token = payload.get("access_token")
    return str(token) if token else None


def _paged(
    path: str,
    params: dict[str, Any],
    *,
    max_pages: int,
    access_token: str | None = None,
) -> list[dict]:
    out: list[dict] = []
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    request_params = dict(params)
    request_params["access_token"] = access_token or config.META_GRAPH_ACCESS_TOKEN
    for _ in range(max_pages):
        try:
            resp = SESSION.get(url, params=request_params, timeout=25)
        except requests.RequestException as exc:
            raise RuntimeError(f"Meta Graph request failed: {type(exc).__name__}") from exc
        if not resp.ok:
            raise RuntimeError(_graph_error_message(resp))
        payload = resp.json()
        data = payload.get("data") or []
        if isinstance(data, list):
            out.extend([item for item in data if isinstance(item, dict)])
        next_url = (payload.get("paging") or {}).get("next")
        if not next_url:
            break
        url = next_url
        request_params = {}
    return out


def _graph_get(path: str, params: dict[str, Any], *, access_token: str | None = None) -> dict:
    request_params = dict(params)
    request_params["access_token"] = access_token or config.META_GRAPH_ACCESS_TOKEN
    try:
        resp = SESSION.get(f"{GRAPH_BASE}/{path.lstrip('/')}", params=request_params, timeout=25)
    except requests.RequestException as exc:
        raise RuntimeError(f"Meta Graph request failed: {type(exc).__name__}") from exc
    if not resp.ok:
        raise RuntimeError(_graph_error_message(resp))
    return resp.json()


def _graph_error_message(resp: requests.Response) -> str:
    message = "Meta Graph request failed"
    try:
        payload = resp.json()
        error = payload.get("error") or {}
        if error.get("message"):
            message = str(error["message"])
        if error.get("code"):
            message = f"{message} (code {error['code']})"
    except ValueError:
        if resp.text:
            message = resp.text[:200]
    return f"{message}; status={resp.status_code}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
