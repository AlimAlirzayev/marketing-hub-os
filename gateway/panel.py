"""İdarəetmə Mərkəzi — the admin control center over the free autonomous brain.

Phase 2 of the roadmap (SHARED_CONTEXT.md): one screen where the operator sees
the system's live body (sense.snapshot), the advisor's grounded next moves,
every job (including risky ones parked at the human checkpoint, with one-click
Approve/Reject), schedules, events — and can submit new tasks and trigger an
engine sync. Zero LLM tokens to render: everything is deterministic reads of
the gateway's own state; the free brain does the actual work.

Runs like every other tool (registered in services.json, embedded in the hub):
    python -m uvicorn gateway.panel:app --host 127.0.0.1 --port 8890

Single-user, localhost-only (the launcher binds 127.0.0.1) — same trust model
as the rest of the Marketing OS. Ops actions here mirror the Telegram bot's
owner commands (/approve, /reject, /update); this is the desktop half.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._bootstrap import load_env
from . import advisor, mic, queue, scheduler, sense

load_env()

ROOT = Path(__file__).resolve().parent.parent
_SYNC = ROOT / "scripts" / "sync_engine.py"

app = FastAPI(title="RAMIN OS — İdarəetmə Mərkəzi")

# Live command center (node-map cockpit) — GET /map + GET /api/flow. Kept in its
# own module so it rides this same localhost tunnel without touching the panel UI.
from . import commandcenter  # noqa: E402
commandcenter.register(app)


# --------------------------------------------------------------------------
# API — deterministic reads of the live body + the operator's few writes
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "panel"}


@app.get("/api/pulse")
def pulse() -> JSONResponse:
    return JSONResponse(sense.snapshot())


@app.get("/api/radar")
def radar(refresh: int = 0) -> JSONResponse:
    """Agent Radar + HF radar governance scans — migrated home from the 8501
    Streamlit archive (2026-07-13). Deterministic local scoring (no LLM, no
    network); auto-reruns when the stored scan is older than 24h."""
    from . import agent_radar, hf_radar
    scan = agent_radar.load_latest_scan()
    if refresh or agent_radar.scan_is_stale(scan):
        scan = agent_radar.run_marketing_os_scan()
    hf = hf_radar.load_latest_scan()
    if refresh or hf_radar.scan_is_stale(hf):
        hf = hf_radar.run_hf_scan()
    return JSONResponse({"scan": scan, "hf": hf})


@app.get("/api/advisor")
def advisor_view() -> JSONResponse:
    findings = [f.as_dict() for f in advisor.observe_state()]
    return JSONResponse({"findings": findings})


_ADS_STUDIO = "http://127.0.0.1:8800"


@app.get("/api/finance")
def finance() -> JSONResponse:
    """Cross-process pull from Ads Studio (8800): live spend/budget pacing +
    organic reach, surfaced here so the front office shows the financial
    reality without a separate tab-hop. Best-effort — Ads Studio being down
    must degrade cleanly, never 500 the whole panel."""
    try:
        meta = requests.get(f"{_ADS_STUDIO}/api/meta", timeout=5).json()
        month = meta["months"][0]["value"]
        account = meta.get("default_account")
        report = requests.get(f"{_ADS_STUDIO}/api/report",
                               params={"month": month, "account": account}, timeout=10).json()
        organic = requests.get(f"{_ADS_STUDIO}/api/organic", timeout=10).json()
        return JSONResponse({
            "ok": True,
            "data_mode": meta.get("data_mode"),
            "sym": meta.get("currency_symbol", "$"),
            "account_name": meta.get("account"),
            "period": report["report"]["period"],
            "totals": report["report"]["combined_totals"],
            "pacing": report["analytics"]["pacing"],
            "organic": organic,
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


_LAB_ROOT = "/opt/research-lab"


def _brain_bridge():
    if _LAB_ROOT not in sys.path:
        sys.path.insert(0, _LAB_ROOT)
    import brain_bridge
    return brain_bridge


@app.get("/api/trends")
def trends() -> JSONResponse:
    """Research-lab marketing/creative radar findings, surfaced visually so
    they stop rotting unseen in SHARED_CONTEXT.md (memory: radar bridge,
    2026-07-12). Read-only; adopt/reject reuse the lab's own tested CLI."""
    try:
        bb = _brain_bridge()
        findings = bb.read_findings()
        status = bb._load(bb.STATUS_FILE, {})
        proposals = bb.read_open_proposals()
        out = []
        for f in findings:
            st = status.get(f["title"], {}).get("status", "new")
            idea = bb._short(bb._field(bb.KNOW / f["file"], "Application idea"), 220)
            out.append({**f, "status": st, "idea": idea})
        out.sort(key=lambda f: (0 if f["status"] == "new" else 1, -f["score"]))
        return JSONResponse({"ok": True, "findings": out, "proposals": proposals})
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "findings": [],
            "proposals": [],
            "error_code": "research_lab_unavailable",
            "message": "Research Lab bu maşında əlçatan deyil.",
            "retryable": True,
        })


class TrendAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)


@app.post("/api/trends/{action}")
def trends_action(action: str, body: TrendAction) -> JSONResponse:
    if action not in ("adopt", "reject"):
        return JSONResponse({"ok": False, "error": "bad action"}, status_code=400)
    if not body.title.strip():
        return JSONResponse({"ok": False, "error": "boş başlıq"}, status_code=400)
    try:
        proc = subprocess.run(
            [sys.executable, f"{_LAB_ROOT}/brain_bridge.py", action, body.title],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return JSONResponse({"ok": proc.returncode == 0, "out": (proc.stdout or proc.stderr)[-500:]})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _job_dict(j: queue.Job, preview: int = 400) -> dict:
    return {
        "id": j.id, "source": j.source, "status": j.status, "approved": j.approved,
        "task": j.task,
        "result_preview": (j.result or "")[:preview],
        "error": (j.error or "")[:200],
        "created_at": j.created_at, "finished_at": j.finished_at,
    }


@app.get("/api/jobs")
def jobs(status: str | None = None, limit: int = 30) -> JSONResponse:
    return JSONResponse([_job_dict(j) for j in queue.list_jobs(status=status, limit=limit)])


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int) -> JSONResponse:
    j = queue.get(job_id)
    if j is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    d = _job_dict(j, preview=100_000)
    d["result"] = j.result or ""
    d["artifacts"] = j.artifacts
    return JSONResponse(d)


class NewTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1, max_length=12_000)

    @field_validator("task")
    @classmethod
    def _clean_task(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("tapşırıq boş ola bilməz")
        return value


@app.post("/api/jobs")
def submit(body: NewTask) -> JSONResponse:
    task = (body.task or "").strip()
    if not task:
        return JSONResponse({"error": "boş tapşırıq"}, status_code=400)
    job_id = mic.speak(task, source="panel")
    return JSONResponse({"id": job_id, "status": "queued"})


@app.post("/api/jobs/{job_id}/approve")
def approve(job_id: int) -> JSONResponse:
    ok = queue.approve(job_id)
    if ok:
        sense.emit("job", f"#{job_id} approved (panel)")
    return JSONResponse({"ok": ok})


@app.post("/api/jobs/{job_id}/reject")
def reject(job_id: int) -> JSONResponse:
    ok = queue.reject(job_id)
    if ok:
        sense.emit("job", f"#{job_id} rejected (panel)")
    return JSONResponse({"ok": ok})


@app.get("/api/chat")
def chat_history(n: int = 40) -> JSONResponse:
    """The one-microphone conversation, straight from the shared blackboard —
    what was said on ANY channel (chat, Telegram, Codex, panel), in order."""
    try:
        from brain import blackboard
        blackboard.init()
        turns = blackboard.working_buffer(mic.MIC_THREAD, max_turns=n)
    except Exception:
        turns = []
    return JSONResponse({"thread": mic.MIC_THREAD, "turns": turns})


@app.get("/api/schedules")
def schedules() -> JSONResponse:
    return JSONResponse(scheduler.list_schedules())


@app.get("/api/events")
def events(n: int = 30) -> JSONResponse:
    return JSONResponse(sense.recent(n))


class NewCouncilRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=10, max_length=12_000)


@app.get("/api/council/status")
def council_status() -> JSONResponse:
    """Readiness for the explicit, consultation-only council workspace."""
    from . import council_workspace
    return JSONResponse(council_workspace.availability())


@app.get("/api/council/runs")
def council_runs(limit: int = 20) -> JSONResponse:
    from . import council_workspace
    return JSONResponse(council_workspace.recent(limit))


@app.get("/api/council/runs/{run_id}")
def council_run(run_id: str) -> JSONResponse:
    from . import council_workspace
    found = council_workspace.get(run_id)
    if not found:
        return JSONResponse({"error": "Şura sessiyası tapılmadı."}, status_code=404)
    return JSONResponse(found)


@app.post("/api/council/runs")
def start_council_run(req: NewCouncilRun) -> JSONResponse:
    """Start advice only; execution remains a separate operator decision."""
    from . import council_workspace
    try:
        return JSONResponse(council_workspace.start(req.topic), status_code=202)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/sync")
def sync_now() -> JSONResponse:
    """One-click engine sync — same brain every other trigger uses."""
    try:
        proc = subprocess.run(
            [sys.executable, str(_SYNC)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=90, encoding="utf-8", errors="replace")
        out = (proc.stdout or proc.stderr or "").strip()
        return JSONResponse({"ok": True, "summary": out or "sync bitdi"})
    except Exception as exc:  # sync is best-effort, never a 500
        return JSONResponse({"ok": False, "summary": f"sync alınmadı: {exc.__class__.__name__}"})


# --------------------------------------------------------------------------
# Deliverables — the visual front office: SEE what the system built, don't just
# read a path. Sites preview live in an iframe, images/video inline, reports
# rendered. Files are served ONLY from these output roots (never .env / source).
# --------------------------------------------------------------------------

_DELIVERABLE_ROOTS = [ROOT / "output", ROOT / "workspace", ROOT / "published", ROOT / "data" / "seo"]
# A conversation turn is not a work product. The executor files chat replies and
# operational messages under output/replies; the gallery must never show them as
# "nəticələr" — that is what turned this wall into chat noise. (Still SERVABLE
# via /file, so a job's artifact link keeps working; just not listed.)
_NOT_DELIVERABLE = {ROOT / "output" / "replies"}
_PREVIEW_EXT = {
    ".html", ".htm", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg", ".md", ".pdf",
    ".zip", ".csv", ".json", ".pptx", ".docx",
}
_KIND = {
    "site": {".html", ".htm"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"},
    "video": {".mp4", ".webm", ".mov"},
    "audio": {".mp3", ".wav", ".ogg"},
    "report": {".md"},
    "pdf": {".pdf"},
    "bundle": {".zip"},
}


def _kind_of(ext: str) -> str:
    for k, exts in _KIND.items():
        if ext in exts:
            return k
    return "file"


_META_CACHE: dict[str, tuple[float, dict]] = {}


def _content_meta(p: Path, kind: str) -> dict:
    """Human title + text snippet so content tiles read as CONTENT, not as
    anonymous job-NN.md file icons. Cached per (path, mtime) — the gallery
    polls once a minute and files rarely change."""
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    key = str(p)
    hit = _META_CACHE.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    meta: dict = {}
    try:
        if kind == "report":
            text = p.read_text(errors="ignore")[:4000]
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            title = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("#")), None)
            if not title and lines:
                title = lines[0]
            body = " ".join(ln for ln in lines if not ln.startswith("#"))
            body = re.sub(r"[*_`>#|-]|\[|\]|\(http\S+\)", "", body)
            meta = {"title": (title or p.stem)[:90], "snippet": body.strip()[:220]}
        elif kind == "site":
            head = p.read_text(errors="ignore")[:2000]
            m = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
            if m and m.group(1).strip():
                meta = {"title": m.group(1).strip()[:90]}
    except OSError:
        meta = {}
    _META_CACHE[key] = (mt, meta)
    return meta


def _safe_resolve(rel_path: str) -> Path | None:
    """Resolve a requested path and allow it ONLY if it lives inside a
    deliverable root. This is the guard against path traversal and against ever
    serving .env, secrets, or source from elsewhere in the repo."""
    try:
        target = (ROOT / rel_path).resolve()
    except Exception:
        return None
    for root in _DELIVERABLE_ROOTS:
        try:
            target.relative_to(root.resolve())
        except ValueError:
            continue
        return target if target.is_file() else None
    return None


@app.get("/file/{file_path:path}")
def serve_file(file_path: str):
    """Serve a deliverable (sandboxed to the output roots). Path-based so an
    HTML site's relative assets (css/js/img) resolve correctly in the iframe."""
    target = _safe_resolve(file_path)
    if target is None:
        return JSONResponse({"error": "not found or not allowed"}, status_code=404)
    return FileResponse(str(target))


def _site_dirs() -> list[Path]:
    """Directories that ARE a website (contain index.html). A multi-file site
    shows as ONE tile whose iframe loads index.html — its relative css/js/img
    resolve through the path-based /file route, so the preview is the real site.
    Nested index.htmls collapse into the shallowest site dir."""
    dirs: list[Path] = []
    for root in _DELIVERABLE_ROOTS:
        if root.exists():
            dirs += [p.parent for p in root.rglob("index.html")]
    return [d for d in dirs if not any(o != d and o in d.parents for o in dirs)]


@app.get("/api/deliverables")
def deliverables(limit: int = 60) -> JSONResponse:
    """Everything the system produced, newest first, classified for visual
    review. Multi-file sites are grouped into one entry; loose files listed
    individually."""
    items: dict[str, dict] = {}
    sites = _site_dirs()

    def _site_of(p: Path) -> Path | None:
        return next((d for d in sites if d == p.parent or d in p.parents), None)

    def _excluded(p: Path) -> bool:
        return any(d == p.parent or d in p.parents for d in _NOT_DELIVERABLE)

    for root in _DELIVERABLE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or _excluded(p):
                continue
            site = _site_of(p)
            if site is not None:
                # everything inside a site dir folds into ONE site tile
                idx = site / "index.html"
                if p != idx:
                    continue
                try:
                    rel = idx.relative_to(ROOT).as_posix()
                    stat = idx.stat()
                except (ValueError, OSError):
                    continue
                entry = {
                    "name": site.name, "path": rel, "url": f"/file/{rel}",
                    "kind": "site", "size": stat.st_size, "mtime": stat.st_mtime,
                }
                entry.update(_content_meta(idx, "site"))
                items[rel] = entry
                continue
            if p.suffix.lower() not in _PREVIEW_EXT:
                continue
            try:
                rel = p.relative_to(ROOT).as_posix()
                stat = p.stat()
            except (ValueError, OSError):
                continue
            entry = {
                "name": p.name,
                "path": rel,
                "url": f"/file/{rel}",
                "kind": _kind_of(p.suffix.lower()),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
            if entry["kind"] == "report":
                entry.update(_content_meta(p, "report"))
            items[rel] = entry
    ordered = sorted(items.values(), key=lambda d: d["mtime"], reverse=True)
    return JSONResponse(ordered[:limit])


# --------------------------------------------------------------------------
# UI v4 "Studio" — content-first front office, zero external assets
# (corporate-offline safe). Light editorial look by default, dark via toggle.
# Three rooms: Studiya (talk + approve + latest), Nəticələr (the gallery),
# Mühərrik (all engineering telemetry, demoted out of the operator's face).
# NOTE: _HTML is a plain (non-raw) Python string — JS regexes must write
# backslash-n as \\n or Python eats it and the inline script breaks.
# --------------------------------------------------------------------------

_HTML = """<!doctype html>
<html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ramin Studio — İdarəetmə Mərkəzi</title>
<style>
/* ── design tokens: light editorial (default) + dark ───────────── */
:root{
  --bg:#f4f3f0; --card:#ffffff; --card2:#f8f7f4; --thumb:#edece8;
  --ink:#1b1d23; --ink2:#4d5361; --mut:#626875;
  --line:#e5e3dd; --line2:#d3d0c8;
  --acc:#4338ca; --acc-soft:#eceefc; --acc-line:#c7cdf4;
  --ok:#087f5b; --ok-soft:#e3f5ee; --warn:#9a5b00; --warn-soft:#fdf2df;
  --bad:#c92a2a; --bad-soft:#fdecec;
  --btn:#1b1d23; --btnink:#ffffff;
  --r-lg:16px; --r-md:12px; --r-sm:9px;
  --shadow:0 1px 2px rgba(28,25,15,.04),0 10px 30px rgba(28,25,15,.06);
}
:root[data-theme="dark"]{
  --bg:#0d1117; --card:#151b24; --card2:#1a2230; --thumb:#0f141c;
  --ink:#edf2f8; --ink2:#9fb0c2; --mut:#6d8093;
  --line:rgba(148,163,184,.15); --line2:rgba(148,163,184,.3);
  --acc:#8b93f8; --acc-soft:rgba(129,140,248,.14); --acc-line:rgba(129,140,248,.4);
  --ok:#34d399; --ok-soft:rgba(52,211,153,.12); --warn:#fbbf24; --warn-soft:rgba(251,191,36,.1);
  --bad:#f87171; --bad-soft:rgba(248,113,113,.12);
  --btn:#edf2f8; --btnink:#10141b;
  --shadow:0 1px 0 rgba(255,255,255,.03) inset,0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box;margin:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);
  font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh;
  transition:background .2s,color .2s}
::selection{background:var(--acc-soft)}
button{font:inherit;cursor:pointer;border:0;background:none;color:inherit}
button:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
a{color:var(--acc)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
svg.i{width:16px;height:16px;flex:none}

/* ── topbar: brand · tabs · live · theme ───────────────────────── */
.topbar{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:16px;
  padding:12px 26px;background:color-mix(in srgb,var(--bg) 86%,transparent);
  backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:11px;white-space:nowrap}
.mark{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;
  background:var(--btn);color:var(--btnink);font-weight:800;font-size:16px;
  font-family:Georgia,"Times New Roman",serif}
.bt{font-size:16px;font-weight:700;letter-spacing:.2px}
.bt em{font-family:Georgia,"Times New Roman",serif;font-style:italic;font-weight:500;color:var(--acc)}
.bt small{display:block;font-size:10.5px;font-weight:500;color:var(--mut);letter-spacing:.8px;
  text-transform:uppercase;line-height:1.2}
.tabs{display:flex;gap:4px;background:var(--card2);border:1px solid var(--line);
  border-radius:999px;padding:4px}
.tab{border-radius:999px;padding:7px 17px;font-size:13.5px;font-weight:600;color:var(--mut);
  transition:all .15s;display:flex;align-items:center;gap:7px}
.tab:hover{color:var(--ink)}
.tab.on{background:var(--card);color:var(--ink);box-shadow:var(--shadow)}
.tcnt{font-size:10.5px;background:var(--acc-soft);color:var(--acc);border-radius:999px;
  padding:1px 7px;font-variant-numeric:tabular-nums}
.tcnt:empty{display:none}
.sp{flex:1}
.live{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink2);white-space:nowrap}
.live .dot{width:8px;height:8px;border-radius:50%;background:var(--ok);
  box-shadow:0 0 0 0 var(--ok-soft);animation:pulse 2.2s infinite}
.live.err .dot{background:var(--bad);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 var(--ok-soft)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
.ibtn{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;
  border:1px solid var(--line);background:var(--card);color:var(--ink2);transition:all .15s}
.ibtn:hover{color:var(--ink);border-color:var(--line2)}
.ibtn svg{width:16px;height:16px}

/* ── shared primitives ─────────────────────────────────────────── */
main{max-width:1380px;margin:0 auto;padding:22px 26px 60px}
.page{display:none}
.page.on{display:block;animation:fadein .18s ease-out}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow)}
.pad{padding:20px}
h3{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.3px;color:var(--mut);
  margin-bottom:14px;display:flex;align-items:center;gap:8px}
h3 .lnk{margin-left:auto;font-size:12px;font-weight:600;text-transform:none;letter-spacing:0;
  color:var(--acc);cursor:pointer}
.muted{color:var(--mut)} .mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.btn{display:inline-flex;align-items:center;gap:8px;border-radius:11px;padding:9px 16px;
  font-weight:600;font-size:13.5px;transition:all .15s}
.btn:active{transform:translateY(1px)}
.btn.primary{background:var(--btn);color:var(--btnink)}
.btn.primary:hover{opacity:.88}
.btn.ghost{background:var(--card);color:var(--ink);border:1px solid var(--line)}
.btn.ghost:hover{border-color:var(--line2);background:var(--card2)}
.btn.good{background:var(--ok-soft);color:var(--ok);border:1px solid var(--ok)}
.btn.danger{background:var(--bad-soft);color:var(--bad);border:1px solid var(--bad)}
.btn:disabled{opacity:.5;cursor:wait}
.btn svg{width:15px;height:15px}
.badge{background:var(--card);border:1px solid var(--line);border-radius:999px;
  padding:5px 13px;font-size:12.5px;color:var(--ink2);white-space:nowrap}
.badge b{color:var(--ink);font-variant-numeric:tabular-nums}

/* ── STUDIYA: approvals + chat + aside ─────────────────────────── */
.approvalbar{background:var(--warn-soft);border:1px solid var(--warn);border-radius:var(--r-lg);
  padding:16px 20px;margin-bottom:18px}
.approvalbar h3{color:var(--warn);margin-bottom:10px}
.approval{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:8px 0}
.approval .t{flex:1;min-width:220px;font-size:14px}
.approval .t b{color:var(--warn)}
.stgrid{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:20px;align-items:start}
@media (max-width:1000px){.stgrid{grid-template-columns:1fr}}
.stside{display:flex;flex-direction:column;gap:18px}
.chatcard{display:flex;flex-direction:column;padding:20px;height:calc(100vh - 200px);min-height:460px}
.chat{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:12px;padding:4px 2px;
  scrollbar-width:thin;scrollbar-color:var(--line2) transparent}
.bubble{position:relative;max-width:82%;padding:11px 15px;border-radius:15px;font-size:14px;
  line-height:1.6;white-space:pre-wrap;word-break:break-word}
.bubble.user{align-self:flex-end;background:var(--acc-soft);border:1px solid var(--acc-line);
  border-bottom-right-radius:5px}
.bubble.assistant{align-self:flex-start;background:var(--card2);border:1px solid var(--line);
  border-bottom-left-radius:5px}
.bubble .src{display:block;font-size:10px;color:var(--mut);margin-bottom:4px;
  text-transform:uppercase;letter-spacing:.7px}
.bubble.pending{opacity:.6;font-style:italic}
.bubble .cpy{position:absolute;top:-10px;right:8px;background:var(--card);border:1px solid var(--line2);
  color:var(--ink2);border-radius:7px;padding:2px 9px;font-size:10.5px;opacity:0;transition:opacity .15s}
.bubble:hover .cpy{opacity:1}
.bubble .more{display:block;color:var(--acc);cursor:pointer;font-size:12px;font-weight:600;margin-top:6px}
.bubble b{font-weight:700}
.bubble code,.mdoc code{background:var(--thumb);border:1px solid var(--line);border-radius:5px;
  padding:1px 5px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
.bubble .mh{display:inline-block;font-weight:700;color:var(--acc)}
.mdoc .mh{display:inline-block;font-weight:700;font-size:17px;color:var(--ink)}
.bubble .mli,.mdoc .mli{color:var(--acc);font-weight:700}
.bubble pre.mcb,.mdoc pre.mcb{background:var(--thumb);border:1px solid var(--line);border-radius:8px;
  padding:9px 11px;margin:4px 0;font-size:12px;overflow-x:auto;white-space:pre-wrap;color:var(--ink2)}
.mdoc{padding:28px;white-space:pre-wrap;color:var(--ink);font:14.5px/1.7 system-ui;word-break:break-word}
.mdoc b{font-weight:700}
.composer{display:flex;gap:9px;margin-top:14px;align-items:flex-end}
.composer textarea{flex:1;background:var(--card2);border:1px solid var(--line);border-radius:13px;
  color:var(--ink);padding:12px 14px;font:inherit;font-size:14px;min-height:50px;max-height:150px;resize:vertical}
.composer textarea::placeholder{color:var(--mut)}
.composer .send{width:50px;height:50px;border-radius:13px;flex:none;display:grid;place-items:center;
  background:var(--btn);color:var(--btnink)}
.composer .send:hover{opacity:.88}
.composer .send svg{width:19px;height:19px}
.composer .micb{width:50px;height:50px;border-radius:13px;flex:none;display:grid;place-items:center;
  background:var(--card2);border:1px solid var(--line);color:var(--ink2)}
.composer .micb:hover{border-color:var(--line2);color:var(--ink)}
.composer .micb svg{width:19px;height:19px}
.composer .micb.rec{background:var(--bad-soft);border-color:var(--bad);color:var(--bad);
  animation:recpulse 1.4s infinite}
@keyframes recpulse{0%{box-shadow:0 0 0 0 var(--bad-soft)}70%{box-shadow:0 0 0 8px transparent}100%{box-shadow:0 0 0 0 transparent}}
#msg{font-size:12.5px;color:var(--ok);min-height:17px;margin-top:7px}
.trow{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:14px}
.trow:last-child{border-bottom:0}
.trow .v{margin-left:auto;font-weight:700;font-variant-numeric:tabular-nums}
.trow.hot .v{color:var(--warn)}
.rrow{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line);cursor:pointer}
.rrow:last-child{border-bottom:0}
.rrow:hover .rt{color:var(--acc)}
.rthumb{width:44px;height:44px;border-radius:10px;background:var(--thumb);border:1px solid var(--line);
  display:grid;place-items:center;overflow:hidden;flex:none;color:var(--mut)}
.rthumb img{width:100%;height:100%;object-fit:cover}
.rthumb svg{width:19px;height:19px}
.rtx{min-width:0}
.rt{display:block;font-size:13.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rs{display:block;font-size:11.5px;color:var(--mut);margin-top:1px}
.sug{color:var(--acc);font-size:12.5px;margin-top:5px}

/* ── NƏTİCƏLƏR: toolbar + content-first gallery ────────────────── */
.gtools{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.gsearch{background:var(--card);border:1px solid var(--line);border-radius:999px;color:var(--ink);
  padding:8px 16px;font:inherit;font-size:13px;width:200px}
.gsearch::placeholder{color:var(--mut)}
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{background:var(--card);border:1px solid var(--line);color:var(--ink2);border-radius:999px;
  padding:6px 14px;font-size:12.5px;font-weight:600;transition:all .15s}
.chip:hover{border-color:var(--line2);color:var(--ink)}
.chip.on{background:var(--btn);border-color:var(--btn);color:var(--btnink)}
.chip .cnt{margin-left:6px;font-size:10.5px;opacity:.65;font-variant-numeric:tabular-nums}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:16px}
.gtile{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;
  cursor:pointer;display:flex;flex-direction:column;box-shadow:var(--shadow);
  transition:transform .16s,border-color .16s}
.gtile:hover{border-color:var(--acc-line);transform:translateY(-3px)}
.thumb{height:158px;background:var(--thumb);display:flex;align-items:center;justify-content:center;
  overflow:hidden;position:relative;border-bottom:1px solid var(--line)}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb iframe{width:200%;height:316px;transform:scale(.5);transform-origin:0 0;border:0;
  pointer-events:none;background:#fff}
.thumb .gic{width:34px;height:34px;color:var(--mut)}
.rprev{align-self:stretch;width:100%;padding:14px 15px;text-align:left;background:var(--card2)}
.rprev b{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  font-size:13.5px;line-height:1.45;color:var(--ink)}
.rprev p{display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;
  font-size:12px;line-height:1.55;color:var(--ink2);margin-top:7px}
.tmeta{padding:11px 13px}
.tmeta .nm{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tmeta .kd{font-size:11.5px;color:var(--mut);margin-top:5px;display:flex;justify-content:space-between;
  align-items:center;font-variant-numeric:tabular-nums}
.kbadge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  border-radius:5px;padding:2px 8px}
.kbadge.site{background:var(--acc-soft);color:var(--acc)}
.kbadge.image{background:var(--acc-soft);color:var(--acc)}
.kbadge.report{background:var(--ok-soft);color:var(--ok)}
.kbadge.video,.kbadge.audio{background:var(--warn-soft);color:var(--warn)}
.kbadge.bundle,.kbadge.file,.kbadge.pdf{background:var(--thumb);color:var(--ink2)}
.gempty{grid-column:1/-1;text-align:center;padding:70px 20px;color:var(--mut)}
.gempty svg{width:36px;height:36px;margin-bottom:12px;opacity:.6}

/* ── MÜHƏRRİK: telemetry demoted here ──────────────────────────── */
.engbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:18px}
@media (max-width:900px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:16px 17px;box-shadow:var(--shadow)}
.tile .k{font-size:10.5px;text-transform:uppercase;letter-spacing:1px;color:var(--mut);font-weight:700}
.tile .v{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2;margin-top:6px}
.tile .s{font-size:12px;color:var(--mut);margin-top:2px}
.tile.warn .v{color:var(--warn)}
section.card{margin-bottom:18px}

/* ── MALİYYƏ + TRENDLƏR ────────────────────────────────────────── */
.pbar{height:9px;border-radius:999px;background:var(--card2);border:1px solid var(--line);overflow:hidden}
.pbar i{display:block;height:100%;border-radius:999px;background:var(--acc)}
.pbar.warn i{background:var(--warn)} .pbar.over i{background:var(--bad)} .pbar.good i{background:var(--ok)}
.finrow{display:flex;justify-content:space-between;align-items:baseline;font-size:13px;margin-bottom:6px}
.finrow b{font-variant-numeric:tabular-nums}
.trendcard{border:1px solid var(--line);border-radius:var(--r-md);padding:13px 15px;margin-bottom:10px;background:var(--card)}
.trendcard .hd{display:flex;align-items:center;gap:9px;margin-bottom:4px}
.trendscore{font-size:11px;font-weight:800;border-radius:6px;padding:2px 8px;background:var(--acc-soft);color:var(--acc);white-space:nowrap}
.trendtitle{font-weight:700;font-size:14px;line-height:1.3}
.trenddate{font-size:11px;color:var(--mut);white-space:nowrap;margin-left:auto}
.trendidea{font-size:12.5px;color:var(--ink2);margin-top:5px;line-height:1.5}
.trendactions{display:flex;gap:8px;margin-top:9px}
.trendcard.adopted{opacity:.55} .trendcard.rejected{opacity:.4}
.find{display:flex;gap:11px;padding:11px 2px;border-bottom:1px solid var(--line);font-size:13.5px}
.find:last-child{border-bottom:0}
.lvl{font-size:10.5px;font-weight:700;border-radius:6px;padding:3px 9px;height:fit-content;
  white-space:nowrap;text-transform:uppercase;letter-spacing:.5px}
.lvl.risk{background:var(--bad-soft);color:var(--bad)}
.lvl.watch{background:var(--warn-soft);color:var(--warn)}
.lvl.info{background:var(--acc-soft);color:var(--acc)}
.find .d{color:var(--ink2)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{color:var(--mut);text-align:left;font-weight:700;font-size:11px;text-transform:uppercase;
  letter-spacing:.8px;padding:7px 9px;border-bottom:1px solid var(--line2)}
td{padding:9px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
.st{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 11px;
  font-size:11.5px;font-weight:600;white-space:nowrap}
.st::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.st.done{background:var(--ok-soft);color:var(--ok)}
.st.queued,.st.running{background:var(--acc-soft);color:var(--acc)}
.st.error,.st.rejected{background:var(--bad-soft);color:var(--bad)}
.st.awaiting_approval{background:var(--warn-soft);color:var(--warn)}
details summary{cursor:pointer;color:var(--acc);font-size:12.5px;font-weight:600}
pre{white-space:pre-wrap;font-size:12px;color:var(--ink2);margin-top:7px;max-height:300px;
  overflow:auto;background:var(--card2);border:1px solid var(--line);border-radius:9px;padding:11px}
.ev{display:flex;gap:10px;font-size:13px;color:var(--ink2);padding:8px 0;
  border-bottom:1px dashed var(--line);align-items:baseline}
.ev:last-child{border-bottom:0}
.ev .lamp{width:7px;height:7px;border-radius:50%;background:var(--acc);flex:none;transform:translateY(-1px)}
.ev time{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--mut);flex:none}
.ev b{color:var(--ink)}

/* ── modal & toast ─────────────────────────────────────────────── */
.modal{position:fixed;inset:0;background:rgba(22,20,14,.55);backdrop-filter:blur(4px);
  display:none;align-items:center;justify-content:center;z-index:60;padding:20px}
:root[data-theme="dark"] .modal{background:rgba(2,4,8,.75)}
.modal.on{display:flex}
.mbox{background:var(--card);border:1px solid var(--line2);border-radius:var(--r-lg);
  width:min(1150px,96vw);height:90vh;display:flex;flex-direction:column;overflow:hidden;
  box-shadow:0 30px 80px rgba(10,8,4,.35)}
.mbar{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}
.mbar .nm{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mbar a{text-decoration:none}
.mbody{flex:1;overflow:auto;background:var(--card2)}
.mbody iframe{width:100%;height:100%;border:0;background:#fff}
.mbody img{max-width:100%;display:block;margin:0 auto}
#toasts{position:fixed;right:18px;bottom:18px;z-index:70;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--card);border:1px solid var(--line2);border-left:3px solid var(--ok);
  border-radius:10px;padding:11px 15px;font-size:13px;box-shadow:var(--shadow);max-width:340px;
  animation:slidein .2s ease-out}
.toast.err{border-left-color:var(--bad)}
@keyframes slidein{from{transform:translateX(20px);opacity:0}to{transform:none;opacity:1}}
@media (max-width:760px){
  .topbar{flex-wrap:wrap;gap:10px}.tabs{order:3;width:100%;justify-content:stretch}
  .tab{flex:1;justify-content:center}.bt small{display:none}
  main{padding:16px 14px 50px}.chatcard{height:auto;min-height:0}.chat{max-height:46vh}
}
body.embedded .topbar{padding:8px 18px;gap:8px;background:var(--bg)}
body.embedded .topbar .brand,body.embedded .topbar>.sp,
body.embedded .topbar .live,body.embedded .topbar #thBtn{display:none}
body.embedded .tabs{width:100%;overflow-x:auto;scrollbar-width:thin}
body.embedded .tab{min-height:40px;white-space:nowrap}
body.embedded main{padding-top:18px}
body.embedded .page{min-height:calc(100vh - 92px)}
</style></head><body>

<header class="topbar">
  <div class="brand">
    <div class="mark">R</div>
    <div class="bt">Ramin <em>Studio</em><small>İdarəetmə Mərkəzi</small></div>
  </div>
  <nav class="tabs">
    <button class="tab" data-t="studiya" onclick="showTab('studiya')">Studiya</button>
    <button class="tab" data-t="maliyye" onclick="showTab('maliyye')">Maliyyə</button>
    <button class="tab" data-t="neticeler" onclick="showTab('neticeler')">Nəticələr<span class="tcnt" id="tabCnt"></span></button>
    <button class="tab" data-t="trendler" onclick="showTab('trendler')">Trendlər<span class="tcnt" id="trendCnt"></span></button>
    <button class="tab" data-t="muherrik" onclick="showTab('muherrik')">Mühərrik</button>
  </nav>
  <span class="sp"></span>
  <div class="live" id="liveDot"><span class="dot"></span><span id="liveTxt">canlı</span></div>
  <button class="ibtn" id="thBtn" onclick="flipTheme()" title="Tema">
    <svg id="thIcMoon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>
    <svg id="thIcSun" style="display:none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
  </button>
</header>

<main>

<!-- ═══ STUDIYA — talk, approve, see the latest ═══ -->
<section class="page" id="page-studiya">

  <div class="approvalbar" id="approvalsWrap" style="display:none">
    <h3>Təsdiq gözləyir — bayıra yönəlik əməllər</h3>
    <div id="approvals"></div>
  </div>

  <div class="stgrid">
    <div class="card chatcard">
      <h3>Söhbət — bir mikrofon
        <span class="lnk" style="cursor:default;color:var(--mut)">bura · Telegram · Codex — bir yaddaş</span></h3>
      <div class="chat" id="chat"><div class="muted">yüklənir…</div></div>
      <div class="composer">
        <textarea id="task" placeholder="Danış… (məs.: KASKO üçün 3 kampaniya ideyası hazırla)"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();submitTask();}"></textarea>
        <button class="micb" id="micBtn" onclick="toggleMic()" title="Səslə de (az-AZ)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
        </button>
        <button class="send" onclick="submitTask()" title="Göndər (Enter)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4Z"/></svg>
        </button>
      </div>
      <div id="msg"></div>
    </div>

    <aside class="stside">
      <div class="card pad">
        <h3>Bu gün</h3>
        <div id="today" class="muted">yüklənir…</div>
      </div>
      <div class="card pad">
        <h3>Son nəticələr <span class="lnk" onclick="showTab('neticeler')">hamısı →</span></h3>
        <div id="recents" class="muted">yüklənir…</div>
      </div>
      <div class="card pad" id="hintCard" style="display:none">
        <h3>Məsləhət</h3>
        <div id="topHint"></div>
      </div>
    </aside>
  </div>
</section>

<!-- ═══ MALİYYƏ — live spend/budget/pacing, pulled from Ads Studio (8800) ═══ -->
<section class="page" id="page-maliyye">
  <div class="engbar">
    <span class="badge" id="finPeriod">…</span>
    <span class="sp"></span>
    <a class="btn ghost" href="http://localhost:8800" target="_blank">↗ Tam Ads Studio</a>
    <button class="btn ghost" onclick="loadFinance()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 2.6-6.3M3 3v6h6"/></svg>
      Yenilə</button>
  </div>
  <div id="finBody"><div class="muted">yüklənir…</div></div>
</section>

<!-- ═══ NƏTİCƏLƏR — the content gallery, the real product ═══ -->
<section class="page" id="page-neticeler">
  <div class="gtools">
    <input class="gsearch" id="gq" placeholder="ada və ya başlığa görə axtar…" oninput="setQuery(this.value)">
    <div class="chips" id="delChips"></div>
    <span class="sp"></span>
    <button class="ibtn" onclick="loadDeliverables()" title="Yenilə">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 2.6-6.3M3 3v6h6"/></svg>
    </button>
  </div>
  <div class="gallery" id="gallery"><div class="muted">yüklənir…</div></div>
</section>

<!-- ═══ TRENDLƏR — research-lab marketing/creative radar, made visible ═══ -->
<section class="page" id="page-trendler">
  <div class="engbar">
    <span class="badge" id="trendMeta">…</span>
    <span class="sp"></span>
    <button class="btn ghost" onclick="loadTrends()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 2.6-6.3M3 3v6h6"/></svg>
      Yenilə</button>
  </div>
  <section class="card pad" id="trendProposalsWrap" style="display:none">
    <h3>Açıq tikinti təklifləri (engineer/builder loops)</h3>
    <div id="trendProposals"></div>
  </section>
  <section class="card pad">
    <h3>Açıq tapıntılar — hələ heç kim əməl etməyib
      <span class="lnk" style="cursor:default;color:var(--mut)">tədqiqat lab · VPS-də hər 3 gündə bir</span></h3>
    <div id="trendList" class="muted">yüklənir…</div>
  </section>
</section>

<!-- ═══ MÜHƏRRİK — the engine room: telemetry lives here now ═══ -->
<section class="page" id="page-muherrik">
  <div class="engbar">
    <span class="badge" id="git">git: …</span>
    <span class="badge" id="cost">LLM bu gün: …</span>
    <span class="sp"></span>
    <button class="btn ghost" id="syncBtn" onclick="doSync()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-2.6-6.3M21 3v6h-6"/></svg>
      Engine sync</button>
    <button class="btn ghost" onclick="refresh()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 2.6-6.3M3 3v6h6"/></svg>
      Yenilə</button>
  </div>
  <div class="tiles" id="cards"></div>
  <section class="card pad">
    <h3>Məsləhətçi — növbəti ən yaxşı addımlar
      <span class="lnk" style="cursor:default;color:var(--mut)">canlı fakt · LLM-siz</span></h3>
    <div id="advisor" class="muted">yüklənir…</div>
  </section>
  <section class="card pad">
    <h3>Son işlər</h3>
    <div style="overflow-x:auto">
    <table><thead><tr><th>#</th><th>Status</th><th>Mənbə</th><th>Tapşırıq</th><th>Vaxt</th><th>Nəticə</th></tr></thead>
    <tbody id="jobs"></tbody></table>
    </div>
  </section>
  <section class="card pad">
    <h3>Son hadisələr</h3>
    <div id="events" class="muted">yüklənir…</div>
  </section>
  <section class="card pad">
    <h3>Agent Radar — avtomatik governance
      <span class="lnk" onclick="loadRadar(1)">↻ yenidən skan et</span></h3>
    <div id="radar" class="muted">yüklənir…</div>
  </section>
</section>

</main>

<div class="modal" id="modal" onclick="if(event.target.id==='modal')closeModal()">
  <div class="mbox">
    <div class="mbar">
      <span class="nm" id="mNm"></span>
      <a class="badge" id="mOpen" target="_blank">↗ tam aç</a>
      <a class="badge" id="mDl" download>⬇ yüklə</a>
      <button class="btn ghost" onclick="closeModal()" style="padding:6px 10px">✕</button>
    </div>
    <div class="mbody" id="mBody"></div>
  </div>
</div>
<div id="toasts"></div>

<script>
const $=id=>document.getElementById(id);
const _tabLoaded=new Set();
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
/* tiny safe markdown: escape FIRST, then transform — only whitelisted tags come out.
   Inline-style output on purpose: bubbles/mdoc are pre-wrap, newlines already render. */
function md(t){
  const cbs=[];
  let h=esc(t).replace(/```(\\w*)\\n?([\\s\\S]*?)```/g,(m,l,c)=>{cbs.push(c);return "§CB"+(cbs.length-1)+"§";});
  h=h
    .replace(/`([^`\\n]+)`/g,'<code>$1</code>')
    .replace(/^#{1,4} (.+)$/gm,'<span class="mh">$1</span>')
    .replace(/\\*\\*([^*\\n]+)\\*\\*/g,'<b>$1</b>')
    .replace(/\\[([^\\]]+)\\]\\((https?:[^)\\s]+)\\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^[ \\t]*[-*•] /gm,'<span class="mli">• </span>')
    .replace(/^---+$/gm,'───');
  return h.replace(/§CB(\\d+)§/g,(m,i)=>`<pre class="mcb">${cbs[+i].trimEnd()}</pre>`);
}
async function j(url,opt){
  const r=await fetch(url,opt);let data;
  try{data=await r.json();}catch(e){throw new Error(`HTTP ${r.status}: JSON cavabı alınmadı`);}
  if(!r.ok)throw new Error(data.message||data.error||`HTTP ${r.status}`);
  return data;
}
function toast(txt,err){
  const t=document.createElement("div");t.className="toast"+(err?" err":"");t.textContent=txt;
  $("toasts").appendChild(t);setTimeout(()=>t.remove(),4200);
}
function ago(ts){
  if(!ts)return"";
  let ms=typeof ts==="number"?(ts>2e10?ts:ts*1000):Date.parse(ts);
  if(!ms||isNaN(ms))return"";
  const s=(Date.now()-ms)/1000;
  if(s<60)return"indicə"; if(s<3600)return Math.floor(s/60)+" dəq əvvəl";
  if(s<86400)return Math.floor(s/3600)+" saat əvvəl";
  return Math.floor(s/86400)+" gün əvvəl";
}
const ST_AZ={queued:"növbədə",running:"işləyir",done:"hazır",error:"xəta",
  awaiting_approval:"təsdiq gözləyir",rejected:"imtina"};
const KIND_AZ={site:"sayt",image:"şəkil",report:"hesabat",video:"video",audio:"audio",
  bundle:"paket",pdf:"pdf",file:"fayl"};
function _gicon(k){
  const p={
    site:'<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>',
    report:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M16 13H8M16 17H8"/>',
    video:'<path d="m22 8-6 4 6 4V8Z"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
    audio:'<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    bundle:'<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="M3.3 7l8.7 5 8.7-5M12 22V12"/>',
    pdf:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
    file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>'
  }[k]||"";
  return `<svg class="gic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
}

/* ── tabs & theme ── */
function showTab(t){
  document.querySelectorAll(".page").forEach(p=>p.classList.toggle("on",p.id==="page-"+t));
  document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
  try{localStorage.setItem("rs-tab",t);}catch(e){}
  if(!_tabLoaded.has(t)){
    _tabLoaded.add(t);
    if(t==="studiya"||t==="neticeler")loadDeliverables();
    if(t==="maliyye")loadFinance();
    if(t==="trendler")loadTrends();
    if(t==="muherrik")loadRadar(0);
  }
}
function applyTheme(t){
  document.documentElement.dataset.theme=t;
  try{localStorage.setItem("rs-theme",t);}catch(e){}
  $("thIcSun").style.display=t==="dark"?"block":"none";
  $("thIcMoon").style.display=t==="dark"?"none":"block";
}
function flipTheme(){applyTheme((document.documentElement.dataset.theme||"light")==="light"?"dark":"light");}

/* ── deliverables — the content gallery ── */
let _deliverables=[],_delFilter="all",_delQuery="",_pulse=null;
const _FILTERS=[["all","hamısı"],["site","saytlar"],["image","şəkillər"],["report","hesabatlar"],["video","video"],["bundle","paketlər"]];
function fmtSize(b){return b>1e6?(b/1e6).toFixed(1)+"MB":b>1e3?(b/1e3).toFixed(0)+"KB":b+"B"}
function _visList(){
  const q=_delQuery;
  return _deliverables.filter(d=>(_delFilter==="all"||d.kind===_delFilter)
    &&(!q||(d.name+" "+(d.title||"")).toLowerCase().includes(q)));
}
function renderChips(){
  const n=k=>k==="all"?_deliverables.length:_deliverables.filter(d=>d.kind===k).length;
  $("delChips").innerHTML=_FILTERS.map(([k,l])=>
    `<button class="chip${_delFilter===k?" on":""}" onclick="setFilter('${k}')">${l}<span class="cnt">${n(k)}</span></button>`).join("");
}
function setFilter(k){_delFilter=k;renderChips();renderDeliverables();}
function setQuery(v){_delQuery=v.trim().toLowerCase();renderDeliverables();}
async function loadDeliverables(){
  try{_deliverables=await j("/api/deliverables?limit=60");}catch(e){_deliverables=[];}
  renderChips();renderDeliverables();renderRecents();renderToday();
}
function renderDeliverables(){
  const list=_visList();
  if(!list.length){
    $("gallery").innerHTML=`<div class="gempty">${_gicon("image")}<div>${_delQuery?"Axtarışa uyğun nəticə yoxdur.":"Hələ nəticə yoxdur — Studiyada bir tapşırıq ver, hazır olanda burada görünəcək."}</div></div>`;
    return;
  }
  $("gallery").innerHTML=list.map((d,i)=>{
    let thumb;
    if(d.kind==="image") thumb=`<img src="${d.url}" loading="lazy" alt="${esc(d.name||'Nəticə şəkli')}">`;
    else if(d.kind==="site") thumb=`<iframe src="${d.url}" scrolling="no" loading="lazy" tabindex="-1"></iframe>`;
    else if(d.kind==="report"&&(d.title||d.snippet))
      thumb=`<div class="rprev"><b>${esc(d.title||d.name)}</b><p>${esc(d.snippet||"")}</p></div>`;
    else thumb=_gicon(d.kind);
    const hasPrev=d.kind==="report"&&(d.title||d.snippet);
    return `<div class="gtile" onclick="openDeliverable(${i})" title="${esc(d.title||d.name)}">
      <div class="thumb">${thumb}</div>
      <div class="tmeta">${hasPrev?"":`<div class="nm">${esc(d.title||d.name)}</div>`}
        <div class="kd"><span class="kbadge ${d.kind}">${KIND_AZ[d.kind]||d.kind}</span><span>${fmtSize(d.size)} · ${ago(d.mtime)}</span></div>
      </div></div>`;
  }).join("");
}
function renderRecents(){
  $("tabCnt").textContent=_deliverables.length||"";
  const rs=_deliverables.slice(0,4);
  $("recents").innerHTML=rs.map((d,i)=>`<div class="rrow" onclick="openRecent(${i})">
    <span class="rthumb">${d.kind==="image"?`<img src="${d.url}" loading="lazy" alt="${esc(d.name||'Nəticə şəkli')}">`:_gicon(d.kind)}</span>
    <span class="rtx"><span class="rt">${esc(d.title||d.name)}</span>
    <span class="rs">${KIND_AZ[d.kind]||d.kind} · ${ago(d.mtime)}</span></span>
  </div>`).join("")||`<div class="muted">hələ nəticə yoxdur</div>`;
}
function openRecent(i){const d=_deliverables[i];if(d)openD(d);}
function openDeliverable(i){const d=_visList()[i];if(d)openD(d);}
async function openD(d){
  $("mNm").textContent=d.title||d.name; $("mOpen").href=d.url; $("mDl").href=d.url;
  const b=$("mBody");
  if(d.kind==="image") b.innerHTML=`<img src="${d.url}" alt="${esc(d.name||'Nəticə şəkli')}">`;
  else if(d.kind==="site") b.innerHTML=`<iframe src="${d.url}" title="${esc(d.name||'Sayt önizləməsi')}" sandbox="allow-scripts allow-forms"></iframe>`;
  else if(d.kind==="pdf") b.innerHTML=`<iframe src="${d.url}" title="${esc(d.name||'PDF önizləməsi')}"></iframe>`;
  else if(d.kind==="video") b.innerHTML=`<video src="${d.url}" controls style="width:100%;max-height:100%"></video>`;
  else if(d.kind==="audio") b.innerHTML=`<div style="padding:40px"><audio src="${d.url}" controls style="width:100%"></audio></div>`;
  else if(d.kind==="report"){
    try{const t=await (await fetch(d.url)).text(); b.innerHTML=`<div class="mdoc">${md(t)}</div>`;}
    catch(e){b.innerHTML=`<div class="muted" style="padding:40px">oxunmadı</div>`;}
  } else b.innerHTML=`<div style="padding:48px;text-align:center" class="muted">Önizləmə yoxdur — "yüklə" düyməsini işlət.</div>`;
  $("modal").classList.add("on");
}
function closeModal(){$("modal").classList.remove("on"); $("mBody").innerHTML="";}
document.addEventListener("keydown",e=>{
  if(e.key==="Escape")closeModal();
  if(e.key==="/"&&!/INPUT|TEXTAREA/.test(e.target.tagName)){e.preventDefault();showTab("studiya");$("task").focus();}
});

/* ── Studiya aside: today + top hint ── */
function trow(label,val,hot){
  return `<div class="trow${hot?" hot":""}"><span>${label}</span><span class="v">${val}</span></div>`;
}
function renderToday(){
  const q=(_pulse&&_pulse.queue)||{};
  const today=_deliverables.filter(d=>(Date.now()/1000-d.mtime)<86400).length;
  $("today").innerHTML=
    trow("hazır nəticə (son 24 saat)",today)+
    trow("növbədə / işləyir",(q.queued??0)+" / "+(q.running??0))+
    trow("təsdiq gözləyir",q.awaiting_approval??0,(q.awaiting_approval||0)>0);
}

/* ── engine room tiles ── */
function tile(cls,k,v,s){return `<div class="tile ${cls||""}">
  <div class="k">${k}</div><div class="v">${v}</div><div class="s">${s||""}</div></div>`}

async function refresh(){
  let p;
  try{p=await j("/api/pulse");$("liveDot").classList.remove("err");$("liveTxt").textContent="canlı";}
  catch(e){$("liveDot").classList.add("err");$("liveTxt").textContent="əlaqə yoxdur";return;}
  _pulse=p;
  const q=p.queue||{}, llm=p.llm||{}, env=p.env||{};
  const envOk=Object.values(env).filter(v=>String(v).startsWith("SET")).length;
  const envAll=Object.keys(env).length;
  $("git").innerHTML=`git: <b>${esc(p.git&&p.git.head||"?")}</b>${p.git&&p.git.dirty?" · dirty":""}`;
  $("cost").innerHTML=`LLM bu gün: <b>${llm.calls_today||0}</b> uğurlu / <b>${llm.attempts_today??llm.calls_today??0}</b> cəhd · <b>$${(llm.cost_usd_today||0).toFixed(3)}</b>`;
  $("cards").innerHTML =
    tile("","Növbədə", q.queued??"–","işləyir: "+(q.running??0))+
    tile("","Hazır", q.done??"–","xəta: "+(q.error??0))+
    tile((q.awaiting_approval||0)>0?"warn":"","Təsdiq gözləyir", q.awaiting_approval??0,"riskli əməllər")+
    tile("","Açarlar", `${envOk}/${envAll}`,"canlı .env refleksi")+
    tile("","Yaddaş", (p.memory&&p.memory.turns)??"–","dialoq dövrləri")+
    tile("","Cədvəllər",(p.schedules&&p.schedules.enabled)??"–","aktiv plan");
  renderToday();

  const jobs=await j("/api/jobs?limit=25");
  $("jobs").innerHTML=jobs.map(x=>`<tr>
    <td class="mono">${x.id}</td>
    <td><span class="st ${x.status}">${ST_AZ[x.status]||x.status}</span></td>
    <td class="muted">${esc(x.source)}</td>
    <td title="${esc(x.task)}">${esc(x.task.slice(0,90))}</td>
    <td class="muted" style="white-space:nowrap">${ago(x.created_at)||"—"}</td>
    <td>${x.result_preview?`<details><summary>bax</summary><pre>${esc(x.result_preview)}</pre></details>`:`<span class="muted">${esc(x.error||"—")}</span>`}</td>
  </tr>`).join("")||`<tr><td colspan="6" class="muted">hələ iş yoxdur</td></tr>`;

  const parked=jobs.filter(x=>x.status==="awaiting_approval");
  $("approvalsWrap").style.display=parked.length?"block":"none";
  $("approvals").innerHTML=parked.map(x=>`<div class="approval">
     <div class="t"><b>#${x.id}</b> — ${esc(x.task)}</div>
     <button class="btn good" onclick="decide(${x.id},'approve')">✓ Təsdiqlə</button>
     <button class="btn danger" onclick="decide(${x.id},'reject')">✕ İmtina</button>
   </div>`).join("");

  const a=await j("/api/advisor");
  const finds=(a.findings||[]);
  $("advisor").innerHTML=finds.length
    ? finds.map(f=>`<div class="find"><span class="lvl ${f.level}">${f.level}</span>
        <div><div>${esc(f.title)} — <span class="d">${esc(f.detail)}</span></div>
        ${f.suggestion?`<div class="sug">→ ${esc(f.suggestion)}</div>`:""}</div></div>`).join("")
    : `<div class="muted">Hər şey qaydasında — kritik risk görünmür ✓</div>`;
  const top=finds.find(f=>f.level==="risk"||f.level==="watch");
  if(top){
    $("hintCard").style.display="block";
    $("topHint").innerHTML=`<span class="lvl ${top.level}">${top.level==="risk"?"risk":"diqqət"}</span>
      <div style="margin-top:8px;font-size:13.5px">${esc(top.title)}</div>
      ${top.suggestion?`<div class="sug">→ ${esc(top.suggestion)}</div>`:""}`;
  } else $("hintCard").style.display="none";

  const ev=await j("/api/events?n=15");
  $("events").innerHTML=ev.reverse().map(e=>{
    const t=new Date((e.ts||0)*1000).toLocaleTimeString("az",{hour:"2-digit",minute:"2-digit"});
    return `<div class="ev"><span class="lamp"></span><time>${t}</time><span><b>${esc(e.kind)}</b> — ${esc(e.summary)}</span></div>`
  }).join("")||`<div class="muted">hadisə yoxdur</div>`;
}

async function decide(id,action){
  await j(`/api/jobs/${id}/${action}`,{method:"POST"});
  toast(action==="approve"?`✓ #${id} təsdiqləndi`:`✕ #${id} imtina edildi`,action!=="approve");
  refresh();
}

/* ── chat: one microphone ── */
let _watchJob=null,_turns=[],_bubTxt=[],_lastFailure=null;
const _open=new Set();
function hkey(t){let h=0;for(let i=0;i<t.length;i++)h=(h*31+t.charCodeAt(i))|0;return h}
function bubble(role,text,src,pending){
  const s=src?`<span class="src">${esc(src)}</span>`:"";
  const k=hkey(text), long=text.length>1600&&!pending, open=_open.has(k);
  const shown=long&&!open?text.slice(0,1600)+" …":text;
  const body=role==="assistant"&&!pending?md(shown):esc(shown);
  const more=long?`<a class="more" onclick="toggleMore(${k})">${open?"— yığ":"davamı →"}</a>`:"";
  const i=_bubTxt.push(text)-1;
  const cpy=role==="assistant"&&!pending?`<button class="cpy" title="Mətni kopyala" onclick="copyBub(${i})">⧉ kopyala</button>`:"";
  return `<div class="bubble ${role}${pending?" pending":""}">${cpy}${s}${body}${more}</div>`;
}
function toggleMore(k){_open.has(k)?_open.delete(k):_open.add(k);renderChat();}
async function copyBub(i){
  try{await navigator.clipboard.writeText(_bubTxt[i]||"");toast("⧉ kopyalandı");}
  catch(e){toast("kopyalama alınmadı",true);}
}
function renderChat(){
  const box=$("chat");
  const atBottom = box.scrollTop+box.clientHeight >= box.scrollHeight-40;
  _bubTxt=[];
  let html=_turns.map(t=>{
    let src=null, txt=t.content||"";
    if(t.role==="user"){
    const m=txt.match(/^\\[([\\w-]+)\\]\\s*/); if(m){src=m[1];txt=txt.slice(m[0].length);}
    }else{
    const m=txt.match(/^_\\[chat:([^\\]]*)\\]_\\s*/);
      if(m){src=(m[1].split(/[:/]/).pop()||"").slice(0,30);txt=txt.slice(m[0].length);}
    }
    return bubble(t.role==="user"?"user":"assistant", txt, src, false);
  }).join("");
  if(_lastFailure)html+=bubble("assistant",_lastFailure,"xəta",false);
  if(_watchJob) html+=bubble("assistant","… işləyir (job #"+_watchJob+")",null,true);
  box.innerHTML=html||`<div class="muted">Söhbətə başla — bura, Telegram və Codex eyni yaddaşı görür.</div>`;
  if(atBottom||_watchJob) box.scrollTop=box.scrollHeight;
}
async function loadChat(){
  try{const c=await j("/api/chat?n=40");_turns=c.turns||[];renderChat();}catch(e){}
}
async function watchJob(id){
  _watchJob=id; renderChat();
  for(let i=0;i<120;i++){
    await new Promise(r=>setTimeout(r,2500));
    try{
      const d=await j(`/api/jobs/${id}`);
      if(d.status==="done"||d.status==="error"||d.status==="awaiting_approval"||d.status==="rejected"){
        _watchJob=null;
        _lastFailure=d.status==="error"?(d.error||"Tapşırıq tamamlanmadı."):null;
        await loadChat(); refresh(); loadDeliverables(); return;
      }
    }catch(e){}
  }
  _watchJob=null; loadChat();
}
async function submitTask(){
  const t=$("task").value.trim(); if(!t)return;
  _lastFailure=null;
  const r=await j("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({task:t})});
  $("msg").textContent=r.id?`Job #${r.id} növbəyə salındı`:(r.error||"xəta");
  setTimeout(()=>{$("msg").textContent="";},6000);
  $("task").value="";
  if(r.id){ $("chat").innerHTML+=bubble("user",t,"panel",false); $("chat").scrollTop=$("chat").scrollHeight; watchJob(r.id); }
  refresh();
}

/* ── Agent Radar (governance) — cached scan; ↻ forces a fresh run ── */
async function loadRadar(force){
  const box=$("radar");
  if(force)box.innerHTML=`<div class="muted">skan işləyir…</div>`;
  let r;
  try{r=await j("/api/radar"+(force?"?refresh=1":""));}
  catch(e){box.innerHTML=`<div class="muted">radar oxunmadı</div>`;return;}
  const s=r.scan||{},hf=r.hf||{};
  const sum=s.system_fit_summary||{},rec=s.recommendation||{};
  const hsum=hf.system_fit_summary||{},hrec=hf.recommendation||{};
  const chip=(k,v)=>`<span class="badge">${k}: <b>${v??"–"}</b></span>`;
  const rows=(s.ranked_candidates||[]).map(it=>`<tr>
    <td>${esc(it.candidate.name)}</td><td class="muted">${esc(it.phase||"")}</td>
    <td class="mono">${it.fit_score}</td><td class="mono">${it.evaluation.risk_score}</td>
    <td>${esc(it.evaluation.verdict)}</td><td class="muted">${esc(it.decision)}</td></tr>`).join("");
  const hrows=(hf.ranked_opportunities||[]).slice(0,6).map(it=>`<tr>
    <td>${esc(it.opportunity.name)}</td><td class="muted">${esc(it.opportunity.category)}</td>
    <td class="mono">${it.evaluation.fit_score}</td><td class="mono">${it.evaluation.risk_score}</td>
    <td>${esc(it.evaluation.verdict)}</td><td class="muted">${esc(it.evaluation.decision)}</td></tr>`).join("");
  box.classList.remove("muted");
  box.innerHTML=`
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
      ${chip("Ümumi uyğunluq",(sum.overall_rating??"–")+"/100")}
      ${chip("Orta fit",sum.avg_fit_score)} ${chip("Orta risk",sum.avg_risk_score)}
      <span class="badge">tövsiyə: <b>${esc(rec.name||"–")}</b> → ${esc(rec.decision||"")}</span>
    </div>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>Modul</th><th>Faza</th><th>Fit</th><th>Risk</th><th>Verdikt</th><th>Qərar</th></tr></thead>
      <tbody>${rows||`<tr><td colspan="6" class="muted">skan yoxdur</td></tr>`}</tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 10px">
      <span class="badge">🤗 Hugging Face radarı</span>
      ${chip("HF fit",(hsum.overall_rating??"–")+"/100")}
      <span class="badge">tövsiyə: <b>${esc(hrec.name||"–")}</b> → ${esc(hrec.decision||"")}</span>
    </div>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>Fürsət</th><th>Kateqoriya</th><th>Fit</th><th>Risk</th><th>Verdikt</th><th>Qərar</th></tr></thead>
      <tbody>${hrows||`<tr><td colspan="6" class="muted">skan yoxdur</td></tr>`}</tbody></table></div>
    <div class="muted" style="font-size:12px;margin-top:8px">
      Yerli deterministik skorlama — LLM-siz · hesabatlar: output/agent-radar · output/hf-radar
      ${s.generated_at_iso?` · son skan: ${esc(s.generated_at_iso)}`:""}</div>`;
}

async function doSync(){
  const b=$("syncBtn"); b.disabled=true;
  const r=await j("/api/sync",{method:"POST"});
  b.disabled=false;
  toast(r.summary||"sync bitdi",!r.ok);
  refresh();
}

/* ── MALİYYƏ — live pull from Ads Studio (8800) ── */
function fmoney(sym,n){return sym+new Intl.NumberFormat("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}).format(n||0)}
function pbar(pct,status){return `<div class="pbar ${status||""}"><i style="width:${Math.min(pct||0,100)}%"></i></div>`}
async function loadFinance(){
  const box=$("finBody");
  let f;
  try{f=await j("/api/finance");}catch(e){box.innerHTML=`<div class="muted">Maliyyə datası oxunmadı.</div>`;return;}
  if(!f.ok){
    box.innerHTML=`<div class="muted">Ads Studio (8800) ilə əlaqə yoxdur — servis işləyirmi? <span class="mono" style="font-size:11px">${esc(f.error||"")}</span></div>`;
    $("finPeriod").textContent="əlaqə yoxdur"; return;
  }
  const sym=f.sym||"$", p=f.pacing||{}, t=f.totals||{}, org=f.organic||{};
  $("finPeriod").textContent=`${f.account_name||"—"} · ${f.period&&f.period.label||""} · ${f.data_mode==="live"?"CANLI":"DEMO"}`;

  const budgetStatus=p.budget_status==="over"?"over":p.budget_status==="warn"?"warn":"good";
  const leadsStatus=p.leads_status==="over"?"over":p.leads_status==="warn"?"warn":"good";

  let html=`<div class="tiles">
    ${tile("","Xərc (bu ay)",fmoney(sym,t.spend),"Meta Ads")}
    ${tile("","Lead",t.leads??"–",`${fmoney(sym,t.cpl)} / lead`)}
    ${tile(budgetStatus==="over"?"warn":"","Büdcə istifadəsi",(p.budget_used_pct??"–")+"%",fmoney(sym,p.spend_so_far)+" / "+fmoney(sym,p.budget))}
    ${tile(leadsStatus==="over"?"warn":"","Lead hədəfi",(p.lead_attainment_pct??"–")+"%",(p.leads_so_far??"–")+" / "+(p.target_leads??"–"))}
  </div>
  <section class="card pad">
    <h3>Büdcə Pacing & Ay Sonu Proqnozu</h3>
    <div class="finrow"><span>Büdcə istifadəsi</span><b>${fmoney(sym,p.spend_so_far)} / ${fmoney(sym,p.budget)}</b></div>
    ${pbar(p.budget_used_pct,budgetStatus)}
    <div class="finrow" style="margin-top:12px"><span>Proqnoz ay-sonu xərc</span><b>${fmoney(sym,p.projected_spend)}</b></div>
    <div class="finrow"><span>Lead hədəfi</span><b>${p.leads_so_far??"–"} / ${p.target_leads??"–"}</b></div>
    ${pbar(p.lead_attainment_pct,leadsStatus)}
    <div class="finrow" style="margin-top:12px"><span>Proqnoz CPL</span><b>${fmoney(sym,p.projected_cpl)} <span class="muted">/ limit ${fmoney(sym,p.max_cpl)}</span></b></div>
  </section>
  <section class="card pad">
    <h3>Üzvi (organic) auditoriya <span class="lnk" onclick="showTab('neticeler')" style="cursor:default;color:var(--mut)">Facebook + Instagram</span></h3>
    <div class="tiles">
      ${tile("","FB izləyici",(org.facebook&&org.facebook.fan_count!=null)?org.facebook.fan_count:"–",esc(org.facebook&&org.facebook.name||""))}
      ${tile("","IG izləyici",(org.instagram&&org.instagram.followers_count!=null)?org.instagram.followers_count:"–",org.instagram&&org.instagram.username?"@"+esc(org.instagram.username):"")}
    </div>
    ${(org.facebook&&org.facebook.insights_error)?`<div class="muted" style="font-size:12px">⚠ FB: ${esc(org.facebook.insights_error)}</div>`:""}
    ${(org.instagram&&org.instagram.insights_error)?`<div class="muted" style="font-size:12px">⚠ IG: ${esc(org.instagram.insights_error)}</div>`:""}
  </section>`;
  box.innerHTML=html;
}

/* ── TRENDLƏR — research-lab marketing radar ── */
async function loadTrends(){
  const box=$("trendList");
  let r;
  try{r=await j("/api/trends");}catch(e){box.innerHTML=`<div class="muted">radar oxunmadı</div>`;return;}
  if(r.ok===false){
    $("trendCnt").textContent="";
    $("trendMeta").innerHTML=`<b>əlçatan deyil</b>`;
    box.innerHTML=`<div class="find"><span class="lvl watch">diqqət</span><div><div>${esc(r.message||'Research Lab əlçatan deyil.')}</div><div class="sug">→ Bağlantını yoxlayın və yenidən cəhd edin.</div></div></div>`;
    return;
  }
  const findings=r.findings||[], proposals=r.proposals||[];
  const open=findings.filter(f=>f.status==="new");
  $("trendCnt").textContent=open.length||"";
  $("trendMeta").innerHTML=`<b>${open.length}</b> açıq tapıntı · ${findings.length} cəmi`;

  $("trendProposalsWrap").style.display=proposals.length?"block":"none";
  $("trendProposals").innerHTML=proposals.map(p=>`<div class="find">
      <span class="lvl info">tikinti</span>
      <div><div>${esc(p.title)}</div><div class="d">${esc(p.status)}</div></div>
    </div>`).join("");

  if(!findings.length){box.innerHTML=`<div class="muted">Tapıntı yoxdur.</div>`;return;}
  box.classList.remove("muted");
  box.innerHTML=findings.map(f=>`
    <div class="trendcard ${f.status!=="new"?f.status:""}">
      <div class="hd">
        <span class="trendscore">${f.score}/10</span>
        <span class="trendtitle">${esc(f.title)}</span>
        <span class="trenddate">${esc(f.date)}</span>
      </div>
      ${f.idea?`<div class="trendidea">→ ${esc(f.idea)}</div>`:""}
      ${f.status==="new"?`<div class="trendactions">
          <button class="btn good" onclick="trendAction('${esc(f.title).replace(/'/g,"\\\\'")}','adopt',this)">✓ Qəbul et</button>
          <button class="btn danger" onclick="trendAction('${esc(f.title).replace(/'/g,"\\\\'")}','reject',this)">✕ Rədd et</button>
        </div>`:`<div class="trendactions"><span class="badge">${f.status==="adopted"?"✓ qəbul edilib":"✕ rədd edilib"}</span></div>`}
    </div>`).join("");
}
async function trendAction(title,action,btn){
  if(btn) btn.closest(".trendactions").querySelectorAll("button").forEach(b=>b.disabled=true);
  try{
    const r=await j(`/api/trends/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title})});
    toast(r.ok?(action==="adopt"?"✓ qəbul edildi":"✕ rədd edildi"):"əməliyyat alınmadı",!r.ok);
    loadTrends();
  }catch(e){toast("əməliyyat alınmadı",true);}
}

/* ── voice input — Web Speech API, az-AZ (Chrome; localhost = secure context) ── */
let _rec=null,_recOn=false;
const _SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!_SR)$("micBtn").style.display="none";
function toggleMic(){
  if(!_SR)return;
  if(_recOn){try{_rec.stop();}catch(e){} return;}
  _rec=new _SR();
  _rec.lang="az-AZ"; _rec.interimResults=true; _rec.continuous=true;
  const base=$("task").value.trim();
  _rec.onresult=e=>{
    let t=""; for(const r of e.results)t+=r[0].transcript;
    $("task").value=(base?base+" ":"")+t;
  };
  _rec.onend=()=>{_recOn=false;$("micBtn").classList.remove("rec");$("task").focus();};
  _rec.onerror=e=>{
    _recOn=false;$("micBtn").classList.remove("rec");
    if(e.error!=="aborted"&&e.error!=="no-speech")toast("mikrofon alınmadı: "+e.error+" (Chrome-da aç)",true);
  };
  try{_rec.start();_recOn=true;$("micBtn").classList.add("rec");}
  catch(e){toast("mikrofon başlamadı",true);}
}

const _qs=new URLSearchParams(location.search);
if(_qs.get("embed")==="1")document.body.classList.add("embedded");
let _theme="light";
try{_theme=localStorage.getItem("rs-theme")||"light";}catch(e){}
applyTheme(_qs.get("theme")||_theme);
let _tab="studiya";
try{_tab=localStorage.getItem("rs-tab")||"studiya";}catch(e){}
showTab(_qs.get("tab")||_tab);
refresh();
loadChat();
setInterval(refresh, 15000);
setInterval(loadChat, 12000);
setInterval(()=>{if(_tabLoaded.has("studiya")||_tabLoaded.has("neticeler"))loadDeliverables();},60000);
setInterval(()=>{if(_tabLoaded.has("maliyye"))loadFinance();},90000);
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML
