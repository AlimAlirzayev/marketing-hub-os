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

import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

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


def _signature(a: dict) -> tuple:
    """The 'problem set' — drift ports + missing dirs. Telegram fires only when
    this changes, so a persistent drift is reported once, not every cycle."""
    return (tuple(d["port"] for d in a["drift"]),
            tuple(s["key"] for s in a["missing_dir"]))


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
                if sig != ((), ()):  # a problem exists (new or changed)
                    if audit_services._send_telegram(audit_services._telegram_text(a)):
                        MONITOR["last_alert"] = MONITOR["last_run"]
                elif _last_sig not in (None, ((), ())):  # problem just cleared
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
