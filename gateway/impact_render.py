"""Impact Ledger — report-grade HTML/PDF render (the "show leadership" surface).

The Telegram text (impact_ledger.report) is right for the chat; this is the
leadership-facing document per the deliverable design bar
([[feedback_deliverable_design]]): a cover header, KPI cards with source + delta
badges, a work panel, and the one-line indispensability headline — in Xalq brand
(red + charcoal, NOT navy/teal — the corrected brand, [[project_seo_hub_canvas_app]]).

render_html(scorecard) is PURE over the scorecard dict (unit-testable, no IO); save()
does the IO and the optional PDF. The PDF path is headless Edge — the SAME proven
converter seo/render.py uses on this locked-down machine (replicated, not imported,
to keep gateway independent of the seo package whose seo/http.py shadows stdlib http).

Azerbaijani, because this is a user-facing deliverable ([[feedback_language_split]]).
No fabricated numbers: a down source renders its ƏLÇATMAZ badge, never an invented value.
"""

from __future__ import annotations

import datetime as _dt
import html
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_SOURCE_CLASS = {"CANLI": "live", "DEMO": "demo", "ƏLÇATMAZ": "down"}


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _source_badge(src: str) -> str:
    cls = _SOURCE_CLASS.get(src, "down")
    return f'<span class="badge {cls}">{_esc(src)}</span>'


def _delta_badge(delta: float | None, *, lower_better: bool = False) -> str:
    """Delta pill that never relies on colour alone — arrow + sign + a ✓/! glyph,
    so it survives a black-and-white print and colour-blind readers."""
    if delta is None:
        return ""
    good = (delta < 0) if lower_better else (delta > 0)
    arrow = "↓" if delta < 0 else "↑"
    glyph = "✓" if good else "!"
    cls = "good" if good else "warn"
    return f'<span class="delta {cls}">{arrow} {abs(delta):.0f}% {glyph}</span>'


def _kpi_card(*, label: str, value: str, sub: str, badge: str, delta: str = "",
              accent: str) -> str:
    return f"""
      <div class="card" style="--accent:{accent}">
        <div class="card-label">{_esc(label)}</div>
        <div class="card-value">{value}</div>
        <div class="card-meta">{delta}{badge}</div>
        <div class="card-sub">{_esc(sub)}</div>
      </div>"""


def render_html(sc: dict) -> str:
    """Pure: the blended scorecard -> a self-contained, print-ready HTML document."""
    month = _esc(sc.get("month", ""))
    r = sc.get("results", {}) or {}
    w = sc.get("work", {}) or {}
    lead, cpa = r.get("leads", {}), r.get("cpa", {})
    conv, sla = r.get("conversions", {}), r.get("sla", {})

    # KPI cards — a missing measure shows "—" + its source badge, never a made-up value.
    cards = []
    cards.append(_kpi_card(
        label="Müraciət (lead + mesaj)",
        value=("—" if lead.get("value") is None else _esc(lead["value"])),
        sub="Ay ərzində daxil olan bütün təmaslar",
        badge=_source_badge(lead.get("source", "ƏLÇATMAZ")),
        delta=_delta_badge(lead.get("delta_pct")),
        accent="#DA1A32"))
    cards.append(_kpi_card(
        label="Reklam CPA",
        value=("—" if cpa.get("value") is None else _esc(cpa["value"])),
        sub="Müraciət başına reklam xərci (az = yaxşı)",
        badge=_source_badge(cpa.get("source", "ƏLÇATMAZ")),
        delta=_delta_badge(cpa.get("delta_pct"), lower_better=True),
        accent="#DA1A32"))
    cards.append(_kpi_card(
        label="Konversiya (GA4)",
        value=("—" if conv.get("value") is None else _esc(conv["value"])),
        sub="Saytda hədəf hərəkətləri",
        badge=_source_badge(conv.get("source", "ƏLÇATMAZ")),
        accent="#2F6FED"))
    sla_sub = "Şikayət/müraciətlərin həll faizi"
    if sla.get("signals") is not None:
        sla_sub = f"{_esc(sla['signals'])} siqnal · " + sla_sub
    cards.append(_kpi_card(
        label="Şikayət həlli (SLA)",
        value=("—" if sla.get("value") is None else f"{_esc(sla['value'])}%"),
        sub=sla_sub,
        badge=_source_badge(sla.get("source", "ƏLÇATMAZ")),
        accent="#159C8C"))  # teal accent for the CX pillar

    # Work panel — category chips from the real job queue.
    from .impact_ledger import _CATEGORY_AZ  # label map (single source)
    chips = "".join(
        f'<span class="chip">{_esc(_CATEGORY_AZ.get(c, c))} <b>{n}</b></span>'
        for c, n in (w.get("by_category") or {}).items() if n)

    sources = sc.get("sources", {}) or {}
    honesty = ""
    if "DEMO" in sources.values() or "ƏLÇATMAZ" in sources.values():
        honesty = ('<p class="note">ⓘ Bəzi mənbələr <b>DEMO/ƏLÇATMAZ</b> vəziyyətdədir — '
                   'canlı konnektor qoşulan kimi rəqəmlər avtomatik doğrulanır. '
                   'Bu hesabatda heç bir rəqəm uydurulmur.</p>')

    generated = _dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    headline = _esc(sc.get("headline", ""))

    return f"""<!DOCTYPE html>
<html lang="az">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Xalq Təsir Jurnalı — {month}</title>
<style>
  @page {{ size: A4; margin: 16mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family:'Segoe UI',system-ui,-apple-system,sans-serif; color:#202733;
          background:#eef0f3; margin:0; padding:28px; line-height:1.5; }}
  .sheet {{ max-width:840px; margin:0 auto; background:#fff; border-radius:16px;
            overflow:hidden; box-shadow:0 10px 40px rgba(20,25,35,.12); }}
  .hero {{ background:linear-gradient(135deg,#232a36,#161b24); color:#fff;
           padding:28px 40px; border-top:6px solid #DA1A32; }}
  .hero .kicker {{ color:#ff5a6e; font-size:12px; font-weight:700; letter-spacing:.18em;
                   text-transform:uppercase; margin:0 0 6px; }}
  .hero h1 {{ margin:0; font-size:30px; letter-spacing:.5px; }}
  .hero .month {{ margin:4px 0 0; color:#aeb8c7; font-size:15px; }}
  .hero .headline {{ margin:16px 0 0; font-size:17px; font-weight:600; color:#fff;
                     border-left:3px solid #DA1A32; padding-left:14px; }}
  .body {{ padding:22px 40px 24px; }}
  .eyebrow {{ font-size:12px; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
              color:#8a94a6; margin:0 0 12px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  .card {{ border:1px solid #e7eaef; border-radius:12px; padding:15px 16px 14px;
           position:relative; background:#fcfcfd; }}
  .card::before {{ content:""; position:absolute; left:0; top:14px; bottom:14px; width:4px;
                   border-radius:4px; background:var(--accent,#DA1A32); }}
  .card {{ padding-left:24px; }}
  .card-label {{ font-size:13px; color:#5c6675; font-weight:600; }}
  .card-value {{ font-size:30px; font-weight:800; color:#1a2130; line-height:1.1; margin:5px 0 2px; }}
  .card-meta {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; min-height:22px; }}
  .card-sub {{ font-size:12px; color:#8a94a6; margin-top:6px; }}
  .badge {{ font-size:11px; font-weight:700; padding:2px 8px; border-radius:20px;
            letter-spacing:.04em; }}
  .badge.live {{ background:#e5f6ec; color:#1a7f43; }}
  .badge.demo {{ background:#fef3d8; color:#9a6a00; }}
  .badge.down {{ background:#eceef1; color:#727c8c; }}
  .delta {{ font-size:12px; font-weight:700; padding:2px 8px; border-radius:20px; }}
  .delta.good {{ background:#e5f6ec; color:#1a7f43; }}
  .delta.warn {{ background:#fdeaea; color:#b3261e; }}
  .work {{ margin-top:20px; background:#f7f8fa; border:1px solid #e7eaef; border-radius:12px;
           padding:16px 20px; }}
  .work-row {{ display:flex; gap:30px; flex-wrap:wrap; }}
  .stat b {{ display:block; font-size:28px; font-weight:800; color:#1a2130; }}
  .stat span {{ font-size:12px; color:#8a94a6; }}
  .chips {{ margin-top:14px; display:flex; gap:8px; flex-wrap:wrap; }}
  .chip {{ font-size:12px; background:#fff; border:1px solid #e2e6ec; border-radius:20px;
           padding:4px 11px; color:#5c6675; }}
  .chip b {{ color:#DA1A32; }}
  .note {{ margin:16px 0 0; font-size:12px; color:#6b7482; background:#f4f6f9;
           border-radius:10px; padding:11px 14px; }}
  footer {{ text-align:center; font-size:11px; color:#9aa3b2; padding:14px 40px 18px;
            border-top:1px solid #eef0f3; }}
  footer b {{ color:#DA1A32; }}
  @media print {{ body {{ background:#fff; padding:0; }} .sheet {{ box-shadow:none; border-radius:0; }} }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="hero">
      <p class="kicker">Xalq Sığorta · RAMIN OS</p>
      <h1>Təsir Jurnalı</h1>
      <p class="month">{month} — aylıq nəticə və iş göstəriciləri</p>
      <p class="headline">{headline}</p>
    </div>
    <div class="body">
      <p class="eyebrow">Nəticə (biznes göstəriciləri)</p>
      <div class="grid">{''.join(cards)}</div>

      <div class="work">
        <p class="eyebrow">İş — sistem bu ay nə etdi</p>
        <div class="work-row">
          <div class="stat"><b>{_esc(w.get('deliverables', 0))}</b><span>Hazır deliverable</span></div>
          <div class="stat"><b>{_esc(w.get('requests_answered', 0))}</b><span>Cavablanan iş</span></div>
          <div class="stat"><b>~{_esc(w.get('hours_saved_est', 0))}</b><span>Təxmini qənaət (saat)</span></div>
        </div>
        <div class="chips">{chips}</div>
      </div>
      {honesty}
    </div>
    <footer>RAMIN OS tərəfindən avtomatik hazırlandı · {generated} · rəqəmlər canlı mənbələrdən, uydurma yoxdur · <b>bir adam, bir komandanın işi</b></footer>
  </div>
</body>
</html>"""


def _to_pdf(html_path: Path) -> Path | None:
    """Headless Edge — the proven PDF path on the locked-down machine (mirrors
    seo/render.py._to_pdf so the whole OS shares one PDF converter)."""
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


def save(sc: dict, *, to_pdf: bool = False, out_dir: Path | None = None) -> Path:
    """Render the scorecard to output/impact/impact-<month>.html (+ .pdf if asked).
    Returns the HTML path (the leadership artifact)."""
    out_dir = out_dir or (_ROOT / "output" / "impact")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"impact-{sc.get('month', 'latest')}.html"
    path.write_text(render_html(sc), encoding="utf-8")
    if to_pdf:
        _to_pdf(path)  # best-effort; HTML is the guaranteed artifact
    return path
