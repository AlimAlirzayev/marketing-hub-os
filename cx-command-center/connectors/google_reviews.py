"""Google Business Profile review pull connector."""

from __future__ import annotations

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


def configured() -> bool:
    return bool(config.GBP_ACCESS_TOKEN and config.GBP_ACCOUNT_ID and config.GBP_LOCATION_IDS)


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
        headers={"Authorization": f"Bearer {config.GBP_ACCESS_TOKEN}"},
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
    if not config.GBP_ACCESS_TOKEN:
        raise RuntimeError("GOOGLE_BUSINESS_PROFILE_ACCESS_TOKEN is not configured")
    resp = requests.put(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {config.GBP_ACCESS_TOKEN}"},
        timeout=20,
    )
    resp.raise_for_status()
    return {"dry_run": False, "status_code": resp.status_code, "response": resp.json() if resp.text else {}}
