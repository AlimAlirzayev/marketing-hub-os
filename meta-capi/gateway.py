"""Meta CAPI backup gateway — the server-side twin of the browser Pixel.

The browser Pixel only fires client-side, so ad-blockers, Safari/iOS ITP and
cookie loss silently drop ~10-30% of events — including the *funnel steps* and
*button clicks* you build retargeting audiences and optimise on. This gateway
closes that gap: the website JS fires every event to BOTH the Pixel and here,
sharing one ``event_id`` so Meta deduplicates and counts each action once.
Server events survive ad-blockers, so your funnel data stops leaking.

It is the real-time counterpart to ``import_sales.py`` (batch CRM Purchases):

    Pixel only            ──►  loses adblocked events, no backup
    Pixel + this gateway  ──►  every event has a CAPI twin, deduped by event_id

Pair it with the Pixel using the bundled bridge served at ``/capi-bridge.js``.

    .venv\\Scripts\\python.exe -m uvicorn gateway:app --port 8812   (or run_gateway.ps1)

Why a separate app from web.py? ``web.py`` is the team's INTERNAL CRM-upload
panel; this is a PUBLIC, browser-facing collector with CORS and real end-user
IP/UA capture — a different trust boundary, so it lives apart.

Safety:
  * Set ``META_TEST_EVENT_CODE`` in .env → every event lands only in Events
    Manager → Test Events (project-wide convention, same as verify/import).
  * Set ``CAPI_GATEWAY_DRY_RUN=1`` → builds + hashes but sends NOTHING to Meta
    (smoke-test the wiring locally with zero side effects).
"""

from __future__ import annotations

import os
from collections import deque
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

import capi
import config

BASE = os.path.dirname(os.path.abspath(__file__))

# Browser origins allowed to POST events. Default "*" (open collector); lock it
# down to the real site(s) in production via CAPI_GATEWAY_ORIGINS=https://a,https://b
_ORIGINS = [o.strip() for o in os.getenv("CAPI_GATEWAY_ORIGINS", "*").split(",") if o.strip()]

# Build + hash but never POST to Meta — for safe local wiring checks.
DRY_RUN = os.getenv("CAPI_GATEWAY_DRY_RUN", "") == "1"

app = FastAPI(title="Xalq Sigorta — CAPI Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_credentials=("*" not in _ORIGINS),   # credentials are illegal with "*"
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Lightweight in-process observability (single machine, single process).
STATS: dict[str, Any] = {"received": 0, "sent": 0, "failed": 0, "last_error": None}
RECENT: deque[dict] = deque(maxlen=50)


class CollectIn(BaseModel):
    event_name: str
    event_id: str | None = None
    event_source_url: str | None = None
    action_source: str = "website"
    event_time: int | None = None
    # Raw PII (email/phone/…) is hashed here; fbp/fbc/external_id pass through.
    user_data: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None
    # Force this single event to Test Events regardless of .env (used by /demo).
    test: bool | None = None


def _client_ip(request: Request) -> str:
    """Real end-user IP. The browser calls this gateway directly, so the socket
    peer IS the user — unless a reverse proxy sits in front, then trust its
    forwarded header (first hop)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else ""


def _fbc_from_url(url: str | None) -> str:
    """Reconstruct fbc from an ?fbclid=… in the landing URL (no _fbc cookie yet)."""
    if not url or "fbclid=" not in url:
        return ""
    try:
        from urllib.parse import parse_qs, urlsplit
        q = parse_qs(urlsplit(url).query)
        fbclid = (q.get("fbclid") or [""])[0]
        return capi.build_fbc(fbclid)
    except Exception:
        return ""


def _remember(name: str, event_id: str, status: str, detail: Any, test: bool) -> None:
    import time
    RECENT.appendleft({"t": int(time.time()), "event": name, "event_id": event_id,
                       "status": status, "detail": str(detail)[:200], "test": test})


def _dispatch(name: str, ud: dict, custom: dict | None, event_id: str,
              action_source: str, url: str | None, event_time: int | None,
              test_code: str | None) -> None:
    """Hash + send one event to the website Pixel dataset (background)."""
    try:
        resp = capi.send_custom_event(
            name, user_data=ud, custom_data=custom, event_id=event_id,
            action_source=action_source, event_source_url=url, event_time=event_time,
            dataset_id=config.active_dataset(),         # website Pixel dataset (dedup target)
            test_event_code=test_code, dry_run=DRY_RUN)
        if DRY_RUN:
            STATS["sent"] += 1
            _remember(name, event_id, "dry_run", "(göndərilmədi — DRY_RUN)", bool(test_code))
        else:
            STATS["sent"] += int(resp.get("events_received", 0))
            _remember(name, event_id, "ok", resp.get("fbtrace_id"), bool(test_code))
    except Exception as exc:                              # surface, never silently drop
        STATS["failed"] += 1
        STATS["last_error"] = str(exc)
        _remember(name, event_id, "error", str(exc), bool(test_code))


@app.post("/collect")
async def collect(payload: CollectIn, request: Request, bg: BackgroundTasks) -> JSONResponse:
    """Receive one browser event and forward it to Meta as its CAPI twin.

    Enriches the event with the data only the server reliably has: real IP, real
    user-agent, and fbp/fbc (from body, then same-origin cookies, then the
    fbclid in the URL). The ``event_id`` MUST equal the Pixel's eventID so Meta
    deduplicates — if it is missing we still send (server-only) but say so.
    """
    if not payload.event_name:
        return JSONResponse({"ok": False, "error": "event_name boşdur"}, status_code=400)

    ud = dict(payload.user_data or {})

    ip = _client_ip(request)
    if ip and "client_ip_address" not in ud:
        ud["client_ip_address"] = ip
    ua = request.headers.get("user-agent")
    if ua and "client_user_agent" not in ud:
        ud["client_user_agent"] = ua

    # fbp / fbc: body wins (set by the JS bridge from document.cookie), then any
    # same-origin cookie reaching us, then reconstruct fbc from the URL's fbclid.
    if "fbp" not in ud:
        fbp = request.cookies.get("_fbp")
        if fbp:
            ud["fbp"] = fbp
    if "fbc" not in ud:
        fbc = request.cookies.get("_fbc") or _fbc_from_url(payload.event_source_url)
        if fbc:
            ud["fbc"] = fbc

    warnings: list[str] = []
    event_id = payload.event_id
    if not event_id:
        import uuid
        event_id = uuid.uuid4().hex
        warnings.append("event_id yoxdur — Pixel ilə dedup OLMAYACAQ (server-only sayılır). "
                        "Bridge istifadə et ki, eyni event_id hər iki kanala getsin.")

    # Test routing: per-request flag, else the project-wide META_TEST_EVENT_CODE.
    test_code = None
    if payload.test or config.TEST_EVENT_CODE:
        test_code = config.TEST_EVENT_CODE or "GATEWAY_TEST"

    STATS["received"] += 1
    bg.add_task(_dispatch, payload.event_name, ud, payload.custom_data, event_id,
                payload.action_source, payload.event_source_url, payload.event_time,
                test_code)

    return JSONResponse({
        "ok": True,
        "event_id": event_id,
        "test": bool(test_code),
        "dry_run": DRY_RUN,
        # keys only (never values) so the site can confirm match signals server-side
        "match_keys": sorted(ud.keys()),
        "warnings": warnings,
    })


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "dataset": config.active_dataset(),
            "test_mode": bool(config.TEST_EVENT_CODE), "dry_run": DRY_RUN}


@app.get("/stats")
def stats() -> dict:
    return {**STATS, "recent": list(RECENT)}


@app.get("/capi-bridge.js")
def bridge() -> FileResponse:
    return FileResponse(os.path.join(BASE, "static", "capi-bridge.js"),
                        media_type="application/javascript")


@app.get("/demo")
def demo() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "bridge_demo.html"))


@app.get("/")
def index() -> HTMLResponse:
    ds = config.active_dataset() or "(yoxdur)"
    mode = ("DRY-RUN (göndərilmir)" if DRY_RUN
            else "TEST Events" if config.TEST_EVENT_CODE else "PRODUCTION")
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8>
<title>CAPI Gateway</title>
<body style="font-family:system-ui;max-width:640px;margin:40px auto;color:#0f172a">
<h2>🛡️ Meta CAPI Gateway <span style="color:#E31E24">· Xalq Sigorta</span></h2>
<p>Brauzer Pixel-inin server tərəfi əkizi. Hər event həm Pixel, həm CAPI ilə
gedir → adblocker itkisi bağlanır, <code>event_id</code> ilə dedup olunur.</p>
<ul>
  <li>Dataset (Pixel): <b>{ds}</b></li>
  <li>Rejim: <b>{mode}</b></li>
  <li>Snippet: <a href="/capi-bridge.js">/capi-bridge.js</a></li>
  <li>Canlı demo: <a href="/demo">/demo</a></li>
  <li>Statistika: <a href="/stats">/stats</a> · Sağlamlıq: <a href="/healthz">/healthz</a></li>
</ul>
<p style="color:#64748b;font-size:13px">Sayta əlavə et (Pixel base kodundan SONRA):<br>
<code>&lt;script src="http://HOST:8812/capi-bridge.js"&gt;&lt;/script&gt;</code><br>
sonra: <code>capi.track('ViewContent', {{content_name:'KASKO'}});</code></p>
</body>""")
