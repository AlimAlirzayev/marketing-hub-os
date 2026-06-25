"""Apify deep-render engine - the managed, robust tier for hostile JS-SPAs.

Apify runs real browsers in the cloud and sails past WAFs / JS gating that our
local stack can't. This module is dormant until APIFY_API_TOKEN is set in .env
(it is empty right now), then `--deep` prefers it over local Playwright.

Default actor: apify/website-content-crawler - a full JS browser render that
returns clean text/markdown (built for feeding LLMs), which our digest + LLM
extractor consumes directly. Override with PH_APIFY_ACTOR; if the name contains
"web-scraper" we send the Puppeteer pageFunction input instead.
"""

from __future__ import annotations

import json
import os

import config

# Fallback for apify/web-scraper (Puppeteer): render, lazy-load, return <html>.
# (waitForLoadState/waitForTimeout are Playwright-only and #error on this actor.)
_PAGE_FUNCTION = (
    "async function pageFunction(context){"
    "const {page,request}=context;"
    "await new Promise(r=>setTimeout(r,5000));"
    "try{for(let i=0;i<3;i++){await page.evaluate(()=>window.scrollBy(0,3500));"
    "await new Promise(r=>setTimeout(r,1200));}}catch(e){}"
    "return { url: request.url, html: await page.content() };}"
)

DEFAULT_ACTOR = "apify~website-content-crawler"


def available() -> bool:
    return bool(config.APIFY_API_TOKEN)


def _input_for(actor: str, url: str) -> dict:
    if "web-scraper" in actor:
        return {"startUrls": [{"url": url}], "runMode": "PRODUCTION",
                "pageFunction": _PAGE_FUNCTION,
                "proxyConfiguration": {"useApifyProxy": True}, "maxPagesPerCrawl": 1}
    # website-content-crawler / playwright-scraper: full render -> text+markdown.
    return {
        "startUrls": [{"url": url}],
        "crawlerType": "playwright:chrome",
        "maxCrawlDepth": 0, "maxCrawlPages": 1,
        "dynamicContentWaitSecs": 10, "saveMarkdown": True, "saveHtml": True,
        "proxyConfiguration": {"useApifyProxy": True},
        "removeCookieWarnings": True,
    }


def render(url: str, *, timeout_s: int = 110) -> str:
    """Return rendered text/markdown/HTML for `url` via Apify, or "" on failure."""
    if not config.APIFY_API_TOKEN:
        return ""
    import httpx

    actor = os.getenv("PH_APIFY_ACTOR", DEFAULT_ACTOR)
    endpoint = (f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
                f"?token={config.APIFY_API_TOKEN}&timeout={timeout_s}")
    try:
        r = httpx.post(endpoint, json=_input_for(actor, url), timeout=timeout_s + 40)
        if r.status_code >= 400:
            return ""
        items = r.json()
        if isinstance(items, list) and items:
            it = items[0]
            if "#error" in it:
                return ""
            # content-crawler -> text/markdown; web-scraper -> html
            return (it.get("markdown") or it.get("text") or it.get("html") or "")
    except Exception:
        return ""
    return ""
