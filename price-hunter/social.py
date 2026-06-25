"""Social-commerce source - Instagram sellers (via the user's Apify actor).

A huge slice of AZ retail (electronics, cosmetics, fashion) sells ONLY on
Instagram/TikTok with no website at all. A web-only price tool is blind to them.
This scrapes Instagram hashtag pages, pulls the price from the post caption and
the seller handle, and surfaces them as offers - clearly tagged as social
sellers (DM to buy, no warranty) and scored on the low "social" trust tier so
they inform without ever masquerading as an official deal.

directUrls (hashtag explore pages) is the input that works; hashtag *search* mode
is blocked by Instagram. Dormant without APIFY_API_TOKEN.
"""

from __future__ import annotations

import re

import config
from models import Offer

_ACTOR = "apify~instagram-scraper"
_PRICE = re.compile(r"(\d{2,3}(?:[ .,]\d{3})*(?:[.,]\d{1,2})?)\s*(?:₼|azn|man\.?|manat)", re.I)


def available() -> bool:
    return bool(config.APIFY_API_TOKEN)


def _tags(query: str) -> list[str]:
    core = re.sub(r"[^a-z0-9]+", "", query.lower())
    head = re.sub(r"[^a-z0-9]+", "", query.lower().split()[0]) if query.split() else core
    tags = [core, core + "baku", head + "baku", head + "az"]
    # de-dup, keep short/usable hashtags
    out = []
    for t in tags:
        if 3 <= len(t) <= 30 and t not in out:
            out.append(t)
    return out[:3]


def _to_float(s: str):
    s = s.strip().replace(" ", "")
    if s.count(".") > 1:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _anchors(query: str) -> list[str]:
    """Distinguishing phrases to locate the product inside a multi-item caption,
    e.g. "airpods pro 2" -> ["airpods pro 2", "pro 2", "pro2"]."""
    q = re.sub(r"\s+", " ", query.lower()).strip()
    toks = q.split()
    out = [q]
    if len(toks) >= 2:
        out.append(" ".join(toks[-2:]))            # "pro 2"
        out.append("".join(toks[-2:]))             # "pro2"
    return list(dict.fromkeys(out))


def _price_near_product(caption: str, query: str):
    """Pick the price closest to where the product is mentioned - so in
    'Airpods 4 239Azn ... Pro 2 389Azn' we return 389 for a 'pro 2' query."""
    low = caption.lower()
    anchor_pos = [low.find(a) for a in _anchors(query) if low.find(a) >= 0]
    if not anchor_pos:
        return None
    best = None
    for m in _PRICE.finditer(caption):
        val = _to_float(m.group(1))
        if not val:
            continue
        dist = min(abs(m.start() - ap) for ap in anchor_pos)
        if dist <= 40 and (best is None or dist < best[1]):   # within ~40 chars
            best = (val, dist)
    return best[0] if best else None


def search(query: str, limit: int = 40) -> list[Offer]:
    if not config.APIFY_API_TOKEN:
        return []
    import httpx
    urls = [f"https://www.instagram.com/explore/tags/{t}/" for t in _tags(query)]
    ep = (f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"
          f"?token={config.APIFY_API_TOKEN}&timeout=150")
    payload = {"directUrls": urls, "resultsType": "posts",
               "resultsLimit": limit, "addParentData": False}
    try:
        r = httpx.post(ep, json=payload, timeout=210)
        if r.status_code >= 400:
            return []
        items = r.json()
    except Exception:
        return []

    offers: list[Offer] = []
    seen = set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or it.get("error"):
            continue
        cap = it.get("caption") or ""
        owner = it.get("ownerUsername") or it.get("ownerFullName") or "seller"
        # Multi-product captions are the norm ("Airpods 4 239Azn ... Pro 2
        # 389Azn") - take the price NEAREST the queried product, never the first.
        price = _price_near_product(cap, query)
        if not price:
            continue
        # Title = canonical-ish product mention + handle, NOT the whole caption
        # (the caption may name other models and confuse the matcher's excludes).
        title = f"{query} — Instagram @{owner}"
        url = it.get("url") or (f"https://instagram.com/p/{it.get('shortCode')}"
                                if it.get("shortCode") else f"https://instagram.com/{owner}")
        key = (owner, round(price))
        if key in seen:
            continue
        seen.add(key)
        offers.append(Offer(
            title=title, price=price, url=url,
            source=f"instagram:@{owner}", seller=f"@{owner}", condition="unknown",
            official=None, flags=["Instagram seller — DM to verify, no warranty"]))
    return offers
