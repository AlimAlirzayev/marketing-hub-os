"""Conversions upload panel — a small FastAPI app for the marketing team.

Drag a CRM sales export (CSV/Excel) onto the page → preview (how many policies,
how many too old / without contact) → send to Meta as Purchase events. The send
runs in a background thread so the page stays responsive and the job continues
even while the user watches the progress bar.

Self-contained: imports meta-capi's own modules (its own `config`), so it never
collides with ads-studio's `config`. Ads Studio links here.

    .venv\\Scripts\\python.exe -m uvicorn web:app --port 8810   (or run_web.ps1)
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import capi
import config
from import_sales import (
    UnsupportedFile,
    _chunks,
    detect_columns,
    load_rows,
    read_table,
)

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Xalq Sigorta — Konversiyalar")

# In-memory job registry (single-user, single-process — fine for this machine).
JOBS: dict[str, dict] = {}


def _save_upload(file: UploadFile) -> str:
    ext = os.path.splitext(file.filename or "")[1] or ".csv"
    fd, path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(file.file.read())
    return path


def _build(path: str, max_age: int):
    headers, rows, header_line = read_table(path, {})
    mapping = detect_columns(headers, {})
    if "policy_no" not in mapping:
        raise UnsupportedFile("Polis № sütunu tapılmadı. Faylın başlıqlarını yoxla.")
    events, warnings = load_rows(rows, mapping, max_age)
    return headers, header_line, mapping, events, warnings


def _summary(file_name: str, headers, header_line, mapping, events, warnings) -> dict:
    valued = [e for e in events if e["custom_data"].get("value", 0) > 0]
    sample = events[0] if events else None
    return {
        "ok": True,
        "filename": file_name,
        "header_line": header_line,
        "headers": headers,
        "mapping": {k: mapping.get(k) for k in (
            "policy_no", "premium", "currency", "product", "email",
            "phone", "first_name", "last_name", "date", "external_id")},
        "prepared": len(events),
        "valued": len(valued),
        "has_premium": "premium" in mapping,
        "total_premium": round(sum(e["custom_data"]["value"] for e in valued), 2),
        "currency": valued[0]["custom_data"]["currency"] if valued else "AZN",
        "warnings": warnings,
        "dataset": config.OFFLINE_DATASET_ID,
        "sample": None if not sample else {
            "event": sample["event_name"],
            "id": sample["event_id"],
            "user_keys": sorted(sample["user_data"]),
        },
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "conversions.html"))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "dataset": config.OFFLINE_DATASET_ID}


@app.get("/api/config")
def cfg() -> dict:
    return {
        "dataset": config.OFFLINE_DATASET_ID,
        "pixel": config.PIXEL_ID,
        "has_test_code": bool(config.TEST_EVENT_CODE),
        "account": "Xalq Sigorta",
    }


@app.post("/api/preview")
async def preview(file: UploadFile = File(...), max_age: int = Form(62)) -> JSONResponse:
    path = _save_upload(file)
    try:
        headers, header_line, mapping, events, warnings = _build(path, max_age)
    except UnsupportedFile as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"Fayl oxunmadı: {exc}"}, status_code=400)
    finally:
        os.remove(path)
    return JSONResponse(_summary(file.filename, headers, header_line, mapping, events, warnings))


def _run_send(job_id: str, events: list[dict], test_code: str | None) -> None:
    job = JOBS[job_id]
    try:
        for batch in _chunks(events, 1000):
            resp = capi.send_events(batch, dataset_id=config.OFFLINE_DATASET_ID,
                                    test_event_code=test_code)
            job["sent"] += int(resp.get("events_received", 0))
            job["batches"].append({"received": resp.get("events_received"),
                                   "fbtrace_id": resp.get("fbtrace_id")})
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)


@app.post("/api/send")
async def send(file: UploadFile = File(...), max_age: int = Form(62),
               mode: str = Form("test")) -> JSONResponse:
    """mode='test' → events go only to Test Events (safe). mode='live' → production."""
    path = _save_upload(file)
    try:
        _, _, _, events, _ = _build(path, max_age)
    except UnsupportedFile as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"Fayl oxunmadı: {exc}"}, status_code=400)
    finally:
        os.remove(path)

    if not events:
        return JSONResponse({"ok": False, "error": "Göndəriləcək hadisə yoxdur."}, status_code=400)

    test_code = None
    if mode == "test":
        test_code = config.TEST_EVENT_CODE or "TESTPANEL"

    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "running", "total": len(events), "sent": 0,
                    "batches": [], "error": None, "mode": mode}
    threading.Thread(target=_run_send, args=(job_id, events, test_code), daemon=True).start()
    return JSONResponse({"ok": True, "job_id": job_id, "total": len(events), "mode": mode})


@app.get("/api/job/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    return JSONResponse(JOBS.get(job_id, {"status": "unknown"}))
