"""Live command center — the cockpit map of the whole OS.

Alim's ask (2026-07-11): "I forget how our OS works; I need a LIVE visual map —
a node graph where I can see every agent, worker and workflow, who is doing what
right now, in real time" (the kind Doruk Yalçınsöy / Mert Durmazer built).

The engine already exposes every signal we need — this module is the *face*:
  * flow_state() turns sense.snapshot() + sense.recent() into a TOPOLOGY (the
    real architecture as nodes + edges) annotated with LIVE state — which node
    fired most recently, how long ago, how many times, and whether it needs the
    operator (parked approvals, missing keys, contradictions).
  * register(app) mounts GET /api/flow (the data) and GET /map (the page) onto
    the existing panel, so it rides the same localhost tunnel and launcher — no
    new service, no new port, no CDN (inline, offline-safe like the rest).

Zero LLM tokens to render: it is a deterministic read of the gateway's own body.
"""

from __future__ import annotations

import time

from . import sense

# --- the architecture, as the operator should see it ----------------------
# group = which lane/column the node sits in. Order matters for layout.
_NODES = [
    # intake channels (the microphones)
    ("ch_telegram", "Telegram", "channel"),
    ("ch_codex", "Codex", "channel"),
    ("ch_panel", "Panel", "channel"),
    ("ch_schedule", "Scheduler", "channel"),
    # unified intake
    ("mic", "One Microphone", "intake"),
    ("queue", "Job Queue", "intake"),
    ("supervisor", "Supervisor 24/7", "intake"),
    # the dispatch brain
    ("executor", "Executor / Router", "brain"),
    ("checkpoint", "Human Checkpoint", "brain"),
    # specialist lanes
    ("m_converse", "Converse", "lane"),
    ("m_fanout", "Specialist Fan-out", "lane"),
    ("m_content", "Content Studio", "lane"),
    ("m_tools", "Tools / Hands", "lane"),
    ("m_browser", "Browser Agent", "lane"),
    ("m_research", "Research (grounded)", "lane"),
    ("m_council", "AI Council", "lane"),
    ("m_creds", "doit (credentials)", "lane"),
    # shared backends
    ("gateway", "Model Gateway", "backend"),
    ("studios", "Studios", "backend"),
    ("memory", "Shared Memory", "backend"),
]

_EDGES = [
    ("ch_telegram", "mic"), ("ch_codex", "mic"), ("ch_panel", "mic"),
    ("ch_schedule", "queue"),
    ("mic", "queue"), ("supervisor", "queue"),
    ("queue", "executor"),
    ("executor", "checkpoint"),
    ("executor", "m_converse"), ("executor", "m_fanout"), ("executor", "m_content"),
    ("executor", "m_tools"), ("executor", "m_browser"), ("executor", "m_research"),
    ("executor", "m_council"), ("executor", "m_creds"),
    ("m_converse", "gateway"), ("m_fanout", "gateway"), ("m_content", "gateway"),
    ("m_research", "gateway"), ("m_council", "gateway"),
    ("m_tools", "studios"), ("m_content", "studios"), ("m_browser", "studios"),
    ("m_converse", "memory"), ("m_fanout", "memory"), ("m_tools", "memory"),
    ("checkpoint", "memory"),
]


def _classify(ev: dict) -> str | None:
    """Map one sense event to the node it lit up."""
    kind = ev.get("kind", "")
    s = (ev.get("summary") or "").lower()
    if kind == "mic":
        if "telegram" in s:
            return "ch_telegram"
        if "codex" in s:
            return "ch_codex"
        if "panel" in s:
            return "ch_panel"
        return "mic"
    if kind == "schedule":
        return "ch_schedule"
    if kind == "job":
        return "queue"
    if kind == "sync":
        return "supervisor"
    if kind == "security":
        return "checkpoint"
    if kind == "credential":
        return "m_creds"
    if kind == "stt":
        return "ch_telegram"
    if kind == "llm":
        # the label carries the mode: "fanout:...", "chat:...", "council:...",
        # "content:...", "browser:...", "google-search...", "agentic-tools:..."
        if s.startswith("fanout"):
            return "m_fanout"
        if s.startswith("content"):
            return "m_content"
        if s.startswith("council"):
            return "m_council"
        if s.startswith("browser"):
            return "m_browser"
        if "search" in s or "research" in s or "grounded" in s:
            return "m_research"
        if "tool" in s:
            return "m_tools"
        return "m_converse"
    return None


def _state_for(age_s: float | None, warn: bool) -> str:
    if warn:
        return "warn"
    if age_s is None:
        return "idle"
    if age_s <= 12:
        return "active"
    if age_s <= 90:
        return "recent"
    return "idle"


def flow_state() -> dict:
    """The full live topology + KPIs for one poll of the command center."""
    snap = sense.snapshot()
    now = time.time()
    events = sense.recent(60)

    # newest event + hit count per node, from the event stream
    last_ts: dict[str, float] = {}
    hits: dict[str, int] = {}
    last_summary: dict[str, str] = {}
    annotated = []
    for ev in events:
        node = _classify(ev)
        annotated.append({**ev, "node": node})
        if not node:
            continue
        hits[node] = hits.get(node, 0) + 1
        ts = ev.get("ts") or 0
        if ts >= last_ts.get(node, 0):
            last_ts[node] = ts
            last_summary[node] = ev.get("summary", "")

    q = snap.get("queue", {}) or {}
    parked = int(q.get("awaiting_approval", 0) or 0)
    env = snap.get("env", {}) or {}
    missing = [k for k, v in env.items() if isinstance(v, str) and v.startswith("MISSING")]
    contradictions = snap.get("contradictions", []) or []

    # per-node warning conditions surface where the operator is needed
    warn_nodes: dict[str, str] = {}
    if parked:
        warn_nodes["checkpoint"] = f"{parked} approval gözləyir"
    if missing:
        warn_nodes["gateway"] = f"{len(missing)} açar yoxdur: {', '.join(missing)[:60]}"
    if int(q.get("error", 0) or 0):
        warn_nodes["queue"] = f"{q.get('error')} uğursuz iş"

    nodes = []
    for nid, label, group in _NODES:
        ts = last_ts.get(nid)
        age = (now - ts) if ts else None
        warn = nid in warn_nodes
        nodes.append({
            "id": nid, "label": label, "group": group,
            "state": _state_for(age, warn),
            "age_s": round(age) if age is not None else None,
            "hits": hits.get(nid, 0),
            "last": warn_nodes.get(nid) or last_summary.get(nid, ""),
        })

    llm = snap.get("llm", {}) or {}
    git = snap.get("git", {}) or {}
    return {
        "ts": now,
        "kpis": {
            "running": int(q.get("running", 0) or 0),
            "queued": int(q.get("queued", 0) or 0),
            "done": int(q.get("done", 0) or 0),
            "parked": parked,
            "errors": int(q.get("error", 0) or 0),
            "calls_today": int(llm.get("calls_today", 0) or 0),
            "cost_usd_today": llm.get("cost_usd_today", 0),
            "memory": (snap.get("memory", {}) or {}).get("shared_entries")
                      or (snap.get("memory", {}) or {}).get("entries", 0),
            "schedules": (snap.get("schedules", {}) or {}).get("active", 0),
            "git_dirty": bool(git.get("dirty")),
            "branch": git.get("branch", "?"),
        },
        "health": {
            "needs_operator": bool(parked or missing or contradictions),
            "missing_keys": missing,
            "contradictions": len(contradictions),
        },
        "nodes": nodes,
        "edges": _EDGES,
        "events": list(reversed(annotated))[:24],  # newest first
        "by_model": llm.get("by_model", {}),
    }


def register(app) -> None:
    """Mount the command center onto an existing FastAPI app."""
    from fastapi.responses import HTMLResponse, JSONResponse

    @app.get("/api/flow")
    def _flow() -> JSONResponse:  # noqa: ANN202
        return JSONResponse(flow_state())

    @app.get("/map", response_class=HTMLResponse)
    def _map() -> str:  # noqa: ANN202
        return _MAP_HTML


# The page is intentionally self-contained (inline CSS/JS, no CDN) — offline-safe
# like every other Ramin-OS surface, and it rides the panel's localhost tunnel.
_MAP_HTML = r"""<!doctype html>
<html lang="az"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ramin-OS — Komanda Mərkəzi (canlı)</title>
<style>
:root{
  --bg:#0b0f17; --panel:#121826; --panel2:#0e1420; --line:#1e2942;
  --ink:#e7eefc; --dim:#8595b4; --accent:#5b8cff; --ok:#25c26e; --warn:#f5a524;
  --err:#f2495c; --active:#42e6a4; --recent:#3b6fd4;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{display:flex;flex-direction:column;height:100vh}
header{display:flex;align-items:center;gap:16px;padding:12px 18px;
  border-bottom:1px solid var(--line);background:var(--panel2)}
header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:.2px}
header .dot{width:9px;height:9px;border-radius:50%;background:var(--active);
  box-shadow:0 0 0 0 rgba(66,230,164,.6);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(66,230,164,.5)}
  70%{box-shadow:0 0 0 9px rgba(66,230,164,0)}100%{box-shadow:0 0 0 0 rgba(66,230,164,0)}}
header .spacer{flex:1}
header .meta{color:var(--dim);font-size:12px}
.kpis{display:flex;gap:10px;padding:10px 18px;flex-wrap:wrap;
  border-bottom:1px solid var(--line);background:var(--panel2)}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:8px 12px;min-width:96px}
.kpi .v{font-size:19px;font-weight:700}
.kpi .l{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.4px}
.kpi.warn .v{color:var(--warn)} .kpi.err .v{color:var(--err)} .kpi.ok .v{color:var(--ok)}
.main{flex:1;display:flex;min-height:0}
.mapwrap{flex:1;position:relative;overflow:auto}
svg{display:block;width:100%;height:100%;min-width:900px;min-height:560px}
.side{width:340px;border-left:1px solid var(--line);background:var(--panel2);
  display:flex;flex-direction:column;min-height:0}
.side h2{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);
  margin:0;padding:12px 16px 8px}
.events{overflow:auto;flex:1;padding:0 12px 12px}
.ev{display:flex;gap:8px;padding:7px 8px;border-radius:8px;font-size:12.5px;
  border:1px solid transparent}
.ev:hover{background:var(--panel);border-color:var(--line)}
.ev .k{font-size:10px;padding:1px 6px;border-radius:20px;background:var(--line);
  color:var(--ink);height:fit-content;white-space:nowrap}
.ev .s{color:var(--ink)} .ev .t{color:var(--dim);margin-left:auto;white-space:nowrap;font-size:11px}
.k.llm{background:#243a6b} .k.job{background:#1f4d38} .k.mic{background:#3a2a5c}
.k.security,.k.credential{background:#5c3320} .k.sync{background:#24405c} .k.schedule{background:#4a3b1c}
.banner{margin:0 12px 10px;padding:9px 12px;border-radius:9px;font-size:12.5px;
  background:rgba(245,165,36,.12);border:1px solid rgba(245,165,36,.35);color:#ffd98a;display:none}
.node{cursor:default}
.node rect{fill:var(--panel);stroke:var(--line);stroke-width:1.2;rx:9}
.node text{fill:var(--ink);font-size:12px;font-weight:600}
.node .sub{fill:var(--dim);font-size:9.5px;font-weight:500}
.node.active rect{stroke:var(--active);fill:#0f2620}
.node.recent rect{stroke:var(--recent);fill:#0f1a30}
.node.warn rect{stroke:var(--warn);fill:#2a2211}
.node .hit{fill:var(--dim);font-size:9px}
.edge{stroke:var(--line);stroke-width:1.3;fill:none}
.edge.hot{stroke:var(--active);stroke-width:2}
.grouplbl{fill:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:1px}
.legend{display:flex;gap:14px;padding:8px 18px;border-top:1px solid var(--line);
  background:var(--panel2);font-size:11px;color:var(--dim);flex-wrap:wrap}
.legend b{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:5px;vertical-align:middle}
</style></head>
<body><div class="wrap">
<header>
  <span class="dot"></span>
  <h1>Ramin-OS · Komanda Mərkəzi</h1>
  <span class="meta" id="clock"></span>
  <div class="spacer"></div>
  <span class="meta" id="branch"></span>
</header>
<div class="kpis" id="kpis"></div>
<div class="main">
  <div class="mapwrap"><svg id="svg" viewBox="0 0 1070 620" preserveAspectRatio="xMidYMid meet"></svg></div>
  <div class="side">
    <h2>Canlı axın</h2>
    <div class="banner" id="banner"></div>
    <div class="events" id="events"></div>
  </div>
</div>
<div class="legend">
  <span><b style="background:#42e6a4"></b>indi aktiv</span>
  <span><b style="background:#3b6fd4"></b>bir az əvvəl</span>
  <span><b style="background:#f5a524"></b>diqqət lazımdır</span>
  <span><b style="background:#1e2942"></b>boşdur</span>
  <span class="spacer"></span>
</div>
</div>
<script>
// layout: fixed columns by group, real architecture left→right
const COLS = {channel:30, intake:250, brain:455, lane:665, backend:895};
const GY = {channel:0, intake:0, brain:0, lane:0, backend:0};
const NW=150, NH=46, VGAP=16;
let LAYOUT=null;

function layout(nodes){
  const byg={};
  nodes.forEach(n=>{(byg[n.group]=byg[n.group]||[]).push(n)});
  const pos={};
  Object.entries(byg).forEach(([g,list])=>{
    const totalH=list.length*NH+(list.length-1)*VGAP;
    let y=(620-totalH)/2;
    list.forEach(n=>{pos[n.id]={x:COLS[g]||500,y:y,cx:(COLS[g]||500)+NW/2,cy:y+NH/2};y+=NH+VGAP});
  });
  return pos;
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function ago(s){if(s==null)return '';if(s<60)return s+'s';if(s<3600)return Math.round(s/60)+'d';return Math.round(s/3600)+'h'}

function draw(d){
  const svg=document.getElementById('svg');
  const pos=layout(d.nodes); LAYOUT=pos;
  const active=new Set(d.nodes.filter(n=>n.state==='active').map(n=>n.id));
  let g='';
  // group headers
  const seen={};
  d.nodes.forEach(n=>{if(!seen[n.group]){seen[n.group]=1;
    const x=(COLS[n.group]||500);
    g+=`<text class="grouplbl" x="${x}" y="24">${({channel:'KANALLAR',intake:'QƏBUL',brain:'BEYİN',lane:'İXTİSAS XƏTLƏRİ',backend:'ARXA SERVİS'})[n.group]||n.group}</text>`;
  }});
  // edges
  d.edges.forEach(([a,b])=>{
    const pa=pos[a],pb=pos[b]; if(!pa||!pb)return;
    const hot=active.has(a)&&(active.has(b)|| d.nodes.find(n=>n.id===b&&n.state!=='idle'));
    const x1=pa.x+NW,y1=pa.cy,x2=pb.x,y2=pb.cy,mx=(x1+x2)/2;
    g+=`<path class="edge ${hot?'hot':''}" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
  });
  // nodes
  d.nodes.forEach(n=>{
    const p=pos[n.id]; if(!p)return;
    const sub=(n.last||'').slice(0,18);
    g+=`<g class="node ${n.state}" transform="translate(${p.x},${p.y})">
      <rect width="${NW}" height="${NH}" rx="9"></rect>
      <text x="12" y="19">${esc(n.label)}</text>
      <text class="sub" x="12" y="34">${esc(sub)||'&#8203;'}</text>
      ${n.hits?`<text class="hit" x="${NW-10}" y="16" text-anchor="end">${n.hits}</text>`:''}
      ${n.age_s!=null?`<text class="hit" x="${NW-10}" y="34" text-anchor="end">${ago(n.age_s)}</text>`:''}
    </g>`;
  });
  svg.innerHTML=g;
}

function kpis(k){
  const box=document.getElementById('kpis');
  const cost=(k.cost_usd_today||0);
  const items=[
    ['İŞLƏYİR',k.running,k.running?'ok':''],
    ['NÖVBƏDƏ',k.queued,k.queued?'warn':''],
    ['TAMAM',k.done,''],
    ['TƏSDİQ GÖZLƏYİR',k.parked,k.parked?'warn':''],
    ['XƏTA',k.errors,k.errors?'err':''],
    ['MODEL ÇAĞIRIŞI (bugün)',k.calls_today,''],
    ['XƏRC $ (bugün)',cost.toFixed?cost.toFixed(2):cost,cost>0?'warn':'ok'],
    ['YADDAŞ',k.memory,''],
    ['CƏDVƏL',k.schedules,''],
  ];
  box.innerHTML=items.map(([l,v,c])=>`<div class="kpi ${c}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  document.getElementById('branch').textContent=(k.branch||'')+(k.git_dirty?' ●':'');
}

function events(evs){
  const box=document.getElementById('events');
  box.innerHTML=evs.map(e=>{
    const t=new Date((e.ts||0)*1000).toLocaleTimeString('az',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
    return `<div class="ev"><span class="k ${esc(e.kind)}">${esc(e.kind)}</span>
      <span class="s">${esc((e.summary||'').slice(0,70))}</span><span class="t">${t}</span></div>`;
  }).join('');
}

async function tick(){
  try{
    const d=await (await fetch('/api/flow')).json();
    draw(d); kpis(d.kpis); events(d.events);
    const b=document.getElementById('banner');
    if(d.health.needs_operator){
      const parts=[];
      if(d.kpis.parked)parts.push(d.kpis.parked+' iş təsdiq gözləyir');
      if(d.health.missing_keys.length)parts.push('açar yoxdur: '+d.health.missing_keys.join(', '));
      if(d.health.contradictions)parts.push(d.health.contradictions+' ziddiyyət');
      b.textContent='⚠ '+parts.join(' · '); b.style.display='block';
    } else b.style.display='none';
    document.getElementById('clock').textContent='yeniləndi '+new Date().toLocaleTimeString('az');
  }catch(e){
    document.getElementById('clock').textContent='bağlantı yoxdur — yenidən cəhd…';
  }
}
tick(); setInterval(tick, 2500);
</script></body></html>"""
