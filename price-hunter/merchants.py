"""Merchant reputation layer - the 'store rating / trust' dimension.

AZ shops don't publish structured per-product star ratings, so a real price tool
supplies the *other* rating that matters for a buy decision: how trustworthy the
seller is. We keep a curated reputation registry (authorized-partner > official
chain > marketplace > aggregator-unknown > classified) and an optional Google
Maps rating enrichment (via the user's Apify Google-Maps actor), cached to disk.

reputation() is the single entry point used by the scorer.
"""

from __future__ import annotations

import json
import os
import time

import config

# tier -> (base reputation 0..1, human label)
_TIERS = {
    "authorized": (1.00, "authorized Apple partner"),
    "official": (0.90, "official retailer"),
    "official_mid": (0.85, "official store"),
    "marketplace": (0.70, "marketplace (verified sellers)"),
    "aggregator": (0.55, "price aggregator (mixed sellers — verify)"),
    "classified": (0.40, "classified / individual seller"),
    "social": (0.35, "social-media seller (Instagram/TikTok — DM, no warranty)"),
    "unknown": (0.50, "unknown seller"),
}

# Curated AZ merchant map (domain -> tier). Extend freely.
_MERCHANTS = {
    "ispace.az": "authorized",
    "kontakt.az": "official", "irshad.az": "official",
    "bakuelectronics.az": "official", "umico.az": "official", "birmarket.az": "official",
    "maxi.az": "official_mid", "soliton.az": "official_mid", "optimal.az": "official_mid",
    "smarton.az": "official_mid", "worldtelecom.az": "official_mid", "w-t.az": "official_mid",
    "espace.az": "official_mid", "tehnomart.az": "official_mid", "almali.az": "official_mid",
    "qiymetleri.az": "aggregator", "ucuzu.az": "aggregator", "qiymeti.net": "aggregator",
    "tap.az": "classified", "lalafo.az": "classified",
}

_GMAPS_CACHE = os.path.join(config.DATA_DIR, "gmaps_ratings.json")


def tier_of(source: str) -> str:
    s = (source or "").lower()
    if s.startswith(("instagram", "tiktok", "ig:", "social")):
        return "social"
    for dom, tier in _MERCHANTS.items():
        if dom in s:
            return tier
    return "unknown"


def _gmaps_cache() -> dict:
    try:
        with open(_GMAPS_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def reputation(source: str, seller: str = "") -> dict:
    """Return {score, tier, label, gmaps_rating?, gmaps_reviews?} for a seller.

    Curated tier is the reliable base; a cached Google-Maps rating (if fetched)
    nudges the score and is shown to the user as a real-world signal.
    """
    tier = tier_of(source)
    base, label = _TIERS[tier]
    out = {"score": base, "tier": tier, "label": label}

    cache = _gmaps_cache()
    key = (source or "").lower()
    g = cache.get(key)
    if g and g.get("rating"):
        out["gmaps_rating"] = g["rating"]
        out["gmaps_reviews"] = g.get("reviews")
        # blend: a strong/weak Google rating shifts reputation by up to ±0.1
        out["score"] = round(min(1.0, max(0.1,
                          base + (float(g["rating"]) - 4.0) * 0.05)), 3)
    return out


def fetch_gmaps_ratings(merchant_queries: dict[str, str], max_per: int = 1) -> dict:
    """Use the user's Apify Google-Maps actor to fetch store ratings, cache them.

    merchant_queries: {domain: "search term", e.g. "iSpace Baku"}.
    Safe no-op without APIFY_API_TOKEN. Run occasionally (ratings are stable).
    """
    if not config.APIFY_API_TOKEN:
        return _gmaps_cache()
    import httpx
    cache = _gmaps_cache()
    ep = ("https://api.apify.com/v2/acts/compass~crawler-google-places/"
          f"run-sync-get-dataset-items?token={config.APIFY_API_TOKEN}&timeout=120")
    for dom, q in merchant_queries.items():
        try:
            payload = {"searchStringsArray": [q], "maxCrawledPlacesPerSearch": max_per,
                       "language": "en"}
            r = httpx.post(ep, json=payload, timeout=160)
            if r.status_code < 400:
                items = r.json()
                if isinstance(items, list) and items:
                    it = items[0]
                    cache[dom.lower()] = {"rating": it.get("totalScore"),
                                          "reviews": it.get("reviewsCount"),
                                          "ts": time.strftime("%Y-%m-%d")}
        except Exception:
            continue
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_GMAPS_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return cache
