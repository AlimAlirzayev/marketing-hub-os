"""Bilik Bazası (RAG) — corporate knowledge base as its own service.

Migrated home from the 8501 Streamlit archive (2026-07-13): the last of its
three modules. The engine is unchanged (`gateway/rag.py`: Brain embedding
adapter + local JSON vector DB); this server adds the honest HTTP face:

  GET  /              — the UI (add documents · semantic search · ask)
  GET  /api/health    — liveness + document count
  GET  /api/docs      — stored documents (title + preview, no vectors)
  POST /api/docs      — embed and store a document {title, text}
  GET  /api/search?q= — vector search, returns scored sources
  POST /api/ask       — search + free-first LLM answer grounded ONLY in sources

Answering goes through llm_router (free cascade + usage ledger) instead of the
old direct-Gemini call — same policy as every other text completion.

Run:  uvicorn gateway.rag_server:app --port 8895   (registered in services.json)
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ._bootstrap import load_env
from . import rag

load_env()  # embeddings (Gemini/TEI) and llm_router need the .env keys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI(title="Bilik Bazası (RAG)")


class NewDoc(BaseModel):
    title: str
    text: str


class Question(BaseModel):
    question: str


@app.get("/api/health")
def health() -> dict:
    try:
        docs = len(rag.load_db())
    except Exception:
        docs = -1
    return {"ok": True, "docs": docs}


@app.get("/api/docs")
def list_docs() -> JSONResponse:
    out = [{"title": (d.get("metadata") or {}).get("title") or "adsız",
            "preview": (d.get("text") or "")[:180],
            "chars": len(d.get("text") or "")}
           for d in rag.load_db()]
    return JSONResponse(out)


@app.post("/api/docs")
def add_doc(body: NewDoc) -> JSONResponse:
    text = (body.text or "").strip()
    if not text:
        return JSONResponse({"error": "mətn boşdur"}, status_code=400)
    try:
        rag.add_document(text, {"title": (body.title or "").strip() or "adsız"})
    except Exception as exc:
        # Embedding provider missing/limited — say it plainly, never pretend.
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    return JSONResponse({"ok": True, "docs": len(rag.load_db())})


@app.get("/api/search")
def search(q: str) -> JSONResponse:
    try:
        results = rag.search(q)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    return JSONResponse([{"title": (r.get("metadata") or {}).get("title"),
                          "text": r.get("text"), "score": r.get("score")}
                         for r in results])


@app.post("/api/ask")
def ask(body: Question) -> JSONResponse:
    q = (body.question or "").strip()
    if not q:
        return JSONResponse({"error": "sual boşdur"}, status_code=400)
    try:
        results = rag.search(q)
    except Exception as exc:
        return JSONResponse({"error": f"axtarış alınmadı — {type(exc).__name__}: {exc}"},
                            status_code=502)
    if not results:
        return JSONResponse({"answer": None, "sources": [],
                             "note": "Bu suala uyğun daxili məlumat tapılmadı."})
    context = "\n\n".join(
        f"Mənbə: {(r.get('metadata') or {}).get('title')}\nMəzmun: {r.get('text')}"
        for r in results)
    prompt = ("Aşağıdakı korporativ məlumatlara əsasən istifadəçinin sualına dəqiq, "
              "rəsmi və qısa Azərbaycan dilində cavab ver. Yalnız verilən mənbələrə "
              "əsaslan; mənbələrdə cavab yoxdursa, açıq de — uydurma.\n\n"
              f"{context}\n\nSual: {q}\nCavab:")
    try:
        import llm_router
        answer, model = llm_router.complete(prompt, tier="cheap", temperature=0.2)
    except Exception as exc:
        return JSONResponse({"error": f"cavab hazırlanmadı — {type(exc).__name__}: {exc}",
                             "sources": [{"title": (r.get("metadata") or {}).get("title"),
                                          "text": r.get("text"), "score": r.get("score")}
                                         for r in results]}, status_code=502)
    return JSONResponse({
        "answer": (answer or "").strip(), "model": model,
        "sources": [{"title": (r.get("metadata") or {}).get("title"),
                     "text": r.get("text"), "score": r.get("score")}
                    for r in results],
    })


_HTML = """<!doctype html>
<html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bilik Bazası — RAG</title>
<style>
:root{
  --bg:#f4f3f0; --card:#ffffff; --card2:#f8f7f4; --ink:#1b1d23; --ink2:#4d5361;
  --mut:#8b8f9a; --line:#e5e3dd; --line2:#d3d0c8; --acc:#4338ca; --acc-soft:#eceefc;
  --acc-line:#c7cdf4; --ok:#087f5b; --ok-soft:#e3f5ee; --warn:#9a5b00;
  --warn-soft:#fdf2df; --bad:#c92a2a; --bad-soft:#fdecec; --btn:#1b1d23; --btnink:#fff;
  --shadow:0 1px 2px rgba(28,25,15,.04),0 10px 30px rgba(28,25,15,.06);
}
:root[data-theme="dark"]{
  --bg:#0d1117; --card:#151b24; --card2:#1a2230; --ink:#edf2f8; --ink2:#9fb0c2;
  --mut:#6d8093; --line:rgba(148,163,184,.15); --line2:rgba(148,163,184,.3);
  --acc:#8b93f8; --acc-soft:rgba(129,140,248,.14); --acc-line:rgba(129,140,248,.4);
  --ok:#34d399; --ok-soft:rgba(52,211,153,.12); --warn:#fbbf24; --warn-soft:rgba(251,191,36,.1);
  --bad:#f87171; --bad-soft:rgba(248,113,113,.12); --btn:#edf2f8; --btnink:#10141b;
  --shadow:0 1px 0 rgba(255,255,255,.03) inset,0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
button{font:inherit;cursor:pointer;border:0;background:none;color:inherit}
.topbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;padding:12px 26px;
  background:color-mix(in srgb,var(--bg) 86%,transparent);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.mark{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;background:var(--btn);
  color:var(--btnink);font-weight:800;font-family:Georgia,serif}
.bt{font-size:16px;font-weight:700}
.bt small{display:block;font-size:10.5px;font-weight:500;color:var(--mut);letter-spacing:.8px;text-transform:uppercase;line-height:1.2}
.sp{flex:1}
.badge{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 13px;font-size:12.5px;color:var(--ink2)}
.badge b{color:var(--ink)}
main{max-width:1100px;margin:0 auto;padding:22px 26px 60px;display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
@media (max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:20px}
h3{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.3px;color:var(--mut);margin-bottom:14px}
input,textarea{width:100%;background:var(--card2);border:1px solid var(--line);border-radius:11px;color:var(--ink);
  padding:11px 13px;font:inherit;font-size:14px}
textarea{min-height:130px;resize:vertical}
input:focus-visible,textarea:focus-visible,button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
label{display:block;font-size:12.5px;color:var(--ink2);margin:10px 0 5px}
.btn{display:inline-flex;align-items:center;gap:8px;border-radius:11px;padding:9px 16px;font-weight:600;font-size:13.5px;margin-top:12px}
.btn.primary{background:var(--btn);color:var(--btnink)}
.btn.primary:hover{opacity:.88}
.btn:disabled{opacity:.5;cursor:wait}
.note{font-size:12.5px;margin-top:10px;border-radius:9px;padding:9px 12px;display:none}
.note.ok{display:block;background:var(--ok-soft);color:var(--ok)}
.note.err{display:block;background:var(--bad-soft);color:var(--bad)}
.answer{background:var(--acc-soft);border:1px solid var(--acc-line);border-radius:12px;padding:14px;margin-top:14px;
  font-size:14px;white-space:pre-wrap;display:none}
.answer .mdl{display:block;font-size:10.5px;color:var(--mut);margin-top:8px}
.src{border:1px dashed var(--line2);border-radius:11px;padding:11px 13px;margin-top:10px;font-size:13px}
.src b{color:var(--acc)}
.src .sc{float:right;font-size:11px;color:var(--mut)}
.drow{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px dashed var(--line);font-size:13.5px}
.drow:last-child{border-bottom:0}
.drow b{white-space:nowrap}
.drow span{color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.drow .ch{margin-left:auto;font-size:11px;color:var(--mut);white-space:nowrap}
.muted{color:var(--mut)}
</style></head><body>
<header class="topbar">
  <div class="mark">B</div>
  <div class="bt">Bilik Bazası<small>korporativ RAG · vektor axtarışı</small></div>
  <span class="sp"></span>
  <span class="badge" id="cnt">sənəd: <b>…</b></span>
</header>
<main>
  <div style="display:flex;flex-direction:column;gap:18px">
    <div class="card">
      <h3>📥 Yeni məlumat yüklə</h3>
      <label>Sənədin adı / kateqoriya</label>
      <input id="title" placeholder="məs.: KASKO françiza qaydaları">
      <label>Məzmun (şərtlər, qərarlar, qaydalar…)</label>
      <textarea id="text" placeholder="Mətni bura yapışdır…"></textarea>
      <button class="btn primary" id="addBtn" onclick="addDoc()">Vektorlaşdır və yadda saxla</button>
      <div class="note" id="addNote"></div>
    </div>
    <div class="card">
      <h3>🗂 Saxlanan sənədlər</h3>
      <div id="docs" class="muted">yüklənir…</div>
    </div>
  </div>
  <div class="card">
    <h3>🔍 Axtarış və sual-cavab</h3>
    <input id="q" placeholder="məs.: KASKO üçün françiza qaydası necədir?"
      onkeydown="if(event.key==='Enter')askQ()">
    <button class="btn primary" id="askBtn" onclick="askQ()">Sorğu göndər</button>
    <div class="note" id="askNote"></div>
    <div class="answer" id="answer"></div>
    <div id="sources"></div>
  </div>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
try{
  const t=new URLSearchParams(location.search).get('theme')||localStorage.getItem('rs-theme');
  if(t)document.documentElement.dataset.theme=t;
}catch(e){}
function note(id,msg,err){const n=$(id);n.textContent=msg;n.className='note '+(err?'err':'ok');
  setTimeout(()=>{n.className='note';},6000);}
async function loadDocs(){
  try{
    const docs=await (await fetch('/api/docs')).json();
    $('cnt').innerHTML=`sənəd: <b>${docs.length}</b>`;
    $('docs').className='';
    $('docs').innerHTML=docs.length?docs.map(d=>
      `<div class="drow"><b>${esc(d.title)}</b><span>${esc(d.preview)}</span><span class="ch">${d.chars} simvol</span></div>`).join('')
      :'<div class="muted">Hələ sənəd yoxdur — soldan ilk sənədi əlavə et.</div>';
  }catch(e){$('docs').textContent='oxunmadı';}
}
async function addDoc(){
  const b=$('addBtn');b.disabled=true;
  try{
    const r=await fetch('/api/docs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:$('title').value,text:$('text').value})});
    const d=await r.json();
    if(d.error){note('addNote',d.error,true);}
    else{note('addNote','✓ Sənəd vektorlaşdırıldı və yadda saxlanıldı');$('title').value='';$('text').value='';loadDocs();}
  }catch(e){note('addNote','şəbəkə xətası: '+e.message,true);}
  b.disabled=false;
}
async function askQ(){
  const q=$('q').value.trim(); if(!q)return;
  const b=$('askBtn');b.disabled=true;
  $('answer').style.display='none';$('sources').innerHTML='<div class="muted" style="margin-top:12px">axtarılır…</div>';
  try{
    const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q})});
    const d=await r.json();
    if(d.error)note('askNote',d.error,true);
    if(d.note){$('sources').innerHTML='';note('askNote',d.note,true);}
    if(d.answer){
      $('answer').style.display='block';
      $('answer').innerHTML=`🤖 ${esc(d.answer)}<span class="mdl">model: ${esc(d.model||'?')} · pulsuz-birinci router</span>`;
    }
    $('sources').innerHTML=(d.sources||[]).map(s=>
      `<div class="src"><span class="sc">uyğunluq ${(+s.score).toFixed(2)}</span><b>${esc(s.title)}</b><br>${esc(s.text)}</div>`).join('');
  }catch(e){note('askNote','şəbəkə xətası: '+e.message,true);$('sources').innerHTML='';}
  b.disabled=false;
}
loadDocs();
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML
