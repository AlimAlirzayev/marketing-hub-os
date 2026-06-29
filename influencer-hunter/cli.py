"""Command-line entry for Influencer Hunter."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import config  # noqa: E402
import decision  # noqa: E402
import report as report_mod  # noqa: E402
from hunt import hunt  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

console = Console()


def render(res, limit: int) -> None:
    b = res.brief
    console.print(Panel.fit(
        f"[bold]{b.product}[/bold]\n"
        f"brand: [cyan]{b.brand or '-'}[/cyan] | angle: [magenta]{b.selling_angle or '-'}[/magenta]\n"
        f"LLM: {config.llm_status()} | Apify: {'on' if config.APIFY_API_TOKEN else 'off'}",
        title="Influencer Hunter",
        border_style="cyan",
    ))
    frame = decision.result_decision(res)
    console.print(Panel(
        f"[bold]{frame['campaign_question']}[/bold]\n\n"
        f"{frame['answer']}\n\n"
        f"Confidence: {frame['confidence']} - {frame['confidence_reason']}\n"
        f"Next: {frame['recommended_next_step']}",
        title="Decision",
        border_style="green" if res.shortlist else "yellow",
    ))
    if res.verdict:
        console.print(Panel(res.verdict, title="Verdict", border_style="green"))
    t = Table(show_lines=False, header_style="bold")
    for col, just in [
        ("#", "right"), ("Creator", "left"), ("Score", "right"),
        ("Followers", "right"), ("ER", "right"), ("Proof", "left"),
    ]:
        t.add_column(col, justify=just, overflow="fold")
    for i, c in enumerate(res.candidates[:limit], 1):
        er = f"{c.engagement_rate * 100:.2f}%" if c.engagement_rate else "-"
        t.add_row(str(i), f"@{c.handle}", f"{c.total_score:.2f}/10", str(c.followers or "-"), er, c.proof_summary)
    console.print(t)

    for i, c in enumerate(res.shortlist, 1):
        cd = decision.candidate_decision(c, i - 1)
        console.print(f"\n[bold green]{i}. @{c.handle}[/bold green] - {c.total_score:.2f}/10")
        console.print(f"[bold]{cd['decision']}[/bold]")
        console.print("Why: " + "; ".join(cd["why"]))
        console.print("Next checks: " + "; ".join(cd["next_checks"]))
        console.print(
            f"audience {c.audience_fit:.1f} | content {c.content_fit:.1f} | "
            f"engagement {c.engagement_quality:.1f} | feedback {c.feedback_sentiment:.1f} {cd['sentiment_emoji']} | "
            f"safety {c.brand_safety:.1f} | authenticity {c.authenticity:.1f}"
        )
        if c.flags:
            console.print("[yellow]Flags:[/yellow] " + "; ".join(c.flags))
        for e in sorted(c.evidence, key=lambda x: (x.relevance, x.metrics.get("video_views", 0), x.metrics.get("likes", 0)), reverse=True)[:4]:
            m = e.metrics or {}
            console.print(
                f"  - {e.kind}: rel {e.relevance:.1f}, likes {m.get('likes', 0)}, "
                f"comments {m.get('comments', 0)}, views {m.get('video_views', 0)} | {e.url or '-'}"
            )
            if e.text:
                console.print(f"    [dim]{e.text[:180]}[/dim]")

    cov = Table(title="Source coverage", header_style="bold", show_lines=False)
    cov.add_column("Source")
    cov.add_column("Status")
    cov.add_column("Note")
    for s in res.source_status:
        style = "green" if s.status == "ok" else "yellow" if s.status in {"skipped", "empty"} else "red"
        cov.add_row(s.source, f"[{style}]{s.status}[/{style}]", s.note)
    console.print(cov)
    console.print(f"[dim]Seen {res.total_seen} raw items | ranked {len(res.candidates)} | shortlisted {len(res.shortlist)}[/dim]")


def _handles(text: str | None) -> list[str]:
    if not text:
        return []
    return [x.strip().lstrip("@") for x in text.replace("\n", ",").split(",") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="AZ influencer intelligence agent")
    ap.add_argument("query", nargs="+", help="campaign brief")
    ap.add_argument("--source", default="instagram", help="data source: instagram | youtube | all | comma-separated")
    ap.add_argument("--top", type=int, default=3, help="shortlist size")
    ap.add_argument("--min-score", type=float, default=0.0, help="minimum total score, 0..10")
    ap.add_argument("--min-followers", type=int, default=config.DEFAULT_MIN_FOLLOWERS, help="minimum Instagram follower count for shortlist")
    ap.add_argument("--allow-unknown-followers", action="store_true", help="allow profiles without follower count into shortlist")
    ap.add_argument("--seed-handles", help="comma-separated Instagram handles to force-analyze")
    ap.add_argument("--no-comments", action="store_true", help="skip comment scraping")
    ap.add_argument("--no-verdict", action="store_true", help="skip LLM verdict")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--limit", type=int, default=20, help="ranked rows to show")
    ap.add_argument("--telegram", action="store_true", help="send shortlist to Telegram")
    args = ap.parse_args()

    query = " ".join(args.query)
    with console.status(f"[cyan]Scanning influencers for '{query[:60]}'...[/cyan]"):
        res = asyncio.run(hunt(
            query,
            source=args.source,
            top_n=args.top,
            min_score=args.min_score,
            min_followers=args.min_followers,
            allow_unknown_followers=args.allow_unknown_followers,
            seed_handles=_handles(args.seed_handles),
            deep_comments=not args.no_comments,
            do_verdict=not args.no_verdict,
        ))

    if args.json:
        console.print_json(json.dumps(report_mod.to_json(res), ensure_ascii=False))
    else:
        render(res, args.limit)
    jpath, mpath = report_mod.save(res)
    console.print(f"[dim]Saved report: {mpath}[/dim]")
    if args.telegram:
        console.print(f"[dim]Telegram: {'sent' if report_mod.telegram(res) else 'not sent'}[/dim]")


if __name__ == "__main__":
    main()
