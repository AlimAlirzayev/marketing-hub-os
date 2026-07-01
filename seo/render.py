"""Premium HTML report for an SEO audit — the deliverable layer.

Design bar (from the ecosystem charter): a cover/hero with a real score gauge,
card layout, status badges, and a prioritized fix roadmap — not a plain table.
Self-contained (inline CSS + inline SVG gauge), Azerbaijani, and print-clean so
headless Edge turns it straight into a PDF. Every data source is labelled; the
report never invents a number.
"""

from __future__ import annotations

import html as _html
import json as _json
import re as _re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .audit.auditor import AuditResult

# grade -> accent colour
_GRADE_COLOR = {"A": "#16c784", "B": "#7ed957", "C": "#f5c518", "D": "#ff9f43", "F": "#ff4d4f"}
_STATUS = {
    "pass": ("#16c784", "✓", "Keçdi"),
    "warn": ("#f5c518", "!", "Xəbərdarlıq"),
    "fail": ("#ff4d4f", "✕", "Problem"),
    "info": ("#4aa8ff", "i", "Məlumat"),
    "na":   ("#6b7280", "–", "N/A"),
}


def _esc(s: str) -> str:
    return _html.escape(str(s or ""))


def _gauge(score: int, grade: str) -> str:
    """Inline SVG circular gauge (no JS, prints perfectly)."""
    color = _GRADE_COLOR.get(grade, "#7ed957")
    r = 84
    circ = 2 * 3.14159 * r
    dash = circ * score / 100
    return f"""
    <svg width="220" height="220" viewBox="0 0 220 220" class="gauge">
      <circle cx="110" cy="110" r="{r}" fill="none" stroke="#1e2a3a" stroke-width="16"/>
      <circle cx="110" cy="110" r="{r}" fill="none" stroke="{color}" stroke-width="16"
              stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}"
              transform="rotate(-90 110 110)"/>
      <text x="110" y="102" text-anchor="middle" class="gauge-num">{score}</text>
      <text x="110" y="130" text-anchor="middle" class="gauge-sub">/ 100</text>
      <text x="110" y="158" text-anchor="middle" class="gauge-grade" fill="{color}">{grade}</text>
    </svg>"""


def _finding_row(f) -> str:
    color, sym, _ = _STATUS[f.status]
    fix = f'<div class="fix">🔧 {_esc(f.fix)}</div>' if f.fix and f.status in ("fail", "warn") else ""
    return f"""
      <div class="row">
        <span class="dot" style="background:{color}">{sym}</span>
        <div class="row-body">
          <div class="row-title">{_esc(f.title)}</div>
          <div class="row-detail">{_esc(f.detail)}</div>
          {fix}
        </div>
      </div>"""


def _roadmap(findings) -> str:
    fixes = [f for f in findings if f.status in ("fail", "warn") and f.fix]
    fixes.sort(key=lambda f: (f.status != "fail", -f.weight))
    if not fixes:
        return '<div class="empty">🎉 Prioritetli düzəliş yoxdur — sayt SEO baxımından güclüdür.</div>'
    cards = []
    for i, f in enumerate(fixes, 1):
        sev = ("KRİTİK", "#ff4d4f") if f.status == "fail" and f.weight >= 3 else \
              ("VACİB", "#ff9f43") if f.weight >= 2 else ("KİÇİK", "#f5c518")
        cards.append(f"""
          <div class="fix-card">
            <div class="fix-num">{i}</div>
            <div>
              <span class="sev" style="background:{sev[1]}22;color:{sev[1]};border:1px solid {sev[1]}55">{sev[0]}</span>
              <span class="fix-t">{_esc(f.title)}</span>
              <div class="fix-d">{_esc(f.fix)}</div>
            </div>
          </div>""")
    return "\n".join(cards)


def audit_html(r: AuditResult) -> str:
    host = urlparse(r.final_url).netloc or r.url
    s = r.summary()
    accent = _GRADE_COLOR.get(r.grade, "#7ed957")
    dt = datetime.now().strftime("%d.%m.%Y  %H:%M")

    # category sections
    cats: list[str] = []
    for f in r.findings:
        if f.category not in cats:
            cats.append(f.category)
    sections = []
    for cat in cats:
        rows = "".join(_finding_row(f) for f in r.findings if f.category == cat)
        cat_fs = [f for f in r.findings if f.category == cat]
        ok = sum(1 for f in cat_fs if f.status == "pass")
        sections.append(f"""
        <section class="card">
          <div class="card-head"><h3>{_esc(cat)}</h3><span class="pill">{ok}/{len(cat_fs)}</span></div>
          {rows}
        </section>""")

    return f"""<!doctype html><html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Audit — {_esc(host)}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Segoe UI',system-ui,sans-serif; background:#0b1220; color:#e6edf5;
         line-height:1.5; padding:32px; }}
  .wrap {{ max-width:1000px; margin:0 auto; }}
  .hero {{ display:flex; align-items:center; gap:32px; background:linear-gradient(135deg,#111c30,#0d1626);
          border:1px solid #1e2a3a; border-radius:20px; padding:32px; margin-bottom:24px;
          box-shadow:0 8px 40px rgba(0,0,0,.4); }}
  .hero-txt {{ flex:1; }}
  .kicker {{ letter-spacing:3px; font-size:12px; color:{accent}; font-weight:700; text-transform:uppercase; }}
  .hero h1 {{ font-size:26px; margin:6px 0 4px; word-break:break-all; }}
  .hero .meta {{ color:#8aa0b8; font-size:13px; }}
  .badges {{ margin-top:16px; display:flex; gap:10px; flex-wrap:wrap; }}
  .b {{ padding:8px 14px; border-radius:10px; font-size:13px; font-weight:600; border:1px solid #24344a; }}
  .b.pass {{ background:#16c78418; color:#16c784; }}
  .b.warn {{ background:#f5c51818; color:#f5c518; }}
  .b.fail {{ background:#ff4d4f18; color:#ff4d4f; }}
  .b.na   {{ background:#6b728018; color:#9aa7b4; }}
  .gauge-num {{ font-size:52px; font-weight:800; fill:#fff; }}
  .gauge-sub {{ font-size:15px; fill:#8aa0b8; }}
  .gauge-grade {{ font-size:30px; font-weight:800; }}
  .card {{ background:#0f1a2b; border:1px solid #1e2a3a; border-radius:16px; padding:22px; margin-bottom:16px; }}
  .card-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;
               border-bottom:1px solid #1e2a3a; padding-bottom:12px; }}
  .card-head h3 {{ font-size:16px; color:#cde1f5; }}
  .pill {{ background:#16283e; color:#7fb7f0; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:700; }}
  .row {{ display:flex; gap:14px; padding:12px 0; border-bottom:1px solid #16202f; }}
  .row:last-child {{ border-bottom:none; }}
  .dot {{ flex:none; width:26px; height:26px; border-radius:50%; color:#06111d; font-weight:800;
         display:flex; align-items:center; justify-content:center; font-size:14px; }}
  .row-title {{ font-weight:600; font-size:14px; }}
  .row-detail {{ color:#8aa0b8; font-size:13px; margin-top:2px; }}
  .fix {{ color:#ffd27f; font-size:12.5px; margin-top:6px; background:#1c1608; border-left:3px solid #f5c518;
         padding:6px 10px; border-radius:6px; }}
  h2.sec {{ font-size:20px; margin:28px 0 14px; display:flex; align-items:center; gap:10px; }}
  .fix-card {{ display:flex; gap:16px; background:#0f1a2b; border:1px solid #1e2a3a; border-radius:14px;
              padding:16px 18px; margin-bottom:10px; }}
  .fix-num {{ flex:none; width:34px; height:34px; border-radius:10px; background:{accent}22; color:{accent};
             font-weight:800; display:flex; align-items:center; justify-content:center; }}
  .sev {{ font-size:11px; font-weight:800; padding:3px 8px; border-radius:6px; margin-right:8px; }}
  .fix-t {{ font-weight:700; font-size:14px; }}
  .fix-d {{ color:#a9bccf; font-size:13px; margin-top:6px; }}
  .empty {{ text-align:center; padding:26px; color:#16c784; font-weight:600; }}
  footer {{ margin-top:26px; color:#63758a; font-size:12px; text-align:center; line-height:1.7; }}
  @media print {{ body {{ background:#fff; color:#0b1220; padding:0; }}
    .card,.hero,.fix-card {{ break-inside:avoid; box-shadow:none; }} }}
</style></head><body><div class="wrap">

  <div class="hero">
    <div class="hero-txt">
      <div class="kicker">RAMIN OS · Texniki SEO Audit</div>
      <h1>{_esc(host)}</h1>
      <div class="meta">{_esc(r.final_url)} · {dt} · mənbə: <b style="color:{accent}">CANLI</b> (real-vaxt tarama)</div>
      <div class="badges">
        <span class="b pass">✓ {s.get('pass',0)} keçdi</span>
        <span class="b warn">! {s.get('warn',0)} xəbərdarlıq</span>
        <span class="b fail">✕ {s.get('fail',0)} problem</span>
        <span class="b na">– {s.get('na',0)} n/a</span>
      </div>
    </div>
    <div>{_gauge(r.score, r.grade)}</div>
  </div>

  {''.join(sections)}

  <h2 class="sec">🔧 Yol Xəritəsi — Prioritetli Düzəlişlər</h2>
  {_roadmap(r.findings)}

  <footer>
    2026 SEO checklist · {len(r.findings)} yoxlama · İndeksləmə, On-page, Struktur, Performans, Etibar & AI (GEO).<br>
    Core Web Vitals: Google PageSpeed Insights. Ölçülə bilməyən göstəricilər <b>ƏLÇATMAZ</b> kimi işarələnir — heç bir rəqəm uydurulmur.<br>
    RAMIN OS SEO Engine v{getattr(__import__('seo'), '__version__', '0.1')}
  </footer>
</div></body></html>"""


def save_audit_html(r: AuditResult, *, to_pdf: bool = False) -> Path:
    host = (urlparse(r.final_url).netloc or "site").replace(":", "_")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = config.OUTPUT_DIR / f"audit-{host}-{stamp}.html"
    path.write_text(audit_html(r), encoding="utf-8")
    if to_pdf:
        pdf = _to_pdf(path)
        if pdf:
            return pdf
    return path


# --------------------------------------------------------------------------- #
# Article deliverable (light, readable blog style — a different aesthetic from
# the dark audit dashboard) with a copy-ready SEO/JSON-LD panel.
# --------------------------------------------------------------------------- #

def _md_to_html(md: str) -> str:
    """Minimal, dependency-free markdown -> HTML for the subset the writer emits
    (## / ### / #### headings, - and 1. lists, **bold**, paragraphs)."""
    out: list[str] = []
    list_type: str | None = None

    def close_list():
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = None

    def inline(t: str) -> str:
        t = _esc(t)
        t = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = _re.sub(r"(?<!\*)\*(?!\s)(.+?)\*", r"<em>\1</em>", t)
        return t

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_list()
            continue
        m = _re.match(r"^(#{2,4})\s+(.*)$", line)
        if m:
            close_list()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            continue
        if _re.match(r"^\s*[-*]\s+", line):
            if list_type != "ul":
                close_list(); out.append("<ul>"); list_type = "ul"
            out.append(f"<li>{inline(_re.sub(r'^\s*[-*]\s+', '', line))}</li>")
            continue
        if _re.match(r"^\s*\d+[.)]\s+", line):
            if list_type != "ol":
                close_list(); out.append("<ol>"); list_type = "ol"
            out.append(f"<li>{inline(_re.sub(r'^\s*\d+[.)]\s+', '', line))}</li>")
            continue
        close_list()
        out.append(f"<p>{inline(line)}</p>")
    close_list()
    return "\n".join(out)


def article_html(art) -> str:
    """Full standalone HTML page for the article. Also the on-page self-audit
    target: proper head (title, meta, viewport, lang, single H1) + JSON-LD."""
    body = _md_to_html(art.markdown)
    faq_html = ""
    if art.faq:
        items = "".join(
            f'<div class="faq-item"><h3>{_esc(q["q"])}</h3><p>{_esc(q["a"])}</p></div>'
            for q in art.faq
        )
        faq_html = f'<section class="faq"><h2>Tez-tez verilən suallar</h2>{items}</section>'

    jsonld_scripts = "\n".join(
        f'<script type="application/ld+json">{_json.dumps(obj, ensure_ascii=False)}</script>'
        for obj in art.jsonld
    )
    jsonld_pretty = _esc(_json.dumps(art.jsonld, ensure_ascii=False, indent=2))
    sec_kw = art.brief.secondary_keywords[:10] if art.brief else []
    kw_chips = "".join(f'<span class="chip">{_esc(k)}</span>' for k in [art.keyword] + sec_kw)

    return f"""<!doctype html><html lang="{art.lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(art.meta_title)}</title>
<meta name="description" content="{_esc(art.meta_description)}">
<link rel="canonical" href="https://REPLACE-ME.az/{_re.sub(r'[^a-z0-9]+','-',art.keyword.lower()).strip('-')}">
{jsonld_scripts}
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Georgia','Segoe UI',serif;background:#f4f6f9;color:#1a2231;line-height:1.75;padding:32px}}
  .wrap{{max-width:760px;margin:0 auto}}
  .seo-panel{{font-family:'Segoe UI',sans-serif;background:#0f1a2b;color:#e6edf5;border-radius:16px;
    padding:22px 24px;margin-bottom:28px}}
  .seo-panel h4{{color:#7ed957;font-size:12px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
  .seo-panel .kv{{font-size:13px;margin:6px 0;color:#b9c8d8}}
  .seo-panel .kv b{{color:#fff}}
  .chips{{margin:10px 0 4px;display:flex;flex-wrap:wrap;gap:6px}}
  .chip{{background:#16283e;color:#8fc0f5;font-size:12px;padding:3px 10px;border-radius:20px}}
  details{{margin-top:12px}} summary{{cursor:pointer;color:#7ed957;font-size:13px;font-family:'Segoe UI',sans-serif}}
  pre{{background:#08111d;color:#cfe3ff;padding:14px;border-radius:10px;overflow:auto;font-size:11.5px;margin-top:10px}}
  article{{background:#fff;border-radius:16px;padding:44px 48px;box-shadow:0 4px 30px rgba(20,40,80,.08)}}
  article h1{{font-size:32px;line-height:1.25;margin-bottom:8px;color:#0d1b34}}
  .byline{{font-family:'Segoe UI',sans-serif;color:#7a8aa0;font-size:13px;margin-bottom:26px;
    border-bottom:1px solid #eef1f6;padding-bottom:16px}}
  article h2{{font-size:23px;margin:30px 0 10px;color:#12213c}}
  article h3{{font-size:18px;margin:22px 0 8px;color:#1c2b46}}
  article p{{margin:12px 0}} article ul,article ol{{margin:12px 0 12px 24px}} article li{{margin:6px 0}}
  .faq{{margin-top:20px}} .faq-item{{border-top:1px solid #eef1f6;padding:14px 0}}
  .faq-item h3{{font-size:17px;margin:0 0 4px}}
  footer{{font-family:'Segoe UI',sans-serif;text-align:center;color:#8a97a8;font-size:12px;margin-top:26px}}
  @media print{{body{{background:#fff;padding:0}} article{{box-shadow:none}}}}
</style></head><body><div class="wrap">

  <div class="seo-panel">
    <h4>◆ SEO Paketi — CMS-ə hazır</h4>
    <div class="kv"><b>Meta title:</b> {_esc(art.meta_title)} <span style="color:#63758a">({len(art.meta_title)} simvol)</span></div>
    <div class="kv"><b>Meta description:</b> {_esc(art.meta_description)} <span style="color:#63758a">({len(art.meta_description)} simvol)</span></div>
    <div class="kv"><b>Axtarış niyyəti:</b> {_esc(art.brief.intent if art.brief else '')}</div>
    <div class="chips">{kw_chips}</div>
    <details><summary>Strukturlaşdırılmış data (JSON-LD) — kopyala/yapışdır</summary><pre>{jsonld_pretty}</pre></details>
  </div>

  <article>
    <h1>{_esc(art.h1)}</h1>
    <div class="byline">Xalq Sigorta · {datetime.now().strftime('%d.%m.%Y')} · ~{len(art.markdown.split())} söz</div>
    {body}
    {faq_html}
  </article>

  <footer>RAMIN OS SEO Engine · məzmun AI ilə yaradılıb, nəşrdən əvvəl redaktə/faktçek tövsiyə olunur</footer>
</div></body></html>"""


def save_article_html(art, *, to_pdf: bool = False) -> Path:
    slug = _re.sub(r"[^a-z0-9]+", "-", art.keyword.lower()).strip("-")[:40] or "article"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = config.OUTPUT_DIR / f"article-{slug}-{stamp}.html"
    path.write_text(article_html(art), encoding="utf-8")
    (config.OUTPUT_DIR / f"article-{slug}-{stamp}.md").write_text(
        f"# {art.h1}\n\n{art.markdown}\n", encoding="utf-8")
    if to_pdf:
        pdf = _to_pdf(path)
        if pdf:
            return pdf
    return path


def _to_pdf(html_path: Path) -> Path | None:
    """Headless Edge is the proven PDF path on the locked-down machine."""
    import shutil
    import subprocess

    pdf_path = html_path.with_suffix(".pdf")
    for exe in ("msedge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        binary = shutil.which(exe) or (exe if Path(exe).exists() else None)
        if not binary:
            continue
        try:
            subprocess.run(
                [binary, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                 f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                timeout=60, capture_output=True,
            )
            if pdf_path.exists():
                return pdf_path
        except Exception:  # noqa: BLE001
            continue
    return None
