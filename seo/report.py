"""Turn an AuditResult into an Azerbaijani, human-readable report.

Two consumers: the CLI (prints this) and, later, the FastAPI panel / PDF layer.
Deliverable-quality: score header, findings grouped by category, and a
prioritized action list (kritik → vacib) so the operator knows what to fix first.
"""

from __future__ import annotations

from .audit.auditor import AuditResult
from .research.gap import GapResult
from .research.keywords import ResearchResult

_BAR = "─" * 64


def _grade_line(r: AuditResult) -> str:
    bar_len = 24
    filled = round(bar_len * r.score / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    return f"  SEO BALI:  {r.score}/100  ({r.grade})   [{bar}]"


def audit_report(r: AuditResult) -> str:
    lines: list[str] = []
    lines.append(_BAR)
    lines.append(f"  TEXNİKİ SEO AUDİT — {r.final_url}")
    lines.append(f"  {r.ts}  ·  mənbə: CANLI (real vaxt tarama)")
    lines.append(_BAR)

    if not r.fetched_ok:
        lines.append(f"  ❌ Audit alınmadı: {r.error}")
        lines.append(_BAR)
        return "\n".join(lines)

    s = r.summary()
    lines.append(_grade_line(r))
    lines.append(f"  ✅ {s.get('pass',0)} keçdi   ⚠️ {s.get('warn',0)} xəbərdarlıq   "
                 f"❌ {s.get('fail',0)} problem   ➖ {s.get('na',0)} n/a")
    lines.append("")

    # grouped by category, in registry order
    cats: list[str] = []
    for f in r.findings:
        if f.category not in cats:
            cats.append(f.category)
    for cat in cats:
        lines.append(f"  ▸ {cat}")
        for f in [x for x in r.findings if x.category == cat]:
            lines.append(f"      {f.icon} {f.title} — {f.detail}")
        lines.append("")

    # prioritized fixes
    fixes = [f for f in r.findings if f.status in ("fail", "warn") and f.fix]
    fixes.sort(key=lambda f: (f.status != "fail", -f.weight))
    if fixes:
        lines.append(_BAR)
        lines.append("  🔧 PRİORİTETLİ DÜZƏLİŞLƏR (kritik → kiçik)")
        lines.append(_BAR)
        for i, f in enumerate(fixes, 1):
            tag = "KRİTİK" if f.status == "fail" and f.weight >= 3 else \
                  "VACİB" if f.weight >= 2 else "KİÇİK"
            lines.append(f"  {i}. [{tag}] {f.title}: {f.fix}")
    else:
        lines.append("  🎉 Prioritetli düzəliş yoxdur — sayt SEO baxımından güclüdür.")
    lines.append(_BAR)
    return "\n".join(lines)


def research_report(r: ResearchResult) -> str:
    lines: list[str] = []
    lines.append(_BAR)
    lines.append(f"  AÇAR SÖZ KƏŞFİYYATI — “{r.seed}”")
    src = "Google Suggest (CANLI) + AI klaster" if r.intelligence == "llm" else "Google Suggest (CANLI)"
    lines.append(f"  {r.total} açar söz  ·  mənbə: {src}  ·  {r.hl}/{r.gl}")
    lines.append(_BAR)
    if r.clusters:
        for c in r.clusters:
            lines.append(f"  ▸ {c.name}   [{c.intent_az}]")
            if c.primary:
                lines.append(f"      ★ əsas: {c.primary}")
            for kw in c.keywords[:10]:
                lines.append(f"        · {kw}")
            lines.append("")
    else:
        lines.append("  (AI klaster əlçatmaz — düz siyahı)")
        for kw in r.keywords[:40]:
            lines.append(f"    · {kw}")
    lines.append(_BAR)
    return "\n".join(lines)


def gap_report(g: GapResult) -> str:
    lines: list[str] = []
    lines.append(_BAR)
    lines.append(f"  SERP RƏQİB & CONTENT-GAP TƏHLİLİ — “{g.keyword}”")
    src = "CANLI SERP + AI təhlil" if g.source == "llm" else "CANLI SERP"
    lines.append(f"  {len(g.competitors)} rəqib · {g.analyzed} başlıq oxundu · mənbə: {src}")
    lines.append(_BAR)
    if g.competitors:
        lines.append("  ▸ TOP rəqiblər")
        for c in g.competitors:
            lines.append(f"      {c.rank}. {c.domain} — {c.title[:60]}")
        lines.append("")
    if g.common_subtopics:
        lines.append("  ▸ Table-stakes (hamı örtür — mütləq lazım)")
        for t in g.common_subtopics:
            lines.append(f"      · {t}")
        lines.append("")
    if g.content_gaps:
        lines.append("  ★ BOŞLUQLAR (sıralanma fürsəti)")
        for t in g.content_gaps:
            lines.append(f"      → {t}")
        lines.append("")
    if g.faq_questions:
        lines.append("  ▸ FAQ üçün real suallar")
        for q in g.faq_questions:
            lines.append(f"      ? {q}")
    lines.append(_BAR)
    return "\n".join(lines)


def gsc_report(rep) -> str:
    lines: list[str] = []
    lines.append(_BAR)
    src = "CANLI (Search Console)" if rep.mode == "live" else "DEMO (sintetik — GSC açarı yoxdur)"
    lines.append(f"  SEARCH CONSOLE — {rep.site}  ·  {rep.dimension}")
    lines.append(f"  {rep.start} → {rep.end}  ·  mənbə: {src}")
    lines.append(_BAR)
    if rep.error:
        lines.append(f"  ❌ {rep.error}")
        lines.append(_BAR)
        return "\n".join(lines)
    lines.append(f"  Cəmi: {rep.total_clicks:,} klik · {rep.total_impressions:,} göstərim")
    lines.append("")
    lines.append(f"  {'#':>2}  {'klik':>6} {'göstərim':>9} {'CTR':>6} {'mövqe':>6}  sorğu/səhifə")
    for i, r in enumerate(rep.rows[:20], 1):
        lines.append(f"  {i:>2}  {r.clicks:>6} {r.impressions:>9} "
                     f"{r.ctr*100:>5.1f}% {r.position:>6.1f}  {r.key[:52]}")
    lines.append(_BAR)
    return "\n".join(lines)


def reinforce_report(o) -> str:
    icon = {"winning": "🏆", "climbing": "📈", "struggling": "⚠️", "no-data": "➖"}.get(o.verdict, "•")
    src = "CANLI" if o.mode == "live" else "DEMO"
    lines = [
        _BAR,
        f"  REINFORCEMENT — nəşr olunmuş səhifənin real nəticəsi ({src})",
        f"  {o.page_url}",
        _BAR,
        f"  {icon} Hökm: {o.verdict.upper()}  ·  orta mövqe {o.avg_position}  ·  "
        f"{o.clicks} klik  ·  {o.impressions} göstərim  ·  CTR {o.ctr*100:.1f}%",
        "",
    ]
    if o.top_queries:
        lines.append("  Ən güclü sorğular:")
        for q in o.top_queries:
            lines.append(f"      · {q['query'][:48]}  (poz {q['position']}, {q['clicks']} klik)")
        lines.append("")
    lines.append(f"  📚 Brain dərsi: {'yazıldı ✓' if o.lesson_saved else '(brain əlçatmaz / data yox)'}"
                 f"   ·   korpus: {o.corpus_size} sətir (D2 fine-tune üçün)")
    lines.append(_BAR)
    return "\n".join(lines)


def audit_json(r: AuditResult) -> dict:
    """Machine-readable form (for the panel / brain / API)."""
    return {
        "url": r.url,
        "final_url": r.final_url,
        "ok": r.fetched_ok,
        "score": r.score,
        "grade": r.grade,
        "ts": r.ts,
        "error": r.error,
        "summary": r.summary(),
        "findings": [
            {"id": f.id, "category": f.category, "title": f.title,
             "status": f.status, "weight": f.weight, "detail": f.detail, "fix": f.fix}
            for f in r.findings
        ],
    }
