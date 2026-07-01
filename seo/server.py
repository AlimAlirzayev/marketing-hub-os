"""FastAPI panel for the SEO Engine — the front-end branch in Marketing OS.

Same shape as the other studios (price-hunter, ga4-studio): localhost, a single
premium dashboard + a JSON API, all work on-demand. It reuses the exact premium
renderers the CLI uses, so the browser deliverable === the file deliverable.

Run:
    .venv/Scripts/python -m uvicorn seo.server:app --port 8860
Registered in services.json (key "seo") so the hub embeds it automatically.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config
from .audit.auditor import audit_url
from .content.brief import build_brief
from .content.writer import onpage_selfcheck, write_article
from .render import article_html, audit_html
from .report import audit_json
from .research.gap import analyze_gap
from .research.keywords import research_keywords

app = FastAPI(title="RAMIN OS · SEO Studiyası", docs_url="/api/docs")

_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(_STATIC, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/api/health")
def health() -> JSONResponse:
    from . import llm
    return JSONResponse({
        "ok": True, "service": "seo", "version": __version__,
        "engines": ["audit", "research", "content"],
        "llm": llm.available(),
        "core_web_vitals": bool(config.PSI_API_KEY),  # key present = CWV live
    })


# --- Audit ------------------------------------------------------------------ #

@app.get("/audit/view", response_class=HTMLResponse)
def audit_view(url: str = Query(...), mobile: int = 1, vitals: int = 1) -> HTMLResponse:
    r = audit_url(url, with_vitals=bool(vitals), strategy="mobile" if mobile else "desktop")
    return HTMLResponse(audit_html(r))


@app.get("/api/audit")
def api_audit(url: str = Query(...), vitals: int = 1) -> JSONResponse:
    r = audit_url(url, with_vitals=bool(vitals))
    return JSONResponse(audit_json(r))


# --- Research --------------------------------------------------------------- #

@app.get("/api/research")
def api_research(seed: str = Query(...), limit: int = 100, cluster: int = 1) -> JSONResponse:
    r = research_keywords(seed, cluster=bool(cluster), max_keywords=limit)
    return JSONResponse({
        "seed": r.seed, "total": r.total, "intelligence": r.intelligence,
        "clusters": [
            {"name": c.name, "intent": c.intent, "intent_az": c.intent_az,
             "primary": c.primary, "keywords": c.keywords}
            for c in r.clusters
        ],
        "keywords": r.keywords,
    })


@app.get("/api/gap")
def api_gap(keyword: str = Query(...), top: int = 5) -> JSONResponse:
    g = analyze_gap(keyword, top_n=top)
    return JSONResponse({
        "keyword": g.keyword, "source": g.source, "analyzed": g.analyzed,
        "competitors": [{"rank": c.rank, "domain": c.domain, "title": c.title,
                         "url": c.url, "headings": c.headings} for c in g.competitors],
        "common_subtopics": g.common_subtopics,
        "content_gaps": g.content_gaps,
        "faq_questions": g.faq_questions,
        "recommended_outline": g.recommended_outline,
    })


# --- Content ---------------------------------------------------------------- #

@app.get("/article/view", response_class=HTMLResponse)
def article_view(keyword: str = Query(...)) -> HTMLResponse:
    art = write_article(build_brief(keyword))
    return HTMLResponse(article_html(art))


@app.get("/api/write")
def api_write(keyword: str = Query(...)) -> JSONResponse:
    art = write_article(build_brief(keyword))
    check = onpage_selfcheck(article_html(art))
    return JSONResponse({
        "keyword": art.keyword, "h1": art.h1,
        "meta_title": art.meta_title, "meta_description": art.meta_description,
        "words": len(art.markdown.split()), "source": art.source,
        "intent": art.brief.intent if art.brief else "",
        "secondary_keywords": art.brief.secondary_keywords if art.brief else [],
        "faq": art.faq,
        "jsonld_types": [o.get("@type") for o in art.jsonld],
        "selfcheck": {"passed": check["passed"], "total": check["total"]},
    })
