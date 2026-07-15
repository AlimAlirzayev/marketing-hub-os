"""Ads Studio - FastAPI server.

Serves a single-page dashboard plus a JSON API. Heavy work (AI summary, segment
breakdowns) lives in lazy endpoints so the dashboard paints instantly and the
extras stream in as the user scrolls.

Run:
    uvicorn app:app --port 8800        (or use ./run.ps1)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from analytics import ai, analyze, segments as segm
from connectors import (
    get_creative_diagnostics,
    get_segments,
    get_top_campaigns,
    get_video_metrics,
)

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Ads Studio", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _available_months() -> list[dict]:
    now = config.today()
    y, m = now.year, now.month
    out = []
    for _ in range(config.HISTORY_MONTHS):
        ym = f"{y}-{m:02d}"
        out.append({"value": ym, "label": config.month_label(ym)})
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def _save_snapshot(report: dict) -> None:
    """Persist daily combined totals - your own historical record beats
    Meta's 37-month rolling window over time."""
    try:
        os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
        ym = report["period"]["month"]
        path = os.path.join(config.SNAPSHOT_DIR, f"{ym}.json")
        store = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                store = json.load(f)
        store[config.today().isoformat()] = report["combined_totals"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # snapshots are best-effort


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "dashboard.html"))


# --------------------------------------------------------------------------
# Gündəlik Rəhbərlik Hesabatı — migrated home from the 8501 Streamlit archive
# (2026-07-13). All numbers come from scripts/daily_briefing.py collectors;
# demo/unavailable sources are labelled, never invented.
# --------------------------------------------------------------------------
ROOT = os.path.dirname(BASE)
BRIEFINGS_DIR = os.path.join(ROOT, "output", "briefings")
_BRIEFING_TTL = 600  # seconds — same 10-min cache the old panel used
_briefing_cache: dict = {"at": 0.0, "vm": None}


def _briefing_vm(refresh: bool = False) -> dict:
    if (not refresh and _briefing_cache["vm"]
            and time.time() - _briefing_cache["at"] < _BRIEFING_TTL):
        return _briefing_cache["vm"]
    scripts_dir = os.path.join(ROOT, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import daily_briefing as briefing
    cx, ads_data = briefing.collect_all()
    ga4 = briefing.collect_ga4()
    vm = briefing.build_view_model(cx, ads_data, ga4)
    _briefing_cache.update(at=time.time(), vm=vm)
    return vm


@app.get("/briefing")
def briefing_page() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "briefing.html"))


@app.get("/api/briefing")
def briefing_api(refresh: int = 0) -> JSONResponse:
    try:
        return JSONResponse(_briefing_vm(bool(refresh)))
    except Exception as exc:  # collectors must never 500 the page
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)


@app.post("/api/briefing/save")
def briefing_save() -> JSONResponse:
    vm = _briefing_vm()
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    name = f"briefing-{date.today().isoformat()}.md"
    with open(os.path.join(BRIEFINGS_DIR, name), "w", encoding="utf-8") as f:
        f.write(vm["markdown"])
    return JSONResponse({"saved": name})


@app.get("/api/briefing/archive")
def briefing_archive() -> JSONResponse:
    if not os.path.isdir(BRIEFINGS_DIR):
        return JSONResponse([])
    names = sorted((n for n in os.listdir(BRIEFINGS_DIR)
                    if re.fullmatch(r"briefing-\d{4}-\d{2}-\d{2}\.md", n)), reverse=True)
    return JSONResponse(names)


@app.get("/api/briefing/archive/{name}")
def briefing_archive_item(name: str) -> PlainTextResponse:
    if not re.fullmatch(r"briefing-\d{4}-\d{2}-\d{2}\.md", name):
        return PlainTextResponse("bad name", status_code=400)
    path = os.path.join(BRIEFINGS_DIR, name)
    if not os.path.isfile(path):
        return PlainTextResponse("not found", status_code=404)
    with open(path, encoding="utf-8") as f:
        return PlainTextResponse(f.read())


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def _live_health() -> dict:
    """Probe the live Meta token once so the UI can surface 'token expired'
    immediately instead of quietly falling back to demo."""
    if config.DATA_MODE != "live":
        return {"ok": True, "mode": config.DATA_MODE}
    try:
        from connectors import meta as live_meta
        info = live_meta.account_info()
        return {"ok": True, "mode": "live", "account": info["name"], "currency": info["currency"]}
    except Exception as exc:
        msg = str(exc).lower()
        if "expired" in msg or "code\":190" in msg or "oauthexception" in msg:
            return {"ok": False, "mode": "live", "code": "token_expired",
                    "hint": "Meta token bitib. Graph API Explorer-də yenidən 'Generate Access Token' "
                             "basın, və ya daimi üçün System User token qurun."}
        return {"ok": False, "mode": "live", "code": "unknown",
                "hint": "Meta-ya bağlantı uğursuz oldu. Tokeni və ad account icazəsini yoxlayın.",
                "error": type(exc).__name__}


@app.get("/api/meta")
def meta() -> JSONResponse:
    """Static context the UI needs once: brand, months, accounts, suggestions."""
    return JSONResponse({
        "account": config.ACCOUNT_NAME,
        "tagline": config.ACCOUNT_TAGLINE,
        "currency_symbol": config.CURRENCY_SYMBOL,
        "data_mode": config.DATA_MODE,
        "brand": config.BRAND,
        "months": _available_months(),
        "accounts": config.AD_ACCOUNTS,
        "default_account": config.DEFAULT_ACCOUNT_ID,
        "suggested_questions": ai.SUGGESTED_QUESTIONS,
        "live": _live_health(),
    })


@app.get("/api/report")
def report(month: str, platform: str = "all",
            account: str | None = None,
            compare: str = "prev_month") -> JSONResponse:
    """Fast path: numbers, funnel, deltas, pacing, anomalies, insight,
    saturation, fatigue. AI summary is a separate slow call."""
    data = analyze(month, platform, account, with_ai_summary=False, compare_mode=compare)
    _save_snapshot(data["report"])
    return JSONResponse(data)


@app.get("/api/summary")
def summary(month: str, platform: str = "all",
             account: str | None = None,
             compare: str = "prev_month") -> JSONResponse:
    """Returns both the executive summary AND an AI-narrated 'insight of the
    day' so the dashboard can upgrade the rule-based insight in place."""
    from analytics import whats_changed
    data = analyze(month, platform, account, with_ai_summary=False, compare_mode=compare)
    s = ai.exec_summary(data["report"], data["analytics"])
    mode_label = data["analytics"]["comparison"]["label"]
    ai_insight = whats_changed.narrate(
        data["analytics"]["deltas"], mode_label, data["report"],
        data["analytics"]["anomalies"], use_ai=True)
    return JSONResponse({"summary": s, "insight": ai_insight})


@app.get("/report")
def board_report() -> FileResponse:
    """Print-optimized single-page board report (open in browser → Save as PDF)."""
    return FileResponse(os.path.join(BASE, "templates", "report.html"))


@app.get("/api/segments")
def segments_endpoint(month: str, account: str | None = None) -> JSONResponse:
    """Placement, position, device, age, gender, region, hourly + day-of-week."""
    raw = get_segments(month, account)
    # Day-of-week computed locally from the report's daily series.
    report_data = analyze(month, "all", account, with_ai_summary=False)["report"]
    dow = segm.day_of_week(report_data["daily"])
    return JSONResponse({
        "segments": raw,
        "day_of_week": dow,
        "callouts": {
            "best_hour": segm.best_worst(raw.get("hourly", []), "leads", "hour")
                if isinstance(raw.get("hourly"), list) else None,
            "best_placement": segm.best_worst(raw.get("placement", []), "leads", "key")
                if isinstance(raw.get("placement"), list) else None,
            "best_age": segm.best_worst(raw.get("age", []), "leads", "key")
                if isinstance(raw.get("age"), list) else None,
            "best_region": segm.best_worst(raw.get("region", []), "leads", "key")
                if isinstance(raw.get("region"), list) else None,
        },
    })


@app.get("/api/campaigns")
def campaigns_endpoint(month: str, account: str | None = None,
                        limit: int = 10) -> JSONResponse:
    return JSONResponse(get_top_campaigns(month, account, limit))


@app.get("/api/diagnostics")
def diagnostics_endpoint(month: str, account: str | None = None) -> JSONResponse:
    """Meta's Quality / Engagement / Conversion ranking + health roll-up."""
    ads = get_creative_diagnostics(month, account)
    return JSONResponse({
        "ads": ads,
        "health": segm.creative_health(ads),
    })


@app.get("/api/video")
def video_endpoint(month: str, account: str | None = None) -> JSONResponse:
    v = get_video_metrics(month, account)
    return JSONResponse({"metrics": v, "verdict": segm.video_verdict(v)})


@app.get("/api/organic")
def organic_endpoint(days: int = 30) -> JSONResponse:
    """Owned-audience (organic) Facebook Page + Instagram Business snapshot.
    Month-independent — always the trailing `days` window from today."""
    from connectors import get_organic_summary
    return JSONResponse(get_organic_summary(days=days))


class Ask(BaseModel):
    question: str
    month: str
    platform: str = "all"
    account: str | None = None


@app.post("/api/ask")
def ask(body: Ask) -> JSONResponse:
    data = analyze(body.month, body.platform, body.account, with_ai_summary=False)
    return JSONResponse(ai.answer(body.question, data["report"], data["analytics"]))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "data_mode": config.DATA_MODE,
            "model": config.GEMINI_MODEL, "accounts": len(config.AD_ACCOUNTS)}
