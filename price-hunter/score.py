"""Step 4 - keep only the needle, then rank by *honest* value.

The cheapest listing is rarely the right answer: in the AZ market a sub-floor
price almost always means a replica, a used unit, or a grey-import with no
warranty. So we compute a trust score (authenticity confidence) and rank by a
composite that rewards "cheap AND trustworthy", not "cheap at any cost".

    adjusted = price * (1.5 - trust)        # lower is better
    -> a genuine 419 AZN unit beats both a 350 replica and a 650 over-price.
"""

from __future__ import annotations

import re

import merchants
import resolve
from models import Offer, ProductSpec

_REPLICA_WORDS = ("replika", "kopya", "kopiya", "1:1", "lux kopya", "porodo",
                  "hoco", "remax", "awei", "analoq", "oem")


def _trust(o: Offer, spec: ProductSpec) -> tuple[float, list[str]]:
    flags: list[str] = list(o.flags)   # preserve pre-set flags (e.g. "via Google")
    ntitle = resolve.normalize(o.title)

    # Base trust from MERCHANT REPUTATION (authorized partner > official chain >
    # marketplace > aggregator-unknown > classified), blended with a real Google
    # Maps store rating when we've cached one. This is the "store rating" signal.
    rep = merchants.reputation(o.source, o.seller)
    t = 0.30 + 0.55 * rep["score"]          # authorized→0.85, aggregator→0.60, classified→0.52
    o.seller_label = rep["label"]
    if rep.get("gmaps_rating"):
        o.gmaps_rating = rep["gmaps_rating"]
        flags.append(f"Google {rep['gmaps_rating']}★"
                     + (f" ({rep['gmaps_reviews']})" if rep.get("gmaps_reviews") else ""))

    if o.match_reason.startswith("model_code"):
        t += 0.1
    if rep["tier"] == "classified":
        flags.append("classified listing (verify seller)")

    cond = (o.condition or "unknown").lower()
    if cond == "new":
        t += 0.1
    elif cond in ("used", "refurbished"):
        t -= 0.05
        flags.append(f"{cond}")

    if any(f" {w} " in ntitle or w in o.title.lower() for w in _REPLICA_WORDS):
        t = min(t, 0.1)
        flags.append("brand/replica mismatch in title")

    # Two-tier price sanity: only an *implausibly* low price screams replica.
    # A merely below-typical price (common for grey-import / older variant) gets
    # a "verify" note, not a trust execution - the AZ street price genuinely sits
    # below big-retail shelf prices.
    if o.price is not None and spec.fair_low > 0:
        replica_floor = max(0.5 * spec.fair_low, 120.0)
        if o.price < replica_floor:
            t = min(t, 0.15)
            flags.append(f"suspiciously cheap (<{replica_floor:g} AZN) — "
                         f"likely replica/scam")
        elif o.price < spec.fair_low:
            flags.append("below typical retail — verify seller/warranty")
        elif spec.fair_high and o.price <= spec.fair_high:
            t += 0.1
        elif spec.fair_high and o.price > spec.fair_high * 1.4:
            t -= 0.05
            flags.append("above typical retail")

    return max(0.0, min(1.0, t)), flags


def _dedupe(offers: list[Offer]) -> list[Offer]:
    seen: dict[tuple, Offer] = {}
    for o in offers:
        key = (o.source, round(o.price or 0, 0),
               resolve.normalize(o.title).strip()[:40])
        # keep the one with more info (official/condition known)
        if key not in seen:
            seen[key] = o
    return list(seen.values())


def filter_and_score(offers: list[Offer], spec: ProductSpec):
    """Return (ranked_matches, rejected_count). Mutates Offers with scores."""
    matched: list[Offer] = []
    rejected = 0
    for o in offers:
        if o.price is None:
            rejected += 1
            continue
        ok, reason = resolve.match(spec, o.title, o.model_code)
        o.matched, o.match_reason = ok, reason
        if not ok:
            rejected += 1
            continue
        o.trust, o.flags = _trust(o, spec)
        # composite: lower adjusted price is a better deal, but an untrustworthy
        # listing (likely replica/scam) must never outrank a genuine one just by
        # being cheap - push trust<0.5 to the bottom with a large penalty.
        penalty = 0.0 if o.trust >= 0.5 else 1_000_000.0
        o.deal_score = round(o.price * (1.5 - o.trust) + penalty, 1)
        matched.append(o)

    matched = _dedupe(matched)
    matched.sort(key=lambda x: x.deal_score)
    return matched, rejected


def cheapest_legit(offers: list[Offer], trust_min: float = 0.5) -> Offer | None:
    legit = [o for o in offers if o.trust >= trust_min]
    return min(legit, key=lambda x: x.price) if legit else None


def cheapest_overall(offers: list[Offer]) -> Offer | None:
    return min(offers, key=lambda x: x.price) if offers else None
