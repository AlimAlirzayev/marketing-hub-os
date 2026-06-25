"""Customer Relations Center - FastAPI server.

Run:
    .\run.ps1
    # or
    python -m uvicorn app:app --port 8810
"""

from __future__ import annotations

import hmac
import csv
import io
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

import alerts
import analytics
import collector
import config
import resolution_agent
import store
import triage
from connectors.chatplace import normalize_payload as normalize_chatplace_payload
from connectors.demo import seed_if_empty
from connectors.google_reviews import normalize_review, reply_to_review, sync_reviews
from connectors.meta_graph import discover_assets
from connectors.meta import normalize_meta_payload
from models import AskRequest, IncomingMessage, ReplyRequest, StatusUpdate

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Customer Relations Center", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    store.init_db()
    if config.DATA_MODE == "demo":
        seed_if_empty()
    collector.start_background_sync()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "dashboard.html"))


@app.get("/api/meta")
def meta() -> dict:
    return {
        "app_name": config.APP_NAME,
        "account": config.ACCOUNT_NAME,
        "tagline": config.ACCOUNT_TAGLINE,
        "data_mode": config.DATA_MODE,
        "brand": config.BRAND,
        "channels": config.CHANNELS,
        "categories": config.CATEGORIES,
        "statuses": config.STATUSES,
        "ai_enabled": bool(config.AI_ENABLED and config.GEMINI_API_KEY),
        "meta_webhook_configured": bool(config.META_VERIFY_TOKEN),
        "meta_graph_pull_configured": collector.integration_status()["channels"]["meta_graph_pull"]["configured"],
        "chatplace_pull_configured": collector.integration_status()["channels"]["chatplace_pull"]["configured"],
        "google_reviews_configured": bool(config.GBP_ACCESS_TOKEN and config.GBP_ACCOUNT_ID and config.GBP_LOCATION_IDS),
        "alerts_configured": bool(config.TELEGRAM_BOT_TOKEN and config.CX_ALERT_CHAT_ID),
        "sync_interval_seconds": config.CX_SYNC_INTERVAL_SECONDS,
        "public_base_url_configured": config.PUBLIC_BASE_URL.startswith("https://"),
    }


@app.get("/api/integrations/status")
def integrations_status() -> JSONResponse:
    return JSONResponse(collector.integration_status())


@app.get("/api/report")
def report(days: int = 30) -> JSONResponse:
    data = analytics.build_report(days)
    data["brief"] = analytics.executive_brief(data)
    return JSONResponse(data)


@app.get("/api/resolution-agent/draft")
def resolution_agent_draft(days: int = 7, limit: int = 20) -> JSONResponse:
    """Draft-only recovery plan. Does not send replies or change statuses."""
    plan = resolution_agent.build_plan_from_store(days=days, limit=limit)
    return JSONResponse(plan)


@app.get("/api/complaints")
def complaints(
    status: str = "all",
    severity: str = "all",
    channel: str = "all",
    q: str = "",
    days: int = 30,
) -> JSONResponse:
    items = store.list_complaints(
        status=status,
        severity=severity,
        channel=channel,
        q=q.strip() or None,
        days=days,
        limit=250,
    )
    return JSONResponse({"items": items})


@app.get("/api/export.csv")
def export_csv(days: int = 30) -> Response:
    items = store.list_complaints(days=days, limit=5000)
    buf = io.StringIO()
    fields = [
        "id",
        "occurred_at",
        "channel",
        "source",
        "author_name",
        "author_handle",
        "rating",
        "sentiment",
        "severity",
        "urgency_score",
        "category",
        "assigned_team",
        "status",
        "owner",
        "sla_due_at",
        "text",
        "ai_summary",
        "recommended_reply",
        "url",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow(item)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="customer-relations-{days}d.csv"'},
    )


@app.get("/api/complaints/{complaint_id}/events")
def complaint_events(complaint_id: int) -> JSONResponse:
    return JSONResponse({"events": store.events_for(complaint_id)})


@app.post("/api/ingest")
def ingest(
    message: IncomingMessage,
    x_cx_signature: str | None = Header(default=None),
    x_cx_token: str | None = Header(default=None),
) -> JSONResponse:
    _verify_optional_secret(message.model_dump_json(), x_cx_signature, x_cx_token)
    payload = message.model_dump()
    item, result, alert = _triage_store_alert(payload)
    return JSONResponse({"ok": True, "complaint": item, "triage": result, "alert": alert})


@app.post("/api/webhooks/chatplace")
async def chatplace_webhook(
    request: Request,
    x_cx_signature: str | None = Header(default=None),
    x_cx_token: str | None = Header(default=None),
) -> JSONResponse:
    body = await request.body()
    _verify_optional_secret(body.decode("utf-8", errors="ignore"), x_cx_signature, x_cx_token)
    raw = await request.json()
    message = normalize_chatplace_payload(raw)
    item, result, alert = _triage_store_alert(message)
    return JSONResponse({"ok": True, "complaint": item, "triage": result, "alert": alert})


@app.post("/api/webhooks/google-review")
async def google_review_webhook(
    request: Request,
    x_cx_signature: str | None = Header(default=None),
    x_cx_token: str | None = Header(default=None),
) -> JSONResponse:
    body = await request.body()
    _verify_optional_secret(body.decode("utf-8", errors="ignore"), x_cx_signature, x_cx_token)
    raw = await request.json()
    message = _normalize_google_review(raw)
    item, result, alert = _triage_store_alert(message)
    return JSONResponse({"ok": True, "complaint": item, "triage": result, "alert": alert})


@app.get("/api/webhooks/meta")
def meta_webhook_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == config.META_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Meta webhook verification failed")


@app.post("/api/webhooks/meta")
async def meta_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    body = await request.body()
    _verify_meta_signature(body, x_hub_signature_256)
    raw = await request.json()
    messages = normalize_meta_payload(raw)
    created = []
    alerts_sent = []
    for message in messages:
        item, result, alert = _triage_store_alert(message)
        created.append({"complaint": item, "triage": result})
        alerts_sent.append(alert)
    return JSONResponse({"ok": True, "count": len(created), "items": created, "alerts": alerts_sent})


@app.post("/api/sync/google-reviews")
def sync_google_reviews(max_pages_per_location: int = 2) -> JSONResponse:
    result = collector.sync_google_reviews(max_pages_per_location=max_pages_per_location)
    if not result["ok"]:
        first = next((ch for ch in result["channels"].values() if ch.get("error")), None)
        detail = _safe_error(first.get("error") if first else "Google reviews sync failed")
        raise HTTPException(status_code=400, detail=detail)
    return JSONResponse(result)


@app.post("/api/sync/meta")
def sync_meta(max_pages: int = 1) -> JSONResponse:
    result = collector.sync_meta(max_pages=max_pages)
    if not result["ok"]:
        first = next((ch for ch in result["channels"].values() if ch.get("error")), None)
        detail = _safe_error(first.get("error") if first else "Meta sync failed")
        raise HTTPException(status_code=400, detail=detail)
    return JSONResponse(result)


@app.post("/api/sync/all")
def sync_all(max_pages: int = 1) -> JSONResponse:
    result = collector.sync_all(max_pages=max_pages)
    status_code = 200 if result["ok"] else 207
    return JSONResponse(result, status_code=status_code)


@app.get("/api/sync/meta/discover")
def discover_meta_assets() -> JSONResponse:
    try:
        result = discover_assets()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_safe_error(str(exc))) from exc
    return JSONResponse({"ok": True, **result})


@app.post("/api/complaints/{complaint_id}/status")
def set_status(complaint_id: int, body: StatusUpdate) -> JSONResponse:
    if body.status not in config.STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported status")
    item = store.update_status(complaint_id, body.status, body.owner, body.note)
    if not item:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return JSONResponse({"ok": True, "complaint": item})


@app.post("/api/complaints/{complaint_id}/reply/google")
def reply_google_review(complaint_id: int, body: ReplyRequest) -> JSONResponse:
    item = store.get_complaint(complaint_id)
    if not item:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if item["channel"] != "google_review":
        raise HTTPException(status_code=400, detail="Complaint is not a Google review")
    metadata = item.get("metadata") or {}
    resource_name = metadata.get("resource_name") or (metadata.get("google_review") or {}).get("name")
    message = body.message or item.get("recommended_reply")
    result = reply_to_review(resource_name, message, dry_run=body.dry_run)
    store.add_event(
        complaint_id,
        actor="operator",
        event_type="google_reply_dry_run" if body.dry_run else "google_reply_sent",
        note=message,
    )
    return JSONResponse({"ok": True, "result": result})


@app.post("/api/ask")
def ask(body: AskRequest) -> dict:
    data = analytics.build_report(body.days)
    brief = analytics.executive_brief(data)
    question = body.question.lower()
    if "kritik" in question or "critical" in question:
        items = data["priority_queue"][:5]
        answer = "Top critical/open issues: " + "; ".join(
            f"#{i['id']} {i['category']} via {i['channel']} - {i['ai_summary']}" for i in items
        )
    elif "səbəb" in question or "sebeb" in question or "root" in question:
        answer = "Main root causes: " + "; ".join(
            f"{r['category']} ({r['count']}, {r['team']})" for r in data["root_causes"][:5]
        )
    elif "sla" in question or "gecik" in question:
        answer = f"{data['totals']['overdue']} items are overdue. Risk score is {data['totals']['risk_score']}."
    else:
        answer = brief["text"]
    return {"answer": answer, "source": "grounded-rules", "brief": brief}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": config.DATA_MODE, "database": config.DATABASE_PATH}


def _triage_store_alert(message: dict) -> tuple[dict, dict, dict]:
    result = triage.triage_message(message)
    item = store.upsert_complaint(message, result)
    alert = alerts.maybe_alert(item)
    return item, result, alert


def _safe_error(message: str) -> str:
    lowered = message.lower()
    if "access_token=" in lowered or "authorization" in lowered:
        return "External provider request failed. Check server logs and token permissions."
    return message


def _verify_optional_secret(body: str, signature: str | None, token: str | None = None) -> None:
    if not config.WEBHOOK_SECRET:
        return
    if token and hmac.compare_digest(token, config.WEBHOOK_SECRET):
        return
    expected = hmac.new(config.WEBHOOK_SECRET.encode(), body.encode(), "sha256").hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _verify_meta_signature(body: bytes, signature: str | None) -> None:
    if not config.META_APP_SECRET:
        return
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing Meta signature")
    expected = hmac.new(config.META_APP_SECRET.encode(), body, "sha256").hexdigest()
    provided = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid Meta signature")


def _pick(raw: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = raw
        ok = True
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                ok = False
                break
        if ok and value not in (None, ""):
            return value
    return None


def _normalize_chatplace(raw: dict[str, Any]) -> dict:
    text = _pick(raw, "message.text", "text", "last_message", "comment.text") or ""
    channel = _pick(raw, "channel", "platform", "message.channel") or "instagram_dm"
    if channel == "instagram":
        channel = "instagram_dm"
    return {
        "source": "chatplace",
        "channel": channel,
        "account": _pick(raw, "account.name", "account", "page.name"),
        "external_id": _pick(raw, "message.id", "id", "comment.id"),
        "author_name": _pick(raw, "user.name", "contact.name", "author.name"),
        "author_handle": _pick(raw, "user.username", "contact.username", "author.username"),
        "text": text,
        "url": _pick(raw, "url", "message.url", "comment.url"),
        "occurred_at": _pick(raw, "created_at", "timestamp", "message.created_at"),
        "metadata": {"chatplace": raw},
        "raw_payload": raw,
    }


def _normalize_google_review(raw: dict[str, Any]) -> dict:
    review = raw.get("review") if isinstance(raw.get("review"), dict) else raw
    location_id = _pick(raw, "locationName", "location_id", "account", "place.name") or "manual"
    return normalize_review(review, location_id)
