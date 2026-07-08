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


@app.get("/api/deliverables")
def deliverables(limit: int = 60) -> JSONResponse:
    """Everything the system produced, newest first, classified for visual
    review. Job artifacts + a scan of the output roots."""
    items: dict[str, dict] = {}
    for root in _DELIVERABLE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in _PREVIEW_EXT:
                continue
            try:
                rel = p.relative_to(ROOT).as_posix()
            except ValueError:
                continue
            try:
                stat = p.stat()
            except OSError:
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
:root{--bg:#0b0f14;--card:#121a23;--card2:#0f1620;--line:#1f2b3a;--txt:#e8eef5;
--dim:#8aa0b5;--acc:#38bdf8;--ok:#34d399;--warn:#fbbf24;--bad:#f87171;--vio:#a78bfa}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--txt);font:14px/1.5 "Segoe UI",system-ui,sans-serif;padding:24px}
h1{font-size:20px;letter-spacing:.3px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim);margin-bottom:10px}
.top{display:flex;align-items:center;gap:14px;margin-bottom:20px;flex-wrap:wrap}
.top .sp{flex:1}
.badge{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:12px;color:var(--dim)}
.badge b{color:var(--txt)}
button{background:var(--acc);color:#04212e;border:0;border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer}
button.ghost{background:var(--card);color:var(--txt);border:1px solid var(--line)}
button.ok{background:var(--ok);color:#052e21} button.bad{background:var(--bad);color:#3a0a0a}
button:disabled{opacity:.5;cursor:wait}
select{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--dim)}
.card .v{font-size:22px;font-weight:700;margin-top:4px}
.card .s{font-size:12px;color:var(--dim);margin-top:2px}
section{background:var(--card2);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:18px}
.approval{border:1px solid #4a3305;background:#1d1503;border-radius:12px;padding:12px;margin-bottom:8px;
display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.approval .t{flex:1;min-width:220px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--dim);text-align:left;font-weight:500;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.st{border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap}
.st.done{background:#0b2e22;color:var(--ok)} .st.queued{background:#0b2233;color:var(--acc)}
.st.running{background:#251d3f;color:var(--vio)} .st.error{background:#330f0f;color:var(--bad)}
.st.awaiting_approval{background:#332605;color:var(--warn)} .st.rejected{background:#2a1212;color:#e08b8b}
.find{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px}
.find:last-child{border-bottom:0}
.find .lvl{font-size:11px;font-weight:700;border-radius:6px;padding:2px 8px;height:fit-content;white-space:nowrap}
.lvl.risk{background:#330f0f;color:var(--bad)} .lvl.watch{background:#332605;color:var(--warn)}
.lvl.info{background:#0b2233;color:var(--acc)}
.find .sug{color:var(--dim);font-size:12px;margin-top:2px}
textarea{width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;color:var(--txt);
padding:10px;font:inherit;min-height:64px;resize:vertical}
.row{display:flex;gap:10px;margin-top:10px;align-items:center}
.ev{font-size:12px;color:var(--dim);padding:3px 0;border-bottom:1px dashed var(--line)}
.lamp{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.muted{color:var(--dim)} .mono{font-family:Consolas,monospace;font-size:12px}
#msg{font-size:13px;color:var(--ok);min-height:18px}
details summary{cursor:pointer;color:var(--acc);font-size:12px}
pre{white-space:pre-wrap;font-size:12px;color:var(--dim);margin-top:6px;max-height:300px;overflow:auto}
/* deliverables gallery — the visual front office */
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;cursor:pointer;transition:.15s;display:flex;flex-direction:column}
.tile:hover{border-color:var(--acc);transform:translateY(-2px)}
.thumb{height:148px;background:#0a0e13;display:flex;align-items:center;justify-content:center;overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb iframe{width:200%;height:296px;transform:scale(.5);transform-origin:0 0;border:0;pointer-events:none;background:#fff}
.thumb .ic{font-size:42px;opacity:.85}
.tmeta{padding:9px 12px}
.tmeta .nm{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tmeta .kd{font-size:11px;color:var(--dim);margin-top:4px;display:flex;justify-content:space-between;align-items:center}
.kbadge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;border-radius:5px;padding:1px 7px}
.kbadge.site{background:#0b2233;color:var(--acc)} .kbadge.image{background:#251d3f;color:var(--vio)}
.kbadge.report{background:#0b2e22;color:var(--ok)} .kbadge.video,.kbadge.audio{background:#332605;color:var(--warn)}
.kbadge.bundle,.kbadge.file,.kbadge.pdf{background:#1f2b3a;color:var(--dim)}
.modal{position:fixed;inset:0;background:rgba(3,6,10,.86);display:none;align-items:center;justify-content:center;z-index:50;padding:20px}
.modal.on{display:flex}
.mbox{background:var(--card2);border:1px solid var(--line);border-radius:16px;width:min(1150px,96vw);height:90vh;display:flex;flex-direction:column;overflow:hidden}
.mbar{display:flex;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line)}
.mbar .nm{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mbar a{text-decoration:none}
.mbody{flex:1;overflow:auto;background:#0a0e13}
.mbody iframe{width:100%;height:100%;border:0;background:#fff}
.mbody img{max-width:100%;display:block;margin:0 auto}
.mbody pre.md{padding:26px;white-space:pre-wrap;color:var(--txt);font:14px/1.65 "Segoe UI",system-ui;max-height:none;margin:0}
</style></head><body>

<div class="top">
  <h1>🎛️ RAMIN OS — İdarəetmə Mərkəzi</h1>
  <span class="badge" id="git">git: …</span>
  <span class="badge" id="cost">LLM bu gün: …</span>
  <span class="sp"></span>
  <button class="ghost" id="syncBtn" onclick="doSync()">🔄 Engine sync</button>
  <button class="ghost" onclick="refresh()">↻ Yenilə</button>
</div>

<div class="grid" id="cards"></div>

<section>
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
    <h2 style="margin:0">🖥️ Nəticələr — ön büro (gözünlə yoxla)</h2>
    <span style="flex:1"></span>
    <select id="delFilter" onchange="renderDeliverables()">
      <option value="all">hamısı</option>
      <option value="site">🌐 saytlar</option>
      <option value="image">🖼️ şəkillər</option>
      <option value="report">📄 hesabatlar</option>
      <option value="video">🎬 video</option>
      <option value="bundle">📦 paketlər</option>
    </select>
    <button class="ghost" onclick="loadDeliverables()">↻</button>
  </div>
  <div class="gallery" id="gallery"><div class="muted">yüklənir…</div></div>
</section>

<section id="approvalsWrap" style="display:none">
  <h2>⏸ Təsdiq gözləyənlər — bayıra yönəlik əməllər</h2>
  <div id="approvals"></div>
</section>

<section>
  <h2>➕ Yeni tapşırıq (pulsuz beyin icra edir)</h2>
  <textarea id="task" placeholder="Tapşırığı yaz… (məs.: KASKO üçün 3 kampaniya ideyası hazırla)"></textarea>
  <div class="row">
    <button onclick="submitTask()">Növbəyə göndər</button>
    <span id="msg"></span>
  </div>
</section>

<section>
  <h2>🧭 Məsləhətçi — növbəti ən yaxşı addımlar (canlı fakt, LLM-siz)</h2>
  <div id="advisor" class="muted">yüklənir…</div>
</section>

<section>
  <h2>🗂 Son işlər</h2>
  <table><thead><tr><th>#</th><th>Status</th><th>Mənbə</th><th>Tapşırıq</th><th>Nəticə</th></tr></thead>
  <tbody id="jobs"></tbody></table>
</section>

<section>
  <h2>📡 Son hadisələr</h2>
  <div id="events" class="muted">yüklənir…</div>
</section>

<div class="modal" id="modal" onclick="if(event.target.id==='modal')closeModal()">
  <div class="mbox">
    <div class="mbar">
      <span class="nm" id="mNm"></span>
      <a class="badge" id="mOpen" target="_blank">↗ tam aç</a>
      <a class="badge" id="mDl" download>⬇ yüklə</a>
      <button class="ghost" onclick="closeModal()">✕</button>
    </div>
    <div class="mbody" id="mBody"></div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function j(url,opt){const r=await fetch(url,opt);return r.json()}

// ---- deliverables: the visual front office ----
let _deliverables=[];
const _IC={site:"🌐",image:"🖼️",report:"📄",video:"🎬",audio:"🎵",bundle:"📦",pdf:"📕",file:"📎"};
function fmtSize(b){return b>1e6?(b/1e6).toFixed(1)+"MB":b>1e3?(b/1e3).toFixed(0)+"KB":b+"B"}
async function loadDeliverables(){
  try{_deliverables=await j("/api/deliverables?limit=60");}catch(e){_deliverables=[];}
  renderDeliverables();
}
function renderDeliverables(){
  const f=$("delFilter")?$("delFilter").value:"all";
  const list=_deliverables.filter(d=>f==="all"||d.kind===f);
  if(!list.length){$("gallery").innerHTML=`<div class="muted">hələ nəticə yoxdur — bir tapşırıq ver, burada görünəcək.</div>`;return;}
  $("gallery").innerHTML=list.map((d,i)=>{
    let thumb;
    if(d.kind==="image") thumb=`<img src="${d.url}" loading="lazy">`;
    else if(d.kind==="site") thumb=`<iframe src="${d.url}" scrolling="no" loading="lazy"></iframe>`;
    else thumb=`<div class="ic">${_IC[d.kind]||"📎"}</div>`;
    return `<div class="tile" onclick="openDeliverable(${i})" title="${esc(d.name)}">
      <div class="thumb">${thumb}</div>
      <div class="tmeta"><div class="nm">${esc(d.name)}</div>
        <div class="kd"><span class="kbadge ${d.kind}">${d.kind}</span><span>${fmtSize(d.size)}</span></div>
      </div></div>`;
  }).join("");
}
async function openDeliverable(i){
  const d=_deliverables[i]; if(!d)return;
  $("mNm").textContent=d.name; $("mOpen").href=d.url; $("mDl").href=d.url;
  const b=$("mBody");
  if(d.kind==="image") b.innerHTML=`<img src="${d.url}">`;
  else if(d.kind==="site"||d.kind==="pdf") b.innerHTML=`<iframe src="${d.url}"></iframe>`;
  else if(d.kind==="video") b.innerHTML=`<video src="${d.url}" controls style="width:100%;max-height:100%"></video>`;
  else if(d.kind==="audio") b.innerHTML=`<div style="padding:40px"><audio src="${d.url}" controls style="width:100%"></audio></div>`;
  else if(d.kind==="report"){
    try{const t=await (await fetch(d.url)).text(); b.innerHTML=`<pre class="md">${esc(t)}</pre>`;}
    catch(e){b.innerHTML=`<div class="muted" style="padding:40px">oxunmadı</div>`;}
  } else b.innerHTML=`<div style="padding:48px;text-align:center" class="muted">Önizləmə yoxdur — “yüklə” düyməsini işlət.</div>`;
  $("modal").classList.add("on");
}
function closeModal(){$("modal").classList.remove("on"); $("mBody").innerHTML="";}
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});

function card(k,v,s){return `<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s||""}</div></div>`}

async function refresh(){
  const p=await j("/api/pulse");
  const q=p.queue||{}, llm=p.llm||{}, env=p.env||{};
  const envOk=Object.values(env).filter(v=>String(v).startsWith("SET")).length;
  const envAll=Object.keys(env).length;
  $("git").innerHTML=`git: <b>${esc(p.git&&p.git.head||"?")}</b>${p.git&&p.git.dirty?" · dirty":""}`;
  $("cost").innerHTML=`LLM bu gün: <b>${llm.calls_today||0} çağırış</b> · $${(llm.cost_usd_today||0).toFixed(3)}`;
  $("cards").innerHTML =
    card("Növbədə", q.queued??"–","işləyir: "+(q.running??0))+
    card("Bitmiş", q.done??"–","xəta: "+(q.error??0))+
    card("Təsdiq gözləyir", q.awaiting_approval??0,"riskli əməllər")+
    card("Açarlar", `${envOk}/${envAll}`,"canlı .env refleksi")+
    card("Yaddaş", (p.memory&&p.memory.turns)??"–","dialoq dövrləri")+
    card("Cədvəllər",(p.schedules&&p.schedules.enabled)??"–","aktiv plan");

  const jobs=await j("/api/jobs?limit=25");
  $("jobs").innerHTML=jobs.map(x=>`<tr>
    <td class="mono">${x.id}</td>
    <td><span class="st ${x.status}">${x.status}</span></td>
    <td class="muted">${esc(x.source)}</td>
    <td>${esc(x.task.slice(0,90))}</td>
    <td>${x.result_preview?`<details><summary>bax</summary><pre>${esc(x.result_preview)}</pre></details>`:`<span class="muted">${esc(x.error||"—")}</span>`}</td>
  </tr>`).join("");

  const parked=jobs.filter(x=>x.status==="awaiting_approval");
  $("approvalsWrap").style.display=parked.length?"block":"none";
  $("approvals").innerHTML=parked.map(x=>`<div class="approval">
     <div class="t"><b>#${x.id}</b> — ${esc(x.task)}</div>
     <button class="ok" onclick="decide(${x.id},'approve')">✅ Təsdiqlə</button>
     <button class="bad" onclick="decide(${x.id},'reject')">🚫 İmtina</button>
   </div>`).join("");

  const a=await j("/api/advisor");
  $("advisor").innerHTML=(a.findings&&a.findings.length)
    ? a.findings.map(f=>`<div class="find"><span class="lvl ${f.level}">${f.level}</span>
        <div><div>${esc(f.title)} — <span class="muted">${esc(f.detail)}</span></div>
        ${f.suggestion?`<div class="sug">→ ${esc(f.suggestion)}</div>`:""}</div></div>`).join("")
    : `<div class="muted">Hər şey qaydasında — kritik risk görünmür ✅</div>`;

  const ev=await j("/api/events?n=15");
  $("events").innerHTML=ev.reverse().map(e=>{
    const t=new Date((e.ts||0)*1000).toLocaleTimeString("az");
    return `<div class="ev"><span class="lamp" style="background:var(--acc)"></span>[${t}] <b>${esc(e.kind)}</b> — ${esc(e.summary)}</div>`
  }).join("")||`<div class="muted">hadisə yoxdur</div>`;
}

async function decide(id,action){
  await j(`/api/jobs/${id}/${action}`,{method:"POST"});
  refresh();
}

async function submitTask(){
  const t=$("task").value.trim(); if(!t)return;
  const r=await j("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({task:t})});
  $("msg").textContent=r.id?`📥 Job #${r.id} növbəyə salındı`:(r.error||"xəta");
  $("task").value=""; refresh();
}

async function doSync(){
  const b=$("syncBtn"); b.disabled=true; b.textContent="🔄 sinxronlaşır…";
  const r=await j("/api/sync",{method:"POST"});
  b.disabled=false; b.textContent="🔄 Engine sync";
  $("msg").textContent=r.summary||"";
  refresh();
}

refresh();
loadDeliverables();
setInterval(refresh, 15000);
setInterval(loadDeliverables, 60000);
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML
