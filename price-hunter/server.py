"""FastAPI backend for Price Hunter - the always-on engine behind the dashboard.

Same shape as the other Xalq Insurance Digital OS studios (ads-studio, atelier):
pure-Python, localhost, a single-page dashboard + a JSON API. No scheduler - the
hunt runs ON DEMAND when the dashboard (or any client) asks. The heavy work lives
in one async POST endpoint so the UI paints instantly.

Run:
    .venv/Scripts/python -m uvicorn server:app --port 8830
    (or double-click run.bat)
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from hunt import hunt

config.ensure_dirs()

app = FastAPI(title="Price Hunter", docs_url="/api/docs")
_STATIC = os.path.join(config.BASE, "static")
os.makedirs(_STATIC, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


class HuntRequest(BaseModel):
    query: str
    max_price: float | None = None
    min_price: float | None = None
    min_trust: float | None = None
    official: bool = False
    condition: str | None = None
    source: str | None = None
    sort: str = "deal"
    deep: bool = False
    serp: bool = False
    social: bool = False
    verdict: bool = True


def _offer_dict(o) -> dict:
    return {"price": o.price, "currency": o.currency, "trust": round(o.trust, 2),
            "source": o.source, "seller": o.seller, "condition": o.condition,
            "official": bool(o.official), "in_stock": o.in_stock,
            "flags": o.flags, "title": o.title, "url": o.url,
            "model_code": o.model_code, "seller_label": o.seller_label,
            "gmaps_rating": o.gmaps_rating, "hist_low": o.hist_low,
            "is_lowest": o.is_lowest}


def _payload(res) -> dict:
    return {
        "query": res.query,
        "canonical_name": res.spec.canonical_name,
        "fair_low": res.spec.fair_low, "fair_high": res.spec.fair_high,
        "market": res.stats or {},
        "history": res.history or {},
        "best_legit": _offer_dict(res.best_legit) if res.best_legit else None,
        "cheapest": _offer_dict(res.cheapest) if res.cheapest else None,
        "verdict": res.verdict,
        "offers": [_offer_dict(o) for o in res.ranked],
        "coverage": [{"source": s, "status": st, "note": n}
                     for s, st, n in res.source_status],
        "totals": {"seen": res.total_seen, "matched": len(res.ranked),
                   "rejected": res.rejected},
        "engines": {"llm": config.llm_status(), "apify": bool(config.APIFY_API_TOKEN)},
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/api/health")
def health():
    return {"ok": True, "llm": config.llm_status(),
            "apify": bool(config.APIFY_API_TOKEN)}


@app.post("/api/hunt")
async def api_hunt(req: HuntRequest):
    if not req.query.strip():
        return JSONResponse({"error": "empty query"}, status_code=400)
    filters = {"max_price": req.max_price, "min_price": req.min_price,
               "min_trust": req.min_trust, "official_only": req.official,
               "condition": req.condition, "source": req.source, "sort": req.sort}
    res = await hunt(req.query.strip(), do_verdict=req.verdict,
                     filters=filters, deep=req.deep, serp=req.serp, social=req.social)
    return _payload(res)


# Convenience GET so you can hit it from the browser bar / curl too.
@app.get("/api/hunt")
async def api_hunt_get(q: str, deep: bool = False, official: bool = False,
                       max_price: float | None = None, sort: str = "deal",
                       verdict: bool = True):
    return await api_hunt(HuntRequest(query=q, deep=deep, official=official,
                                      max_price=max_price, sort=sort, verdict=verdict))
