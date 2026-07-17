"""Media Studio front-end — FastAPI + a single premium studio page.

The whole experience the user asked for: type one sentence, the system fires
its brain and returns a directed, professional promo package (concept, model
decision, storyboard, cost-gated ready-to-fire command, visual board).

Run:
    uvicorn media_studio.server:app --port 8870
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from . import knowledge, models, pipeline, resources, runs, ugc

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="Media Studio", docs_url="/api/docs")


class CreateRequest(BaseModel):
    sentence: str
    use_llm: bool = True
    mode: str = "promo"


class RunStageRequest(BaseModel):
    stage: str
    confirm_spend: bool = False
    approved_slug: str | None = None
    approved_stage: str | None = None
    approved_credits: int | None = None
    picks: str | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(TEMPLATES / "studio.html"))


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "media_studio",
            "display_name": "Media Studio",
            "version": "0.4.0",
        }
    )


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


@app.get("/api/resources")
def resource_status() -> JSONResponse:
    return JSONResponse(resources.build_status())


@app.get("/api/resources/{slug}")
def resource_status_for_slug(slug: str) -> JSONResponse:
    safe = slug.replace("..", "").replace("/", "").replace("\\", "")
    path = pipeline.CAMPAIGNS / safe / "package.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    package = json.loads(path.read_text(encoding="utf-8"))
    return JSONResponse(resources.build_status(package))


@app.get("/api/generate/{slug}/plan")
def generation_plan(slug: str) -> JSONResponse:
    try:
        return JSONResponse(runs.plan_for_slug(slug))
    except FileNotFoundError:
        return JSONResponse({"error": "not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/generate/{slug}/run")
def run_generation_stage(slug: str, req: RunStageRequest) -> JSONResponse:
    try:
        return JSONResponse(
            runs.start_run(
                slug,
                stage=req.stage,
                confirm_spend=req.confirm_spend,
                approved_slug=req.approved_slug,
                approved_stage=req.approved_stage,
                approved_credits=req.approved_credits,
                picks=req.picks,
            )
        )
    except FileNotFoundError:
        return JSONResponse({"error": "not found"}, status_code=404)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/generate/runs/{run_id}")
def generation_run_status(run_id: str) -> JSONResponse:
    try:
        return JSONResponse(runs.get_run(run_id))
    except FileNotFoundError:
        return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/artifact/{slug}/{artifact_path:path}")
def artifact(slug: str, artifact_path: str):
    safe = slug.replace("..", "").replace("/", "").replace("\\", "")
    root = (pipeline.CAMPAIGNS / safe).resolve()
    target = (root / artifact_path).resolve()
    if target != root and not str(target).startswith(str(root) + os.sep):
        return JSONResponse({"error": "not found"}, status_code=404)
    if not target.exists() or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(target))


@app.get("/api/board/{slug}")
def board(slug: str) -> Response:
    """Serve the generated SVG storyboard board for a slug."""
    safe = slug.replace("..", "").replace("/", "").replace("\\", "")
    path = pipeline.CAMPAIGNS / safe / "storyboard-board.svg"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(path.read_text(encoding="utf-8"), media_type="image/svg+xml")
