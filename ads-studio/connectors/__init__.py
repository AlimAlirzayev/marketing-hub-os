"""Data-source dispatcher.

Every downstream caller goes through these functions and never needs to know
whether the data came from the live Meta Marketing API or the demo engine. Each
function takes an optional ``account_id`` so the same dashboard can serve
multiple ad accounts (Xalq Sigorta, clients, side projects).
"""

from __future__ import annotations

import sys

from config import DATA_MODE

from . import demo, gmail


def _live_or_demo(fn_name: str, *args, **kwargs):
    """Try live Meta for the requested function; fall back to demo on failure.

    The connector already retries throttles/5xx, so reaching this fallback means
    a real, persistent problem. We log the full (token-safe) reason to stderr so
    the degradation is never silent, while the UI still gets a labelled badge.
    """
    if DATA_MODE == "live":
        try:
            from . import meta
            return getattr(meta, fn_name)(*args, **kwargs), "meta-live"
        except Exception as exc:
            print(f"[ads-studio] live Meta '{fn_name}' failed → demo fallback: {exc}",
                  file=sys.stderr)
            return getattr(demo, fn_name)(*args, **kwargs), f"demo (live failed: {type(exc).__name__})"
    return getattr(demo, fn_name)(*args, **kwargs), "demo"


def get_report(ym: str, platform: str = "all", account_id: str | None = None) -> dict:
    report, source = _live_or_demo("build_report", ym, platform, account_id)
    # Always tag the source so the UI badge stays accurate after a fallback.
    report["account"]["source"] = source
    cached = gmail.load_cached_invoices(ym)
    if cached:
        report["invoices"] = cached
        report["invoices"]["source"] = "gmail"
    else:
        report["invoices"]["source"] = source
    return report


def get_segments(ym: str, account_id: str | None = None) -> dict:
    data, _ = _live_or_demo("segments", ym, account_id)
    return data


def get_top_campaigns(ym: str, account_id: str | None = None, limit: int = 10) -> list[dict]:
    data, _ = _live_or_demo("top_campaigns", ym, account_id, limit)
    return data


def get_creative_diagnostics(ym: str, account_id: str | None = None,
                              limit: int = 10) -> list[dict]:
    data, _ = _live_or_demo("creative_diagnostics", ym, account_id, limit)
    return data


def get_video_metrics(ym: str, account_id: str | None = None) -> dict:
    data, _ = _live_or_demo("video_metrics", ym, account_id)
    return data
