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
    return [{k: s.get(k) for k in ("key", "name", "desc", "port", "icon", "cat", "path")}
            for s in _load_services() if s.get("hub_show")]


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
    cards = [s for s in _load_services() if s.get("hub_show")]
    with ThreadPoolExecutor(max_workers=max(len(cards), 1)) as pool:
        results = pool.map(
            lambda s: (s["key"], _alive(s["port"], s.get("health", "/api/health"))), cards)
    return JSONResponse(dict(results))


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
