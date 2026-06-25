"""Shared dataclasses for Price Hunter.

Kept in one tiny module so every layer (resolve / sources / extract / score)
speaks the same vocabulary without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class ProductSpec:
    """Canonical understanding of *what the user is actually hunting for*.

    This is the disambiguation contract: it tells every downstream layer which
    titles count as the needle (must_include / variants) and which are
    look-alikes to throw away (must_exclude: cases, straps, replicas, wrong gen).
    """
    query: str
    canonical_name: str
    brand: str = ""
    family: str = ""
    generation: str = ""
    # Distinct sellable variants (e.g. USB-C vs Lightning) with their model codes.
    variants: list[str] = field(default_factory=list)
    model_codes: list[str] = field(default_factory=list)
    # Title tokens that should appear (any-of groups handled in resolve.match()).
    must_include: list[str] = field(default_factory=list)
    # Title tokens that disqualify an offer (accessories / wrong product).
    must_exclude: list[str] = field(default_factory=list)
    # Plausible *legit, new, official* price window in AZN. Used by trust scoring
    # to flag implausibly-cheap listings (replicas / scams).
    fair_low: float = 0.0
    fair_high: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Offer:
    """A single price listing found on a source page."""
    title: str
    price: Optional[float]
    url: str
    source: str                 # domain, e.g. "kontakt.az"
    seller: str = ""            # marketplace sub-seller, if any
    currency: str = "AZN"
    condition: str = "unknown"  # new | used | refurbished | unknown
    official: Optional[bool] = None
    warranty: str = ""
    in_stock: Optional[bool] = None
    model_code: str = ""
    raw_price: str = ""         # original price string as seen on the page

    # Filled in by the scoring layer.
    matched: bool = False
    match_reason: str = ""
    trust: float = 0.0          # 0..1 authenticity confidence
    deal_score: float = 0.0     # composite ranking score
    flags: list[str] = field(default_factory=list)
    # Filled in by the merchant-reputation layer.
    seller_label: str = ""             # e.g. "authorized Apple partner"
    gmaps_rating: Optional[float] = None  # cached Google Maps store rating
    # Filled in by the price-history layer.
    hist_low: Optional[float] = None   # lowest trustworthy price ever seen
    hist_avg: Optional[float] = None   # 30-day average
    is_lowest: bool = False            # this price is at/below the historical low

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
