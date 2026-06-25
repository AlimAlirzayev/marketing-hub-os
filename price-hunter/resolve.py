"""Step 1 - turn a fuzzy human query into a canonical ProductSpec.

This is the "needle definition" layer. An AI engineer's edge over a plain search
is here: before fetching a single page we decide exactly which variants count
(AirPods Pro 2 USB-C vs Lightning), which look-alikes to reject (cases, straps,
replicas, the wrong generation), and what a *legit* price window looks like so
absurdly-cheap scam listings can be flagged later.

LLM-built (Gemini/Groq) with a deterministic fallback so the agent still runs
with no keys / no network.
"""

from __future__ import annotations

import json
import re
import unicodedata

import llm
from models import ProductSpec

_SYSTEM = """You are a product-disambiguation engine for an Azerbaijani price
comparison agent. Given a shopping query, return STRICT JSON describing the exact
product so a scraper can keep only matching listings and reject look-alikes.

Return this schema (no prose):
{
 "canonical_name": str,            // clean English name, e.g. "Apple AirPods Pro 2"
 "brand": str,
 "family": str,                    // e.g. "AirPods Pro"
 "generation": str,                // e.g. "2" or "3" or "" if N/A
 "variants": [str],                // sellable variants, e.g. ["USB-C","Lightning"]
 "model_codes": [str],             // known SKUs/MPNs if confident, else []
 "must_include": [str],            // lowercase tokens a real listing's title should contain
 "must_exclude": [str],            // lowercase tokens that mean WRONG product
                                   //   (cases, straps, replicas, wrong gen, accessories)
 "fair_low": number,              // realistic STREET-price floor (AZN) for a
                                  //   genuine unit incl. grey-import/older variant
                                  //   - NOT big-retail shelf price, NOT a replica
 "fair_high": number,             // highest normal official retail price (AZN)
 "notes": str                      // 1 sentence on traps to avoid
}

Rules:
- must_exclude MUST include obvious accessories for this product (e.g. for
  earbuds: "case","kabro","qabi","strap","tips","holder","replika","kopya",
  "1:1","lux kopya") and the OTHER generations the user did NOT ask for.
- Prices are Azerbaijani Manat (AZN). Be realistic for the AZ market, not the US.
  In AZ the genuine street price is often well BELOW official big-retail shelf
  prices, so set fair_low to that realistic floor; only a price under ~half of
  fair_low is a replica. fair_high is the priciest official listing.
- If the query names a generation, do NOT include other generations as variants.
"""


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _first_int(s) -> int | None:
    m = re.search(r"\d+", str(s or ""))
    return int(m.group()) if m else None


def normalize(text: str) -> str:
    """Lowercase, de-accent, collapse punctuation - for robust token matching.

    Azerbaijani retailers mix latin, AZ diacritics and transliteration freely
    (qulaqliq / qulaqcıq, kabro / qabı), so we fold everything to bare ascii.
    """
    text = _strip_accents(text.lower())
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Fold ordinals so "2nd generation" matches the "2" include token, and the
    # "3rd"/"1st" exclusions still line up with bare-digit comparisons.
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", r"\1", text)
    return f" {text.strip()} "


# Deterministic fallback specs for the products we care about most, so the agent
# is useful even with zero LLM keys. The LLM path supersedes these when available.
_FALLBACK: dict[str, dict] = {
    "airpods pro 2": {
        "canonical_name": "Apple AirPods Pro 2",
        "brand": "Apple", "family": "AirPods Pro", "generation": "2",
        "variants": ["USB-C", "Lightning"],
        "model_codes": ["MTJV3", "MQD83"],
        "must_include": ["airpods", "pro"],
        "must_exclude": ["case", "kabro", "qabi", "qab", "cover", "strap",
                          "tips", "holder", "replika", "kopya", "1:1", "lux",
                          "pro 3", "gen 3", "3rd", "pro max", "airpods 2",
                          "airpods 3", "airpods 4"],
        "fair_low": 330.0, "fair_high": 720.0,
        "notes": "Reject cases and the Pro 3; sub-165 AZN is usually a replica.",
    },
    "airpods pro 3": {
        "canonical_name": "Apple AirPods Pro 3",
        "brand": "Apple", "family": "AirPods Pro", "generation": "3",
        "variants": ["USB-C"],
        "model_codes": ["MFHP4"],
        "must_include": ["airpods", "pro", "3"],
        "must_exclude": ["case", "kabro", "qabi", "qab", "cover", "strap",
                          "tips", "holder", "replika", "kopya", "1:1", "lux",
                          "pro 2", "gen 2", "2nd", "pro max", "airpods 3",
                          "airpods 4"],
        "fair_low": 460.0, "fair_high": 900.0,
        "notes": "Newest gen; reject Pro 2 and plain AirPods 3 mislabels.",
    },
}


def _fallback_spec(query: str) -> ProductSpec:
    key = normalize(query).strip()
    for k, v in _FALLBACK.items():
        if k in f" {key} ":
            return ProductSpec(query=query, **v)
    # Generic last resort: treat each word as a soft include token.
    toks = [t for t in key.split() if len(t) > 1]
    return ProductSpec(
        query=query,
        canonical_name=query.strip().title(),
        must_include=toks[:3],
        must_exclude=["replika", "kopya", "case", "kabro"],
        notes="Generic spec (no LLM, no known fallback).",
    )


def _harden(spec: ProductSpec) -> ProductSpec:
    """Make matching robust to LLM non-determinism.

    The LLM is great at canonical name / variants / model codes / fair prices,
    but its free-form must_include/must_exclude are unstable - one run it adds a
    required phrase like "2nd gen" that no real title contains (rejecting
    everything), another it drops a bare "1" into excludes (nuking "1 il
    zəmanət"). So we DERIVE those two lists deterministically from family +
    generation and only fold in the LLM's *safe* exclusions.
    """
    # Build the required tokens from the CANONICAL NAME (it carries the full
    # "iPhone 15 Pro"), not just `family` (the LLM often sets family="iPhone",
    # which would drop the "Pro" qualifier). Strip brand + storage/unit noise.
    _STOP = {"apple", "samsung", "xiaomi", "huawei", "with", "gen", "generation",
             "wireless", "smartfon", "smartphone", "qulaqliq", "telefon", "the"}
    canon = normalize(spec.canonical_name)
    fam = normalize(spec.family or spec.canonical_name)
    fam_head = (fam.split()[0] if fam.split() else "")  # "iphone", "airpods", ...
    words = [w for w in canon.split()
             if w.isalpha() and len(w) > 1 and w not in _STOP][:4]
    inc = words or [w for w in fam.split() if len(w) > 1]

    # Generation as an int: prefer spec.generation, else first number in the
    # canonical name. This is what stops an "iPhone 17 Pro" matching "iPhone 15".
    gnum = _first_int(spec.generation) or _first_int(spec.canonical_name)
    if gnum is not None:
        inc.append(str(gnum))
    spec.must_include = list(dict.fromkeys(inc)) or [fam_head or "airpods"]

    ex: list[str] = []
    if gnum is not None:
        # Exclude a window of *neighbouring* generations (covers AirPods 1-4 AND
        # iPhone 13-17 etc.), in both word orders ("pro 14" / "14 pro" / "iphone 14").
        for o in range(max(1, gnum - 4), gnum + 5):
            if o == gnum:
                continue
            ex += [f"pro {o}", f"{o} pro", f"gen {o}"]
            if fam_head:
                ex.append(f"{fam_head} {o}")
    # Fold in only safe LLM/fallback excludes: multi-char, not a bare number,
    # and not one of our own include tokens.
    for t in spec.must_exclude:
        nt = normalize(t).strip()
        if nt and len(nt) >= 2 and not nt.isdigit() and nt not in spec.must_include:
            ex.append(t)
    spec.must_exclude = list(dict.fromkeys(ex))
    return spec


def resolve(query: str) -> ProductSpec:
    """Build the canonical ProductSpec for `query`."""
    if not llm.available():
        return _harden(_fallback_spec(query))
    data = llm.complete_json(
        f"Query: {query!r}\nReturn the JSON spec.",
        system=_SYSTEM, temperature=0.0, default=None)
    if not isinstance(data, dict) or not data.get("canonical_name"):
        return _harden(_fallback_spec(query))
    # Coerce/normalise LLM output into the dataclass, lowercasing token lists.
    def low(xs):
        return [str(x).lower().strip() for x in (xs or []) if str(x).strip()]
    try:
        spec = ProductSpec(
            query=query,
            canonical_name=str(data["canonical_name"]),
            brand=str(data.get("brand", "")),
            family=str(data.get("family", "")),
            generation=str(data.get("generation", "")),
            variants=[str(x) for x in (data.get("variants") or [])],
            model_codes=[str(x).upper() for x in (data.get("model_codes") or [])],
            must_include=low(data.get("must_include")),
            must_exclude=low(data.get("must_exclude")),
            fair_low=float(data.get("fair_low") or 0) or 0.0,
            fair_high=float(data.get("fair_high") or 0) or 0.0,
            notes=str(data.get("notes", "")),
        )
        return _harden(spec)
    except Exception:
        return _harden(_fallback_spec(query))


# --------------------------------------------------------------------------
# Matching - does a found listing title describe the needle?
# --------------------------------------------------------------------------
# Non-Apple audio brands whose presence means this is a clone, not the product.
_NON_APPLE_BRANDS = {
    "porodo", "hoco", "remax", "awei", "recci", "wiwu", "baseus", "anker",
    "jbl", "oraimo", "ldnio", "borofone", "earldom", "yison", "qcy", "realme",
    "devia", "joyroom", "wk", "jr", "p47", "i7", "i9", "i11", "i12", "tws",
}
# Strong "this listing is an accessory" markers (AZ + EN). Deliberately does NOT
# include bare "case": Apple's real product is literally "... with MagSafe Case".
_ACCESSORY_MARKERS = (
    "kabro", "qabi", "silikon", "chexol", "cexol", "qoruyucu", "cover", "strap",
    "ear tips", "tips", "holder", "skin", "klips", "futlyar", "case for",
    "for airpods", "ucun", "brelok", "aksesuar", "stiker", "naklейka",
)
# Spec-exclude tokens we always ignore because they collide with the genuine
# product name / are handled by smarter rules above.
_AMBIGUOUS_EXCLUDE = {"case", "box", "with", "magsafe", "cover"}


def _has_word(ntitle: str, token: str) -> bool:
    """Whole-word / whole-phrase presence (ntitle is space-padded).

    A pure-digit token (a generation number) matches when those digits aren't
    part of a larger number - so "24" matches both "iPhone ... 24" and a glued
    model like "S24", but NOT "2024" or "256". Non-digit tokens need a whole word.
    """
    nt = normalize(token).strip()
    if not nt:
        return False
    if nt.isdigit():
        return re.search(rf"(?<!\d){nt}(?!\d)", ntitle) is not None
    return f" {nt} " in ntitle


def match(spec: ProductSpec, title: str, model_code: str = "") -> tuple[bool, str]:
    """Return (is_match, reason). Whole-word matching only - so "pro" does not
    match "Porodo" and "2" does not match "pro2"."""
    ntitle = normalize(title)
    code = (model_code or "").upper()

    # Hard reject: a competing brand name appears -> clone / different product.
    for b in _NON_APPLE_BRANDS:
        if _has_word(ntitle, b):
            return False, f"brand:{b}"

    # Hard reject: the listing is an accessory (phrase match, not whole-word,
    # so "for airpods" / "ucun" catch real accessory titles).
    for m in _ACCESSORY_MARKERS:
        if normalize(m).strip() in ntitle:
            return False, f"accessory:{m}"

    # Strong positive: a known model code appears (title or extracted field).
    if spec.model_codes:
        hay = ntitle.upper() + " " + code
        for mc in spec.model_codes:
            if mc and mc.upper() in hay:
                return True, f"model_code:{mc}"

    # Reject the wrong generation / variant (whole-word, skipping ambiguous ones).
    bad = _hit_exclude(spec, ntitle)
    if bad:
        return False, f"excluded:{bad}"

    # Every required include token must be present as a whole word.
    missing = [t for t in spec.must_include if not _has_word(ntitle, t)]
    if missing:
        return False, f"missing:{','.join(missing)}"

    return True, "include-tokens"


def _hit_exclude(spec: ProductSpec, ntitle: str) -> str:
    for t in spec.must_exclude:
        nt = normalize(t).strip()
        if not nt or nt in _AMBIGUOUS_EXCLUDE:
            continue
        if f" {nt} " in ntitle:   # whole word / phrase
            return t
    return ""


if __name__ == "__main__":  # quick manual check
    import sys
    s = resolve(" ".join(sys.argv[1:]) or "airpods pro 2")
    print(json.dumps(s.to_dict(), ensure_ascii=False, indent=2))
