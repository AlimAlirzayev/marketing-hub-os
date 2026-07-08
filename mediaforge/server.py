"""MediaForge front-end — FastAPI + a single premium studio page.

The whole experience the user asked for: type one sentence, the system fires
its brain and returns a directed, professional promo package (concept, model
decision, storyboard, cost-gated ready-to-fire command, visual board).

Run:
    uvicorn mediaforge.server:app --port 8870
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from . import knowledge, models, pipeline, ugc

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="MediaForge — Media Rejissoru", docs_url="/api/docs")


class CreateRequest(BaseModel):
    sentence: str
    use_llm: bool = True
    mode: str = "promo"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(TEMPLATES / "studio.html"))


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "mediaforge", "version": "0.2.0"})


@app.get("/api/catalog")
def catalog() -> JSONResponse:
    """Model catalog + category playbooks, for the UI to render chips/help."""
    return JSONResponse(
        {
            "models": [
                {
                    "id": m.id,
                    "label": m.label,
                    "tier": m.tier,
                    "kind": m.kind,
                    "durations": list(m.durations_s),
                    "max_resolution": m.max_resolution,
                    "strength": m.strength,
                }
                for m in models.CATALOG.values()
            ],
            "categories": [
                {"key": k, "product": v["product"], "hero_emotion": v["hero_emotion"]}
                for k, v in knowledge.CATEGORY_PLAYBOOKS.items()
            ],
            "modes": ["promo", "ugc"],
            "catalog_refreshed": models.CATALOG_REFRESHED,
        }
    )


@app.post("/api/create")
def create(req: CreateRequest) -> JSONResponse:
    sentence = (req.sentence or "").strip()
    if not sentence:
        return JSONResponse({"error": "Boş cümlə"}, status_code=400)
    mode = (req.mode or "promo").strip().casefold()
    pkg = ugc.create(sentence, use_llm=req.use_llm) if mode == "ugc" else pipeline.create(
        sentence, use_llm=req.use_llm
    )
    return JSONResponse(pkg)


@app.get("/api/board/{slug}")
def board(slug: str) -> Response:
    """Serve the generated SVG storyboard board for a slug."""
    safe = slug.replace("..", "").replace("/", "").replace("\\", "")
    path = pipeline.CAMPAIGNS / safe / "storyboard-board.svg"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(path.read_text(encoding="utf-8"), media_type="image/svg+xml")
