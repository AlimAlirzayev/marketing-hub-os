"""Step 3 - turn messy aggregator HTML into structured Offers.

Structured sources (embedded JSON / API) are already clean and skip this module.
Aggregators like qiymetleri.az / irshad.az render dozens of store prices into
prose-y HTML with no stable schema - exactly where an LLM beats CSS selectors.
We hand the cleaned page text to Gemini/Groq with the canonical ProductSpec so it
keeps only real matches and ignores accessories. A regex price-scanner is the
fallback when no LLM key is configured or the call fails.
"""

from __future__ import annotations

import re

import llm
from models import Offer, ProductSpec
from resolve import normalize

_SYSTEM = """You extract product price listings from a noisy Azerbaijani price
comparison page. You are given the target product and the page text. Return
STRICT JSON: {"offers":[{"title":str,"price":number,"store":str,"condition":
"new|used|unknown"}]}.

Rules:
- price is in Azerbaijani Manat (AZN), a plain number (e.g. 419 or 419.99).
- Include ONLY listings that ARE the target product (or its named variants).
- EXCLUDE accessories (cases/kabro/qab/cover/strap/tips), replicas/copies
  ("replika","kopya","1:1","lux"), and the wrong generation.
- "store" = the seller/shop name if the page shows it, else "".
- If nothing matches, return {"offers":[]}. Do not invent prices.
"""

_PRICE_RE = re.compile(
    r"(\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{1,2})?)\s*(?:₼|AZN|man\.?|manat)", re.I)


def _to_float(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    if s.count(".") > 1:  # thousands dots: 1.299
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        f = float(s)
        return f if f > 0 else None
    except ValueError:
        return None


def _regex_offers(text: str, spec: ProductSpec, source: str, url: str,
                  official, condition: str) -> list[Offer]:
    """Fallback: pair each price token with the text just before it as a title.

    Only keep a price if its preceding window mentions a meaningful product
    token (e.g. "airpods"), otherwise an aggregator page yields hundreds of
    unrelated price tokens. The downstream resolve.match() still filters, this
    just keeps the noise out of the candidate set in the first place.
    """
    # Degraded path (LLM unavailable): favour PRECISION over recall. The strong
    # anchor is the brand/family head (e.g. "airpods"); it must sit CLOSE to the
    # price, otherwise a window bleeds across adjacent listings and grabs the
    # wrong product's price. The LLM path (primary) handles recall.
    fam = (spec.family or "airpods").split()[0].lower()
    fam_n = normalize(fam).strip()
    out = []
    for m in _PRICE_RE.finditer(text):
        price = _to_float(m.group(1))
        if not price:
            continue
        start = max(0, m.start() - 85)               # one listing's worth
        window = re.sub(r"\s+", " ", text[start:m.start()]).strip()
        if fam_n and fam_n not in normalize(window):
            continue
        mi = window.lower().rfind(fam)
        title = window[mi:mi + 60].strip() if mi >= 0 else spec.canonical_name
        out.append(Offer(title=title or spec.canonical_name, price=price,
                         url=url, source=source, official=official,
                         condition=condition, raw_price=m.group(0)))
    return out


def extract_offers(text: str, spec: ProductSpec, source: str, url: str,
                   official=None, condition: str = "unknown") -> list[Offer]:
    if not text.strip():
        return []
    if llm.available():
        prompt = (f"TARGET PRODUCT: {spec.canonical_name}\n"
                  f"Accepted variants: {', '.join(spec.variants) or 'any'}\n"
                  f"Reject these: {', '.join(spec.must_exclude[:18])}\n\n"
                  f"PAGE TEXT (source: {source}):\n{text}")
        data = llm.complete_json(prompt, system=_SYSTEM, temperature=0.0,
                                 default=None)
        offers = _from_llm(data, source, url, official, condition)
        if offers:
            return offers
    return _regex_offers(text, spec, source, url, official, condition)


def _from_llm(data, source, url, official, condition) -> list[Offer]:
    if isinstance(data, dict):
        rows = data.get("offers") or data.get("items") or []
    elif isinstance(data, list):
        rows = data
    else:
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        price = r.get("price")
        try:
            price = float(re.sub(r"[^\d.]", "", str(price))) if price else None
        except ValueError:
            price = None
        title = (r.get("title") or r.get("name") or "").strip()
        if not (price and title):
            continue
        out.append(Offer(
            title=title, price=price, url=url, source=source,
            seller=(r.get("store") or r.get("seller") or "").strip(),
            official=official,
            condition=(r.get("condition") or condition or "unknown").lower(),
        ))
    return out
