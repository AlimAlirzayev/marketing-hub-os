"""Tiny, resilient HTTP layer for the SEO engine.

One place for fetching so timeouts, redirects, size caps and error handling are
consistent everywhere. Returns a small Fetched record instead of raising, so the
auditor can turn a network failure into an honest finding rather than a crash.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

from . import config


@dataclass
class Fetched:
    url: str                       # final URL (after redirects)
    requested_url: str             # what we asked for
    status: int = 0
    ok: bool = False
    html: str = ""
    headers: dict = field(default_factory=dict)
    elapsed_ms: int = 0
    redirected: bool = False
    error: str = ""
    content_type: str = ""


def normalize_url(url: str) -> str:
    """Add a scheme if the user typed a bare domain."""
    url = url.strip()
    if not url:
        return url
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


def fetch(url: str, *, method: str = "GET") -> Fetched:
    """GET a URL. Never raises — failures come back on Fetched.error."""
    url = normalize_url(url)
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "az,en;q=0.8,ru;q=0.6",
    }
    t0 = time.time()
    try:
        resp = requests.request(
            method, url, headers=headers, timeout=config.FETCH_TIMEOUT,
            allow_redirects=True, stream=True,
        )
        ctype = resp.headers.get("Content-Type", "")
        # size-capped read so a giant asset can't blow up memory
        raw = b""
        for chunk in resp.iter_content(64 * 1024):
            raw += chunk
            if len(raw) > config.MAX_HTML_BYTES:
                break
        enc = resp.encoding or "utf-8"
        html = raw.decode(enc, errors="replace") if "text" in ctype or "xml" in ctype or not ctype else ""
        return Fetched(
            url=str(resp.url),
            requested_url=url,
            status=resp.status_code,
            ok=resp.ok,
            html=html,
            headers={k.lower(): v for k, v in resp.headers.items()},
            elapsed_ms=int((time.time() - t0) * 1000),
            redirected=str(resp.url).rstrip("/") != url.rstrip("/"),
            content_type=ctype,
        )
    except requests.RequestException as e:
        return Fetched(
            url=url, requested_url=url,
            elapsed_ms=int((time.time() - t0) * 1000),
            error=str(e)[:200],
        )


def resolve(base: str, href: str) -> str:
    """Absolute URL from a possibly-relative href."""
    return urljoin(base, href)


def same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc.replace("www.", "") == urlparse(b).netloc.replace("www.", "")
