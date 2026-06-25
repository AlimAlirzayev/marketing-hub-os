"""Google SERP catch-all source (via the user's Apify google-search-scraper).

AZ shops barely do SEO/structured-data, but Google still indexes them and very
often shows the price right in the result snippet. So a Google search for
"<product> qiymət" surfaces prices from stores we can't reach directly (the JS
SPAs umico/ucuzu/qiymeti.net AND smaller shops like w-t.az) in one cheap call.
We keep only .az results, pull the price from title+snippet, and tag the real
store domain so merchant-reputation still applies. Flagged "via Google — verify
on site" because a snippet price can be stale/promotional.

Dormant without APIFY_API_TOKEN.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import config
from models import Offer

_ACTOR = "apify~google-search-scraper"
_PRICE = re.compile(r"(\d{1,3}(?:[ .,]\d{3})*(?:[.,]\d{1,2})?)\s*(?:₼|AZN|man\.?|manat)", re.I)
# obvious non-shop domains to drop even if .az
_DROP = ("wikipedia", "youtube", "facebook", "instagram", "apple.com")


def available() -> bool:
    return bool(config.APIFY_API_TOKEN)


def _to_float(s: str):
    s = s.strip().replace(" ", "")
    if s.count(".") > 1:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def search(query: str, az_only: bool = True) -> list[Offer]:
    if not config.APIFY_API_TOKEN:
        return []
    import httpx
    ep = (f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"
          f"?token={config.APIFY_API_TOKEN}&timeout=90")
    payload = {"queries": f"{query} qiymət\n{query} qiyməti azn",
               "resultsPerPage": 20, "maxPagesPerQuery": 1,
               "countryCode": "az", "languageCode": "az", "saveHtml": False}
    try:
        r = httpx.post(ep, json=payload, timeout=140)
        if r.status_code >= 400:
            return []
        pages = r.json()
    except Exception:
        return []

    offers: list[Offer] = []
    seen = set()
    for page in pages if isinstance(pages, list) else []:
        for o in (page.get("organicResults") or []):
            url = o.get("url") or ""
            dom = _domain(url)
            if not dom or any(d in dom for d in _DROP):
                continue
            if az_only and not dom.endswith(".az"):
                continue
            text = f"{o.get('title','')} {o.get('description','')}"
            prices = [p for p in (_to_float(m.group(1)) for m in _PRICE.finditer(text)) if p]
            if not prices:
                continue
            # the largest snippet price is usually the real price, not a monthly
            # instalment / accessory teaser.
            price = max(prices)
            key = (dom, round(price))
            if key in seen:
                continue
            seen.add(key)
            offers.append(Offer(
                title=str(o.get("title") or query), price=price, url=url,
                source=dom, seller="(via Google)", condition="unknown",
                official=None, flags=["via Google — verify on site"]))
    return offers
