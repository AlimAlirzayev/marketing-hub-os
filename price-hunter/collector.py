"""Background price collector - builds real price-history depth, silently.

Reads a watchlist (data/watchlist.json) of product queries and runs a hunt for
each, which records every matched offer into history.db. NO notifications - it
just accumulates data so the dashboard's "lowest-ever / 30-day" intelligence
becomes real over days/weeks. Schedule it (Windows Task Scheduler / cron) to run
e.g. hourly; the dashboard stays on-demand.

    .venv/Scripts/python collector.py           # one pass over the watchlist
    .venv/Scripts/python collector.py --add "airpods pro 2"   # add to watchlist
    .venv/Scripts/python collector.py --list
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import config
from hunt import hunt

_WATCHLIST = os.path.join(config.DATA_DIR, "watchlist.json")
_DEFAULT = ["airpods pro 2", "airpods pro 3"]


def _load() -> list[str]:
    try:
        with open(_WATCHLIST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return list(_DEFAULT)


def _save(items: list[str]) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(_WATCHLIST, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


async def collect_once(queries: list[str]) -> None:
    for q in queries:
        try:
            res = await hunt(q, do_verdict=False, deep=False)
            best = res.best_legit or res.cheapest
            lo = (res.history or {}).get("lowest_ever")
            bp = f"{best.price:g}" if best else "-"
            bs = best.source if best else "-"
            print(f"[{config.now_iso()}] {q}: matched {len(res.ranked)} · "
                  f"best {bp} @ {bs} · lowest-ever {lo}")
        except Exception as exc:  # noqa: BLE001 - keep going through the list
            print(f"[{config.now_iso()}] {q}: ERROR {type(exc).__name__}: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Price Hunter background collector")
    ap.add_argument("--add", help="add a product query to the watchlist")
    ap.add_argument("--remove", help="remove a product query from the watchlist")
    ap.add_argument("--list", action="store_true", help="print the watchlist")
    args = ap.parse_args()

    items = _load()
    if args.add:
        if args.add not in items:
            items.append(args.add)
            _save(items)
        print("watchlist:", items)
        return
    if args.remove:
        items = [x for x in items if x != args.remove]
        _save(items)
        print("watchlist:", items)
        return
    if args.list:
        print("watchlist:", items)
        return

    if not items:
        print("watchlist is empty — add items with --add")
        return
    config.ensure_dirs()
    asyncio.run(collect_once(items))


if __name__ == "__main__":
    main()
