"""Core regression tests for Price Hunter - the safety net that keeps matching,
scoring, the data layer and price history correct as the agent evolves.

Run:  .venv/Scripts/python -m pytest -q
Pure-logic only (no network / no LLM): fast and deterministic.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import frame as frame_mod      # noqa: E402
import history as history_mod  # noqa: E402
import merchants               # noqa: E402
import resolve                 # noqa: E402
import score as score_mod      # noqa: E402
from models import Offer, ProductSpec  # noqa: E402


def _spec(query, canonical, family, generation):
    return resolve._harden(ProductSpec(query=query, canonical_name=canonical,
                                       brand="Apple", family=family,
                                       generation=generation))


# --------------------------------------------------------------------------
# Matching / disambiguation
# --------------------------------------------------------------------------
def test_airpods_pro2_matches_and_rejects():
    s = resolve._harden(resolve._fallback_spec("airpods pro 2"))
    assert resolve.match(s, "Apple AirPods Pro (2nd Generation) MagSafe")[0]
    assert resolve.match(s, "Apple AirPods Pro 2 USB-C MTJV3RU/A")[0]
    assert not resolve.match(s, "Apple AirPods Pro 3")[0]            # wrong gen
    assert not resolve.match(s, "Porodo AirPods Pro2 replica")[0]    # clone brand
    assert not resolve.match(s, "AirPods Pro 2 üçün silikon kabro")[0]  # accessory
    # MagSafe *Case* is part of the genuine product, must NOT be excluded
    assert resolve.match(s, "AirPods Pro 2 with MagSafe Case USB-C")[0]


def test_iphone_generation_not_confused():
    s = _spec("iphone 15 pro 256gb", "Apple iPhone 15 Pro 256GB", "iPhone", "15")
    assert resolve.match(s, "Apple iPhone 15 Pro 256GB Natural Titanium")[0]
    assert resolve.match(s, "iPhone 15 Pro 128GB Blue")[0]
    assert not resolve.match(s, "iPhone 17 Pro Deep Blue 256GB")[0]  # newer gen
    assert not resolve.match(s, "iPhone 14 Pro 256GB")[0]            # older gen
    assert not resolve.match(s, "Apple iPhone 15 256GB")[0]          # missing 'pro'
    assert not resolve.match(s, "iPhone 2024 promo")[0]              # 2024 != gen 15


def test_glued_model_number_samsung():
    s = _spec("samsung galaxy s24 ultra", "Samsung Galaxy S24 Ultra", "Galaxy S", "24")
    assert resolve.match(s, "Samsung Galaxy S24 Ultra 256GB")[0]     # S24 glued
    assert not resolve.match(s, "Samsung Galaxy S23 Ultra 256GB")[0]
    assert not resolve.match(s, "Samsung Galaxy S240 Ultra")[0]      # 240 != 24


# --------------------------------------------------------------------------
# Merchant reputation + trust scoring
# --------------------------------------------------------------------------
def test_merchant_reputation_tiers():
    assert merchants.reputation("ispace.az")["tier"] == "authorized"
    assert merchants.reputation("qiymetleri.az")["tier"] == "aggregator"
    assert merchants.reputation("tap.az")["tier"] == "classified"
    assert merchants.reputation("ispace.az")["score"] > merchants.reputation("tap.az")["score"]


def test_official_outranks_and_replica_demoted():
    s = resolve._harden(resolve._fallback_spec("airpods pro 2"))
    raw = [
        Offer("Apple AirPods Pro 2", 349, "", "ispace.az", official=True, condition="new"),
        Offer("Apple AirPods Pro 2", 35, "", "qiymetleri.az", official=False, condition="new"),
        Offer("Apple AirPods Pro 2", 399, "", "qiymetleri.az", official=False, condition="new"),
    ]
    ranked, _ = score_mod.filter_and_score(raw, s)
    # the 35 AZN scam must NOT be first despite being cheapest
    assert ranked[0].price != 35
    # cheapest legit excludes the low-trust scam
    assert score_mod.cheapest_legit(ranked).trust >= 0.5
    scam = next(o for o in ranked if o.price == 35)
    assert scam.trust < 0.3 and any("replica" in f for f in scam.flags)


# --------------------------------------------------------------------------
# pandas data layer
# --------------------------------------------------------------------------
def test_fair_band_ignores_scam_cluster():
    if not frame_mod.HAVE_PANDAS:
        return
    s = _spec("iphone 15 pro", "Apple iPhone 15 Pro", "iPhone", "15")
    raw = [Offer("iPhone 15 Pro", p, "", "bakuelectronics.az", official=True, condition="new")
           for p in (2829, 3049, 3149)]
    raw += [Offer("iPhone 15 Pro", p, "", "qiymetleri.az", official=False, condition="new")
            for p in (199, 209, 299)]  # scam cluster
    ranked, _ = score_mod.filter_and_score(raw, s)
    df = frame_mod.to_frame(ranked)
    df, stats = frame_mod.enrich(df, s)
    # median must reflect the genuine ~3000 cluster, not be dragged to ~300
    assert stats["median"] > 1500


def test_filters():
    if not frame_mod.HAVE_PANDAS:
        return
    s = resolve._harden(resolve._fallback_spec("airpods pro 2"))
    raw = [Offer("AirPods Pro 2", 349, "", "ispace.az", official=True, condition="new"),
           Offer("AirPods Pro 2", 759, "", "bakuelectronics.az", official=True, condition="new")]
    ranked, _ = score_mod.filter_and_score(raw, s)
    df = frame_mod.to_frame(ranked)
    df, _ = frame_mod.enrich(df, s)
    cheap = frame_mod.apply_filters(df, max_price=400)
    assert len(cheap) == 1 and cheap.iloc[0]["price"] == 349


# --------------------------------------------------------------------------
# Price history
# --------------------------------------------------------------------------
def test_history_records_and_summarizes(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "_DB", str(tmp_path / "h.db"))
    key = "test apods"
    history_mod.record(key, [Offer("AirPods Pro 2", 349, "", "ispace.az",
                                   official=True, condition="new", trust=0.9)])
    history_mod.record(key, [Offer("AirPods Pro 2", 330, "", "ispace.az",
                                   official=True, condition="new", trust=0.9)])
    s = history_mod.summary(key)
    assert s["lowest_ever"] == 330.0 and s["observations"] == 2
    cur = [Offer("AirPods Pro 2", 330, "", "ispace.az", trust=0.9)]
    history_mod.annotate(cur, s)
    assert cur[0].is_lowest is True
