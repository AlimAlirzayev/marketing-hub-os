"""GA4 Studio — website analytics dashboard for Marketing OS.

FastAPI app: serves the dashboard and a small JSON API over the demo/live GA4
connector. Self-contained (own config), so it never collides with ads-studio's
or meta-capi's ``config`` module.

    .venv\\Scripts\\python.exe -m uvicorn app:app --port 8850   (or run.ps1)
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

import analytics
import config
import connectors

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="GA4 Studio — Xalq Sigorta")


def _resolve_range(days: int, start: str | None, end: str | None) -> tuple[str, str]:
    if start and end:
        return start, end
    return config.default_range(days)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "dashboard.html"))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": config.DATA_MODE, "property": config.PROPERTY_ID or None}


@app.get("/api/config")
def cfg() -> dict:
    return {
        "mode": config.DATA_MODE,
        "property": config.PROPERTY_ID or None,
        "site": config.SITE_DOMAIN,
        "account": config.ACCOUNT_NAME,
        "tagline": config.ACCOUNT_TAGLINE,
        "blockers": config.live_blockers() if config.DATA_MODE == "demo" else [],
        "has_ai": bool(config.GEMINI_API_KEY),
        "brand": config.BRAND,
    }


@app.get("/api/report")
def report(days: int = Query(28, ge=1, le=365),
           start: str | None = None, end: str | None = None) -> JSONResponse:
    s, e = _resolve_range(days, start, end)
    try:
        data = analytics.enrich(connectors.get_report(s, e))
    except Exception as exc:
        return JSONResponse({"ok": False, "mode": config.DATA_MODE,
                             "error": f"GA4 məlumatı alınmadı: {exc}"}, status_code=502)
    return JSONResponse({"ok": True, **data})


@app.get("/api/ai")
def ai(days: int = Query(28, ge=1, le=365),
       start: str | None = None, end: str | None = None) -> JSONResponse:
    s, e = _resolve_range(days, start, end)
    try:
        data = analytics.enrich(connectors.get_report(s, e))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"Data alınmadı: {exc}"}, status_code=502)
    return JSONResponse(analytics.ai_narrative(data))
