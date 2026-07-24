"""Marketing OS — the single front door.

One interface for the whole marketing system. The admin opens this, sees every
tool as a category in the sidebar, clicks one, and it loads inside the shell.
Each tool still runs as its own service on its own port; the hub hides that — it
embeds them and shows a live up/down dot per service (checked server-side, so no
browser CORS issues).

    .venv\\Scripts\\python.exe -m uvicorn app:app --port 8000   (or run.ps1)
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import re

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
REGISTRY = os.path.join(ROOT, "services.json")
sys.path.insert(0, ROOT)  # so we can reuse the one audit implementation
import audit_services  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
app = FastAPI(title="Marketing OS Hub")

# --- Self-monitor -----------------------------------------------------------
# Drift only appears when someone ADDS a service without registering it (a
# code-time event, not runtime), so a 24/7 real-time watcher would be waste.
# Instead the always-on hub re-audits on a timer and pings Telegram ONLY when
# the problem-set CHANGES (edge-triggered → no spam). Free: no LLM tokens.
MONITOR = {
    "enabled": os.getenv("HUB_AUDIT_TELEGRAM", "1") != "0",
    "interval_min": int(os.getenv("HUB_AUDIT_INTERVAL_MIN", "60")),
    "last_run": None, "last_ok": None, "last_alert": None,
}
_last_sig: tuple | None = None


def _load_services() -> list[dict]:
    """Single source of truth — every tool comes from services.json, never a
    hardcoded list here. Add a tool there and it shows up automatically."""
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)["services"]


# Cards shown in the sidebar (everything except the hub itself).
def _cards() -> list[dict]:
    # Front-line tools + the legacy monolith (shown apart, under Arxiv, so the
    # sidebar stays a workspace and not a museum). Ordered by job, not by port.
    keys = ("key", "name", "desc", "port", "icon", "cat", "path", "order",
            "legacy", "legacy_note")
    cards = [{k: s.get(k) for k in keys}
             for s in _load_services() if s.get("hub_show") or s.get("legacy")]
    # NB: `or 99` would send order=0 (the panel — the daily driver) to the end.
    return sorted(cards, key=lambda s: 99 if s.get("order") is None else s["order"])


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(BASE, "templates", "portal.html"))


@app.get("/api/services")
def services() -> JSONResponse:
    return JSONResponse(_cards())


@app.get("/api/capabilities")
def capabilities() -> JSONResponse:
    """Port-less organs (slash commands, CLIs, gateway agents) — the sonarzum
    rule: every capability gets a sidebar card saying HOW to invoke it, so no
    organ ever again rusts invisible outside the front door."""
    with open(REGISTRY, encoding="utf-8") as f:
        return JSONResponse(json.load(f).get("capabilities", []))


@app.get("/api/brand")
def brand_info() -> JSONResponse:
    """Brand identity for the shell header — from brand.py (BRAND env), so the
    portal never hardcodes a deployment's name (see docs/BRANDING.md)."""
    try:
        from brand import BRAND
        return JSONResponse({"name": BRAND.name, "system_name": BRAND.system_name})
    except Exception:
        return JSONResponse({"name": "", "system_name": "Marketing OS"})


def _alive(port: int, health: str) -> bool:
    # Probe the declared health path, then fall back to "/". A closed port on
    # Windows can hang on connect, so callers run these concurrently with a
    # short timeout.
    for path in (health, "/"):
        try:
            if requests.get(f"http://127.0.0.1:{port}{path}", timeout=1.0).ok:
                return True
        except requests.RequestException:
            continue
    return False


@app.get("/api/status")
def status() -> JSONResponse:
    cards = [s for s in _load_services() if s.get("hub_show") or s.get("legacy")]
    with ThreadPoolExecutor(max_workers=max(len(cards), 1)) as pool:
        results = pool.map(
            lambda s: (s["key"], _alive(s["port"], s.get("health", "/api/health"))), cards)
    return JSONResponse(dict(results))


def _panel(path: str, default):
    """Read the panel's own API server-side (no CORS, no browser round-trip).
    The panel is the operator's brain; the hub just re-serves its facts."""
    try:
        port = next(s["port"] for s in _load_services() if s["key"] == "panel")
        r = requests.get(f"http://127.0.0.1:{port}{path}", timeout=2.0)
        return r.json() if r.ok else default
    except Exception:
        return default


def _panel_response(method: str, path: str, payload: dict | None = None) -> JSONResponse:
    """Re-serve an internal panel API as part of the one-origin Hub product."""
    try:
        port = next(s["port"] for s in _load_services() if s["key"] == "panel")
        response = requests.request(
            method,
            f"http://127.0.0.1:{port}{path}",
            json=payload,
            timeout=20.0,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"error": "İş masası etibarlı JSON qaytarmadı."}
        return JSONResponse(body, status_code=response.status_code)
    except Exception as exc:
        return JSONResponse(
            {"error": f"İş masası hazırda əlçatan deyil: {type(exc).__name__}"},
            status_code=503,
        )


@app.get("/workdesk")
def workdesk_deep_link() -> RedirectResponse:
    return RedirectResponse(url="/?open=workdesk")


@app.get("/observation")
def observation_deep_link() -> RedirectResponse:
    return RedirectResponse(url="/?open=observation")


@app.get("/council")
def council_deep_link() -> RedirectResponse:
    return RedirectResponse(url="/?open=council")


@app.get("/api/flow")
def flow() -> JSONResponse:
    return _panel_response("GET", "/api/flow")


@app.get("/api/council/status")
def council_status() -> JSONResponse:
    return _panel_response("GET", "/api/council/status")


@app.get("/api/council/runs")
def council_runs(limit: int = 20) -> JSONResponse:
    return _panel_response("GET", f"/api/council/runs?limit={max(1, min(limit, 50))}")


@app.get("/api/council/runs/{run_id}")
def council_run(run_id: str) -> JSONResponse:
    return _panel_response("GET", f"/api/council/runs/{run_id}")


@app.post("/api/council/runs")
async def start_council_run(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"error": "Etibarlı sorğu göndərin."}, status_code=400)
    return _panel_response("POST", "/api/council/runs", {"topic": payload.get("topic", "")})


@app.get("/api/overview")
def overview() -> JSONResponse:
    """The front door opens on a BRIEFING, not on a random tool: what the
    system did, what it needs from you, and whether anything is broken."""
    pulse = _panel("/api/pulse", {})
    deliverables = _panel("/api/deliverables?limit=60", [])
    findings = (_panel("/api/advisor", {}) or {}).get("findings", [])
    cards = [s for s in _load_services() if s.get("hub_show") or s.get("legacy")]
    with ThreadPoolExecutor(max_workers=max(len(cards), 1)) as pool:
        up = list(pool.map(lambda s: _alive(s["port"], s.get("health", "/api/health")), cards))
    day_ago = time.time() - 86400
    return JSONResponse({
        "queue": pulse.get("queue", {}),
        "llm": pulse.get("llm", {}),
        "tools": {"up": sum(up), "total": len(cards)},
        "fresh": sum(1 for d in deliverables if d.get("mtime", 0) > day_ago),
        "deliverables": deliverables[:6],
        "findings": [f for f in findings if f.get("level") in ("risk", "watch")][:3],
        "audit_ok": audit_services.audit_data()["ok"],
    })


def _tcp_up(host: str, port: int) -> bool:
    # External worlds are not ours to HTTP-probe (some are raw TCP: postgres,
    # redis) — a connect() answers "is anybody home" for all of them alike.
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


@app.get("/api/external")
def external() -> JSONResponse:
    """The other worlds on this machine (services.json "external"): visible
    from the front door with a live status dot, but never merged into the
    Marketing OS world — CONTROL-MAP keeps the worlds separate on purpose."""
    with open(REGISTRY, encoding="utf-8") as f:
        entries = json.load(f).get("external", [])
    def probe(e: dict) -> dict:
        out = dict(e)
        out["up"] = (_tcp_up(e.get("host", "127.0.0.1"), e["port"])
                     if e.get("port") else None)
        return out
    with ThreadPoolExecutor(max_workers=max(len(entries), 1)) as pool:
        return JSONResponse(list(pool.map(probe, entries)))


@app.get("/api/audit")
def audit() -> JSONResponse:
    """Registry-vs-reality drift check, same logic the CLI uses (audit_services).
    Lets the admin see blind spots (unregistered ports) from inside the hub."""
    data = audit_services.audit_data()
    data["monitor"] = MONITOR
    return JSONResponse(data)


# ── server-side tool proxy ──────────────────────────────────────────────
# The portal's iframes historically pointed the BROWSER at 127.0.0.1:<port>,
# which only works on the machine that runs the services (or via SSH tunnels).
# This proxy lets ONE exposed origin serve every tool: /t/<key>/<path> forwards
# server-side to the service registered under <key> in services.json. Remote
# access goes hub -> bridge relay -> Caddy (basic_auth) -> the world.

_HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "upgrade",
                "content-encoding", "content-length", "te", "trailers"}
_PROXY_TIMEOUT = 60


def _service_ports() -> dict:
    return {s["key"]: s["port"] for s in _load_services()
            if s.get("key") and s.get("port")}


def _forward(method: str, url: str, params, body: bytes, ctype: str | None):
    headers = {"content-type": ctype} if ctype else {}
    return requests.request(method, url, params=params, data=body or None,
                            headers=headers, timeout=_PROXY_TIMEOUT,
                            allow_redirects=False)


async def _proxy(key: str, path: str, request: Request):
    ports = _service_ports()
    if key not in ports:
        return JSONResponse({"error": f"unknown tool {key!r}"}, status_code=404)
    url = f"http://127.0.0.1:{ports[key]}/{path}"
    body = await request.body()
    try:
        r = await run_in_threadpool(
            _forward, request.method, url, dict(request.query_params), body,
            request.headers.get("content-type"))
    except Exception as exc:  # service down -> readable answer, not a hang
        return JSONResponse({"error": f"{key} əlçatan deyil: {exc}"}, status_code=502)
    out_headers = {k: v for k, v in r.headers.items()
                   if k.lower() not in _HOP_HEADERS and k.lower() != "content-type"}
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type"), headers=out_headers)


@app.api_route("/t/{key}", methods=["GET"])
def tool_root(key: str):
    return RedirectResponse(url=f"/t/{key}/")


@app.api_route("/t/{key}/{path:path}", methods=["GET", "POST"])
async def tool_proxy(key: str, path: str, request: Request):
    return await _proxy(key, path, request)


# ---------- Morning signals: champion verdicts -> approve/reject cards --------
# The research lab's champion loop judges each radar finding (ADOPT/BUILD/SKIP)
# into radar-verdicts.json. Here we surface the ADOPT/BUILD cards still 'new' so
# the operator can approve (adopt) or reject them from the portal on any device --
# the same decision the nightly Telegram brief asks for, now one tap. Twin-safe:
# the Windows twin has no lab, so this degrades to available:false / empty.
LAB_ROOT = "/opt/research-lab"


def _lab_signals() -> dict:
    vf = os.path.join(LAB_ROOT, "radar-verdicts.json")
    sf = os.path.join(LAB_ROOT, "radar-status.json")
    if not os.path.isdir(LAB_ROOT) or not os.path.exists(vf):
        return {"available": False, "cards": []}
    try:
        with open(vf, encoding="utf-8") as fh:
            verdicts = json.load(fh)
    except Exception:
        return {"available": False, "cards": []}
    try:
        with open(sf, encoding="utf-8") as fh:
            status = json.load(fh)
    except Exception:
        status = {}
    scores: dict = {}
    try:  # best-effort score enrichment; brain_bridge is a light stdlib module
        if LAB_ROOT not in sys.path:
            sys.path.insert(0, LAB_ROOT)
        import brain_bridge as _bb  # noqa: E402
        for f in _bb.read_findings():
            scores[f["title"]] = f.get("score")
    except Exception:
        pass
    cards = []
    for title, v in verdicts.items():
        if not isinstance(v, dict) or v.get("verdict") not in ("ADOPT", "BUILD"):
            continue
        if status.get(title, {}).get("status", "new") != "new":
            continue
        cards.append({"title": title, "verdict": v.get("verdict", ""),
                      "why": v.get("why", ""), "action": v.get("action", ""),
                      "ts": v.get("ts", ""), "score": scores.get(title)})
    order = {"ADOPT": 0, "BUILD": 1}
    cards.sort(key=lambda c: (order.get(c["verdict"], 9), -(c.get("score") or 0)))
    return {"available": True, "cards": cards}


@app.get("/api/signals")
async def signals() -> JSONResponse:
    return JSONResponse(await run_in_threadpool(_lab_signals))


@app.post("/api/signals/decide")
async def signals_decide(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    title = (body.get("title") or "").strip()
    decision = (body.get("decision") or "").strip()
    if not title or decision not in ("approve", "reject"):
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    if not os.path.isdir(LAB_ROOT):
        return JSONResponse({"ok": False, "error": "lab not on this host"},
                            status_code=409)
    verb = "adopt" if decision == "approve" else "reject"

    def _run():
        import subprocess
        return subprocess.run(
            ["python3", os.path.join(LAB_ROOT, "brain_bridge.py"), verb, title],
            cwd=LAB_ROOT, capture_output=True, text=True, timeout=120)

    try:
        proc = await run_in_threadpool(_run)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)[:200]}, status_code=500)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and "no finding matches" not in out
    return JSONResponse({"ok": ok, "out": out[-500:], "err": (proc.stderr or "")[-300:]})


# Proxied tool pages often fetch ABSOLUTE paths (fetch("/api/report")). Those
# arrive here instead of at the tool. The Referer names the tool the page came
# from, so forward such strays to it. Registered LAST: every explicit hub route
# above wins first.
@app.api_route("/{path:path}", methods=["GET", "POST"])
async def stray_from_tool(path: str, request: Request):
    m = re.search(r"/t/([a-zA-Z0-9_-]+)/", request.headers.get("referer", ""))
    if m and m.group(1) in _service_ports() and not path.startswith("t/"):
        return await _proxy(m.group(1), path, request)
    return JSONResponse({"error": "not found"}, status_code=404)


def _signature(a: dict) -> tuple:
    """The 'problem set' — drift ports, missing dirs, unshowcased organs.
    Telegram fires only when this changes, so a persistent drift is reported
    once, not every cycle."""
    org = a.get("organs", {})
    return (tuple(d["port"] for d in a["drift"]),
            tuple(s["key"] for s in a["missing_dir"]),
            tuple(org.get("unaccounted", [])),
            tuple(m["key"] for m in org.get("missing_home", [])))


def _monitor_loop() -> None:
    global _last_sig
    time.sleep(20)  # let services finish starting after a boot
    while True:
        try:
            a = audit_services.audit_data()
            MONITOR["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            MONITOR["last_ok"] = a["ok"]
            sig = _signature(a)
            if MONITOR["enabled"] and sig != _last_sig:
                if any(sig):  # a problem exists (new or changed)
                    if audit_services._send_telegram(audit_services._telegram_text(a)):
                        MONITOR["last_alert"] = MONITOR["last_run"]
                elif _last_sig is not None and any(_last_sig):  # problem just cleared
                    audit_services._send_telegram(
                        "✅ Marketing OS — drift aradan qalxdı, hər şey qaydasında.")
                    MONITOR["last_alert"] = MONITOR["last_run"]
            _last_sig = sig
        except Exception:
            pass  # never let the watchdog crash the hub
        time.sleep(max(MONITOR["interval_min"], 5) * 60)


@app.on_event("startup")
def _start_monitor() -> None:
    if MONITOR["interval_min"] > 0:
        threading.Thread(target=_monitor_loop, daemon=True).start()
