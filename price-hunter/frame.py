"""Step 5 - the pandas intelligence layer.

Turns the raw per-source Offers into one clean DataFrame and does what a sharp
analyst would: cross-source dedupe, a DATA-DRIVEN fair-price band (robust
median / MAD of the genuine cluster, not an LLM guess), outlier/replica
re-flagging from that band, and flexible filtering/sorting. This is what makes
the final answer correct and honest rather than just "cheapest string found".

Degrades gracefully: if pandas isn't installed the agent still runs on the
plain-list path in score.py.
"""

from __future__ import annotations

from models import Offer, ProductSpec

try:
    import pandas as pd
    HAVE_PANDAS = True
except Exception:  # pragma: no cover
    HAVE_PANDAS = False

_COLS = ["title", "price", "currency", "source", "seller", "condition",
         "official", "in_stock", "model_code", "trust", "deal_score",
         "match_reason", "flags", "url"]


def to_frame(offers: list[Offer]):
    rows = []
    for o in offers:
        d = o.to_dict()
        d["flags"] = "; ".join(o.flags)
        rows.append({c: d.get(c) for c in _COLS})
    return pd.DataFrame(rows, columns=_COLS)


def _robust_band(prices) -> tuple[float, float, float]:
    """Median and a MAD-based genuine band over the main price cluster.

    Median Absolute Deviation is outlier-resistant: a couple of 17 AZN replicas
    or a 1500 AZN mislabel won't drag the band. Returns (median, low, high).
    """
    s = prices.dropna()
    if len(s) == 0:
        return 0.0, 0.0, 0.0
    med = float(s.median())
    mad = float((s - med).abs().median()) or med * 0.15
    # Genuine band: within ~2.5 MAD of the median, floored sensibly.
    low = max(med - 2.5 * mad, med * 0.45)
    high = med + 3.0 * mad
    return med, low, high


def enrich(df, spec: ProductSpec):
    """Cross-source dedupe + data-driven fair band + outlier re-flagging.

    Returns (df, stats). stats carries the empirical median/band used so the CLI
    and verdict can explain *why* a price is called cheap or suspicious.
    """
    if df.empty:
        return df, {"count": 0}

    # Cross-source dedupe: same model_code+price, or same source+title+price.
    df = df.copy()
    df["_dupe_key"] = df.apply(
        lambda r: (str(r["model_code"]).upper().strip(), round(r["price"] or 0))
        if r["model_code"] else (r["source"], str(r["title"]).lower()[:40],
                                 round(r["price"] or 0)), axis=1)
    df = df.sort_values("trust", ascending=False).drop_duplicates("_dupe_key")
    df = df.drop(columns=["_dupe_key"])

    # Compute the fair band over TRUSTWORTHY offers only - otherwise a cluster of
    # 199 AZN "iPhone 17" scams drags the median to nonsense. Fall back to all
    # offers only if too few trustworthy ones exist.
    trusted = df[df["trust"] >= 0.5]
    band_src = trusted["price"] if len(trusted) >= 3 else df["price"]
    med, low, high = _robust_band(band_src)
    stats = {"count": int(len(df)), "median": round(med, 2),
             "band_low": round(low, 2), "band_high": round(high, 2),
             "min": float(df["price"].min()), "max": float(df["price"].max())}

    # Re-flag against the empirical band (honest, data-driven, not LLM-guessed).
    def reflag(r):
        flags = [f for f in str(r["flags"]).split("; ") if f]
        p = r["price"]
        if p is not None and med > 0:
            if p < low and "likely replica/scam" not in " ".join(flags):
                flags = [f for f in flags if "below typical" not in f]
                flags.append(f"far below market median {med:g} AZN — verify hard")
            elif p > high:
                flags.append(f"above market median {med:g} AZN")
        return "; ".join(dict.fromkeys(flags))
    df["flags"] = df.apply(reflag, axis=1)

    return df, stats


def apply_filters(df, *, max_price=None, min_price=None, min_trust=None,
                  official_only=False, condition=None, source=None,
                  sort="deal"):
    """Filter + sort per user request. sort: deal | price | trust."""
    if df.empty:
        return df
    out = df
    if max_price is not None:
        out = out[out["price"] <= max_price]
    if min_price is not None:
        out = out[out["price"] >= min_price]
    if min_trust is not None:
        out = out[out["trust"] >= min_trust]
    if official_only:
        out = out[out["official"] == True]  # noqa: E712
    if condition:
        out = out[out["condition"].str.lower() == condition.lower()]
    if source:
        out = out[out["source"].str.contains(source, case=False, na=False)]
    key = {"price": ("price", True), "trust": ("trust", False),
           "deal": ("deal_score", True)}.get(sort, ("deal_score", True))
    return out.sort_values(key[0], ascending=key[1])
