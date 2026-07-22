"""Live channel synchronization for Customer Relations Center."""

from __future__ import annotations

import threading
import time
from typing import Callable

import alerts
import config
import store
import triage
from connectors import chatplace, google_reviews, meta_graph, youtube_mentions

_scheduler_started = False


def integration_status() -> dict:
    return {
        "mode": config.DATA_MODE,
        "public_base_url": config.PUBLIC_BASE_URL,
        "public_webhooks_ready": config.PUBLIC_BASE_URL.startswith("https://"),
        "auto_sync_interval_seconds": config.CX_SYNC_INTERVAL_SECONDS,
        "channels": {
            "meta_webhook": {
                "configured": bool(config.META_VERIFY_TOKEN),
                "mode": "webhook",
                "detail": "Instagram/Facebook realtime webhook",
            },
            "meta_graph_pull": {
                "configured": meta_graph.configured(),
                "mode": "pull",
                "detail": "Owned Facebook Page and Instagram Business comments",
                "missing": _missing(
                    [
                        ("META_GRAPH_ACCESS_TOKEN or META_ACCESS_TOKEN", bool(config.META_GRAPH_ACCESS_TOKEN)),
                        ("META_FACEBOOK_PAGE_IDS or META_INSTAGRAM_BUSINESS_IDS", bool(config.META_FACEBOOK_PAGE_IDS or config.META_INSTAGRAM_BUSINESS_IDS)),
                    ]
                ),
            },
            "chatplace_webhook": {
                "configured": bool(config.WEBHOOK_SECRET),
                "mode": "webhook",
                "detail": "Chatplace External API request to /api/webhooks/chatplace",
            },
            "chatplace_pull": {
                "configured": chatplace.configured_for_pull(),
                "mode": "pull",
                "detail": "Optional Chatplace-compatible JSON feed",
                "missing": _missing([("CHATPLACE_PULL_URL", bool(config.CHATPLACE_PULL_URL))]),
            },
            "google_reviews": {
                "configured": google_reviews.configured(),
                "mode": "pull+reply",
                "detail": "Google Business Profile reviews (read + reply) — OAuth business.manage; "
                          "needs Google API access approval (quota 0→300 QPM) on a 60-day-verified profile",
                "missing": google_reviews.blockers(),
            },
            "youtube_pull": {
                "configured": youtube_mentions.configured(),
                "mode": "pull",
                "detail": "YouTube brand-mention videos and public comments (social listening)",
                "missing": _missing([("YOUTUBE_API_KEY", bool(config.YOUTUBE_API_KEY))]),
            },
            "telegram_alerts": {
                "configured": bool(config.TELEGRAM_BOT_TOKEN and config.CX_ALERT_CHAT_ID),
                "mode": "alert",
                "detail": "Critical/high alert push",
            },
        },
    }


def sync_all(*, max_pages: int = 1) -> dict:
    results = {
        "ok": True,
        "channels": {},
        "totals": {"received": 0, "new": 0, "updated": 0, "alerts": 0, "errors": 0},
    }
    _run_channel(results, "meta_graph_pull", lambda: meta_graph.sync_comments(max_pages=max_pages))
    _run_channel(results, "chatplace_pull", lambda: chatplace.sync_pull(limit=200))
    _run_channel(results, "google_reviews", lambda: google_reviews.sync_reviews(max_pages_per_location=max_pages))
    _run_channel(results, "youtube_pull", lambda: youtube_mentions.sync_mentions())
    results["ok"] = results["totals"]["errors"] == 0
    return results


def sync_youtube(*, max_videos: int = 5) -> dict:
    results = {
        "ok": True,
        "channels": {},
        "totals": {"received": 0, "new": 0, "updated": 0, "alerts": 0, "errors": 0},
    }
    _run_channel(results, "youtube_pull", lambda: youtube_mentions.sync_mentions(max_videos=max_videos))
    results["ok"] = results["totals"]["errors"] == 0
    return results


def sync_meta(*, max_pages: int = 1) -> dict:
    results = {
        "ok": True,
        "channels": {},
        "totals": {"received": 0, "new": 0, "updated": 0, "alerts": 0, "errors": 0},
    }
    _run_channel(results, "meta_graph_pull", lambda: meta_graph.sync_comments(max_pages=max_pages))
    results["ok"] = results["totals"]["errors"] == 0
    return results


def sync_google_reviews(*, max_pages_per_location: int = 2) -> dict:
    results = {
        "ok": True,
        "channels": {},
        "totals": {"received": 0, "new": 0, "updated": 0, "alerts": 0, "errors": 0},
    }
    _run_channel(
        results,
        "google_reviews",
        lambda: google_reviews.sync_reviews(max_pages_per_location=max_pages_per_location),
    )
    results["ok"] = results["totals"]["errors"] == 0
    return results


def start_background_sync() -> None:
    global _scheduler_started
    if _scheduler_started or config.CX_SYNC_INTERVAL_SECONDS <= 0:
        return
    _scheduler_started = True
    thread = threading.Thread(target=_sync_loop, name="cx-live-sync", daemon=True)
    thread.start()


def _sync_loop() -> None:
    time.sleep(max(5, min(config.CX_SYNC_INTERVAL_SECONDS, 60)))
    while True:
        try:
            sync_all(max_pages=1)
        except Exception:
            pass
        time.sleep(config.CX_SYNC_INTERVAL_SECONDS)


def _run_channel(results: dict, name: str, fetcher: Callable[[], list[dict]]) -> None:
    if name == "meta_graph_pull" and not meta_graph.configured():
        results["channels"][name] = {"configured": False, "skipped": True, "reason": "missing_config"}
        return
    if name == "chatplace_pull" and not chatplace.configured_for_pull():
        results["channels"][name] = {"configured": False, "skipped": True, "reason": "missing_config"}
        return
    if name == "google_reviews" and not google_reviews.configured():
        results["channels"][name] = {"configured": False, "skipped": True, "reason": "missing_config"}
        return
    if name == "youtube_pull" and not youtube_mentions.configured():
        results["channels"][name] = {"configured": False, "skipped": True, "reason": "missing_config"}
        return
    try:
        messages = fetcher()
        summary = _ingest_many(messages)
        results["channels"][name] = {"configured": True, "skipped": False, **summary}
        for key in results["totals"]:
            results["totals"][key] += summary.get(key, 0)
    except Exception as exc:
        results["channels"][name] = {
            "configured": True,
            "skipped": False,
            "error": str(exc),
            "received": 0,
            "new": 0,
            "updated": 0,
            "alerts": 0,
            "errors": 1,
        }
        results["totals"]["errors"] += 1


def _ingest_many(messages: list[dict]) -> dict:
    summary = {"received": len(messages), "new": 0, "updated": 0, "alerts": 0, "errors": 0}
    for message in messages:
        try:
            result = triage.triage_message(message)
            item = store.upsert_complaint(message, result)
            alert = alerts.maybe_alert(item)
            if item.get("_is_new"):
                summary["new"] += 1
            else:
                summary["updated"] += 1
            if alert.get("sent"):
                summary["alerts"] += 1
        except Exception:
            summary["errors"] += 1
    return summary


def _missing(items: list[tuple[str, bool]]) -> list[str]:
    return [name for name, ok in items if not ok]
