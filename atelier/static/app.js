"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => (s ?? "").toString()
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const state = { brand: null, current: null, view: "cards" };

// -------------------------------------------------------------------- API
async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}
const postJSON = (url, body) =>
  api(url, { method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify(body) });

// -------------------------------------------------------------------- UI bits
function toast(msg, ok = true) {
  const t = $("#toast");
  t.textContent = msg;
  t.style.borderColor = ok ? "#2A2A30" : "#E31E24";
  t.style.opacity = "1";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.style.opacity = "0"), 2200);
}
function lightbox(src) {
  $("#lightboxImg").src = src;
  const lb = $("#lightbox");
  lb.classList.remove("hidden"); lb.classList.add("flex");
}
function copy(text, label = "Kopyalandı") {
  navigator.clipboard.writeText(text).then(() => toast(label));
}
function scoreColor(s) {
  if (s == null) return "#8A8A93";
  if (s >= 80) return "#16A34A";
  if (s >= 60) return "#F59E0B";
  return "#E31E24";
}

// -------------------------------------------------------------------- boot
async function boot() {
  try {
    state.brand = await api("/api/brand");
  } catch (e) { toast("Brand yüklənmədi: " + e.message, false); return; }
  const b = state.brand;
  $("#tagline").textContent = b.tagline || "Creative Lab";

  fillSelect($("#selStyle"), b.styles.map(s => [s.key, s.title]), b.state.active_style);
  fillSelect($("#selFormat"), b.formats.map(f => [f, f]), b.state.default_format);
  fillSelect($("#selDialect"), b.dialects.map(d => [d, d]), b.state.active_dialect);
  $("#selN").value = String(b.state.default_n || 4);

  renderBrand();
  loadHealth();
  loadHistory();
}

function fillSelect(el, pairs, active) {
  el.innerHTML = pairs.map(([v, l]) =>
    `<option value="${esc(v)}" ${v === active ? "selected" : ""}>${esc(l)}</option>`).join("");
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("#aiDot").style.background = h.ai ? "#16A34A" : "#F59E0B";
    $("#aiLabel").textContent = h.ai ? "AI hazır" : "AI offline (şablon)";
    $("#aiLabel").className = h.ai ? "text-green-400" : "text-amber-400";
  } catch (e) {
    $("#aiDot").style.background = "#E31E24";
    $("#aiLabel").textContent = "server xəta";
  }
}

// -------------------------------------------------------------------- tabs
$$(".tabbtn").forEach(btn => btn.onclick = () => {
  $$(".tabbtn").forEach(b => b.dataset.active = "false");
  btn.dataset.active = "true";
  const tab = btn.dataset.tab;
  $("#tab-lab").classList.toggle("hidden", tab !== "lab");
  $("#tab-brand").classList.toggle("hidden", tab !== "brand");
});

// -------------------------------------------------------------------- Lab
$("#generateBtn").onclick = generate;
async function generate() {
  const brief = $("#brief").value.trim();
  if (!brief) { toast("Brief yaz", false); return; }
  const btn = $("#generateBtn");
  btn.disabled = true; btn.innerHTML = "<span class='animate-spin inline-block'>◌</span> Yaradılır…";
  $("#emptyLab").classList.add("hidden");
  $("#boardBar").classList.remove("hidden"); $("#boardBar").classList.add("flex");
  $("#briefEcho").textContent = brief;
  $("#sourceBadge").innerHTML = "";
  renderSkeleton(parseInt($("#selN").value, 10) || 4);
  try {
    const data = await postJSON("/api/lab/compose", {
      brief,
      style: $("#selStyle").value,
      format: $("#selFormat").value,
      dialect: $("#selDialect").value,
      n: parseInt($("#selN").value, 10),
      with_caption: $("#withCaption").checked,
    });
    state.current = data;
    renderBoard();
    loadHistory();
  } catch (e) {
    toast("Xəta: " + e.message, false);
    $("#board").innerHTML = "";
  } finally {
    btn.disabled = false; btn.innerHTML = "<span>✦</span> Konsept yarat";
  }
}

function renderSkeleton(n) {
  $("#board").className = "grid gap-4 md:grid-cols-2";
  $("#board").innerHTML = Array.from({ length: n }, () =>
    `<div class="bg-card border border-line rounded-2xl h-72 skel"></div>`).join("");
}

// view toggle
$$(".viewbtn").forEach(btn => btn.onclick = () => {
  $$(".viewbtn").forEach(b => { b.dataset.active = "false"; b.classList.add("text-muted"); });
  btn.dataset.active = "true"; btn.classList.remove("text-muted");
  state.view = btn.dataset.view;
  renderBoard();
});

function renderBoard() {
  const cur = state.current;
  if (!cur) return;
  if (cur.source) {
    $("#sourceBadge").innerHTML = cur.source === "gemini"
      ? `<span class="text-[10px] px-2 py-0.5 rounded-full bg-green-500/15 text-green-400">AI art-director</span>`
      : `<span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400">şablon (AI offline)</span>`;
  }
  state.view === "gallery" ? renderGallery() : renderCards();
}

function imgUrl(c) { return c.image_path ? `/uploads/${c.image_path}` : null; }

function renderCards() {
  const board = $("#board");
  board.className = "grid gap-4 md:grid-cols-2";
  board.innerHTML = "";
  state.current.concepts.forEach(c => board.appendChild(card(c)));
}

function card(c) {
  const el = document.createElement("div");
  el.className = "bg-card border border-line rounded-2xl p-4 fade-in flex flex-col";
  el.id = `concept-${c.id}`;
  const img = imgUrl(c);
  el.innerHTML = `
    <div class="flex items-start justify-between gap-2 mb-2">
      <div>
        <div class="font-bold text-[15px]">${esc(c.angle) || "Konsept"}</div>
        <div class="text-xs text-muted mt-0.5">${esc(c.rationale)}</div>
      </div>
      <button class="starpin shrink-0 text-xl ${c.starred ? "" : "opacity-30"}" title="Seç">⭐</button>
    </div>

    <div class="relative bg-ink border border-line rounded-xl mb-3">
      <pre class="promptbox p-3 max-h-40 overflow-auto text-paper/90">${esc(c.prompt)}</pre>
      <div class="absolute top-2 right-2 flex gap-1">
        <button class="copyPrompt text-[11px] bg-card border border-line rounded-md px-2 py-1 hover:border-brand">📋 Prompt</button>
      </div>
    </div>

    <div class="flex gap-2 mb-3">
      <a href="${esc(state.brand.chatgpt_url)}" target="_blank" rel="noopener"
         class="flex-1 text-center text-xs bg-panel border border-line rounded-lg py-2 hover:border-brand">↗ ChatGPT-də aç</a>
      <button class="uploadBtn flex-1 text-xs bg-panel border border-line rounded-lg py-2 hover:border-brand">⬆ Şəkil yüklə</button>
      <input type="file" accept="image/*" class="fileInput hidden">
    </div>

    <div class="imgSlot ${img ? "" : "dropzone border-2 border-dashed border-line rounded-xl"} mb-3">
      ${img ? imageBlock(c) : `<div class="text-center text-muted text-xs py-8 pointer-events-none">
          Şəkli bura sürüklə və ya <b class="text-paper">Şəkil yüklə</b></div>`}
    </div>

    ${c.caption ? `<div class="bg-ink border border-line rounded-lg p-2.5 mb-3 relative">
        <div class="text-[10px] text-muted mb-1">CAPTION</div>
        <div class="text-sm whitespace-pre-line">${esc(c.caption)}</div>
        <button class="copyCaption absolute top-2 right-2 text-[11px] text-muted hover:text-paper">📋</button>
      </div>` : ""}

    <div class="critiqueSlot">${c.critique ? critiqueBlock(c.critique) : ""}</div>

    <div class="mt-auto pt-3 flex items-center justify-between border-t border-line">
      <div class="stars flex gap-1 text-lg">${stars(c.rating)}</div>
      ${img ? `<button class="critiqueBtn text-xs bg-brand/90 hover:bg-brand text-white rounded-lg px-3 py-1.5 font-semibold">
          ${c.critique ? "↻ Yenidən qiymətləndir" : "✦ Qiymətləndir"}</button>` : ""}
    </div>`;
  wireCard(el, c);
  return el;
}

function imageBlock(c) {
  const url = imgUrl(c);
  const s = c.score;
  return `<div class="relative group">
    <img src="${url}" class="w-full rounded-xl cursor-zoom-in object-cover" data-zoom="${url}">
    ${s != null ? `<span class="absolute top-2 left-2 text-xs font-bold px-2 py-1 rounded-lg"
        style="background:${scoreColor(s)};color:#fff">${s}</span>` : ""}
  </div>`;
}

function stars(rating) {
  return Array.from({ length: 5 }, (_, i) =>
    `<span class="star" data-v="${i + 1}">${i < (rating || 0) ? "★" : "☆"}</span>`).join("");
}

function critiqueBlock(cr) {
  const chip = (txt, cls) => `<span class="text-[11px] px-2 py-0.5 rounded ${cls}">${esc(txt)}</span>`;
  const ov = cr.overlay || {};
  const mark = (v) => v === true ? "✓" : v === false ? "✗" : "—";
  return `<div class="bg-ink border border-line rounded-xl p-3 mb-3 fade-in text-sm">
    <div class="flex items-center gap-2 mb-2">
      ${cr.score != null ? `<span class="font-extrabold text-lg" style="color:${scoreColor(cr.score)}">${cr.score}</span>` : ""}
      <span class="text-muted text-xs">${esc(cr.verdict)}</span>
      <span class="ml-auto text-[10px] ${cr.source === "gemini" ? "text-green-400" : "text-amber-400"}">${cr.source}</span>
    </div>
    ${cr.brand_fit ? `<p class="text-xs text-muted mb-2">${esc(cr.brand_fit)}</p>` : ""}
    ${cr.strengths?.length ? `<div class="mb-1.5"><span class="text-[10px] text-green-400 font-semibold">YAXŞI</span>
      <ul class="text-xs text-paper/90 list-disc ml-4 mt-0.5">${cr.strengths.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    ${cr.fixes?.length ? `<div class="mb-1.5"><span class="text-[10px] text-amber-400 font-semibold">DÜZƏLİŞ</span>
      <ul class="text-xs text-paper/90 list-disc ml-4 mt-0.5">${cr.fixes.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    ${cr.ai_tells?.length ? `<div class="mb-2"><span class="text-[10px] text-brand font-semibold">⚠ AI-TELLS</span>
      <ul class="text-xs text-brand/90 list-disc ml-4 mt-0.5">${cr.ai_tells.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    <div class="flex gap-2 mt-1 text-xs">
      ${chip("Başlıq sahəsi " + mark(ov.top_left_clear), "bg-panel border border-line")}
      ${chip("Footer sahəsi " + mark(ov.bottom_clear), "bg-panel border border-line")}
    </div>
  </div>`;
}

function wireCard(el, c) {
  $(".copyPrompt", el).onclick = () => copy(c.prompt, "Prompt kopyalandı");
  const cap = $(".copyCaption", el);
  if (cap) cap.onclick = () => copy(c.caption, "Caption kopyalandı");

  const file = $(".fileInput", el);
  $(".uploadBtn", el).onclick = () => file.click();
  file.onchange = () => file.files[0] && doUpload(c, file.files[0]);

  // drag & drop
  const slot = $(".imgSlot", el);
  if (slot.classList.contains("dropzone")) {
    ["dragover", "dragenter"].forEach(ev => slot.addEventListener(ev, e => {
      e.preventDefault(); slot.classList.add("drag"); }));
    ["dragleave", "drop"].forEach(ev => slot.addEventListener(ev, e => {
      e.preventDefault(); slot.classList.remove("drag"); }));
    slot.addEventListener("drop", e => {
      const f = e.dataTransfer.files[0];
      if (f) doUpload(c, f);
    });
  }
  const zoom = $("[data-zoom]", el);
  if (zoom) zoom.onclick = () => lightbox(zoom.dataset.zoom);

  const cb = $(".critiqueBtn", el);
  if (cb) cb.onclick = () => doCritique(c, cb);

  $(".starpin", el).onclick = async () => {
    const upd = await postJSON("/api/lab/rate", { concept_id: c.id, starred: !c.starred });
    Object.assign(c, upd); refreshConcept(c);
  };
  $$(".star", el).forEach(s => s.onclick = async () => {
    const upd = await postJSON("/api/lab/rate", { concept_id: c.id, rating: parseInt(s.dataset.v, 10) });
    Object.assign(c, upd); refreshConcept(c);
  });
}

async function doUpload(c, fileObj) {
  const fd = new FormData();
  fd.append("concept_id", c.id);
  fd.append("file", fileObj);
  try {
    const res = await api("/api/lab/upload", { method: "POST", body: fd });
    c.image_path = res.image_path; c.critique = null; c.score = null;
    refreshConcept(c);
    toast("Şəkil yükləndi");
  } catch (e) { toast("Yükləmə xətası: " + e.message, false); }
}

async function doCritique(c, btn) {
  btn.disabled = true; btn.textContent = "Qiymətləndirilir…";
  try {
    c.critique = await postJSON("/api/lab/critique", { concept_id: c.id });
    c.score = c.critique.score;
    refreshConcept(c);
  } catch (e) { toast("Xəta: " + e.message, false); }
  finally { btn.disabled = false; }
}

function refreshConcept(c) {
  if (state.view === "gallery") { renderGallery(); return; }
  const old = $(`#concept-${c.id}`);
  if (old) old.replaceWith(card(c));
}

// -------------------------------------------------------------------- Gallery view
function renderGallery() {
  const board = $("#board");
  board.className = "grid gap-4 grid-cols-2 lg:grid-cols-3";
  const withImg = state.current.concepts.filter(imgUrl);
  if (!withImg.length) {
    board.className = "";
    board.innerHTML = `<div class="text-center text-muted py-16 text-sm">
      Hələ şəkil yoxdur. Kartlar rejimində prompt-ları ChatGPT-də işlət, şəkilləri yüklə —
      sonra burada yan-yana müqayisə edə bilərsən.</div>`;
    return;
  }
  board.innerHTML = "";
  withImg.forEach(c => {
    const url = imgUrl(c);
    const el = document.createElement("div");
    el.className = "bg-card border border-line rounded-2xl overflow-hidden fade-in";
    el.innerHTML = `
      <div class="relative">
        <img src="${url}" class="w-full cursor-zoom-in object-cover" data-zoom="${url}">
        ${c.score != null ? `<span class="absolute top-2 left-2 text-sm font-bold px-2 py-1 rounded-lg"
            style="background:${scoreColor(c.score)};color:#fff">${c.score}</span>` : ""}
        ${c.starred ? `<span class="absolute top-2 right-2 text-xl">⭐</span>` : ""}
      </div>
      <div class="p-3">
        <div class="font-semibold text-sm">${esc(c.angle)}</div>
        <div class="stars flex gap-0.5 text-base mt-1">${stars(c.rating)}</div>
      </div>`;
    $("[data-zoom]", el).onclick = () => lightbox(url);
    $$(".star", el).forEach(s => s.onclick = async () => {
      const upd = await postJSON("/api/lab/rate", { concept_id: c.id, rating: parseInt(s.dataset.v, 10) });
      Object.assign(c, upd); renderGallery();
    });
    board.appendChild(el);
  });
}

// -------------------------------------------------------------------- Brand Brain
function renderBrand() {
  const b = state.brand;
  fillSelect($("#bStyle"), b.styles.map(s => [s.key, s.title]), b.state.active_style);
  fillSelect($("#bVoice"), b.voices.map(v => [v.key, v.title]), b.state.active_voice);
  fillSelect($("#bDialect"), b.dialects.map(d => [d, d]), b.state.active_dialect);
  fillSelect($("#bFormat"), b.formats.map(f => [f, f]), b.state.default_format);
  $("#houseRules").value = b.state.house_rules || "";
  $("#extraExcl").value = b.state.extra_exclusions || "";
  $("#aiTells").textContent = b.ai_tells || "(tapılmadı)";
  $("#brandId").textContent = b.brand_identity || "(tapılmadı)";
  updateDesc();

  $("#bStyle").onchange = () => saveState({ active_style: $("#bStyle").value });
  $("#bVoice").onchange = () => saveState({ active_voice: $("#bVoice").value });
  $("#bDialect").onchange = () => saveState({ active_dialect: $("#bDialect").value });
  $("#bFormat").onchange = () => saveState({ default_format: $("#bFormat").value });
  $("#saveRules").onclick = () => saveState({
    house_rules: $("#houseRules").value, extra_exclusions: $("#extraExcl").value }, true);
}

function updateDesc() {
  const b = state.brand;
  const st = b.styles.find(s => s.key === $("#bStyle").value);
  const vo = b.voices.find(v => v.key === $("#bVoice").value);
  $("#bStyleDesc").textContent = st?.summary || "";
  $("#bVoiceDesc").textContent = vo?.summary || "";
}

async function saveState(patch, flash = false) {
  try {
    const st = await postJSON("/api/brand/state", patch);
    state.brand.state = st;
    // keep the Lab controls in sync with Brand Brain edits
    $("#selStyle").value = st.active_style;
    $("#selDialect").value = st.active_dialect;
    $("#selFormat").value = st.default_format;
    updateDesc();
    if (flash) {
      const f = $("#rulesSaved"); f.style.opacity = "1";
      setTimeout(() => (f.style.opacity = "0"), 1500);
    } else toast("Yadda saxlanıldı");
  } catch (e) { toast("Saxlanmadı: " + e.message, false); }
}

// -------------------------------------------------------------------- History
$("#historyBtn").onclick = () => toggleHistory(true);
$("#historyClose").onclick = () => toggleHistory(false);
$("#historyBackdrop").onclick = () => toggleHistory(false);
function toggleHistory(open) {
  $("#historyPanel").style.transform = open ? "translateX(0)" : "translateX(100%)";
  $("#historyBackdrop").classList.toggle("hidden", !open);
}

async function loadHistory() {
  let items = [];
  try { items = await api("/api/history"); } catch (e) { return; }
  $("#historyList").innerHTML = items.length ? items.map(it => `
    <button class="histItem w-full text-left bg-card border border-line rounded-xl p-3 hover:border-brand" data-id="${it.id}">
      <div class="text-sm font-semibold line-clamp-2">${esc(it.brief)}</div>
      <div class="text-[11px] text-muted mt-1 flex gap-2">
        <span>${esc(it.style || "")}</span>
        <span>· ${it.n_images}/${it.n} şəkil</span>
        ${it.top_score != null ? `<span style="color:${scoreColor(it.top_score)}">· ${it.top_score}</span>` : ""}
      </div>
    </button>`).join("") : `<div class="text-muted text-sm text-center py-8">Hələ brief yoxdur.</div>`;
  $$(".histItem").forEach(b => b.onclick = () => openBrief(parseInt(b.dataset.id, 10)));
}

async function openBrief(id) {
  try {
    const data = await api(`/api/brief/${id}`);
    data.source = data.source || null;
    state.current = data;
    $$(".tabbtn").forEach(b => b.dataset.active = (b.dataset.tab === "lab").toString());
    $("#tab-lab").classList.remove("hidden"); $("#tab-brand").classList.add("hidden");
    $("#emptyLab").classList.add("hidden");
    $("#boardBar").classList.remove("hidden"); $("#boardBar").classList.add("flex");
    $("#briefEcho").textContent = data.brief;
    renderBoard();
    toggleHistory(false);
  } catch (e) { toast("Açılmadı: " + e.message, false); }
}

document.addEventListener("keydown", e => {
  if (e.key === "Escape") { $("#lightbox").classList.add("hidden"); toggleHistory(false); }
});

boot();
