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
    # Real-world AZ sites break the naive fetch in two common ways; we recover
    # (so the on-page audit still runs) but RECORD the defect so the auditor can
    # raise it as an honest finding rather than hiding it behind a lucky retry.
    ssl_verified: bool = True       # False: cert chain failed strict verification
    ssl_error: str = ""             # the verification error, when it failed
    apex_unreachable: bool = False  # apex host failed; served from www fallback
    www_fallback_url: str = ""      # the www host that actually answered


def normalize_url(url: str) -> str:
    """Add a scheme if the user typed a bare domain."""
    url = url.strip()
    if not url:
        return url
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


def _with_www(url: str) -> str:
    """Prepend www. to a bare (non-www) host, preserving scheme/path."""
    p = urlparse(url)
    if p.netloc.startswith("www."):
        return url
    return p._replace(netloc="www." + p.netloc).geturl()


def _read_response(resp, requested_url: str, t0: float) -> Fetched:
    """Turn a live requests.Response into a Fetched (size-capped, encoding-safe)."""
    ctype = resp.headers.get("Content-Type", "")
    raw = b""
    for chunk in resp.iter_content(64 * 1024):
        raw += chunk
        if len(raw) > config.MAX_HTML_BYTES:
            break
    enc = resp.encoding or "utf-8"
    html = raw.decode(enc, errors="replace") if "text" in ctype or "xml" in ctype or not ctype else ""
    return Fetched(
        url=str(resp.url),
        requested_url=requested_url,
        status=resp.status_code,
        ok=resp.ok,
        html=html,
        headers={k.lower(): v for k, v in resp.headers.items()},
        elapsed_ms=int((time.time() - t0) * 1000),
        redirected=str(resp.url).rstrip("/") != requested_url.rstrip("/"),
        content_type=ctype,
    )


def fetch(url: str, *, method: str = "GET", _allow_www_fallback: bool = True) -> Fetched:
    """GET a URL. Never raises — failures come back on Fetched.error.

    Two recoveries make it survive the real Azerbaijani web (both proven on
    xalqsigorta.az): a cert chain that only strict-verifies via the OS store
    (common: server omits the intermediate) is retried unverified so the on-page
    audit still runs, flagged with ssl_verified=False; and an apex host that times
    out is retried once via www. Both defects are recorded, never swallowed."""
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
        return _read_response(resp, url, t0)
    except requests.exceptions.SSLError as e:
        # The cert failed certifi's strict chain check. A browser/OS store often
        # still trusts it (missing intermediate resolved via AIA), so re-fetch
        # UNVERIFIED to read the page — but mark the chain as broken for a finding.
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        try:
            resp = requests.request(
                method, url, headers=headers, timeout=config.FETCH_TIMEOUT,
                allow_redirects=True, stream=True, verify=False,
            )
            f = _read_response(resp, url, t0)
            f.ssl_verified = False
            f.ssl_error = str(e)[:200]
            return f
        except requests.RequestException as e2:
            return Fetched(url=url, requested_url=url,
                           elapsed_ms=int((time.time() - t0) * 1000),
                           error=str(e2)[:200], ssl_verified=False,
                           ssl_error=str(e)[:200])
    except requests.RequestException as e:
        # Connection/timeout. A very common AZ misconfig is a dead apex A-record
        # while www works — try www once so we can both audit the site AND report
        # that the apex is unreachable (a real canonical/reachability defect).
        if _allow_www_fallback and not urlparse(url).netloc.startswith("www."):
            alt = fetch(_with_www(url), method=method, _allow_www_fallback=False)
            if alt.ok or alt.html:
                alt.requested_url = url
                alt.apex_unreachable = True
                alt.www_fallback_url = alt.url
                return alt
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
