"""Google Business Profile review pull + reply connector.

Reviews (read AND reply) are owned-business data: the Business Profile API
(mybusiness.googleapis.com/v4 — still the current reviews surface in 2026)
requires a USER principal that manages the verified profile, authenticated via
OAuth 2.0 with the `business.manage` scope. A service account cannot read or
reply to reviews. Live access additionally requires Google's one-time approval
of the project (quota flips 0 -> 300 QPM once granted); until then this connector
labels itself honestly and never fabricates reviews.

Endpoints used:
  * list  : GET  v4/accounts/{acc}/locations/{loc}/reviews          (verified only)
  * reply : PUT  v4/accounts/{acc}/locations/{loc}/reviews/{id}/reply {"comment": ...}
"""

from __future__ import annotations

import time
from typing import Any

import requests

import config

STAR_RATING = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
}

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_token_cache = {"access_token": "", "exp": 0.0}


def _has_oauth_refresh() -> bool:
    return bool(config.GBP_OAUTH_CLIENT_ID and config.GBP_OAUTH_CLIENT_SECRET
                and config.GBP_OAUTH_REFRESH_TOKEN)


def _has_auth() -> bool:
    """Either a manual short-lived token (testing) or durable refresh creds."""
    return bool(config.GBP_ACCESS_TOKEN or _has_oauth_refresh())


def access_token() -> str:
    """Return a usable bearer token. Prefers an explicit GBP_ACCESS_TOKEN (manual
    OAuth-Playground testing); otherwise mints and caches one from the refresh
    token so the system runs itself without hourly manual refreshes."""
    if config.GBP_ACCESS_TOKEN:
        return config.GBP_ACCESS_TOKEN
    if not _has_oauth_refresh():
        raise RuntimeError(
            "GBP OAuth not configured: need GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN, "
            "or CLIENT_ID + CLIENT_SECRET + REFRESH_TOKEN.")
    now = time.time()
    if _token_cache["access_token"] and _token_cache["exp"] - 60 > now:
        return _token_cache["access_token"]
    resp = requests.post(_TOKEN_URL, data={
        "client_id": config.GBP_OAUTH_CLIENT_ID,
        "client_secret": config.GBP_OAUTH_CLIENT_SECRET,
        "refresh_token": config.GBP_OAUTH_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["exp"] = now + int(payload.get("expires_in", 3600))
    return _token_cache["access_token"]


def configured() -> bool:
    return bool(_has_auth() and config.GBP_ACCOUNT_ID and config.GBP_LOCATION_IDS)


def blockers() -> list[str]:
    """Honest, human-readable reasons live GBP reviews are unavailable."""
    out: list[str] = []
    if not _has_auth():
        out.append("OAuth yoxdur: ya GBP_ACCESS_TOKEN, ya da CLIENT_ID+SECRET+REFRESH_TOKEN lazımdır "
                   "(business.manage scope, profili idarə edən hesabla)")
    if not config.GBP_ACCOUNT_ID:
        out.append("GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID yoxdur")
    if not config.GBP_LOCATION_IDS:
        out.append("GOOGLE_BUSINESS_PROFILE_LOCATION_IDS yoxdur")
    return out


def sync_reviews(max_pages_per_location: int = 2) -> list[dict]:
    if not configured():
        raise RuntimeError("Google Business Profile credentials are not configured")
    out: list[dict] = []
    for location_id in config.GBP_LOCATION_IDS:
        out.extend(_sync_location(location_id, max_pages_per_location))
    return out


def _sync_location(location_id: str, max_pages: int) -> list[dict]:
    reviews: list[dict] = []
    page_token = None
    for _ in range(max_pages):
        payload = _list_reviews(location_id, page_token)
        for review in payload.get("reviews", []) or []:
            reviews.append(normalize_review(review, location_id))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return reviews


def _list_reviews(location_id: str, page_token: str | None) -> dict:
    account_id = config.GBP_ACCOUNT_ID
    location = location_id
    url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location}/reviews"
    params: dict[str, Any] = {
        "pageSize": config.GBP_REVIEW_PAGE_SIZE,
        "orderBy": "updateTime desc",
    }
    if page_token:
        params["pageToken"] = page_token
    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {access_token()}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_review(review: dict, location_id: str) -> dict:
    reviewer = review.get("reviewer") or {}
    name = review.get("name") or ""
    review_id = name.rsplit("/", 1)[-1] if name else review.get("reviewId") or review.get("id")
    comment = review.get("comment") or "(rating-only Google review)"
    raw_rating = review.get("starRating", review.get("rating"))
    rating = STAR_RATING.get(str(raw_rating or "").upper(), raw_rating)
    return {
        "source": "google_business_profile",
        "channel": "google_review",
        "account": location_id,
        "external_id": review_id or name,
        "author_name": reviewer.get("displayName") or review.get("author_name"),
        "author_handle": reviewer.get("profilePhotoUrl") or review.get("author_handle"),
        "text": comment,
        "rating": rating,
        "url": review.get("reviewUrl") or review.get("url"),
        "occurred_at": review.get("updateTime") or review.get("createTime") or review.get("created_at"),
        "metadata": {"google_review": review, "location_id": location_id, "resource_name": name},
        "raw_payload": review,
    }


def reply_to_review(resource_name: str, comment: str, dry_run: bool = True) -> dict:
    if not resource_name:
        raise RuntimeError("Google review resource name is missing")
    url = f"https://mybusiness.googleapis.com/v4/{resource_name}/reply"
    payload = {"comment": comment}
    if dry_run:
        return {"dry_run": True, "method": "PUT", "url": url, "json": payload}
    if not _has_auth():
        raise RuntimeError("GBP OAuth is not configured (no access token / refresh creds)")
    resp = requests.put(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {access_token()}"},
        timeout=20,
    )
    resp.raise_for_status()
    return {"dry_run": False, "status_code": resp.status_code, "response": resp.json() if resp.text else {}}
