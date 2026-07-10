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

import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from ._bootstrap import load_env
from . import advisor, mic, queue, scheduler, sense

load_env()

ROOT = Path(__file__).resolve().parent.parent
_SYNC = ROOT / "scripts" / "sync_engine.py"

app = FastAPI(title="RAMIN OS — İdarəetmə Mərkəzi")


# --------------------------------------------------------------------------
# API — deterministic reads of the live body + the operator's few writes
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "panel"}


@app.get("/api/pulse")
def pulse() -> JSONResponse:
    return JSONResponse(sense.snapshot())


@app.get("/api/advisor")
def advisor_view() -> JSONResponse:
    findings = [f.as_dict() for f in advisor.observe_state()]
    return JSONResponse({"findings": findings})


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
    task: str


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


@app.post("/api/sync")
def sync_now() -> JSONResponse:
    """One-click engine sync — same brain every other trigger uses."""
    try:
        proc = subprocess.run(
            [sys.executable, str(_SYNC)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=90,
        )
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

    for root in _DELIVERABLE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
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
                items[rel] = {
                    "name": site.name, "path": rel, "url": f"/file/{rel}",
                    "kind": "site", "size": stat.st_size, "mtime": stat.st_mtime,
                }
                continue
            if p.suffix.lower() not in _PREVIEW_EXT:
                continue
            try:
                rel = p.relative_to(ROOT).as_posix()
                stat = p.stat()
            except (ValueError, OSError):
                continue
            items[rel] = {
                "name": p.name,
                "path": rel,
                "url": f"/file/{rel}",
                "kind": _kind_of(p.suffix.lower()),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
    ordered = sorted(items.values(), key=lambda d: d["mtime"], reverse=True)
    return JSONResponse(ordered[:limit])


# --------------------------------------------------------------------------
# UI — one premium dark screen, zero external assets (corporate-offline safe)
# --------------------------------------------------------------------------

_HTML = """<!doctype html>
<html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RAMIN OS — İdarəetmə Mərkəzi</title>
<style>
/* ── design tokens ─────────────────────────────────────────────── */
:root{
  --bg0:#090c11; --bg1:#0f141c; --bg2:#141b25; --bg3:#1a2330;
  --line:rgba(148,163,184,.13); --line2:rgba(148,163,184,.22);
  --ink:#eef3f8; --ink2:#9db0c3; --mut:#6b7f94;
  --acc:#38bdf8; --acc2:#818cf8; --vio:#a78bfa;
  --ok:#34d399; --warn:#fbbf24; --bad:#f87171;
  --r-lg:16px; --r-md:12px; --r-sm:8px;
  --shadow:0 1px 0 rgba(255,255,255,.04) inset, 0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box;margin:0}
html{scroll-behavior:smooth}
body{
  background:
    radial-gradient(1100px 520px at 85% -8%, rgba(56,189,248,.07), transparent 60%),
    radial-gradient(900px 480px at -8% 108%, rgba(129,140,248,.06), transparent 60%),
    var(--bg0);
  color:var(--ink);
  font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
  min-height:100vh;
}
::selection{background:rgba(56,189,248,.3)}
button{font:inherit;cursor:pointer;border:0}
button:focus-visible,textarea:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}

/* ── topbar ─────────────────────────────────────────────────────── */
.topbar{
  position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:12px;
  padding:12px 22px;background:rgba(9,12,17,.82);backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line);
}
.mark{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--acc),var(--acc2));color:#04121c;font-weight:800;font-size:15px;
  box-shadow:0 2px 10px rgba(56,189,248,.35)}
.tt{font-size:15px;font-weight:650;letter-spacing:.2px;white-space:nowrap}
.tt small{color:var(--ink2);font-weight:500}
.live{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ink2);white-space:nowrap}
.live .dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 rgba(52,211,153,.5);animation:pulse 2.2s infinite}
.live.err .dot{background:var(--bad);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.45)}70%{box-shadow:0 0 0 7px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.badge{background:var(--bg1);border:1px solid var(--line);border-radius:999px;
  padding:4px 12px;font-size:12px;color:var(--ink2);white-space:nowrap}
.badge b{color:var(--ink);font-variant-numeric:tabular-nums}
.sp{flex:1}
.btn{display:inline-flex;align-items:center;gap:7px;border-radius:10px;padding:8px 14px;font-weight:600;font-size:13px;
  transition:filter .15s, transform .1s, background .15s, border-color .15s}
.btn:active{transform:translateY(1px)}
.btn.primary{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#04121c}
.btn.primary:hover{filter:brightness(1.1)}
.btn.ghost{background:var(--bg1);color:var(--ink);border:1px solid var(--line)}
.btn.ghost:hover{border-color:var(--line2);background:var(--bg2)}
.btn.good{background:rgba(52,211,153,.14);color:var(--ok);border:1px solid rgba(52,211,153,.35)}
.btn.good:hover{background:rgba(52,211,153,.22)}
.btn.danger{background:rgba(248,113,113,.1);color:var(--bad);border:1px solid rgba(248,113,113,.3)}
.btn.danger:hover{background:rgba(248,113,113,.18)}
.btn:disabled{opacity:.5;cursor:wait}
.btn svg{width:15px;height:15px}

/* ── shell: chat rail + content ────────────────────────────────── */
.shell{display:grid;grid-template-columns:minmax(340px,410px) 1fr;gap:18px;
  padding:18px 22px 40px;max-width:1720px;margin:0 auto;align-items:start}
@media (max-width:1080px){.shell{grid-template-columns:1fr}.chatcard{position:static!important;height:auto!important}.chat{max-height:46vh}}

.card{background:linear-gradient(180deg,rgba(255,255,255,.02),transparent 40%),var(--bg1);
  border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow)}
section.card{padding:18px;margin-bottom:16px}
.sect{display:flex;align-items:center;gap:9px;margin-bottom:14px;flex-wrap:wrap}
.sect h2{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.4px;color:var(--ink2)}
.sect .ico{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;font-size:13px;
  background:var(--bg2);border:1px solid var(--line)}
.muted{color:var(--mut)} .mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}

/* ── chat — the one microphone ─────────────────────────────────── */
.chatcard{position:sticky;top:72px;height:calc(100vh - 96px);display:flex;flex-direction:column;padding:16px}
.chat{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:10px;padding:4px 2px;scrollbar-width:thin;scrollbar-color:var(--bg3) transparent}
.bubble{max-width:85%;padding:10px 14px;border-radius:14px;font-size:13.5px;line-height:1.55;
  white-space:pre-wrap;word-break:break-word}
.bubble.user{align-self:flex-end;background:linear-gradient(135deg,rgba(56,189,248,.16),rgba(129,140,248,.14));
  border:1px solid rgba(56,189,248,.3);border-bottom-right-radius:5px}
.bubble.assistant{align-self:flex-start;background:var(--bg2);border:1px solid var(--line);border-bottom-left-radius:5px}
.bubble .src{display:block;font-size:10px;color:var(--mut);margin-bottom:4px;text-transform:uppercase;letter-spacing:.7px}
.bubble.pending{opacity:.6;font-style:italic}
.composer{display:flex;gap:9px;margin-top:12px;align-items:flex-end}
.composer textarea{flex:1;background:var(--bg2);border:1px solid var(--line);border-radius:13px;color:var(--ink);
  padding:11px 13px;font:inherit;min-height:48px;max-height:150px;resize:vertical}
.composer textarea::placeholder{color:var(--mut)}
.composer .send{width:48px;height:48px;border-radius:13px;flex:none;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--acc),var(--acc2));color:#04121c}
.composer .send:hover{filter:brightness(1.12)}
.composer .send svg{width:19px;height:19px}
#msg{font-size:12px;color:var(--ok);min-height:16px;margin-top:6px}

/* ── stat tiles ────────────────────────────────────────────────── */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin-bottom:16px}
.tile{background:linear-gradient(180deg,rgba(255,255,255,.02),transparent 40%),var(--bg1);
  border:1px solid var(--line);border-radius:var(--r-lg);padding:14px 15px;box-shadow:var(--shadow);
  transition:border-color .15s}
.tile:hover{border-color:var(--line2)}
.tile .h{display:flex;align-items:center;gap:8px;margin-bottom:9px}
.tile .tic{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-size:14px}
.tile .k{font-size:10.5px;text-transform:uppercase;letter-spacing:1px;color:var(--mut);font-weight:600}
.tile .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.1}
.tile .s{font-size:11.5px;color:var(--mut);margin-top:3px}
.t-acc .tic{background:rgba(56,189,248,.12);color:var(--acc)}
.t-ok  .tic{background:rgba(52,211,153,.12);color:var(--ok)}
.t-warn .tic{background:rgba(251,191,36,.12);color:var(--warn)}
.t-vio .tic{background:rgba(167,139,250,.12);color:var(--vio)}

/* ── approvals ─────────────────────────────────────────────────── */
.approval{border:1px solid rgba(251,191,36,.3);border-left:3px solid var(--warn);
  background:rgba(251,191,36,.05);border-radius:var(--r-md);padding:13px 15px;margin-bottom:9px;
  display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.approval .t{flex:1;min-width:220px;font-size:13.5px}
.approval .t b{color:var(--warn)}

/* ── gallery ───────────────────────────────────────────────────── */
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{background:var(--bg2);border:1px solid var(--line);color:var(--ink2);border-radius:999px;
  padding:5px 13px;font-size:12px;font-weight:600;transition:all .15s}
.chip:hover{border-color:var(--line2);color:var(--ink)}
.chip.on{background:rgba(56,189,248,.14);border-color:rgba(56,189,248,.45);color:#7dd3fc}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:13px}
.gtile{background:var(--bg2);border:1px solid var(--line);border-radius:14px;overflow:hidden;cursor:pointer;
  display:flex;flex-direction:column;transition:transform .16s, border-color .16s, box-shadow .16s}
.gtile:hover{border-color:rgba(56,189,248,.5);transform:translateY(-3px);box-shadow:0 14px 30px rgba(0,0,0,.45)}
.thumb{height:146px;background:#0a0e14;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb iframe{width:200%;height:292px;transform:scale(.5);transform-origin:0 0;border:0;pointer-events:none;background:#fff}
.thumb .ic{font-size:40px;opacity:.8}
.tmeta{padding:10px 12px}
.tmeta .nm{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tmeta .kd{font-size:11px;color:var(--mut);margin-top:5px;display:flex;justify-content:space-between;align-items:center;font-variant-numeric:tabular-nums}
.kbadge{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;border-radius:5px;padding:2px 7px}
.kbadge.site{background:rgba(56,189,248,.14);color:#7dd3fc}
.kbadge.image{background:rgba(167,139,250,.14);color:#c4b5fd}
.kbadge.report{background:rgba(52,211,153,.13);color:#6ee7b7}
.kbadge.video,.kbadge.audio{background:rgba(251,191,36,.13);color:#fcd34d}
.kbadge.bundle,.kbadge.file,.kbadge.pdf{background:var(--bg3);color:var(--ink2)}

/* ── advisor ───────────────────────────────────────────────────── */
.find{display:flex;gap:11px;padding:11px 2px;border-bottom:1px solid var(--line);font-size:13px}
.find:last-child{border-bottom:0}
.lvl{font-size:10.5px;font-weight:700;border-radius:6px;padding:3px 9px;height:fit-content;white-space:nowrap;text-transform:uppercase;letter-spacing:.5px}
.lvl.risk{background:rgba(248,113,113,.13);color:var(--bad)}
.lvl.watch{background:rgba(251,191,36,.13);color:var(--warn)}
.lvl.info{background:rgba(56,189,248,.13);color:var(--acc)}
.find .sug{color:var(--acc);font-size:12.5px;margin-top:4px}
.find .d{color:var(--ink2)}

/* ── jobs table ────────────────────────────────────────────────── */
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--mut);text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.8px;
  padding:7px 9px;border-bottom:1px solid var(--line2)}
td{padding:9px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr{transition:background .12s}
tbody tr:hover{background:rgba(148,163,184,.05)}
tbody tr:last-child td{border-bottom:0}
.st{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 10px;font-size:11px;font-weight:600;white-space:nowrap}
.st::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.st.done{background:rgba(52,211,153,.11);color:var(--ok)}
.st.queued{background:rgba(56,189,248,.11);color:var(--acc)}
.st.running{background:rgba(167,139,250,.13);color:var(--vio)}
.st.error{background:rgba(248,113,113,.12);color:var(--bad)}
.st.awaiting_approval{background:rgba(251,191,36,.12);color:var(--warn)}
.st.rejected{background:rgba(248,113,113,.09);color:#e08b8b}
details summary{cursor:pointer;color:var(--acc);font-size:12px;font-weight:600}
details summary:hover{text-decoration:underline}
pre{white-space:pre-wrap;font-size:12px;color:var(--ink2);margin-top:7px;max-height:300px;overflow:auto;
  background:var(--bg0);border:1px solid var(--line);border-radius:9px;padding:11px}

/* ── events timeline ───────────────────────────────────────────── */
.ev{display:flex;gap:10px;font-size:12.5px;color:var(--ink2);padding:7px 0;border-bottom:1px dashed var(--line);align-items:baseline}
.ev:last-child{border-bottom:0}
.ev .lamp{width:7px;height:7px;border-radius:50%;background:var(--acc);flex:none;transform:translateY(-1px)}
.ev time{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--mut);flex:none}
.ev b{color:var(--ink)}

/* ── modal & toast ─────────────────────────────────────────────── */
.modal{position:fixed;inset:0;background:rgba(4,7,12,.88);backdrop-filter:blur(4px);
  display:none;align-items:center;justify-content:center;z-index:60;padding:20px}
.modal.on{display:flex}
.mbox{background:var(--bg1);border:1px solid var(--line2);border-radius:var(--r-lg);
  width:min(1150px,96vw);height:90vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)}
.mbar{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}
.mbar .nm{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mbar a{text-decoration:none}
.mbody{flex:1;overflow:auto;background:#0a0e14}
.mbody iframe{width:100%;height:100%;border:0;background:#fff}
.mbody img{max-width:100%;display:block;margin:0 auto}
.mbody pre.md{padding:26px;white-space:pre-wrap;color:var(--ink);font:14px/1.65 system-ui;max-height:none;margin:0;background:none;border:0}
#toasts{position:fixed;right:18px;bottom:18px;z-index:70;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--bg2);border:1px solid var(--line2);border-left:3px solid var(--ok);border-radius:10px;
  padding:11px 15px;font-size:13px;box-shadow:0 12px 30px rgba(0,0,0,.5);max-width:340px;animation:slidein .2s ease-out}
.toast.err{border-left-color:var(--bad)}
@keyframes slidein{from{transform:translateX(20px);opacity:0}to{transform:none;opacity:1}}

/* ── markdown inside bubbles & report modal ────────────────────── */
.bubble b,.mdoc b{font-weight:700}
.bubble code,.mdoc code{background:var(--bg3);border:1px solid var(--line);border-radius:5px;
  padding:1px 5px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
.bubble .mh{display:inline-block;font-weight:700;color:var(--acc)}
.mdoc .mh{display:inline-block;font-weight:700;font-size:17px;color:var(--ink)}
.bubble .mli,.mdoc .mli{color:var(--acc);font-weight:700}
.bubble pre.mcb,.mdoc pre.mcb{background:var(--bg0);border:1px solid var(--line);border-radius:8px;
  padding:9px 11px;margin:4px 0;font-size:12px;overflow-x:auto;white-space:pre-wrap;color:var(--ink2)}
.bubble a,.mdoc a{color:var(--acc)}
.mdoc{padding:26px;white-space:pre-wrap;color:var(--ink);font:14px/1.65 system-ui;word-break:break-word}
.bubble{position:relative}
.bubble .cpy{position:absolute;top:-9px;right:8px;background:var(--bg3);border:1px solid var(--line2);
  color:var(--ink2);border-radius:7px;padding:2px 8px;font-size:10.5px;opacity:0;transition:opacity .15s}
.bubble:hover .cpy{opacity:1}
.bubble .more{display:block;color:var(--acc);cursor:pointer;font-size:12px;font-weight:600;margin-top:6px}

/* ── mic — voice input (az-AZ) ─────────────────────────────────── */
.composer .micb{width:48px;height:48px;border-radius:13px;flex:none;display:grid;place-items:center;
  background:var(--bg2);border:1px solid var(--line);color:var(--ink2)}
.composer .micb:hover{border-color:var(--line2);color:var(--ink)}
.composer .micb svg{width:19px;height:19px}
.composer .micb.rec{background:rgba(248,113,113,.15);border-color:rgba(248,113,113,.5);color:var(--bad);
  animation:recpulse 1.4s infinite}
@keyframes recpulse{0%{box-shadow:0 0 0 0 rgba(248,113,113,.35)}70%{box-shadow:0 0 0 8px rgba(248,113,113,0)}100%{box-shadow:0 0 0 0 rgba(248,113,113,0)}}

/* ── gallery search + chip counts ──────────────────────────────── */
.gsearch{background:var(--bg2);border:1px solid var(--line);border-radius:999px;color:var(--ink);
  padding:6px 13px;font:inherit;font-size:12px;width:150px}
.gsearch::placeholder{color:var(--mut)}
.gsearch:focus{outline:2px solid var(--acc);outline-offset:1px}
.chip .cnt{margin-left:6px;font-size:10px;opacity:.7;font-variant-numeric:tabular-nums}
</style></head><body>

<header class="topbar">
  <div class="mark">R</div>
  <div class="tt">RAMIN OS <small>— İdarəetmə Mərkəzi</small></div>
  <div class="live" id="liveDot"><span class="dot"></span><span id="liveTxt">canlı</span></div>
  <span class="badge" id="git">git: …</span>
  <span class="badge" id="cost">LLM bu gün: …</span>
  <span class="sp"></span>
  <button class="btn ghost" id="syncBtn" onclick="doSync()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-2.6-6.3M21 3v6h-6"/></svg>
    Engine sync</button>
  <button class="btn ghost" onclick="refresh()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 2.6-6.3M3 3v6h6"/></svg>
    Yenilə</button>
</header>

<div class="shell">

  <!-- sol: bir mikrofon -->
  <div class="card chatcard">
    <div class="sect" style="margin-bottom:10px">
      <span class="ico">💬</span><h2>Söhbət — bir mikrofon</h2>
      <span class="sp"></span>
      <span class="muted" style="font-size:11px">bura · Telegram · Codex — bir yaddaş</span>
    </div>
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

  <!-- sağ: canlı bədən -->
  <div>
    <div class="tiles" id="cards"></div>

    <section class="card" id="approvalsWrap" style="display:none;border-color:rgba(251,191,36,.35)">
      <div class="sect"><span class="ico">⏸</span><h2>Təsdiq gözləyənlər — bayıra yönəlik əməllər</h2></div>
      <div id="approvals"></div>
    </section>

    <section class="card">
      <div class="sect">
        <span class="ico">🖥️</span><h2>Nəticələr — ön büro</h2>
        <span class="sp"></span>
        <input class="gsearch" id="gq" placeholder="axtar…" oninput="setQuery(this.value)">
        <div class="chips" id="delChips"></div>
        <button class="btn ghost" onclick="loadDeliverables()" title="Yenilə" style="padding:6px 10px">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 2.6-6.3M3 3v6h6"/></svg>
        </button>
      </div>
      <div class="gallery" id="gallery"><div class="muted">yüklənir…</div></div>
    </section>

    <section class="card">
      <div class="sect"><span class="ico">🧭</span><h2>Məsləhətçi — növbəti ən yaxşı addımlar</h2>
        <span class="sp"></span><span class="muted" style="font-size:11px">canlı fakt · LLM-siz</span></div>
      <div id="advisor" class="muted">yüklənir…</div>
    </section>

    <section class="card">
      <div class="sect"><span class="ico">🗂</span><h2>Son işlər</h2></div>
      <div style="overflow-x:auto">
      <table><thead><tr><th>#</th><th>Status</th><th>Mənbə</th><th>Tapşırıq</th><th>Vaxt</th><th>Nəticə</th></tr></thead>
      <tbody id="jobs"></tbody></table>
      </div>
    </section>

    <section class="card">
      <div class="sect"><span class="ico">📡</span><h2>Son hadisələr</h2></div>
      <div id="events" class="muted">yüklənir…</div>
    </section>
  </div>
</div>

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
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
/* tiny safe markdown: escape FIRST, then transform — only whitelisted tags come out.
   Inline-style output on purpose: bubbles/mdoc are pre-wrap, newlines already render. */
function md(t){
  const cbs=[];
  let h=esc(t).replace(/```(\w*)\\n?([\s\S]*?)```/g,(m,l,c)=>{cbs.push(c);return "§CB"+(cbs.length-1)+"§";});
  h=h
    .replace(/`([^`\\n]+)`/g,'<code>$1</code>')
    .replace(/^#{1,4} (.+)$/gm,'<span class="mh">$1</span>')
    .replace(/\*\*([^*\\n]+)\*\*/g,'<b>$1</b>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^[ \\t]*[-*•] /gm,'<span class="mli">• </span>')
    .replace(/^---+$/gm,'───');
  return h.replace(/§CB(\d+)§/g,(m,i)=>`<pre class="mcb">${cbs[+i].trimEnd()}</pre>`);
}
async function j(url,opt){const r=await fetch(url,opt);return r.json()}
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

/* ── deliverables — the visual front office ── */
let _deliverables=[],_delFilter="all",_delQuery="";
const _IC={site:"🌐",image:"🖼️",report:"📄",video:"🎬",audio:"🎵",bundle:"📦",pdf:"📕",file:"📎"};
const _FILTERS=[["all","hamısı"],["site","🌐 saytlar"],["image","🖼️ şəkillər"],["report","📄 hesabatlar"],["video","🎬 video"],["bundle","📦 paketlər"]];
function fmtSize(b){return b>1e6?(b/1e6).toFixed(1)+"MB":b>1e3?(b/1e3).toFixed(0)+"KB":b+"B"}
function _visList(){
  return _deliverables.filter(d=>(_delFilter==="all"||d.kind===_delFilter)
    &&(!_delQuery||d.name.toLowerCase().includes(_delQuery)));
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
  renderChips();renderDeliverables();
}
function renderDeliverables(){
  const list=_visList();
  if(!list.length){$("gallery").innerHTML=`<div class="muted">${_delQuery?"axtarışa uyğun nəticə yoxdur.":"hələ nəticə yoxdur — bir tapşırıq ver, burada görünəcək."}</div>`;return;}
  $("gallery").innerHTML=list.map((d,i)=>{
    let thumb;
    if(d.kind==="image") thumb=`<img src="${d.url}" loading="lazy">`;
    else if(d.kind==="site") thumb=`<iframe src="${d.url}" scrolling="no" loading="lazy" tabindex="-1"></iframe>`;
    else thumb=`<div class="ic">${_IC[d.kind]||"📎"}</div>`;
    return `<div class="gtile" onclick="openDeliverable(${i})" title="${esc(d.name)}">
      <div class="thumb">${thumb}</div>
      <div class="tmeta"><div class="nm">${esc(d.name)}</div>
        <div class="kd"><span class="kbadge ${d.kind}">${d.kind}</span><span>${fmtSize(d.size)} · ${ago(d.mtime)}</span></div>
      </div></div>`;
  }).join("");
}
async function openDeliverable(i){
  const d=_visList()[i]; if(!d)return;
  $("mNm").textContent=d.name; $("mOpen").href=d.url; $("mDl").href=d.url;
  const b=$("mBody");
  if(d.kind==="image") b.innerHTML=`<img src="${d.url}">`;
  else if(d.kind==="site"||d.kind==="pdf") b.innerHTML=`<iframe src="${d.url}"></iframe>`;
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
  if(e.key==="/"&&!/INPUT|TEXTAREA/.test(e.target.tagName)){e.preventDefault();$("task").focus();}
});

/* ── stat tiles ── */
function tile(cls,ic,k,v,s){return `<div class="tile ${cls}">
  <div class="h"><span class="tic">${ic}</span><span class="k">${k}</span></div>
  <div class="v">${v}</div><div class="s">${s||""}</div></div>`}

async function refresh(){
  let p;
  try{p=await j("/api/pulse");$("liveDot").classList.remove("err");$("liveTxt").textContent="canlı";}
  catch(e){$("liveDot").classList.add("err");$("liveTxt").textContent="əlaqə yoxdur";return;}
  const q=p.queue||{}, llm=p.llm||{}, env=p.env||{};
  const envOk=Object.values(env).filter(v=>String(v).startsWith("SET")).length;
  const envAll=Object.keys(env).length;
  $("git").innerHTML=`git: <b>${esc(p.git&&p.git.head||"?")}</b>${p.git&&p.git.dirty?" · dirty":""}`;
  $("cost").innerHTML=`LLM bu gün: <b>${llm.calls_today||0}</b> çağırış · <b>$${(llm.cost_usd_today||0).toFixed(3)}</b>`;
  $("cards").innerHTML =
    tile("t-acc","📥","Növbədə", q.queued??"–","işləyir: "+(q.running??0))+
    tile("t-ok","✅","Bitmiş", q.done??"–","xəta: "+(q.error??0))+
    tile("t-warn","⏸","Təsdiq gözləyir", q.awaiting_approval??0,"riskli əməllər")+
    tile("t-acc","🔑","Açarlar", `${envOk}/${envAll}`,"canlı .env refleksi")+
    tile("t-vio","🧠","Yaddaş", (p.memory&&p.memory.turns)??"–","dialoq dövrləri")+
    tile("t-vio","🗓","Cədvəllər",(p.schedules&&p.schedules.enabled)??"–","aktiv plan");

  const jobs=await j("/api/jobs?limit=25");
  $("jobs").innerHTML=jobs.map(x=>`<tr>
    <td class="mono">${x.id}</td>
    <td><span class="st ${x.status}">${x.status}</span></td>
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
  $("advisor").innerHTML=(a.findings&&a.findings.length)
    ? a.findings.map(f=>`<div class="find"><span class="lvl ${f.level}">${f.level}</span>
        <div><div>${esc(f.title)} — <span class="d">${esc(f.detail)}</span></div>
        ${f.suggestion?`<div class="sug">→ ${esc(f.suggestion)}</div>`:""}</div></div>`).join("")
    : `<div class="muted">Hər şey qaydasında — kritik risk görünmür ✅</div>`;

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
let _watchJob=null,_turns=[],_bubTxt=[];
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
      const m=txt.match(/^\[(\w+)\]\s*/); if(m){src=m[1];txt=txt.slice(m[0].length);}
    }else{
      const m=txt.match(/^_\[chat:([^\]]*)\]_\s*/);
      if(m){src=(m[1].split(/[:/]/).pop()||"").slice(0,30);txt=txt.slice(m[0].length);}
    }
    return bubble(t.role==="user"?"user":"assistant", txt, src, false);
  }).join("");
  if(_watchJob) html+=bubble("assistant","… işləyir (job #"+_watchJob+")",null,true);
  box.innerHTML=html||`<div class="muted">Söhbətə başla — bura, Telegram və Codex eyni yaddaşı görür.</div>`;
  if(atBottom||_watchJob) box.scrollTop=box.scrollHeight;
}
async function loadChat(){
  try{const c=await j("/api/chat?n=40");_turns=c.turns||[];renderChat();}catch(e){}
}
async function watchJob(id){
  _watchJob=id; loadChat();
  for(let i=0;i<120;i++){
    await new Promise(r=>setTimeout(r,2500));
    try{
      const d=await j(`/api/jobs/${id}`);
      if(d.status==="done"||d.status==="error"||d.status==="awaiting_approval"||d.status==="rejected"){
        _watchJob=null; await loadChat(); refresh(); loadDeliverables(); return;
      }
    }catch(e){}
  }
  _watchJob=null; loadChat();
}
async function submitTask(){
  const t=$("task").value.trim(); if(!t)return;
  const r=await j("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({task:t})});
  $("msg").textContent=r.id?`📥 Job #${r.id} növbəyə salındı`:(r.error||"xəta");
  setTimeout(()=>{$("msg").textContent="";},6000);
  $("task").value="";
  if(r.id){ $("chat").innerHTML+=bubble("user",t,"panel",false); $("chat").scrollTop=$("chat").scrollHeight; watchJob(r.id); }
  refresh();
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

async function doSync(){
  const b=$("syncBtn"); b.disabled=true;
  const r=await j("/api/sync",{method:"POST"});
  b.disabled=false;
  toast(r.summary||"sync bitdi",!r.ok);
  refresh();
}

renderChips();
refresh();
loadChat();
loadDeliverables();
setInterval(refresh, 15000);
setInterval(loadChat, 12000);
setInterval(loadDeliverables, 60000);
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML
