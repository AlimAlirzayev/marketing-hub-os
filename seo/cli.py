"""SEO Engine CLI.

    python -m seo audit <url> [--no-vitals] [--desktop] [--json]

More sub-commands (research, write) land in later phases.
"""

from __future__ import annotations

import argparse
import json
import sys

from .audit.auditor import audit_url
from .report import audit_json, audit_report, gap_report, research_report
from .research.gap import analyze_gap
from .research.keywords import research_keywords


def _cmd_audit(args) -> int:
    r = audit_url(args.url, with_vitals=not args.no_vitals,
                  strategy="desktop" if args.desktop else "mobile")
    if args.json:
        print(json.dumps(audit_json(r), ensure_ascii=False, indent=2))
    else:
        print(audit_report(r))
    if args.html or args.pdf:
        from .render import save_audit_html
        out = save_audit_html(r, to_pdf=args.pdf)
        print(f"\n  📄 Hesabat: {out}")
    return 0 if r.fetched_ok else 1


def _cmd_research(args) -> int:
    r = research_keywords(args.seed, cluster=not args.no_cluster, max_keywords=args.limit)
    print(research_report(r))
    return 0 if r.keywords else 1


def _cmd_gap(args) -> int:
    g = analyze_gap(args.keyword, top_n=args.top)
    print(gap_report(g))
    return 0 if g.competitors else 1


def _cmd_write(args) -> int:
    from .content.brief import build_brief
    from .content.writer import onpage_selfcheck, write_article
    from .render import article_html, save_article_html

    tag = " + CANLI SERP gap" if args.serp else ""
    print(f"  ◆ Brief hazırlanır — “{args.keyword}” (real açar sözlər{tag})...")
    brief = build_brief(args.keyword, use_serp=args.serp)
    if brief.gap and brief.gap.source == "llm":
        print(f"    SERP: {brief.gap.analyzed} rəqib təhlil edildi · "
              f"{len(brief.gap.content_gaps)} boşluq tapıldı")
    print(f"    niyyət: {brief.intent} · {len(brief.grounded_keywords)} real açar söz · "
          f"{len(brief.outline)} bölmə · {len(brief.faqs)} FAQ · mənbə: {brief.source}")
    for t in brief.title_options[:3]:
        print(f"      · başlıq: {t}")

    if args.brief_only:
        return 0

    if args.refine:
        from .content.refine import refine_article
        print("  ◆ Məqalə yazılır + self-reflection döngüsü...")
        rr = refine_article(brief, max_iters=args.max_iters)
        art = rr.article
        for it in rr.iterations:
            extra = f" · {len(it.issues)} problem" if it.issues else ""
            print(f"    iterasiya {it.n}: on-page {it.onpage_passed}/{it.onpage_total} "
                  f"· hökm: {it.verdict}{extra}")
        print(f"    nəticə: {'təkmilləşdirildi ✓' if rr.improved else 'ilk versiya publish-grade idi'}")
        words = len(art.markdown.split())
        print(f"    yekun: ~{words} söz · {len(art.faq)} FAQ · mənbə: {art.source}")
    else:
        print("  ◆ Məqalə yazılır...")
        art = write_article(brief)
        words = len(art.markdown.split())
        print(f"    yazıldı: ~{words} söz · {len(art.faq)} FAQ · JSON-LD: "
              f"{', '.join(o.get('@type','') for o in art.jsonld) or 'yox'} · mənbə: {art.source}")

        check = onpage_selfcheck(article_html(art))
        print(f"  ◆ Öz-audit (dogfood): on-page {check['passed']}/{check['total']} keçdi — "
              + " ".join(f"{i}:{s}" for i, s, _ in check["findings"]))

    out = save_article_html(art, to_pdf=args.pdf)
    print(f"\n  📄 Məqalə: {out}")
    return 0 if art.source == "llm" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="seo", description="RAMIN OS — SEO Engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("audit", help="Bir URL üçün texniki SEO audit")
    pa.add_argument("url")
    pa.add_argument("--no-vitals", action="store_true", help="Core Web Vitals (PageSpeed) çağırışını at")
    pa.add_argument("--desktop", action="store_true", help="Mobil əvəzinə desktop strategiyası")
    pa.add_argument("--json", action="store_true", help="JSON çıxış")
    pa.add_argument("--html", action="store_true", help="Premium HTML hesabat (output/seo/)")
    pa.add_argument("--pdf", action="store_true", help="HTML-i headless Edge ilə PDF-ə çevir")
    pa.set_defaults(func=_cmd_audit)

    pr = sub.add_parser("research", help="Açar söz kəşfiyyatı (Google Suggest + AI klaster)")
    pr.add_argument("seed")
    pr.add_argument("--no-cluster", action="store_true", help="AI klasterləşdirməni at (düz siyahı)")
    pr.add_argument("--limit", type=int, default=120, help="Maksimum açar söz sayı")
    pr.set_defaults(func=_cmd_research)

    pg = sub.add_parser("gap", help="SERP rəqib + content-gap təhlili")
    pg.add_argument("keyword")
    pg.add_argument("--top", type=int, default=5, help="Neçə rəqib təhlil edilsin")
    pg.set_defaults(func=_cmd_gap)

    pw = sub.add_parser("write", help="Açar sözdən on-page mükəmməl SEO məqalə yaz")
    pw.add_argument("keyword")
    pw.add_argument("--serp", action="store_true", help="CANLI SERP rəqib təhlili ilə gücləndir")
    pw.add_argument("--refine", action="store_true", help="Self-reflection: yaz→tənqid→təkmilləşdir→təkrar yoxla")
    pw.add_argument("--max-iters", type=int, default=2, help="Reflection iterasiya limiti")
    pw.add_argument("--brief-only", action="store_true", help="Yalnız SEO brief (məqalə yazma)")
    pw.add_argument("--pdf", action="store_true", help="Məqaləni PDF-ə çevir (headless Edge)")
    pw.set_defaults(func=_cmd_write)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
