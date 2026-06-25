"""Orchestrator - ties the pipeline together.

resolve (what) -> sources (fan-out) -> extract (parse) -> score (filter+rank)
-> verdict (the single most honest answer). Returns a HuntResult the CLI / a
scheduler / a Telegram bot can all render.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import config
import extract
import frame as frame_mod
import history as history_mod
import llm
import resolve as resolve_mod
import score as score_mod
import sources as sources_mod
from models import Offer, ProductSpec

_VERDICT_SYSTEM = """You are a sharp Azerbaijani shopping advisor. Given the
target product and a ranked list of real offers (price in AZN, source, trust%,
flags), write a SHORT verdict in Azerbaijani (3-5 sentences, no lists):
1) the best HONEST buy (cheap + trustworthy) with shop and price and why;
2) the absolute cheapest and whether it's safe or a likely replica/used trap;
3) one concrete next step. Be direct. Do not invent prices or shops."""


@dataclass
class HuntResult:
    query: str
    spec: ProductSpec
    ranked: list[Offer] = field(default_factory=list)
    best_legit: Offer | None = None
    cheapest: Offer | None = None
    verdict: str = ""
    source_status: list[tuple[str, str, str]] = field(default_factory=list)  # (src, status, note)
    rejected: int = 0
    total_seen: int = 0
    stats: dict = field(default_factory=dict)   # empirical median/band from pandas
    history: dict = field(default_factory=dict)  # lowest-ever / 30d low+avg
    frame: object = None                        # enriched+filtered DataFrame (or None)


def _verdict(spec: ProductSpec, ranked: list[Offer], hist_line: str = "") -> str:
    if not llm.available() or not ranked:
        return ""
    top = ranked[:8]
    lines = [f"- {o.price:g} AZN | {o.source} | trust {int(o.trust*100)}% | "
             f"{o.condition} | flags: {', '.join(o.flags) or 'none'} | {o.title[:60]}"
             for o in top]
    prompt = (f"TARGET: {spec.canonical_name}\n"
              f"Fair price window: {spec.fair_low:g}-{spec.fair_high:g} AZN\n"
              + (f"PRICE HISTORY: {hist_line}\n" if hist_line else "")
              + "\nOFFERS (best-ranked first):\n" + "\n".join(lines))
    try:
        return llm.complete(prompt, system=_VERDICT_SYSTEM, temperature=0.3)
    except Exception:
        return ""


async def hunt(query: str, do_verdict: bool = True, filters: dict | None = None,
               deep: bool = False, serp: bool = False, social: bool = False) -> HuntResult:
    config.ensure_dirs()
    spec = resolve_mod.resolve(query)

    results = await sources_mod.crawl_all(query, deep=deep, serp_on=serp,
                                          social_on=social)

    all_offers: list[Offer] = []
    status: list[tuple[str, str, str]] = []
    html_jobs = []
    for r in results:
        status.append((r.source, r.status, r.note))
        all_offers.extend(r.offers)
        if r.needs_llm_html:
            html_jobs.append(r)

    if html_jobs:
        loop = asyncio.get_event_loop()

        def _run(r):
            return extract.extract_offers(r.needs_llm_html, spec, r.source,
                                          r.src_url, official=r.src_official,
                                          condition=r.src_condition)
        # Sequential, not concurrent: the free Gemini/Groq tiers rate-limit
        # bursts, which would force the regex fallback and flood us with noise.
        for r in html_jobs:
            all_offers.extend(await loop.run_in_executor(None, _run, r))

    ranked, rejected = score_mod.filter_and_score(all_offers, spec)

    # pandas intelligence layer: cross-source dedupe, data-driven fair band +
    # outlier re-flag, then user filters. Falls back to the plain list if pandas
    # is unavailable.
    stats: dict = {}
    df = None
    if frame_mod.HAVE_PANDAS and ranked:
        df0 = frame_mod.to_frame(ranked)           # index aligned to `ranked`
        df0, stats = frame_mod.enrich(df0, spec)
        df = frame_mod.apply_filters(df0, **(filters or {}))
        synced = []
        for i in df.index:
            o = ranked[i]
            o.flags = [f for f in str(df.at[i, "flags"]).split("; ") if f]
            synced.append(o)
        ranked = synced

    # Price-history intelligence (akakce-style): record this run, then annotate
    # the offers against the historical low / 30-day average.
    product_key = resolve_mod.normalize(spec.canonical_name).strip()
    hist: dict = {}
    try:
        history_mod.record(product_key, ranked)   # persist this run
        hist = history_mod.summary(product_key)    # lowest-ever / 30d (incl. today)
        history_mod.annotate(ranked, hist)         # mutates offers' flags in place
    except Exception:
        pass

    best = score_mod.cheapest_legit(ranked)
    cheap = score_mod.cheapest_overall(ranked)

    res = HuntResult(
        query=query, spec=spec, ranked=ranked,
        best_legit=best, cheapest=cheap, stats=stats, frame=df, history=hist,
        source_status=status, rejected=rejected, total_seen=len(all_offers))
    if do_verdict:
        hist_line = history_mod.verdict_line(hist, best.price if best else (cheap.price if cheap else None))
        res.verdict = _verdict(spec, ranked, hist_line)
    return res
