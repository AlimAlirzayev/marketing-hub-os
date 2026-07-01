"""The auditor — one call, full technical-SEO picture of a URL.

Gathers every signal (page HTML, robots.txt, sitemap reachability, Core Web
Vitals) in parallel where it helps, runs the 2026 checklist, and returns a
structured AuditResult that the report layer turns into an Azerbaijani deliverable.
"""

from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import http
from ..connectors import pagespeed
from ..connectors import robots as robots_mod
from ..htmlparse import parse
from . import checklist
from .checklist import AuditContext, Finding


@dataclass
class AuditResult:
    url: str
    final_url: str
    fetched_ok: bool
    score: int
    grade: str
    findings: list[Finding] = field(default_factory=list)
    fetched: object = None
    page: object = None
    vitals: object = None
    robots: object = None
    ts: str = ""
    error: str = ""

    def by_status(self, *statuses: str) -> list[Finding]:
        return [f for f in self.findings if f.status in statuses]

    def summary(self) -> dict:
        c: dict[str, int] = {}
        for f in self.findings:
            c[f.status] = c.get(f.status, 0) + 1
        return c


def audit_url(url: str, *, with_vitals: bool = True, strategy: str = "mobile") -> AuditResult:
    """Full technical SEO audit of a single URL. Never raises."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fetched = http.fetch(url)

    if fetched.error or not fetched.html:
        return AuditResult(
            url=http.normalize_url(url), final_url=fetched.url, fetched_ok=False,
            score=0, grade="F", ts=ts, fetched=fetched,
            error=fetched.error or f"boş cavab (HTTP {fetched.status})",
            findings=[Finding("status", checklist._INDEX, "Səhifəyə çıxış", "fail", 3,
                              f"Səhifə yüklənmədi: {fetched.error or fetched.status}",
                              "URL-i və serverin əlçatanlığını yoxla.")],
        )

    page = parse(fetched.html)
    # refine internal/external link split against the real host
    _refine_links(page, fetched.url)

    # robots + sitemap + vitals concurrently (network-bound, independent)
    robots_info = vitals = None
    sitemap_ok, sitemap_url = False, ""
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_robots = ex.submit(robots_mod.check_robots, fetched.url)
        f_vitals = ex.submit(pagespeed.core_web_vitals, fetched.url, strategy) if with_vitals else None
        robots_info = f_robots.result()
        sitemap_ok, sitemap_url = robots_mod.check_sitemap(fetched.url, robots_info.sitemaps)
        vitals = f_vitals.result() if f_vitals else pagespeed.Vitals()

    ctx = AuditContext(
        url=fetched.url, fetched=fetched, page=page, robots=robots_info,
        sitemap_ok=sitemap_ok, sitemap_url=sitemap_url, vitals=vitals,
    )
    findings = checklist.run_all(ctx)
    pct, grade = checklist.score(findings)

    return AuditResult(
        url=http.normalize_url(url), final_url=fetched.url, fetched_ok=True,
        score=pct, grade=grade, findings=findings,
        fetched=fetched, page=page, vitals=vitals, robots=robots_info, ts=ts,
    )


def _refine_links(page, base_url: str) -> None:
    """The parser guesses internal/external by scheme; nothing to recompute here
    without the full href list, but keep the hook so future crawlers can enrich."""
    return
