"""Command-line entry for Price Hunter.

    python cli.py "airpods pro 2"
    python cli.py "airpods pro 3" --no-verdict --json
    python cli.py "iphone 15 pro" --telegram --limit 15

Renders a ranked table, the verdict, and source coverage. Always saves a JSON +
Markdown report under data/reports/.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys

# Windows consoles default to cp1252 and choke on ₼ / Azerbaijani text.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import config  # noqa: E402
import report as report_mod  # noqa: E402
from hunt import hunt  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

console = Console()


def _trust_style(t: float) -> str:
    return "green" if t >= 0.66 else "yellow" if t >= 0.4 else "red"


def render(res, limit: int) -> None:
    s = res.spec
    console.print(Panel.fit(
        f"[bold]{s.canonical_name}[/bold]\n"
        f"query: [cyan]{res.query}[/cyan]   "
        f"fair window: [magenta]{s.fair_low:g}–{s.fair_high:g} AZN[/magenta]   "
        f"LLM: {config.llm_status()}",
        title="🎧 Price Hunter", border_style="cyan"))

    # Data-driven price band from the actual scraped distribution (pandas).
    if res.stats and res.stats.get("count"):
        st = res.stats
        console.print(f"[dim]Market (scraped): median [bold]{st['median']:g}[/bold] AZN · "
                      f"genuine band {st['band_low']:g}–{st['band_high']:g} · "
                      f"range {st['min']:g}–{st['max']:g} · {st['count']} offers[/dim]")
    # Price history (akakce-style): lowest-ever / 30-day context.
    if res.history and res.history.get("lowest_ever"):
        h = res.history
        extra = (f" · 30g aşağı {h['low_30d']:g} · 30g orta {h['avg_30d']:g}"
                 if h.get("avg_30d") else "")
        console.print(f"[magenta]History:[/magenta] lowest-ever [bold]{h['lowest_ever']:g}[/bold] AZN "
                      f"({h['lowest_ever_date']}){extra} · {h['observations']} obs / {h['days_tracked']}d")

    if not res.ranked:
        console.print("[red]No matching offers found.[/red] "
                      "Check source coverage below — sites may be blocking or empty.")
    else:
        t = Table(show_lines=False, header_style="bold")
        for col, just in [("#", "right"), ("Price AZN", "right"), ("Trust", "right"),
                          ("Source", "left"), ("Cond", "left"),
                          ("Flags", "left"), ("Title", "left")]:
            t.add_column(col, justify=just, overflow="fold")
        for i, o in enumerate(res.ranked[:limit], 1):
            ts = _trust_style(o.trust)
            t.add_row(str(i), f"{o.price:g}",
                      f"[{ts}]{int(o.trust*100)}%[/{ts}]",
                      o.source, o.condition,
                      "[red]" + "; ".join(o.flags) + "[/red]" if o.flags else "—",
                      o.title[:54])
        console.print(t)

    # Headline picks
    if res.best_legit:
        b = res.best_legit
        console.print(f"\n[bold green]✓ Best honest buy:[/bold green] "
                      f"{b.price:g} AZN @ {b.source} (trust {int(b.trust*100)}%) — {b.title[:60]}")
    if res.cheapest and res.cheapest is not res.best_legit:
        c = res.cheapest
        warn = f"  [red]⚠ {', '.join(c.flags)}[/red]" if c.flags else ""
        console.print(f"[bold]↓ Absolute cheapest:[/bold] "
                      f"{c.price:g} AZN @ {c.source} (trust {int(c.trust*100)}%){warn}")

    if res.verdict:
        console.print(Panel(res.verdict, title="Verdict (AZ)", border_style="green"))

    # Source coverage - honest about what worked / was blocked.
    st = Table(title="Source coverage", header_style="bold", show_lines=False)
    st.add_column("Source"); st.add_column("Status"); st.add_column("Note")
    for src, status, note in res.source_status:
        style = ("green" if status == "ok" else
                 "yellow" if status in ("skipped", "empty") else "red")
        st.add_row(src, f"[{style}]{status}[/{style}]", note)
    console.print(st)
    console.print(f"[dim]Seen {res.total_seen} raw · {len(res.ranked)} matched · "
                  f"{res.rejected} rejected[/dim]")


def main() -> None:
    ap = argparse.ArgumentParser(description="AZ price-intelligence agent")
    ap.add_argument("query", nargs="+", help="product to hunt, e.g. airpods pro 2")
    ap.add_argument("--limit", type=int, default=20, help="rows to show")
    ap.add_argument("--no-verdict", action="store_true", help="skip LLM verdict")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout")
    ap.add_argument("--telegram", action="store_true", help="push verdict to Telegram")
    # Rich filters (pandas layer)
    ap.add_argument("--max-price", type=float, help="only offers <= this AZN")
    ap.add_argument("--min-price", type=float, help="only offers >= this AZN")
    ap.add_argument("--min-trust", type=float, help="only offers with trust >= 0..1")
    ap.add_argument("--official", action="store_true", help="official retailers only")
    ap.add_argument("--condition", choices=["new", "used", "refurbished"], help="filter by condition")
    ap.add_argument("--source", help="only this source (substring, e.g. ispace)")
    ap.add_argument("--sort", choices=["deal", "price", "trust"], default="deal", help="sort order")
    ap.add_argument("--deep", action="store_true", help="enable headless render of JS-SPA sources")
    ap.add_argument("--serp", action="store_true", help="Google SERP catch-all (Apify; covers SPAs + small shops)")
    ap.add_argument("--social", action="store_true", help="Instagram social-commerce sellers (Apify)")
    ap.add_argument("--wide", action="store_true", help="enable all of --deep --serp --social")
    args = ap.parse_args()
    if args.wide:
        args.deep = args.serp = args.social = True

    filters = {"max_price": args.max_price, "min_price": args.min_price,
               "min_trust": args.min_trust, "official_only": args.official,
               "condition": args.condition, "source": args.source, "sort": args.sort}
    query = " ".join(args.query)
    with console.status(f"[cyan]Hunting '{query}' across AZ sources…[/cyan]"):
        res = asyncio.run(hunt(query, do_verdict=not args.no_verdict,
                               filters=filters, deep=args.deep,
                               serp=args.serp, social=args.social))

    if args.json:
        import json
        console.print_json(json.dumps(report_mod.to_json(res), ensure_ascii=False))
    else:
        render(res, args.limit)

    jpath, mpath = report_mod.save(res)
    console.print(f"[dim]Saved report: {mpath}[/dim]")
    if args.telegram:
        ok = report_mod.telegram(res)
        console.print(f"[dim]Telegram: {'sent ✓' if ok else 'not sent (no token/chat or error)'}[/dim]")


if __name__ == "__main__":
    main()
