"""Media generation studio — image / video / voice / music behind one API.

Engine port of the fleet's standalone /opt/media-gen service (v2), rewritten as a
FastAPI app so the standard launcher (services.json -> uvicorn) runs it on every
machine — same muscle on both twins. Providers are free-first (pollinations,
gemini, g4f, hf, edge-tts) with paid ones activating automatically when their
API key exists in .env (keys arrive via the encrypted vault; none live in code).

  POST /generate/image  {"prompt": "...", "provider": "gemini|pollinations|...", "width": 1024}
  POST /generate/video  {"prompt": "...", "provider": "fal|hf", "model": "kling|wan21"}
  POST /generate/voice  {"text": "...", "provider": "elevenlabs|edge_tts|...", "voice": "..."}
  POST /generate/music  {"prompt": "...", "provider": "suno|fal"}
  GET  /providers       which providers are usable here (bool only, never key values)
  GET  /api/health      launcher/hub health probe

Successful generations return the raw binary (image/audio/video) with the chosen
provider in the X-Provider response header.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """Repo .env first; then the fleet's legacy /opt/stack/.env (best-effort) so
    an already-provisioned box keeps its provider keys without re-entry."""
    for path in (_ROOT / ".env", Path("/opt/stack/.env")):
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass


_load_env()  # must run before importing media_router (providers read env at call time)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402

from .media_router import PROVIDER_TABLE, route  # noqa: E402

app = FastAPI(title="mediagen", docs_url=None, redoc_url=None)

_TASKS = {"image", "video", "voice", "music"}


@app.get("/api/health")
@app.get("/health")  # legacy path — the gateway's generate_media probe uses it
def health() -> dict:
    return {"ok": True, "service": "mediagen", "version": "2.0"}


@app.get("/providers")
def providers() -> dict:
    # bool only — never expose key values
    return {task: {n: bool(av()) for n, fn, av in ps} for task, ps in PROVIDER_TABLE.items()}


@app.post("/generate/{task}")
async def generate(task: str, request: Request) -> Response:
    if task not in _TASKS:
        return JSONResponse({"error": "unknown endpoint"}, status_code=404)
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    prompt = body.get("prompt") or body.get("text", "")
    kwargs = {k: v for k, v in body.items() if k not in ("prompt", "text", "provider", "model")}
    try:
        data, mime, provider = route(
            task, prompt, provider=body.get("provider"), model=body.get("model"), **kwargs
        )
        return Response(content=data, media_type=mime, headers={"X-Provider": str(provider)})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
