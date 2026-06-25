"""Meta payment receipts pulled from Gmail.

Meta does not expose paid-invoice data via the Marketing API, so - exactly like
the reference dashboard - we read the payment-receipt emails Meta sends and parse
the amount/date/reference out of them.

Design choice for this machine: the FastAPI server does NOT do Gmail OAuth itself.
Instead it reads a cache file (``data/invoices_cache.json``) that is refreshed
out-of-band. Two supported refreshers:

  1. The Gmail MCP already available inside Xalq Insurance Digital OS (Claude can search
     "from:Meta receipt" and write the cache) - zero OAuth setup.
  2. A scheduled Gmail API job (google-api-python-client) writing the same file.

If no cache exists, the dispatcher uses the demo invoices so the tab still
renders. The cache schema matches ``demo._invoices`` output exactly.
"""

from __future__ import annotations

import json
import os

from config import DATA_DIR

CACHE_PATH = os.path.join(DATA_DIR, "invoices_cache.json")


def load_cached_invoices(ym: str) -> dict | None:
    """Return cached invoices for ``ym`` if a cache file is present, else None.

    Cache layout:
        { "2026-04": {"rows": [...], "count": N, "total": x, "unbilled": y}, ... }
    """
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return cache.get(ym)


def save_invoices(ym: str, invoices: dict) -> None:
    """Write/replace one month's invoices in the cache (used by refreshers)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}
    cache[ym] = invoices
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
