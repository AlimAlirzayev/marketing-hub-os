"""Price history - the akakce / CamelCamelCamel signature feature.

Every hunt records its matched offers into a local SQLite store. Over time this
turns a one-shot "cheapest right now" into real intelligence: lowest price ever
seen, 30-day low/average, and whether today's best is genuinely a good deal or
just normal. This is what separates a world-class price tool from a scraper -
and it runs on the data we already collect, no extra requests.

Degrades gracefully: all functions no-op safely if sqlite/the file is unusable.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import config

_DB = os.path.join(config.DATA_DIR, "history.db")


def _conn():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    c = sqlite3.connect(_DB, timeout=10)
    c.execute("""CREATE TABLE IF NOT EXISTS obs(
        ts TEXT, product_key TEXT, source TEXT, title TEXT,
        price REAL, currency TEXT, condition TEXT, official INTEGER, trust REAL)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_key ON obs(product_key)")
    return c


def record(product_key: str, offers) -> None:
    """Persist this run's matched offers (one row each)."""
    if not product_key or not offers:
        return
    now = datetime.now().isoformat(timespec="seconds")
    rows = [(now, product_key, o.source, o.title[:120], float(o.price),
             o.currency, o.condition, 1 if o.official else 0, round(o.trust, 3))
            for o in offers if o.price]
    try:
        with closing(_conn()) as c:
            c.executemany("INSERT INTO obs VALUES (?,?,?,?,?,?,?,?,?)", rows)
            c.commit()
    except Exception:
        pass


def summary(product_key: str, trust_min: float = 0.5) -> dict:
    """Historical context for a product, restricted to trustworthy observations.

    Returns lowest-ever (+date), 30-day low, 30-day average, observation/day
    counts. Empty dict if there's no usable history yet.
    """
    if not product_key:
        return {}
    try:
        with closing(_conn()) as c:
            cur = c.execute(
                "SELECT ts, price FROM obs WHERE product_key=? AND trust>=? AND price>0",
                (product_key, trust_min))
            rows = cur.fetchall()
    except Exception:
        return {}
    if not rows:
        return {}
    prices = [p for _, p in rows]
    low_ts, low_p = min(rows, key=lambda r: r[1])
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    recent = [p for ts, p in rows if ts >= cutoff]
    days = len({ts[:10] for ts, _ in rows})
    return {
        "lowest_ever": round(min(prices), 2),
        "lowest_ever_date": low_ts[:10],
        "low_30d": round(min(recent), 2) if recent else None,
        "avg_30d": round(sum(recent) / len(recent), 2) if recent else None,
        "observations": len(rows),
        "days_tracked": days,
    }


def annotate(offers, summ: dict) -> None:
    """Tag the current offers against history (mutates Offer.flags + .hist_*)."""
    if not summ:
        return
    low = summ.get("lowest_ever")
    avg = summ.get("avg_30d")
    for o in offers:
        if o.price is None:
            continue
        o.hist_low = low
        o.hist_avg = avg
        if low and o.price <= low * 1.001:
            o.is_lowest = True
            if summ.get("days_tracked", 0) > 1:
                o.flags.append(f"lowest ever (≥{summ['days_tracked']}d tracked)")
        elif avg and o.price < avg * 0.9:
            o.flags.append(f"below 30-day avg {avg:g} AZN")
        elif avg and o.price > avg * 1.15:
            o.flags.append(f"above 30-day avg {avg:g} AZN")


def verdict_line(summ: dict, today_best: float | None) -> str:
    if not summ:
        return ""
    bits = [f"tarixi ən aşağı {summ['lowest_ever']:g} AZN ({summ['lowest_ever_date']})"]
    if summ.get("avg_30d"):
        bits.append(f"30g orta {summ['avg_30d']:g}")
    if today_best is not None and summ.get("lowest_ever"):
        if today_best <= summ["lowest_ever"] * 1.001:
            bits.append("bugünkü ən yaxşı = tarixi minimum ✓")
        else:
            d = today_best - summ["lowest_ever"]
            bits.append(f"bugünkü ən yaxşı tarixi minimumdan {d:+.0f} AZN")
    return " · ".join(bits) + f" · {summ['observations']} müşahidə"
