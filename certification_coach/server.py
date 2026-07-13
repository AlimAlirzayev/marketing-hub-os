"""FastAPI panel for the Ramin-OS Marketing Certification Coach.

Run:
    python -m uvicorn certification_coach.server:app --port 8880
Registered in services.json so the hub embeds it like the other studios.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from . import coach, journey, knowledge, source_verifier


BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(title="RAMIN OS - Marketing Certification Coach", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class PlanRequest(BaseModel):
    role: str = "Marketing specialist"
    level: str = "foundation"
    weekly_hours: int = 6
    deadline_weeks: int | None = None
    budget: str = "free_first"
    focus_tags: list[str] = []
    goals: str = ""


class MockRequest(BaseModel):
    cert_id: str
    count: int = 6


class GradeRequest(BaseModel):
    cert_id: str
    answers: dict[str, int]
    count: int | None = None
    journey_id: str | None = None


class AskRequest(BaseModel):
    question: str
    profile: dict[str, Any] = {}
    use_llm: bool = True


class JourneyCreateRequest(BaseModel):
    cert_id: str | None = None
    profile: dict[str, Any] = {}


class JourneyActionRequest(BaseModel):
    action: str
    payload: dict[str, Any] = {}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


@app.get("/api/health")
def health() -> JSONResponse:
    data = coach.catalog()
    return JSONResponse(
        {
            "ok": True,
            "service": "certification_coach",
            "version": __version__,
            "certifications": len(data["certifications"]),
            "catalog_last_checked": data["last_checked"],
            "mode": "exam_prep_only",
            "knowledge": knowledge.stats(),
            "sources": source_verifier.load_cached().get("summary", {}),
            "journeys": journey.list_journeys().get("count", 0),
        }
    )


@app.get("/api/catalog")
def api_catalog() -> JSONResponse:
    return JSONResponse(coach.catalog())


@app.post("/api/plan")
def api_plan(req: PlanRequest) -> JSONResponse:
    profile = req.dict()
    plan = coach.build_roadmap(profile)
    knowledge.record_plan(profile, plan)
    return JSONResponse(knowledge.enrich_plan(plan, profile))


@app.post("/api/mock")
def api_mock(req: MockRequest) -> JSONResponse:
    try:
        return JSONResponse(coach.mock_exam(req.cert_id, req.count))
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@app.post("/api/grade")
def api_grade(req: GradeRequest) -> JSONResponse:
    try:
        grade = coach.grade_mock(req.cert_id, req.answers, req.count)
        knowledge.record_mock_grade(grade)
        if req.journey_id:
            grade["journey"] = journey.record_mock_grade(req.journey_id, grade)
        return JSONResponse(grade)
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/certifications/{cert_id}")
def api_certification(cert_id: str) -> JSONResponse:
    try:
        return JSONResponse(coach.certification(cert_id))
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@app.get("/api/knowledge")
def api_knowledge() -> JSONResponse:
    return JSONResponse(
        {
            "stats": knowledge.stats(),
            "learner_memory": knowledge.learner_summary(),
            "sources": source_verifier.load_cached(),
            "sample_chunks": [chunk.as_dict() for chunk in knowledge.knowledge_chunks()[:8]],
        }
    )


@app.post("/api/knowledge/reindex")
def api_reindex() -> JSONResponse:
    index = knowledge.rebuild_index()
    return JSONResponse(
        {
            "ok": True,
            "documents": len(index.get("documents", [])),
            "built_at": index.get("built_at"),
            "index_path": str(knowledge.INDEX_PATH),
        }
    )


@app.get("/api/search")
def api_search(q: str, k: int = 6) -> JSONResponse:
    return JSONResponse({"query": q, "hits": knowledge.search(q, k=k)})


@app.post("/api/ask")
def api_ask(req: AskRequest) -> JSONResponse:
    if not req.question.strip():
        return JSONResponse({"error": "empty question"}, status_code=400)
    return JSONResponse(knowledge.answer_question(req.question, req.profile, use_llm=req.use_llm))


@app.get("/api/journeys")
def api_journeys() -> JSONResponse:
    return JSONResponse(journey.list_journeys())


@app.post("/api/journeys")
def api_create_journey(req: JourneyCreateRequest) -> JSONResponse:
    try:
        return JSONResponse(journey.create_journey(req.cert_id, req.profile))
    except (KeyError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/journeys/{journey_id}")
def api_journey(journey_id: str) -> JSONResponse:
    try:
        return JSONResponse(journey.journey_view(journey_id))
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@app.post("/api/journeys/{journey_id}/action")
def api_journey_action(journey_id: str, req: JourneyActionRequest) -> JSONResponse:
    try:
        return JSONResponse(journey.apply_action(journey_id, req.action, req.payload))
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/sources")
def api_sources() -> JSONResponse:
    return JSONResponse(source_verifier.load_cached())


@app.post("/api/sources/verify")
def api_sources_verify() -> JSONResponse:
    return JSONResponse(source_verifier.verify_catalog())
