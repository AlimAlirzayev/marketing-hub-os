"""YouTube proof-of-concept for Influencer Hunter.

Demonstrates a fully free, official, zero-ban-risk path: YouTube Data API v3 ->
real channel + video + COMMENT data -> existing scoring -> the new analysis layer
(pandas + LLM Azerbaijani sentiment). Runs alongside, not instead of, the
Instagram pipeline.

Run:
    .venv/Scripts/python.exe youtube_poc.py
    .venv/Scripts/python.exe youtube_poc.py "az travel vlogger" --seed-handles @handle1,@handle2
"""

from __future__ import annotations

import argparse
import io
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import analyze  # noqa: E402
import config  # noqa: E402
import resolve as resolve_mod  # noqa: E402
import score as score_mod  # noqa: E402
import sources_youtube as yt  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

console = Console()

DEFAULT_QUERY = (
    "Xalq Sigorta üçün səyahət sığortası barədə emosional video canlandıracaq "
    "Azərbaycanlı travel/lifestyle YouTube creator lazımdır."
)


def _handles(text: str | None) -> list[str]:
    if not text:
        return []
    return [x.strip().lstrip("@") for x in text.replace("\n", ",").split(",") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="YouTube connector PoC")
    ap.add_argument("query", nargs="*", help="campaign brief")
    ap.add_argument("--seed-handles", help="comma-separated YouTube @handles")
    ap.add_argument("--no-comments", action="store_true")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    query = " ".join(args.query) or DEFAULT_QUERY

    if not yt.available():
        console.print("[red]YOUTUBE_API_KEY / GOOGLE_API_KEY tapılmadı (.env).[/red]")
        return

    brief = resolve_mod.resolve(query)
    console.print(Panel.fit(
        f"[bold]{brief.product or query[:60]}[/bold]\n"
        f"brand: [cyan]{brief.brand or '-'}[/cyan]\n"
        f"YouTube Data API v3 | açar: {'var' if yt.available() else 'yox'}",
        title="YouTube Connector PoC", border_style="red"))

    with console.status("[cyan]YouTube skan edilir (kanal · video · rəy)...[/cyan]"):
        candidates, statuses, seen = yt.collect(brief, seed_handles=_handles(args.seed_handles), deep_comments=not args.no_comments)

    # honest stop on a credential/quota blocker, surfacing the precise fix
    blockers = [s for s in statuses if s.status in {"error:key-restricted", "error:disabled", "error:quota"}]
    if blockers:
        console.print(Panel(
            f"[yellow]{blockers[0].note}[/yellow]\n\nDüzəlişdən sonra bu skripti yenidən işə sal.\n"
            "Gündəlik kvota: 10,000 vahid (pulsuz). Ban riski yoxdur.",
            title="Bir addım qalır", border_style="yellow"))
        _coverage(statuses)
        return

    if not candidates:
        console.print("[yellow]Uyğun YouTube kanalı tapılmadı.[/yellow]")
        _coverage(statuses)
        return

    score_mod.score_candidates(candidates, brief)
    analyze.enrich(brief, candidates)
    for c in candidates:
        c.total_score = score_mod.weighted_total(c)
    candidates.sort(key=lambda x: (x.total_score, x.proof_density), reverse=True)

    console.print(f"\n[bold]Tapılan kanallar (xam {seen} element):[/bold]")
    for i, c in enumerate(candidates[: args.top], 1):
        er = f"{c.engagement_rate * 100:.2f}%" if c.engagement_rate else "-"
        comments = [e for e in c.evidence if e.kind == "comment"]
        videos = [e for e in c.evidence if e.kind == "video"]
        console.print(f"\n[bold green]{i}. @{c.handle}[/bold green] [dim]{c.name}[/dim] — [bold]{c.total_score:.2f}/10[/bold]")
        console.print(f"   abunəçi {c.followers if c.followers is not None else '?'} | video {c.posts_count} | ER(views) {er} | {len(videos)} video, {len(comments)} rəy")
        console.print(f"   skorlar: auditoriya {c.audience_fit:.1f} · kontent {c.content_fit:.1f} · engagement {c.engagement_quality:.1f} · rəy {c.feedback_sentiment:.1f} · təhlükəsizlik {c.brand_safety:.1f}")
        if c.audience_summary:
            console.print(f"   [cyan]İzləyici reaksiyası:[/cyan] {c.audience_summary}")
        if c.flags:
            console.print(f"   [yellow]Qeyd:[/yellow] {'; '.join(c.flags)}")
        for e in comments[:3]:
            console.print(f"     [dim]rəy:[/dim] {e.text[:120]}")

    _coverage(statuses)


def _coverage(statuses) -> None:
    cov = Table(title="Source coverage", header_style="bold")
    cov.add_column("Source"); cov.add_column("Status"); cov.add_column("Note")
    for s in statuses:
        style = "green" if s.status == "ok" else "yellow" if s.status in {"skipped", "empty"} else "red"
        cov.add_row(s.source, f"[{style}]{s.status}[/{style}]", s.note)
    console.print(cov)


if __name__ == "__main__":
    main()
