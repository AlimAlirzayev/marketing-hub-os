"""Daily executive briefing for Xalq Insurance Digital OS.

Collects REAL data from the systems running in this workspace and renders an
honest Azerbaijani leadership report:

- Customer complaints / reputation: cx-command-center SQLite + analytics.
- Paid media / sales signals: ads-studio Meta connector (Graph API, live).

Hard rule (see claude-agents/.claude/commands/briefing.md): if a data source
is unavailable or still in demo mode, the report says so explicitly instead
of inventing numbers. Every section carries a source-status label.

Usage:
    python scripts/daily_briefing.py            # print + save report
    python scripts/daily_briefing.py --no-save  # print only

Collectors run as subprocesses with cwd set to each app directory because
cx-command-center and ads-studio both use flat top-level module names
(config, store) that would collide in a single interpreter.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway._bootstrap import load_env  # noqa: E402

load_env()

CX_DIR = REPO_ROOT / "cx-command-center"
ADS_DIR = REPO_ROOT / "ads-studio"
GA4_DIR = REPO_ROOT / "ga4-studio"
OUT_DIR = REPO_ROOT / "output" / "briefings"

CX_COLLECTOR = r"""
import json, os, sys
try:
    import analytics
    last24h = analytics.build_report(days=1)
    last7d = analytics.build_report(days=7)
    brief = analytics.executive_brief(last7d)
    print(json.dumps({
        "status": "ok",
        "mode": os.getenv("CX_DATA_MODE", "demo").lower(),
        "last24h": last24h,
        "last7d": last7d,
        "brief": brief,
    }, default=str))
except Exception as exc:
    print(json.dumps({"status": "error", "detail": f"{type(exc).__name__}: {exc}"}))
"""

ADS_COLLECTOR = r"""
import json
from datetime import date
try:
    import config
    out = {
        "status": "ok",
        "mode": config.DATA_MODE,
        "account": config.DEFAULT_ACCOUNT_ID,
    }
    if config.DATA_MODE == "live":
        from connectors import meta
        ym = date.today().strftime("%Y-%m")
        rep = meta.build_report(ym)
        out["currency"] = rep["account"]["currency"]
        out["account_name"] = rep["account"]["name"]
        out["daily"] = rep["daily"][-3:]
        out["month_totals"] = rep["combined_totals"]
        out["by_platform"] = rep["by_platform"]
        out["campaigns"] = meta.top_campaigns(ym, limit=10)
    print(json.dumps(out, default=str))
except Exception as exc:
    print(json.dumps({"status": "error", "detail": f"{type(exc).__name__}: {exc}"}))
"""

GA4_COLLECTOR = r"""
import json
try:
    import config, connectors, analytics
    start, end = config.default_range(7)
    r = analytics.enrich(connectors.get_report(start, end))
    t = r["totals"]
    print(json.dumps({
        "status": "ok",
        "mode": r["mode"],
        "property": r.get("property"),
        "range": r["range"]["label"],
        "totals": t,
        "deltas": {k: r["deltas"][k]["delta_pct"]
                   for k in ("sessions", "users", "conversions", "conversion_rate")},
        "channels": [{"channel": c["channel"], "channel_az": c["channel_az"],
                      "sessions": c["sessions"], "share": c["share"],
                      "conversion_rate": c["conversion_rate"]} for c in r["channels"][:6]],
        "top_pages": [{"page": p["page"], "title": p["title"], "views": p["views"],
                       "avg_engagement_sec": p["avg_engagement_sec"]} for p in r["top_pages"][:5]],
        "funnel": r["funnel"],
        "insights": r["insights"][:4],
    }, default=str))
except Exception as exc:
    print(json.dumps({"status": "error", "detail": f"{type(exc).__name__}: {exc}"}))
"""


GSC_COLLECTOR = r"""
import json
try:
    from seo import config as scfg
    from seo.connectors import gsc
    days = 7
    totals = gsc.query(days=days, dimension="date", row_limit=10)   # true 7d totals
    q = gsc.top_queries(days=days, limit=100)   # wide pool: brand terms rank #1, opportunities sit deeper
    p = gsc.top_pages(days=days, limit=5)
    err = totals.error or q.error or p.error
    tot_c, tot_i = totals.total_clicks, totals.total_impressions
    imps = sum(r.impressions for r in q.rows) or 1
    avg_pos = round(sum(r.position * r.impressions for r in q.rows) / imps, 1) if q.rows else 0.0
    # SEO opportunity = lots of impressions but off page 1 (position > 10): a term
    # people search, we show for, but rank too low to win the click. Ranked by impressions.
    opp = sorted([r for r in q.rows if r.impressions >= 150 and r.position > 10],
                 key=lambda r: r.impressions, reverse=True)[:5]
    print(json.dumps({
        "status": "ok" if not err else "error",
        "mode": totals.mode,
        "site": scfg.GSC_SITE_URL,
        "range": totals.start + " → " + totals.end,
        "totals": {"clicks": tot_c, "impressions": tot_i,
                   "ctr": round(tot_c / tot_i, 4) if tot_i else 0.0, "position": avg_pos},
        "top_queries": [{"query": r.key, "clicks": r.clicks, "impressions": r.impressions,
                         "ctr": r.ctr, "position": r.position} for r in q.rows[:10]],
        "opportunities": [{"query": r.key, "clicks": r.clicks, "impressions": r.impressions,
                           "ctr": r.ctr, "position": r.position} for r in opp],
        "top_pages": [{"page": r.key, "clicks": r.clicks, "impressions": r.impressions,
                       "position": r.position} for r in p.rows[:5]],
        "detail": err or "",
    }, default=str))
except Exception as exc:
    print(json.dumps({"status": "error", "detail": f"{type(exc).__name__}: {exc}"}))
"""


def collect_ga4() -> dict:
    """Run the GA4 website-analytics collector (7-day window) in its own cwd."""
    return _collect("ga4", GA4_DIR, GA4_COLLECTOR, timeout=60)


def collect_gsc() -> dict:
    """Run the Google Search Console collector (7-day window). Runs from the repo
    root with the root venv because `seo` is a top-level package (not an app dir)."""
    return _collect("gsc", REPO_ROOT, GSC_COLLECTOR, timeout=60)


def collect_all() -> tuple[dict, dict]:
    """Run both collectors and return the raw (cx, ads) structured payloads.

    Importable entry point for the dashboard so the Streamlit panel and the CLI
    share one source of truth. Collectors run in their own cwd as subprocesses
    because cx-command-center and ads-studio both expose flat module names
    (config, store) that would collide in a single interpreter.
    """
    cx = _collect("cx", CX_DIR, CX_COLLECTOR, timeout=30)
    ads = _collect("ads", ADS_DIR, ADS_COLLECTOR, timeout=120)
    return cx, ads


def _app_python(cwd: Path) -> str:
    """Each app's collector runs with that app's own venv when it has one, so
    the briefing works no matter which service imports us (ads-studio serves
    it now; the CLI and tests use the root venv)."""
    for candidate in (cwd / ".venv" / "Scripts" / "python.exe",
                      cwd / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _collect(name: str, cwd: Path, code: str, timeout: int) -> dict:
    try:
        proc = subprocess.run(
            [_app_python(cwd), "-c", code],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": f"{name} collector timed out after {timeout}s"}
    raw = (proc.stdout or "").strip()
    if not raw:
        return {"status": "error", "detail": (proc.stderr or "empty collector output").strip()[:800]}
    try:
        return json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError:
        return {"status": "error", "detail": f"unparseable collector output: {raw[:400]}"}


# ---------------------------------------------------------------------------
# Rendering (report text is Azerbaijani: the audience is leadership)
# ---------------------------------------------------------------------------

MODE_LABEL = {
    "live": "CANLI",
    "demo": "DEMO",
    "error": "ƏLÇATMAZ",
}


def _fmt(n, digits: int = 0) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):,.{digits}f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def _source_status(cx: dict, ads: dict, ga4: dict | None = None, gsc: dict | None = None) -> list[str]:
    rows = [
        "| Mənbə | Status | Qeyd |",
        "|---|---|---|",
    ]
    cx_mode = cx.get("mode", "error") if cx.get("status") == "ok" else "error"
    cx_note = {
        "live": "Real kanal webhookları aktivdir.",
        "demo": "Bazadakı siqnallar test datasıdır — real kanallar hələ qoşulmayıb.",
        "error": cx.get("detail", "naməlum xəta"),
    }[cx_mode]
    rows.append(f"| CX Command Center (şikayətlər) | **{MODE_LABEL[cx_mode]}** | {cx_note} |")

    ads_mode = ads.get("mode", "error") if ads.get("status") == "ok" else "error"
    ads_note = {
        "live": f"Meta Graph API, hesab {ads.get('account', '?')}.",
        "demo": "Token/hesab qoşulmayıb, demo rejim.",
        "error": ads.get("detail", "naməlum xəta"),
    }.get(ads_mode, "")
    rows.append(f"| Meta Ads (ads-studio) | **{MODE_LABEL.get(ads_mode, ads_mode)}** | {ads_note} |")

    if ga4 is not None:
        ga4_mode = ga4.get("mode", "error") if ga4.get("status") == "ok" else "error"
        ga4_note = {
            "live": f"GA4 Data API, property {ga4.get('property', '?')}.",
            "demo": "GA4 service-account qoşulmayıb (GA4_PROPERTY_ID + JSON), demo rejim.",
            "error": ga4.get("detail", "naməlum xəta"),
        }.get(ga4_mode, "")
        rows.append(f"| Vebsayt analitikası (GA4) | **{MODE_LABEL.get(ga4_mode, ga4_mode)}** | {ga4_note} |")

    if gsc is not None:
        gsc_mode = gsc.get("mode", "error") if gsc.get("status") == "ok" else "error"
        gsc_note = {
            "live": f"Search Console API, sayt {gsc.get('site', '?')}.",
            "demo": "GSC service-account / sayt qoşulmayıb (GSC_SITE_URL), demo rejim.",
            "error": gsc.get("detail", "naməlum xəta"),
        }.get(gsc_mode, "")
        rows.append(f"| Axtarış görünürlüyü (Search Console) | **{MODE_LABEL.get(gsc_mode, gsc_mode)}** | {gsc_note} |")

    rows.append(
        "| Sosial dinləmə (TikTok/forumlar) | **QISMƏN** | "
        "YouTube brend-axtarışı CX-ə qoşulub; TikTok/forumlar hələ yox. |"
    )
    rows.append(
        "| Google Reviews | **QOŞULMAYIB** | "
        "GBP rəyləri sahib-OAuth + Google API təsdiqi (kvota 0→300) tələb edir — "
        "kod hazırdır (`cx-command-center/GBP_SETUP.md`), təsdiq gözlənilir. |"
    )
    return rows


def _complaints_section(cx: dict) -> list[str]:
    if cx.get("status") != "ok":
        return [
            "## 1. Müştəri şikayətləri — [MƏNBƏ ƏLÇATMAZ]",
            "",
            f"CX Command Center oxuna bilmədi: `{cx.get('detail', '?')}`. "
            "Bu bölmə üçün rəqəm təqdim edilmir.",
        ]
    mode = MODE_LABEL[cx.get("mode", "demo")]
    t24 = cx["last24h"]["totals"]
    t7 = cx["last7d"]["totals"]
    lines = [
        f"## 1. Müştəri şikayətləri — [{mode}]",
        "",
    ]
    if cx.get("mode") == "demo":
        lines.append(
            "> ⚠ Bu rəqəmlər **test datasıdır** (CX_DATA_MODE=demo). Real şikayət axını "
            "üçün Chatplace/Meta webhookları qoşulmalıdır. Aşağıdakılar yalnız sistemin "
            "işlədiyini göstərir, real müştəri vəziyyətini yox."
        )
        lines.append("")
    lines += [
        f"- Son 24 saat: **{t24['messages']} siqnal** "
        f"({t24['open']} açıq, {t24['critical_open']} kritik, {t24['overdue']} SLA gecikməsi)",
        f"- Son 7 gün: {t7['messages']} siqnal, həll faizi {t7['resolution_rate']}%, "
        f"orta reytinq {t7['avg_rating'] if t7['avg_rating'] is not None else '—'}",
    ]
    channels = cx["last7d"]["breakdowns"]["channel"][:5]
    if channels:
        ch = ", ".join(f"{c['key']} ({c['count']})" for c in channels)
        lines.append(f"- Kanallar (7 gün): {ch}")
    causes = cx["last7d"]["root_causes"][:3]
    if causes:
        rc = ", ".join(f"{c['category']} ({c['count']} → {c['team']})" for c in causes)
        lines.append(f"- Əsas səbəblər: {rc}")
    return lines


def _reputation_section(cx: dict) -> list[str]:
    if cx.get("status") != "ok":
        return [
            "## 2. Reputasiya riski — [MƏNBƏ ƏLÇATMAZ]",
            "",
            "CX datası olmadan risk qiymətləndirilmir.",
        ]
    mode = MODE_LABEL[cx.get("mode", "demo")]
    brief = cx["brief"]
    t7 = cx["last7d"]["totals"]
    level_az = {"red": "QIRMIZI", "amber": "SARI", "green": "YAŞIL"}.get(brief["level"], brief["level"])
    lines = [
        f"## 2. Reputasiya riski — [{mode}]",
        "",
        f"- Risk indeksi (CX modeli): **{t7['risk_score']}/100** — səviyyə **{level_az}**",
        f"- Neqativ siqnal (7 gün): {t7['negative']} / {t7['messages']}",
        f"- Sistemin öz icmalı: {brief['text']}",
    ]
    if cx.get("mode") == "demo":
        lines.append(
            "- ⚠ Demo data üzərində hesablanıb — real reputasiya riski üçün Google "
            "Reviews sync və Meta webhookları qoşulmalıdır."
        )
    return lines


def _sales_section(ads: dict) -> list[str]:
    if ads.get("status") != "ok":
        return [
            "## 3. Satış fürsətləri / Paid media — [MƏNBƏ ƏLÇATMAZ]",
            "",
            f"Meta connector xətası: `{ads.get('detail', '?')}`. Rəqəm təqdim edilmir.",
        ]
    if ads.get("mode") != "live":
        return [
            "## 3. Satış fürsətləri / Paid media — [DEMO]",
            "",
            "Meta hesabı qoşulmayıb; bu bölmə üçün real data yoxdur.",
        ]
    cur = ads.get("currency", "AZN")
    mt = ads["month_totals"]
    lines = [
        "## 3. Satış fürsətləri / Paid media — [CANLI]",
        "",
        f"Hesab: {ads.get('account_name', ads.get('account'))} ({ads.get('account')})",
        "",
        f"- Bu ay cəmi: xərc **{_fmt(mt.get('spend'), 2)} {cur}**, "
        f"{_fmt(mt.get('impressions'))} göstərim, {_fmt(mt.get('clicks'))} klik, "
        f"{_fmt(mt.get('leads'))} lead, {_fmt(mt.get('messages'))} mesaj",
    ]
    daily = ads.get("daily") or []
    for row in daily[-2:]:
        lines.append(
            f"- {row.get('date')}: xərc {_fmt(row.get('spend'), 2)} {cur}, "
            f"klik {_fmt(row.get('clicks'))}, lead {_fmt(row.get('leads'))}, "
            f"mesaj {_fmt(row.get('messages'))}"
        )
    campaigns = ads.get("campaigns") or []
    active = [c for c in campaigns if float(c.get("spend") or 0) > 0]
    if active:
        lines.append("")
        lines.append("Aktiv kampaniyalar (bu ay, xərcə görə):")
        for c in active[:5]:
            lines.append(
                f"- {c['campaign_name']}: {_fmt(c.get('spend'), 2)} {cur}, "
                f"CTR {_fmt(c.get('ctr'), 2)}%, lead {_fmt(c.get('leads'))}, "
                f"mesaj {_fmt(c.get('messages'))}"
            )
    else:
        lines.append("")
        lines.append(
            "- **Bu ay heç bir kampaniya xərc etməyib** — hesabda aktiv çatdırılma yoxdur. "
            "Hazır draft varsa, yayımlanmaması birbaşa itirilmiş fürsətdir."
        )
    return lines


def _website_section(ga4: dict) -> list[str]:
    if ga4.get("status") != "ok":
        return [
            "## 4. Vebsayt davranışı (GA4) — [MƏNBƏ ƏLÇATMAZ]",
            "",
            f"GA4 oxuna bilmədi: `{ga4.get('detail', '?')}`. Rəqəm təqdim edilmir.",
        ]
    mode = MODE_LABEL.get(ga4.get("mode", "demo"), "DEMO")
    t = ga4["totals"]
    d = ga4.get("deltas", {})

    def darrow(key):
        v = d.get(key)
        return f" ({v:+.1f}%)" if isinstance(v, (int, float)) else ""

    lines = [f"## 4. Vebsayt davranışı (GA4) — [{mode}]", ""]
    if ga4.get("mode") == "demo":
        lines += [
            "> ⚠ Bu rəqəmlər **sintetik demo datasıdır** (GA4 service-account hələ "
            "qoşulmayıb). Yalnız sistemin işlədiyini göstərir, real sayt trafikini yox.",
            "",
        ]
    lines += [
        f"- Son 7 gün ({ga4.get('range', '')}): **{_fmt(t['sessions'])} sessiya**"
        f"{darrow('sessions')}, {_fmt(t['users'])} istifadəçi, "
        f"**{_fmt(t['conversions'])} konversiya**{darrow('conversions')}",
        f"- Konversiya nisbəti: {t['conversion_rate']*100:.2f}%{darrow('conversion_rate')}; "
        f"cəlb nisbəti {t['engagement_rate']*100:.0f}%; orta cəlb {t['avg_engagement_sec']} san",
    ]
    channels = ga4.get("channels") or []
    if channels:
        ch = ", ".join(f"{c['channel_az']} {c['share']*100:.0f}%"
                       f" ({c['conversion_rate']*100:.1f}% konv)" for c in channels[:4])
        lines.append(f"- Kanallar: {ch}")
    # The funnel: where website visitors leak
    funnel = ga4.get("funnel") or []
    if len(funnel) >= 3:
        lines.append(f"- Funnel: {_fmt(funnel[0]['value'])} sessiya → "
                     f"{_fmt(funnel[1]['value'])} cəlb → {_fmt(funnel[2]['value'])} konversiya "
                     f"(son addımda {funnel[2]['drop_from_prev']}% itki)")
    for ins in (ga4.get("insights") or [])[:2]:
        lines.append(f"- {ins.get('icon', '•')} {ins.get('text', '')}")
    return lines


def _search_section(gsc: dict) -> list[str]:
    if gsc.get("status") != "ok":
        return [
            "## 4b. Axtarış görünürlüyü (Search Console) — [MƏNBƏ ƏLÇATMAZ]",
            "",
            f"GSC oxuna bilmədi: `{gsc.get('detail', '?')}`. Rəqəm təqdim edilmir.",
        ]
    mode = MODE_LABEL.get(gsc.get("mode", "demo"), "DEMO")
    t = gsc.get("totals", {})
    lines = [f"## 4b. Axtarış görünürlüyü (Search Console) — [{mode}]", ""]
    if gsc.get("mode") == "demo":
        lines += [
            "> ⚠ Bu rəqəmlər **sintetik demo datasıdır** (GSC hələ qoşulmayıb). "
            "Yalnız sistemin işlədiyini göstərir, real axtarış datasını yox.",
            "",
        ]
    lines += [
        f"- Son 7 gün ({gsc.get('range', '')}): **{_fmt(t.get('clicks'))} klik**, "
        f"{_fmt(t.get('impressions'))} göstərim, "
        f"CTR {float(t.get('ctr') or 0)*100:.1f}%, orta mövqe {_fmt(t.get('position'), 1)}",
    ]
    tq = gsc.get("top_queries") or []
    if tq:
        top = ", ".join(f"{q['query']} ({q['clicks']} klik, möv {_fmt(q['position'],1)})"
                        for q in tq[:5])
        lines.append(f"- Ən çox klik gətirən sorğular: {top}")
    # High-impression, off-page-1 queries = the concrete SEO opportunity
    opp = gsc.get("opportunities") or []
    if opp:
        o = ", ".join(f"{q['query']} (möv {_fmt(q['position'],1)}, {_fmt(q['impressions'])} göstərim)"
                      for q in opp[:3])
        lines.append(f"- 🎯 Fürsət (çox göstərim, 1-ci səhifədən kənar): {o}")
    tp = gsc.get("top_pages") or []
    if tp:
        pg = ", ".join(f"{p['page'].replace('https://www.xalqsigorta.az', '') or '/'} ({p['clicks']})"
                       for p in tp[:3])
        lines.append(f"- Ən güclü səhifələr: {pg}")
    return lines


def _crosschannel_note(ads: dict, ga4: dict) -> list[str]:
    """Cross-tool reconciliation — only when BOTH sides are live (real numbers).
    Honest: in demo the two datasets are unrelated, so we don't fake a link."""
    if not (ads.get("status") == "ok" and ads.get("mode") == "live"
            and ga4.get("status") == "ok" and ga4.get("mode") == "live"):
        return []
    paid = next((c for c in (ga4.get("channels") or [])
                 if c["channel"] in ("Paid Social", "Paid Search")), None)
    mt = ads.get("month_totals") or {}
    lines = ["", "**Kanallararası uzlaşdırma (canlı):**"]
    if paid:
        lines.append(
            f"- Meta hesabatı bu ay {_fmt(mt.get('clicks'))} klik göstərir; GA4 "
            f"ödənişli kanaldan {_fmt(paid['sessions'])} sessiya qeydə alıb — fərq "
            "tracking/landing itkisini göstərir.")
    lines.append(
        f"- Meta lead: {_fmt(mt.get('leads'))} · GA4 sayt konversiyası: "
        f"{_fmt((ga4.get('totals') or {}).get('conversions'))} — ikisini tutuşdur.")
    return lines


def _social_section(cx: dict, ads: dict) -> list[str]:
    lines = [
        "## 5. Sosial media siqnalları — [QİSMƏN]",
        "",
        "Ayrıca sosial dinləmə aləti qoşulmayıb. Görünən siqnallar yalnız bunlardır:",
    ]
    if cx.get("status") == "ok":
        social = [
            c for c in cx["last7d"]["breakdowns"]["channel"]
            if any(s in c["key"] for s in ("facebook", "instagram", "telegram", "whatsapp", "web"))
        ]
        if social:
            label = " (demo)" if cx.get("mode") == "demo" else ""
            ch = ", ".join(f"{c['key']} ({c['count']})" for c in social)
            lines.append(f"- CX-ə daxil olan sosial siqnallar{label}: {ch}")
    if ads.get("status") == "ok" and ads.get("mode") == "live":
        bp = ads.get("by_platform") or {}
        parts = []
        for key in ("facebook", "instagram", "messenger"):
            p = bp.get(key) or {}
            if float(p.get("impressions") or 0) > 0:
                parts.append(f"{key}: {_fmt(p.get('impressions'))} göstərim / {_fmt(p.get('clicks'))} klik")
        if parts:
            lines.append(f"- Meta platforma bölgüsü (bu ay, canlı): {'; '.join(parts)}")
        else:
            lines.append("- Meta platformalarında bu ay aktiv göstərim yoxdur (canlı).")
    lines.append(
        "- TikTok, forumlar, rəqib fəaliyyəti: **data yoxdur** — qiymətləndirmə verilmir."
    )
    return lines


def build_actions(cx: dict, ads: dict, ga4: dict | None = None, gsc: dict | None = None) -> list[str]:
    """Derive the top data-driven priority actions. Pure list of action strings
    so both the CLI report and the dashboard can render them. ``ga4``/``gsc`` are
    optional so existing callers (the Streamlit panel) keep working unchanged."""
    actions: list[str] = []

    cx_ok = cx.get("status") == "ok"
    cx_demo = cx_ok and cx.get("mode") == "demo"
    if cx_demo:
        actions.append(
            "**CX-i canlıya keçir:** Chatplace webhook + Meta webhook + GBP sync qoşulsun "
            "(`cx-command-center/INTEGRATIONS.md`). Bu olmadan şikayət/reputasiya bölmələri kor qalır."
        )
    if cx_ok:
        t = cx["last7d"]["totals"]
        if t["overdue"]:
            actions.append(
                f"**SLA bərpası:** {t['overdue']} gecikmiş müraciət var — bu gün cavablandırılsın"
                + (" (demo data)." if cx_demo else ".")
            )
        if t["critical_open"]:
            actions.append(
                f"**Kritik hallar:** {t['critical_open']} açıq kritik şikayət — komanda rəhbərinə eskalasiya"
                + (" (demo data)." if cx_demo else ".")
            )
    else:
        actions.append("**CX kollektorunu düzəlt:** şikayət mənbəyi oxunmur — səbəb hesabatın mənbə cədvəlindədir.")

    if ads.get("status") == "ok" and ads.get("mode") == "live":
        campaigns = ads.get("campaigns") or []
        spend = float((ads.get("month_totals") or {}).get("spend") or 0)
        if spend == 0:
            actions.append(
                "**Meta çatdırılmasını başlat:** hesab canlıdır, amma bu ay xərc 0-dır — "
                "KASKO Bayram draftı Ads Manager-də yayımlanmalı və ya səbəb sənədləşməlidir."
            )
        else:
            low_ctr = [c for c in campaigns if float(c.get("spend") or 0) > 0 and float(c.get("ctr") or 0) < 0.5]
            if low_ctr:
                names = ", ".join(c["campaign_name"] for c in low_ctr[:3])
                actions.append(f"**Aşağı CTR kampaniyaları yoxla:** {names} — kreativ yenilənməsi lazımdır.")
    else:
        actions.append("**Meta connector-u bərpa et:** paid media datası çəkilmir.")

    if ga4 is not None:
        if ga4.get("status") == "ok" and ga4.get("mode") == "demo":
            actions.append(
                "**GA4-ü canlıya qoş:** service-account + GA4_PROPERTY_ID (`ga4-studio/README.md`). "
                "Bu olmadan sayt davranışı/funnel demo qalır — Meta xərcinin saytda nəyə "
                "çevrildiyi görünmür."
            )
        elif ga4.get("status") == "ok" and ga4.get("mode") == "live":
            pages = ga4.get("top_pages") or []
            leak = min((p for p in pages if p["views"] > 0),
                       key=lambda p: p["avg_engagement_sec"], default=None)
            if leak and leak["avg_engagement_sec"] < 30:
                actions.append(
                    f"**Sayt sızması (GA4):** “{leak['title'] or leak['page']}” səhifəsində "
                    f"orta cəlb {leak['avg_engagement_sec']} san — landing/məzmun optimallaşdırılsın."
                )
        elif ga4.get("status") != "ok":
            actions.append("**GA4 kollektorunu düzəlt:** vebsayt datası oxunmur — səbəb mənbə cədvəlindədir.")

    if gsc is not None and gsc.get("status") == "ok" and gsc.get("mode") == "live":
        opp = gsc.get("opportunities") or []
        if opp:
            q0 = opp[0]
            actions.append(
                f"**SEO fürsəti (Search Console, canlı):** “{q0['query']}” sorğusu "
                f"{_fmt(q0['impressions'])} göstərim alır, amma orta mövqe {_fmt(q0['position'],1)} — "
                "hədəf səhifə optimallaşdırılsa 1-ci səhifəyə çıxa bilər (real klik qazancı)."
            )
    elif gsc is not None and gsc.get("status") == "ok" and gsc.get("mode") == "demo":
        actions.append(
            "**Search Console-u canlıya qoş:** service-account Search Console-a əlavə edilsin + "
            "`GSC_SITE_URL` (`seo/config.py`). Bu olmadan axtarış görünürlüyü demo qalır."
        )

    actions.append(
        "**Google Reviews-u qoş:** GBP OAuth (business.manage) + Google API təsdiqi tamamlansın "
        "(`cx-command-center/GBP_SETUP.md`) — reputasiya üçün yeganə müstəqil kənar mənbədir."
    )
    actions.append(
        "**Sosial dinləmə boşluğu:** TikTok/forum monitorinqi üçün mənbə seçilsin "
        "(n8n scheduled scraping → CX `/api/ingest`), yoxsa 5-ci bölmə həmişə kor qalacaq."
    )

    return actions[:6]


def _actions_section(cx: dict, ads: dict, ga4: dict | None = None, gsc: dict | None = None) -> list[str]:
    lines = ["## 6. Prioritet addımlar (data-əsaslı)", ""]
    for i, action in enumerate(build_actions(cx, ads, ga4, gsc), 1):
        lines.append(f"{i}. {action}")
    return lines


def build_view_model(cx: dict, ads: dict, ga4: dict | None = None, gsc: dict | None = None) -> dict:
    """Compact, display-ready payload for any UI (the hub home page consumes
    this as JSON). All business logic stays here in one place; the frontend is
    purely presentational and never recomputes or invents anything. ``ga4``/``gsc``
    are optional so existing callers keep working unchanged."""
    now = datetime.now(timezone.utc).astimezone()

    cx_ok = cx.get("status") == "ok"
    ads_ok = ads.get("status") == "ok"
    ga4_ok = bool(ga4) and ga4.get("status") == "ok"
    gsc_ok = bool(gsc) and gsc.get("status") == "ok"
    cx_mode = cx.get("mode", "error") if cx_ok else "error"
    ads_mode = ads.get("mode", "error") if ads_ok else "error"
    ga4_mode = ga4.get("mode", "error") if ga4_ok else "error"
    gsc_mode = gsc.get("mode", "error") if gsc_ok else "error"

    def kind(mode: str) -> str:
        return {"live": "live", "demo": "demo"}.get(mode, "error")

    sources = [
        {"key": "cx", "label": "Müştəri / Şikayətlər", "status": kind(cx_mode)},
        {"key": "ads", "label": "Meta Ads", "status": kind(ads_mode)},
    ]
    if ga4 is not None:
        sources.append({"key": "ga4", "label": "Vebsayt (GA4)", "status": kind(ga4_mode)})
    if gsc is not None:
        sources.append({"key": "gsc", "label": "Axtarış (Search Console)", "status": kind(gsc_mode)})
    sources += [
        {"key": "reviews", "label": "Google Reviews", "status": "missing"},
        {"key": "listening", "label": "Sosial dinləmə", "status": "missing"},
    ]

    kpis: list[dict] = []
    if cx_ok:
        t24 = cx["last24h"]["totals"]
        t7 = cx["last7d"]["totals"]
        sfx = " · demo" if cx_mode == "demo" else ""
        kpis.append({"label": "Şikayət (24s)", "value": t24["messages"],
                     "sub": f"{t7['messages']} / 7g{sfx}", "tone": "neutral"})
        kpis.append({"label": "Açıq / Kritik", "value": f"{t24['open']} / {t24['critical_open']}",
                     "sub": f"{t7['overdue']} SLA gecikmə", "tone": "warn" if t24["critical_open"] else "neutral"})
        kpis.append({"label": "Reputasiya riski", "value": f"{t7['risk_score']}/100",
                     "sub": cx["brief"]["title"], "tone": cx["brief"]["level"]})
    else:
        kpis.append({"label": "Şikayət (24s)", "value": "—", "sub": "əlçatmaz", "tone": "error"})

    if ads_ok and ads_mode == "live":
        mt = ads["month_totals"]
        cur = ads.get("currency", "AZN")
        kpis.append({"label": f"Meta xərc (ay, {cur})", "value": _fmt(mt.get("spend"), 2),
                     "sub": f"{_fmt(mt.get('leads'))} lead · {_fmt(mt.get('messages'))} mesaj", "tone": "neutral"})
    else:
        kpis.append({"label": "Meta xərc (ay)", "value": "—", "sub": "demo / əlçatmaz", "tone": "error"})

    if ga4_ok:
        gt = ga4["totals"]
        sfx = " · demo" if ga4_mode == "demo" else ""
        kpis.append({"label": "Sayt sessiya (7g)", "value": _fmt(gt["sessions"]),
                     "sub": f"{_fmt(gt['conversions'])} konversiya{sfx}",
                     "tone": "neutral"})
    elif ga4 is not None:
        kpis.append({"label": "Sayt sessiya (7g)", "value": "—", "sub": "demo / əlçatmaz", "tone": "error"})

    if gsc_ok:
        st = gsc.get("totals", {})
        sfx = " · demo" if gsc_mode == "demo" else ""
        kpis.append({"label": "Axtarış klik (7g)", "value": _fmt(st.get("clicks")),
                     "sub": f"{_fmt(st.get('impressions'))} göstərim · möv {_fmt(st.get('position'),1)}{sfx}",
                     "tone": "neutral"})
    elif gsc is not None:
        kpis.append({"label": "Axtarış klik (7g)", "value": "—", "sub": "demo / əlçatmaz", "tone": "error"})

    website = {"status": ga4_mode if ga4 is not None else "missing"}
    if ga4_ok:
        gt = ga4["totals"]
        website.update({
            "property": ga4.get("property"), "range": ga4.get("range"),
            "totals": {k: gt.get(k) for k in
                       ("sessions", "users", "conversions", "conversion_rate",
                        "engagement_rate", "avg_engagement_sec")},
            "deltas": ga4.get("deltas", {}),
            "channels": ga4.get("channels", [])[:6],
            "funnel": ga4.get("funnel", []),
            "top_pages": ga4.get("top_pages", [])[:5],
        })

    search = {"status": gsc_mode if gsc is not None else "missing"}
    if gsc_ok:
        search.update({
            "site": gsc.get("site"), "range": gsc.get("range"),
            "totals": gsc.get("totals", {}),
            "top_queries": (gsc.get("top_queries") or [])[:10],
            "opportunities": (gsc.get("opportunities") or [])[:5],
            "top_pages": (gsc.get("top_pages") or [])[:5],
        })

    complaints = {"status": cx_mode}
    reputation = {"status": cx_mode}
    if cx_ok:
        complaints["channels"] = cx["last7d"]["breakdowns"]["channel"][:6]
        complaints["causes"] = cx["last7d"]["root_causes"][:5]
        t7 = cx["last7d"]["totals"]
        reputation.update({
            "risk_score": t7["risk_score"], "level": cx["brief"]["level"],
            "title": cx["brief"]["title"], "text": cx["brief"]["text"],
            "negative": t7["negative"], "total": t7["messages"],
        })

    sales = {"status": ads_mode}
    social_platforms: list[dict] = []
    if ads_ok and ads_mode == "live":
        mt = ads["month_totals"]
        sales.update({
            "currency": ads.get("currency", "AZN"),
            "account": ads.get("account"), "account_name": ads.get("account_name"),
            "totals": {k: mt.get(k) for k in ("spend", "impressions", "clicks", "leads", "messages")},
            "daily": ads.get("daily") or [],
            "campaigns": [
                {"name": c["campaign_name"], "spend": c.get("spend"), "ctr": c.get("ctr"),
                 "leads": c.get("leads"), "messages": c.get("messages")}
                for c in (ads.get("campaigns") or []) if float(c.get("spend") or 0) > 0
            ][:8],
        })
        for key in ("facebook", "instagram", "messenger"):
            p = (ads.get("by_platform") or {}).get(key) or {}
            if float(p.get("impressions") or 0) > 0:
                social_platforms.append({"key": key, "impressions": p.get("impressions"), "clicks": p.get("clicks")})

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_label": now.strftime("%d.%m.%Y %H:%M"),
        "sources": sources,
        "kpis": kpis,
        "complaints": complaints,
        "reputation": reputation,
        "sales": sales,
        "website": website,
        "search": search,
        "social": {"platforms": social_platforms},
        "actions": build_actions(cx, ads, ga4, gsc),
        "markdown": render(cx, ads, ga4, gsc),
    }


def render(cx: dict, ads: dict, ga4: dict | None = None, gsc: dict | None = None) -> str:
    now = datetime.now(timezone.utc).astimezone()
    parts = [
        "# Xalq Sigorta — Gündəlik rəhbərlik hesabatı",
        "",
        f"**Tarix:** {now.strftime('%d.%m.%Y %H:%M %Z')} | **Dövr:** son 24 saat (kontekst: 7 gün)",
        "",
        "Bu hesabat yalnız qoşulmuş sistemlərdən oxunan real datanı göstərir. "
        "Data olmayan yerdə rəqəm uydurulmur — boşluq açıq qeyd olunur.",
        "",
        "## Mənbə statusu",
        "",
        *_source_status(cx, ads, ga4, gsc),
        "",
        *_complaints_section(cx),
        "",
        *_reputation_section(cx),
        "",
        *_sales_section(ads),
    ]
    if ga4 is not None:
        parts += ["", *_website_section(ga4), *_crosschannel_note(ads, ga4)]
    if gsc is not None:
        parts += ["", *_search_section(gsc)]
    parts += [
        "",
        *_social_section(cx, ads),
        "",
        *_actions_section(cx, ads, ga4, gsc),
        "",
        "---",
        f"_Generated by scripts/daily_briefing.py at {now.isoformat(timespec='seconds')}_",
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the daily executive briefing.")
    parser.add_argument("--no-save", action="store_true", help="print only, do not write a file")
    parser.add_argument("--json", action="store_true", help="emit the view-model as JSON (for the hub home page)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cx, ads = collect_all()
    ga4 = collect_ga4()
    gsc = collect_gsc()

    if args.json:
        print(json.dumps(build_view_model(cx, ads, ga4, gsc), ensure_ascii=False, default=str))
        return 0

    report = render(cx, ads, ga4, gsc)
    print(report)

    if not args.no_save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / f"briefing-{date.today().isoformat()}.md"
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[saved] {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
