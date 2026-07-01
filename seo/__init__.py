"""RAMIN OS — SEO Engine (the system's search-visibility brain).

Three engines over one free-first core, plugged into llm_router + brain like
every other studio:

    Audit    — crawl any URL, score it against the 2026 SEO checklist, and hand
               back a prioritized, Azerbaijani fix report.  ("make my site perfect")
    Research — seed keyword -> Google Suggest expansion -> LLM clustering/intent
               -> SERP/PAA gap.                              ("do SEO research")
    Content  — keyword + SERP -> structured brief -> on-page-perfect draft.
               ("write an SEO article for my site")

Design rules (inherited from the ecosystem charter):
  * Free-first. Nothing here requires a paid SEO tool. PageSpeed Insights runs
    keyless; Google Suggest is public; the crawler is our own; GSC is optional.
  * Dependency-light. HTML is parsed with the stdlib (no bs4/lxml) so it runs on
    the locked-down work machine. Everything degrades gracefully.
  * Never fabricate. Every number is measured or labelled CANLI / DEMO / ƏLÇATMAZ.

Public API (stable):
    audit_url(url, ...)      -> AuditResult    # technical SEO audit of one page
    audit_report(result)     -> str            # ready-to-read Azerbaijani report
"""

from __future__ import annotations

from .audit.auditor import AuditResult, Finding, audit_url
from .report import audit_report

__all__ = ["AuditResult", "Finding", "audit_url", "audit_report"]

__version__ = "0.1.0"
