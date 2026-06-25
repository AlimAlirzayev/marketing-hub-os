"""Atelier - FastAPI server for the marketing cockpit.

MVP scope: Creative Lab + Brand Brain. Serves a single-page cockpit plus a JSON
API. The heavy AI work (prompt composition, vision critique) lives in lazy POST
endpoints so the UI paints instantly. Pure-Python, no Docker - runs on the
locked-down corporate machine just like ads-studio.

Run:
    uvicorn app:app --port 8820        (or use ./run.ps1)
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import brand, config, critique, lab, store

config.ensure_dirs()
store.init()

app = FastAPI(title="Atelier", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=os.path.join(config.BASE, "static")),
          name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".gif": "image/gif"}


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(config.BASE, "templates", "atelier.html"))


# --------------------------------------------------------------------------
# Brand Brain
# --------------------------------------------------------------------------
@app.get("/api/brand")
def get_brand() -> JSONResponse:
    return JSONResponse(brand.payload())


class BrandState(BaseModel):
    active_style: str | None = None
    active_voice: str | None = None
    active_dialect: str | None = None
    default_format: str | None = None
    default_n: int | None = None
    house_rules: str | None = None
    extra_exclusions: str | None = None


@app.post("/api/brand/state")
def save_brand_state(body: BrandState) -> JSONResponse:
    return JSONResponse(brand.save_state(body.model_dump(exclude_none=True)))


# --------------------------------------------------------------------------
# Creative Lab
# --------------------------------------------------------------------------
class Compose(BaseModel):
    brief: str
    style: str | None = None
    voice: str | None = None
    dialect: str | None = None
    format: str | None = None
    n: int | None = None
    with_caption: bool = False


@app.post("/api/lab/compose")
def compose(body: Compose) -> JSONResponse:
    if not body.brief.strip():
        raise HTTPException(400, "Brief boş ola bilməz.")
    st = brand.get_state()
    style = body.style or st["active_style"]
    voice = body.voice or st["active_voice"]
    dialect = body.dialect or st["active_dialect"]
    fmt = body.format or st["default_format"]
    n = body.n or st["default_n"]
    result = lab.compose(
        body.brief, style, voice, dialect, fmt, n, body.with_caption,
        house_rules=st.get("house_rules", ""),
        extra_exclusions=st.get("extra_exclusions", ""))
    saved = store.create_brief(body.brief, result["meta"], result["source"],
                               result["concepts"])
    saved["source"] = result["source"]
    return JSONResponse(saved)


@app.post("/api/lab/upload")
async def upload(concept_id: int = Form(...),
                 file: UploadFile = File(...)) -> JSONResponse:
    concept = store.get_concept(concept_id)
    if not concept:
        raise HTTPException(404, "Konsept tapılmadı.")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _MIME:
        raise HTTPException(400, "Yalnız şəkil faylı (png, jpg, webp).")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Boş fayl.")
    fname = f"c{concept_id}_{int(time.time())}{ext}"
    with open(os.path.join(config.UPLOAD_DIR, fname), "wb") as f:
        f.write(data)
    store.set_image(concept_id, fname)
    return JSONResponse({"image_path": fname, "image_url": f"/uploads/{fname}"})


class ConceptRef(BaseModel):
    concept_id: int


@app.post("/api/lab/critique")
def run_critique(body: ConceptRef) -> JSONResponse:
    concept = store.get_concept(body.concept_id)
    if not concept:
        raise HTTPException(404, "Konsept tapılmadı.")
    if not concept.get("image_path"):
        raise HTTPException(400, "Əvvəlcə şəkil yükləyin.")
    path = os.path.join(config.UPLOAD_DIR, concept["image_path"])
    if not os.path.isfile(path):
        raise HTTPException(404, "Şəkil faylı tapılmadı.")
    with open(path, "rb") as f:
        data = f.read()
    mime = _MIME.get(os.path.splitext(path)[1].lower(), "image/png")
    brief = store.get_brief(concept["brief_id"]) or {}
    result = critique.review(
        data, mime, angle=concept.get("angle", ""),
        prompt_excerpt=(concept.get("prompt") or "")[:600],
        style_key=brief.get("style", ""))
    store.set_critique(body.concept_id, result)
    return JSONResponse(result)


class Rate(BaseModel):
    concept_id: int
    rating: int | None = None
    starred: bool | None = None


@app.post("/api/lab/rate")
def rate(body: Rate) -> JSONResponse:
    updated = store.set_rating(body.concept_id, body.rating, body.starred)
    if not updated:
        raise HTTPException(404, "Konsept tapılmadı.")
    return JSONResponse(updated)


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------
@app.get("/api/history")
def history(limit: int = 30) -> JSONResponse:
    return JSONResponse(store.recent_briefs(limit))


@app.get("/api/brief/{brief_id}")
def brief_detail(brief_id: int) -> JSONResponse:
    b = store.get_brief(brief_id)
    if not b:
        raise HTTPException(404, "Brief tapılmadı.")
    return JSONResponse(b)


@app.get("/api/health")
def health() -> dict:
    from . import llm
    return {"ok": True, "ai": llm.available(), "model": config.GEMINI_MODEL,
            "styles": len(brand.list_style_dna()),
            "voices": len(brand.list_voice_dna())}
