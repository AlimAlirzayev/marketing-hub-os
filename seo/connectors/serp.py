"""SERP connector — free organic results via DuckDuckGo HTML (no key, no block).

Google SERP scraping is fragile and TOS-hostile; DuckDuckGo's HTML endpoint is
free, stable, and returns the same competitive picture (who ranks for a query).
We use it to find the top competitor URLs, then our own crawler reads their
heading structure for gap analysis. Apify (already in the ecosystem) is an
optional heavier fallback.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import requests

_ENDPOINT = "https://html.duckduckgo.com/html/"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_BLOCK = re.compile(r'result__a"[^>]*href="(.*?)".*?>(.*?)</a>', re.DOTALL)
_SNIP = re.compile(r'result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class SerpResult:
    rank: int
    title: str
    url: str
    snippet: str = ""

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.replace("www.", "")


def _clean_url(u: str) -> str:
    if "uddg=" in u:
        qs = parse_qs(urlparse(u).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return u


def _text(t: str) -> str:
    return _html.unescape(_TAG.sub("", t)).strip()


def parse_serp(html: str, *, n: int = 10) -> list[SerpResult]:
    """Parse a DuckDuckGo HTML results page into de-duplicated SerpResults
    (one per domain). Pure function — unit-testable without network."""
    blocks = _BLOCK.findall(html)
    snips = [_text(s) for s in _SNIP.findall(html)]
    out: list[SerpResult] = []
    seen: set[str] = set()
    for i, (href, title) in enumerate(blocks):
        url = _clean_url(href)
        dom = urlparse(url).netloc.replace("www.", "")
        if not url.startswith("http") or dom in seen or "duckduckgo.com" in dom:
            continue
        seen.add(dom)
        out.append(SerpResult(rank=len(out) + 1, title=_text(title), url=url,
                              snippet=snips[i] if i < len(snips) else ""))
        if len(out) >= n:
            break
    return out


def search(query: str, *, n: int = 10, region: str = "az-az") -> list[SerpResult]:
    """Top organic results for a query. Never raises — [] on failure."""
    try:
        r = requests.post(_ENDPOINT, data={"q": query, "kl": region},
                          headers=_UA, timeout=14)
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []
    return parse_serp(r.text, n=n)
