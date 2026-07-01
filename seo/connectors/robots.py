"""robots.txt + sitemap discovery — 100% free, no key.

Fetches /robots.txt, tells us whether it exists, which sitemaps it declares,
whether the audited path is disallowed for a generic crawler, and — a 2026
signal — whether AI/LLM crawlers are governed at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from .. import config
from ..http import fetch


@dataclass
class RobotsInfo:
    exists: bool = False
    url: str = ""
    sitemaps: list[str] = field(default_factory=list)
    disallow_all: bool = False           # blocks the whole site for *
    ai_bots_mentioned: list[str] = field(default_factory=list)
    raw: str = ""
    error: str = ""


def check_robots(site_url: str) -> RobotsInfo:
    parsed = urlparse(site_url if "://" in site_url else "https://" + site_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = urljoin(base, "/robots.txt")
    r = fetch(robots_url)
    info = RobotsInfo(url=robots_url)
    if r.error:
        info.error = r.error
        return info
    # A 200 that is actually HTML (soft-404) doesn't count as a real robots.txt
    if r.status != 200 or "text/html" in r.content_type.lower():
        return info
    info.exists = True
    info.raw = r.html
    cur_agents: list[str] = []
    star_block = False
    for line in r.html.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            if not line:
                cur_agents = []
            continue
        field_, _, value = line.partition(":")
        field_ = field_.strip().lower()
        value = value.strip()
        if field_ == "user-agent":
            cur_agents.append(value)
            for bot in config.AI_BOTS:
                if bot.lower() == value.lower() and bot not in info.ai_bots_mentioned:
                    info.ai_bots_mentioned.append(bot)
        elif field_ == "sitemap" and value:
            info.sitemaps.append(value)
        elif field_ == "disallow" and value == "/" and "*" in cur_agents:
            star_block = True
    info.disallow_all = star_block
    return info


def check_sitemap(site_url: str, declared: list[str]) -> tuple[bool, str]:
    """True if a sitemap is reachable (declared in robots or at /sitemap.xml)."""
    candidates = list(declared)
    parsed = urlparse(site_url if "://" in site_url else "https://" + site_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates.append(urljoin(base, "/sitemap.xml"))
    candidates.append(urljoin(base, "/sitemap_index.xml"))
    for url in candidates:
        r = fetch(url)
        if not r.error and r.status == 200 and (
            "xml" in r.content_type.lower() or "<urlset" in r.html[:2000] or "<sitemapindex" in r.html[:2000]
        ):
            return True, url
    return False, ""
