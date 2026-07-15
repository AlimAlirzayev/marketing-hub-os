/* Ads Studio dashboard — all client logic.
 * Sparklines on every KPI card, lazy-loaded segments + creative tabs,
 * multi-account support, AI assistant, print-to-PDF. */

const COLORS = { blue:'#2563EB', green:'#16A34A', amber:'#F59E0B', red:'#E31E24', ink:'#2B2A29', gray:'#94A3B8', purple:'#7C3AED', pink:'#DB2777', teal:'#0D9488' };
const STATUS = { good:'#16A34A', warn:'#F59E0B', over:'#E31E24', ok:'#16A34A', info:'#2563EB', high:'#E31E24' };
const AZ_SHORT = ['','yan','fev','mar','apr','may','iyn','iyl','avq','sen','okt','noy','dek'];
const RANK_LABEL = { ABOVE_AVERAGE:'Yuxarı orta', AVERAGE:'Orta',
  BELOW_AVERAGE_35:'Aşağı 35%', BELOW_AVERAGE_20:'Aşağı 20%', BELOW_AVERAGE_10:'Aşağı 10%' };
const RANK_COLOR = { ABOVE_AVERAGE:COLORS.green, AVERAGE:COLORS.amber,
  BELOW_AVERAGE_35:'#F87171', BELOW_AVERAGE_20:'#EF4444', BELOW_AVERAGE_10:'#B91C1C' };
const PLAT_LABEL = { instagram:'Instagram', facebook:'Facebook', messenger:'Messenger', audience_network:'Audience Network', unknown:'Naməlum' };
const DEVICE_LABEL = { android_smartphone:'Android telefon', iphone:'iPhone', desktop:'Desktop', ipad:'iPad', android_tablet:'Android tablet' };

const state = { meta:null, month:null, platform:'all', account:null, compare:'prev_month',
                sym:'$', charts:{}, loaded:{report:false, segments:false, creative:false, social:false} };

const $  = (s)=>document.querySelector(s);
const $$ = (s)=>document.querySelectorAll(s);
const nf = (n)=> new Intl.NumberFormat('az-AZ').format(Math.round(n||0));
const money = (n)=> state.sym + new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).format(n||0);
const azDate = (iso)=>{ const [y,m,d]=iso.split('-'); return `${+d} ${AZ_SHORT[+m]} ${y}`; };
const mdLite = (t)=> (t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');

// ---------- init ----------
async function init(){
  state.meta = await (await fetch('/api/meta')).json();
  state.sym  = state.meta.currency_symbol;
  $('#hdr-tagline').textContent = state.meta.tagline;
  $('#foot-src').textContent = state.meta.data_mode;
  const badge = $('#mode-badge');
  badge.textContent = state.meta.data_mode === 'live' ? 'CANLI' : 'DEMO';
  badge.style.background = state.meta.data_mode==='live' ? 'rgba(22,163,74,.25)' : 'rgba(255,255,255,.1)';

  // Live-health badge: surface "token expired" instead of silent demo fallback
  if (state.meta.live && state.meta.live.ok === false) {
    badge.textContent = state.meta.live.code === 'token_expired' ? 'TOKEN BİTİB' : 'CANLI XƏTASI';
    badge.style.background = 'rgba(227,30,36,.35)'; badge.style.color = '#fff';
    badge.title = state.meta.live.hint || '';
    // Top banner
    const b = document.createElement('div');
    b.className = 'no-print bg-red-600 text-white text-sm px-4 py-2 flex items-center gap-2';
    b.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg><span><strong>${badge.textContent}.</strong> ${state.meta.live.hint||''}</span>`;
    document.body.insertBefore(b, document.body.firstChild);
  }

  // Accounts
  state.account = state.meta.default_account;
  $('#hdr-account').textContent = state.meta.accounts[0]?.label || state.meta.account;
  if (state.meta.accounts.length > 1) {
    const sel = $('#account-select');
    sel.innerHTML = state.meta.accounts.map(a=>`<option value="${a.id}">${a.label}</option>`).join('');
    sel.value = state.account;
    sel.classList.remove('hidden');
    sel.addEventListener('change', e=>{ state.account=e.target.value; resetAll(); load(); });
  }

  // Months
  const ms = $('#month-select');
  ms.innerHTML = state.meta.months.map(m=>`<option value="${m.value}">${m.label}</option>`).join('');
  state.month = state.meta.months[0].value;
  ms.value = state.month;

  $('#asst-suggest').innerHTML = state.meta.suggested_questions.map(q=>
    `<button class="sugg text-[12px] bg-white border border-surface-line rounded-full px-3 py-1 hover:border-brand-red hover:text-brand-red transition">${q}</button>`).join('');

  bind();
  setTab('report'); setPlatform('all'); setCompare('prev_month');
  load();
}

function setCompare(m){
  state.compare = m;
  $$('.cmp').forEach(b=>{
    const on = b.dataset.cmp===m;
    b.style.background = on ? '#ffffff' : '';
    b.style.color = on ? '#1C1B17' : '';
    b.classList.toggle('text-white/55', !on);
  });
}

function resetAll(){ state.loaded = {report:false, segments:false, creative:false, social:false}; }

function bind(){
  $('#month-select').addEventListener('change', e=>{ state.month=e.target.value; resetAll(); load(); });
  $$('.tab').forEach(b=> b.addEventListener('click', ()=> setTab(b.dataset.tab)));
  $$('.plat').forEach(b=> b.addEventListener('click', ()=>{ setPlatform(b.dataset.plat); state.loaded.report=false; load(); }));
  $$('.cmp').forEach(b=> b.addEventListener('click', ()=>{ setCompare(b.dataset.cmp); state.loaded.report=false; load(); }));
  $('#asst-fab').addEventListener('click', ()=> toggleAsst(true));
  $('#asst-close').addEventListener('click', ()=> toggleAsst(false));
  $('#asst-form').addEventListener('submit', onAsk);
  $('#asst-suggest').addEventListener('click', e=>{ if(e.target.classList.contains('sugg')){ $('#asst-input').value=e.target.textContent; onAsk(new Event('x')); }});
}

function setTab(name){
  $$('.tab').forEach(b=>{
    const on = b.dataset.tab===name;
    b.classList.toggle('bg-white', on); b.classList.toggle('text-brand-ink', on);
    b.classList.toggle('text-white/60', !on);
  });
  $$('.tabpanel').forEach(p=> p.classList.add('hidden'));
  $('#tab-'+name).classList.remove('hidden');
  if (name==='segments' && !state.loaded.segments) loadSegments();
  if (name==='creative' && !state.loaded.creative) loadCreative();
  if (name==='social' && !state.loaded.social) loadSocial();
}
function setPlatform(p){
  state.platform=p;
  $$('.plat').forEach(b=>{
    const on=b.dataset.plat===p;
    b.style.background = on ? '#2B2A29' : ''; b.classList.toggle('text-white', on); b.classList.toggle('text-gray-500', !on);
  });
}

const qs = ()=>`month=${state.month}&platform=${state.platform}&account=${encodeURIComponent(state.account||'')}&compare=${state.compare}`;

// ---------- HESABAT tab ----------
async function load(){
  const { report, analytics } = await (await fetch(`/api/report?${qs()}`)).json();
  state.last = { report, analytics };

  const p = report.period;
  $('#hdr-account').textContent = report.account.name || state.meta.accounts[0]?.label;
  $('#period-title').textContent = p.label;
  $('#period-sub').textContent = `${p.start} — ${p.end}` + (p.is_current ? ` · ${p.days_elapsed}/${p.days_total} gün` : '');
  $('#pay-period').textContent = p.label; $('#sales-period').textContent = p.label;
  $('#print-period').textContent = `${report.account.name} · ${p.label}`;

  renderInsight(analytics.insight, analytics.comparison);
  renderKpis(report.totals, analytics.deltas, report.daily);
  renderPacing(analytics.pacing);
  renderAnomalies(analytics.anomalies);
  renderTrend(report.daily);
  renderCost(report.totals);
  renderFunnel(analytics.funnel);
  renderPayments(report);
  renderSales(report);
  loadSummary();
  state.loaded.report = true;
}

async function loadSummary(){
  const body=$('#summary-body');
  body.innerHTML = `<div class="skeleton h-4 rounded w-full mb-2"></div><div class="skeleton h-4 rounded w-11/12 mb-2"></div><div class="skeleton h-4 rounded w-3/4"></div>`;
  $('#summary-src').textContent='';
  try{
    const r = await (await fetch(`/api/summary?${qs()}`)).json();
    const s = r.summary || r; // backward compat
    body.innerHTML = `<div class="fade-in whitespace-pre-line">${mdLite(s.text)}</div>`;
    $('#summary-src').textContent = s.source==='gemini' ? 'Gemini ilə' : 'avtomatik';
    // Upgrade the insight hero from rule-based to AI version, if available
    if (r.insight && r.insight.source === 'gemini'){
      renderInsight(r.insight, state.last?.analytics?.comparison);
    }
  }catch(e){ body.innerHTML = '<span class="text-gray-400">Xülasə yüklənmədi.</span>'; }
}

function deltaBadge(d){
  if(!d || d.change===null || d.change===undefined) return '';
  const col = d.good ? COLORS.green : COLORS.red;
  return `<span class="num text-[11px] font-semibold" style="color:${col}">${d.change>=0?'▲':'▼'} ${Math.abs(d.change)}%</span>`;
}

const KPI_BG = (bg,fg,svg)=>`<span class="inline-flex w-9 h-9 items-center justify-center rounded-xl" style="background:${bg};color:${fg}">${svg}</span>`;
const I = {
  money:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>',
  lead:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4z"/></svg>',
  msg:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 11.5a8.38 8.38 0 01-9 8.5 8.5 8.5 0 01-3.8-.9L3 21l1.9-5.2A8.38 8.38 0 0121 11.5z"/></svg>',
  reach:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>',
  click:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 3v4M3 9h4M5 5l2 2m6-4l8 8-4 1 3 5-3 2-3-5-3 3V3z"/></svg>',
  cpm:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 3v18h18M7 14l3-3 3 3 5-6"/></svg>',
  freq:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0114.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0020.5 15"/></svg>',
  impr:'<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2 12s3-6 10-6 10 6 10 6-3 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/></svg>',
};

function kpiCard(slot,icon,bg,fg,label,value,sub,delta){
  return `<div class="card p-4 fade-in">
    <div class="flex items-center justify-between mb-2">${KPI_BG(bg,fg,icon)}${deltaBadge(delta)}</div>
    <div class="text-[11px] text-gray-500 uppercase tracking-wide">${label}</div>
    <div class="num font-extrabold text-2xl leading-tight">${value}</div>
    <div class="flex items-end justify-between mt-1">
      <div class="text-[12px] text-gray-400">${sub||'&nbsp;'}</div>
      <canvas id="spark-${slot}" width="80" height="28" style="width:80px;height:28px"></canvas>
    </div>
  </div>`;
}
function renderKpis(t,d,daily){
  const cards = [
    ['spend', I.money,'#FEE2E2',COLORS.red,'Ümumi Xərc',money(t.spend),'Meta Ads',d.spend],
    ['leads', I.lead,'#DCFCE7',COLORS.green,'Lead',nf(t.leads),`${money(t.cpl)} / lead`,d.leads],
    ['messages', I.msg,'#EDE9FE',COLORS.purple,'Mesaj',nf(t.messages),'söhbət',d.messages],
    ['reach', I.reach,'#FFEDD5','#EA580C','Əhatə',nf(t.reach),'unikal',d.reach],
    ['clicks', I.click,'#DBEAFE',COLORS.blue,'Klik',nf(t.clicks),`${t.ctr}% CTR`,d.clicks],
    ['cpm', I.cpm,'#E0E7FF','#4F46E5','CPM',money(t.cpm),'1000 göstərilmə',d.cpm],
    ['frequency', I.freq,'#FCE7F3',COLORS.pink,'Tezlik',t.frequency+'x','orta',d.frequency],
    ['impressions', I.impr,'#CCFBF1',COLORS.teal,'Göstərilmə',nf(t.impressions),'cəmi',d.impressions],
  ];
  $('#kpis').innerHTML = cards.map(c=>kpiCard(...c)).join('');
  // Sparklines from daily series
  setTimeout(()=>cards.forEach(c=>spark(c[0], daily, c[3])), 0);
}

function spark(metric, daily, color){
  const el = document.getElementById('spark-'+metric);
  if(!el || !daily?.length) return;
  if(state.charts['s-'+metric]) state.charts['s-'+metric].destroy();
  state.charts['s-'+metric] = new Chart(el,{ type:'line',
    data:{ labels: daily.map((_,i)=>i),
      datasets:[{ data: daily.map(d=>d[metric]||0), borderColor:color,
        backgroundColor:color+'18', fill:true, tension:.4, pointRadius:0, borderWidth:1.5 }]},
    options:{ responsive:false, maintainAspectRatio:false, animation:false,
      plugins:{legend:{display:false}, tooltip:{enabled:false}},
      scales:{x:{display:false}, y:{display:false}}}
  });
}

function bar(label,used,statusColor,rightTxt){
  const w=Math.min(used,100);
  return `<div>
    <div class="flex justify-between text-[13px] mb-1"><span class="text-gray-600">${label}</span><span class="num font-semibold">${rightTxt}</span></div>
    <div class="h-2.5 rounded-full bg-gray-100 overflow-hidden"><div class="h-full rounded-full" style="width:${w}%;background:${statusColor}"></div></div>
  </div>`;
}
function renderPacing(p){
  const title = p.is_current ? 'Büdcə Pacing & Ay Sonu Proqnozu' : 'Yekun Nəticə vs Hədəf';
  const paceTag = p.is_current ? `<span class="num text-[12px] text-gray-500">${p.days_elapsed}/${p.days_total} gün · ${p.pace_pct}%</span>` : '';
  const cpl = `<div class="flex items-center gap-2 text-[13px]"><span class="text-gray-500">Proqnoz CPL</span><span class="num font-semibold">${money(p.projected_cpl)}</span><span class="text-gray-400">/ limit ${money(p.max_cpl)}</span><span class="ml-auto px-2 py-0.5 rounded-full text-[11px] font-semibold" style="background:${STATUS[p.cpl_status]}22;color:${STATUS[p.cpl_status]}">${p.cpl_status==='good'?'qənaətli':p.cpl_status==='warn'?'sərhəddə':'yüksək'}</span></div>`;
  $('#pacing').innerHTML = `
    <div class="flex items-center mb-4"><h3 class="font-tight font-bold text-lg">${title}</h3><span class="ml-auto">${paceTag}</span></div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-5">
      <div class="space-y-2">
        ${bar('Büdcə istifadəsi', p.budget_used_pct, STATUS[p.budget_status], money(p.spend_so_far)+' / '+money(p.budget))}
        <div class="text-[13px] text-gray-500">Proqnoz xərc: <span class="num font-semibold text-brand-ink">${money(p.projected_spend)}</span></div>
      </div>
      <div class="space-y-2">
        ${bar('Lead hədəfi', p.lead_attainment_pct, STATUS[p.leads_status], nf(p.leads_so_far)+' / '+nf(p.target_leads))}
        <div class="text-[13px] text-gray-500">Proqnoz lead: <span class="num font-semibold text-brand-ink">${nf(p.projected_leads)}</span> (${p.lead_attainment_pct}%)</div>
      </div>
    </div>
    <div class="mt-4 pt-3 border-t border-gray-100">${cpl}</div>`;
}

const ANOM_ICON = { high:'⚠', warn:'⚠', info:'ℹ', ok:'✓' };
function renderAnomalies(list){
  $('#anomalies').innerHTML = list.map(a=>{
    const c = STATUS[a.severity]||COLORS.gray;
    return `<div class="card p-3.5 flex gap-3 fade-in" style="border-left:3px solid ${c}">
      <span class="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[14px]" style="background:${c}1a;color:${c}">${ANOM_ICON[a.severity]||'•'}</span>
      <div><div class="font-semibold text-[14px] leading-tight">${a.title}</div><div class="text-[12.5px] text-gray-500 mt-0.5">${a.detail}</div></div>
    </div>`;
  }).join('');
}

function renderFunnel(f){
  $('#funnel').innerHTML = f.map((s,i)=>`
    <div>
      <div class="flex justify-between text-[13px] mb-1"><span class="font-medium">${s.stage}</span>
        <span class="num text-gray-500">${nf(s.value)}${i? ` · <span style="color:${COLORS.blue}">${s.step_rate}%</span>`:''}</span></div>
      <div class="h-7 rounded-lg bg-gray-100 overflow-hidden">
        <div class="h-full rounded-lg flex items-center" style="width:${Math.max(s.width_pct,4)}%;background:linear-gradient(90deg,${COLORS.blue},#60A5FA)"></div>
      </div>
    </div>`).join('');
}

function mkChart(id,cfg){ if(state.charts[id]) state.charts[id].destroy(); state.charts[id]=new Chart($('#'+id),cfg); }
const noLegend = { plugins:{legend:{display:false}}, maintainAspectRatio:false, responsive:true };

function renderTrend(daily){
  const labels = daily.map(d=>+d.date.split('-')[2]);
  mkChart('ch-trend',{ type:'line',
    data:{ labels, datasets:[
      { label:'Xərc', data:daily.map(d=>d.spend), borderColor:COLORS.red, backgroundColor:'rgba(227,30,36,.08)', fill:true, tension:.35, yAxisID:'y', pointRadius:0, borderWidth:2 },
      { label:'Lead', data:daily.map(d=>d.leads), borderColor:COLORS.blue, fill:false, tension:.35, yAxisID:'y1', pointRadius:0, borderWidth:2 },
    ]},
    options:{ maintainAspectRatio:false, responsive:true, interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true,position:'top',align:'end',labels:{boxWidth:10,usePointStyle:true}}},
      scales:{ y:{position:'left',grid:{color:'#f1f3f5'},ticks:{callback:v=>state.sym+v}}, y1:{position:'right',grid:{display:false}} } }});
}
function renderCost(t){
  mkChart('ch-cost',{ type:'bar',
    data:{ labels:['Lead başına','Mesaj başına','Klik başına','CPM'], datasets:[{ data:[t.cpl,t.cost_per_message,t.cpc,t.cpm], backgroundColor:[COLORS.blue,COLORS.green,COLORS.amber,COLORS.red], borderRadius:8 }]},
    options:{ ...noLegend, indexAxis:'y', scales:{ x:{grid:{color:'#f1f3f5'},ticks:{callback:v=>state.sym+v}}, y:{grid:{display:false}} } }});
}

// ---------- INSIGHT hero (top of Hesabat) ----------
const METRIC_AZ = { spend:'Xərc', leads:'Lead', messages:'Mesaj', clicks:'Klik', impressions:'Göstərilmə', reach:'Əhatə', ctr:'CTR', cpm:'CPM', cpl:'CPL', cpc:'Klik başına', cost_per_message:'Mesaj başına', frequency:'Tezlik' };
function fmtMoverVal(metric, v){
  if (['spend','cpl','cpm','cpc','cost_per_message'].includes(metric)) return money(v);
  if (metric==='ctr') return Number(v).toFixed(2)+'%';
  if (metric==='frequency') return Number(v).toFixed(2)+'x';
  return nf(v);
}
function renderInsight(ins, cmp){
  $('#insight-headline').textContent = ins?.headline || '—';
  $('#insight-body').textContent = ins?.body || '';
  $('#insight-cmp').textContent = cmp?.baseline_period ? `Müqayisə: ${cmp.label} (${cmp.baseline_period})` : '';
  const m = ins?.movers || {winners:[], losers:[]};
  const pill = (label, change, color)=> `<span class="num text-[11px] font-semibold px-2 py-1 rounded-full" style="background:${color}22;color:${color}">${label} ${change>0?'↑':'↓'}${Math.abs(change)}%</span>`;
  const win = m.winners.map(([k,d])=> pill(METRIC_AZ[k]||k, d.change, '#22C55E')).join('');
  const lose = m.losers.map(([k,d])=> pill(METRIC_AZ[k]||k, d.change, '#F87171')).join('');
  $('#insight-movers').innerHTML = win + lose;
}

// ---------- SEGMENTLƏR tab ----------
async function loadSegments(){
  const account = state.account;
  try{
    const d = await (await fetch(`/api/segments?month=${state.month}&account=${encodeURIComponent(account)}`)).json();
    renderSegments(d);
    state.loaded.segments = true;
  }catch(e){ console.error(e); }
}

function calloutCard(label, valueLabel, valueNum, color){
  return `<div class="card p-4 fade-in">
    <div class="text-[11px] text-gray-500 uppercase tracking-wide">${label}</div>
    <div class="num font-extrabold text-xl mt-1" style="color:${color}">${valueLabel||'—'}</div>
    <div class="text-[12px] text-gray-400 mt-0.5">${valueNum||''}</div>
  </div>`;
}
function renderSegments(d){
  const c = d.callouts || {};
  const dow = (d.day_of_week||[]).reduce((a,b)=> b.leads>(a?.leads||-1)?b:a, null);
  $('#seg-callouts').innerHTML = [
    calloutCard('Ən yaxşı saat', c.best_hour?.best ? `${String(c.best_hour.best.label).padStart(2,'0')}:00` : '—', c.best_hour?.best ? c.best_hour.best.value+' lead' : '', COLORS.blue),
    calloutCard('Ən yaxşı yaş qrupu', c.best_age?.best?.label || '—', c.best_age?.best ? c.best_age.best.value+' lead' : '', COLORS.green),
    calloutCard('Ən yaxşı region', c.best_region?.best?.label || '—', c.best_region?.best ? c.best_region.best.value+' lead' : '', COLORS.amber),
    calloutCard('Ən yaxşı gün', dow?.label || '—', dow ? dow.leads+' lead, CPL '+money(dow.cpl) : '', COLORS.purple),
  ].join('');

  // Publisher platform (bars with metrics)
  renderSegmentBars('seg-publisher', d.segments.publisher_platform, PLAT_LABEL);
  renderSegmentBars('seg-device',    d.segments.impression_device,  DEVICE_LABEL);
  renderSegmentBars('seg-placement', d.segments.placement,          null);
  renderRegions(d.segments.region);

  // Age chart
  const age = (d.segments.age||[]).filter(r=>r.key && r.leads !== undefined)
    .sort((a,b)=> (a.key||'').localeCompare(b.key||''));
  mkChart('ch-age',{ type:'bar',
    data:{ labels: age.map(r=>r.key), datasets:[
      { label:'Lead', data:age.map(r=>r.leads), backgroundColor:COLORS.blue, borderRadius:6, yAxisID:'y' },
      { label:'CPL', data:age.map(r=>r.cpl), type:'line', borderColor:COLORS.red, backgroundColor:COLORS.red, yAxisID:'y1', pointRadius:3, borderWidth:2, tension:.3 },
    ]},
    options:{ maintainAspectRatio:false, responsive:true,
      plugins:{legend:{display:true,position:'top',align:'end',labels:{boxWidth:10,usePointStyle:true}}},
      scales:{ y:{position:'left',grid:{color:'#f1f3f5'}}, y1:{position:'right',grid:{display:false},ticks:{callback:v=>state.sym+v}} } }});

  // Gender doughnut
  const gen = (d.segments.gender||[]).filter(r=>r.key);
  mkChart('ch-gender',{ type:'doughnut',
    data:{ labels:gen.map(r=>r.key==='female'?'Qadın':r.key==='male'?'Kişi':'Naməlum'),
      datasets:[{ data:gen.map(r=>r.leads), backgroundColor:[COLORS.pink, COLORS.blue, COLORS.gray] }]},
    options:{ maintainAspectRatio:false, responsive:true, cutout:'62%',
      plugins:{legend:{position:'bottom',labels:{boxWidth:10,usePointStyle:true}}}}});

  // Hourly chart
  const hr = Array.isArray(d.segments.hourly) ? d.segments.hourly : [];
  mkChart('ch-hourly',{ type:'bar',
    data:{ labels: hr.map(h=>String(h.hour).padStart(2,'0')),
      datasets:[{ label:'Lead', data:hr.map(h=>h.leads), backgroundColor:COLORS.blue, borderRadius:4 }]},
    options:{ ...noLegend, scales:{x:{grid:{display:false}}, y:{grid:{color:'#f1f3f5'},beginAtZero:true}}}});
  const bestH = hr.length ? hr.reduce((a,b)=> b.leads>a.leads?b:a) : null;
  $('#hour-note').textContent = bestH ? `Ən yaxşı saat: ${String(bestH.hour).padStart(2,'0')}:00 — ${bestH.leads} lead, ${money(bestH.spend)} xərc.` : '';

  // Day-of-week
  const dws = d.day_of_week || [];
  mkChart('ch-dow',{ type:'bar',
    data:{ labels:dws.map(b=>b.label),
      datasets:[
        { label:'Lead', data:dws.map(b=>b.leads), backgroundColor:COLORS.green, borderRadius:6, yAxisID:'y' },
        { label:'CPL', data:dws.map(b=>b.cpl), type:'line', borderColor:COLORS.red, yAxisID:'y1', pointRadius:3, borderWidth:2, tension:.3 },
      ]},
    options:{ maintainAspectRatio:false, responsive:true,
      plugins:{legend:{display:true,position:'top',align:'end',labels:{boxWidth:10,usePointStyle:true}}},
      scales:{y:{position:'left',grid:{color:'#f1f3f5'}}, y1:{position:'right',grid:{display:false},ticks:{callback:v=>state.sym+v}}}}});
  const bestDW = dws.length ? dws.reduce((a,b)=> b.leads>a.leads?b:a) : null;
  const cheapDW = dws.filter(b=>b.leads>0).reduce((a,b)=> (!a||b.cpl<a.cpl)?b:a, null);
  $('#dow-note').textContent = bestDW ? `Ən çox lead: ${bestDW.label} (${bestDW.leads}). Ən ucuz CPL: ${cheapDW?.label} (${money(cheapDW?.cpl||0)}).` : '';

  // Age × Gender heatmap
  renderAgeGenderHeatmap(d.segments.age_gender);

  // Saturation curve — needs the report's daily series; fetch + reuse cached if any
  if (state.last?.analytics?.saturation) renderSaturation(state.last.analytics.saturation);
}

function renderAgeGenderHeatmap(rows){
  const el = $('#seg-ag-heatmap');
  if (!Array.isArray(rows) || !rows.length){ el.innerHTML = '<p class="text-[13px] text-gray-400">Data yoxdur.</p>'; return; }
  const ages = ['18-24','25-34','35-44','45-54','55-64','65+'];
  const genders = ['female','male','unknown'];
  const genderLabel = { female:'Qadın', male:'Kişi', unknown:'Naməlum' };
  const matrix = {}; let maxLeads = 0; let maxSpend = 0;
  rows.forEach(r=>{ matrix[`${r.age}|${r.gender}`]=r; if(r.leads>maxLeads) maxLeads=r.leads; if((r.spend||0)>maxSpend) maxSpend=r.spend; });
  if(!maxLeads) maxLeads = 1;
  const cols = `120px repeat(${genders.length}, minmax(0, 1fr))`;
  let html = `<div style="display:grid;grid-template-columns:${cols};gap:6px;min-width:480px">`;
  html += `<div></div>`;
  genders.forEach(g => html += `<div class="text-[11px] text-gray-500 px-2 pb-1 text-center font-medium">${genderLabel[g]}</div>`);
  ages.forEach(a => {
    html += `<div class="text-[12px] text-gray-600 font-medium self-center">${a}</div>`;
    genders.forEach(g => {
      const cell = matrix[`${a}|${g}`];
      const leads = cell?.leads || 0;
      const op = Math.max(0.08, leads/maxLeads);
      const textColor = op > 0.55 ? '#fff' : '#1C1B17';
      const cpl = cell?.leads ? money(cell.cpl) : '—';
      html += `<div style="background:rgba(37,99,235,${op});color:${textColor};padding:10px 8px;border-radius:8px;text-align:center;line-height:1.2"
        title="${a} · ${genderLabel[g]}: ${leads} lead, ${cell?money(cell.spend||0):'—'} xərc, CPL ${cpl}">
        <div class="num font-bold text-base">${leads}</div>
        <div class="text-[10px] opacity-80 mt-0.5">${cell?money(cell.spend||0):'—'}</div>
      </div>`;
    });
  });
  html += '</div>';
  el.innerHTML = html;
}

function renderSaturation(sat){
  const el = $('#sat-status'); el.textContent = sat.verdict ? (sat.status==='good'?'sağlam':sat.status==='warn'?'izlə':'doyub') : '—';
  const c = STATUS[sat.status] || COLORS.gray;
  el.style.background = c+'22'; el.style.color = c;
  $('#sat-verdict').textContent = sat.verdict || '';
  $('#sat-stats').textContent = `Orta gündəlik reach: ${nf(sat.avg_reach)} · Orta tezlik: ${sat.avg_frequency}x · Reach trendi ${sat.reach_trend_pct>=0?'+':''}${sat.reach_trend_pct}%/gün · Tezlik trendi ${sat.freq_trend_pct>=0?'+':''}${sat.freq_trend_pct}%/gün`;
  const pts = sat.points || [];
  mkChart('ch-saturation',{ type:'bar',
    data:{ labels:pts.map(p=>+p.date.split('-')[2]), datasets:[
      { type:'bar', label:'Gündəlik reach', data:pts.map(p=>p.reach), backgroundColor:COLORS.blue+'80', borderRadius:4, yAxisID:'y', order:2 },
      { type:'line', label:'Tezlik', data:pts.map(p=>p.frequency), borderColor:COLORS.red, backgroundColor:COLORS.red, yAxisID:'y1', pointRadius:0, borderWidth:2, tension:.3, order:1 },
    ]},
    options:{ maintainAspectRatio:false, responsive:true,
      plugins:{legend:{display:true,position:'top',align:'end',labels:{boxWidth:10,usePointStyle:true}}},
      scales:{ y:{position:'left',grid:{color:'#f1f3f5'},beginAtZero:true}, y1:{position:'right',grid:{display:false}} } }});
}

function renderSegmentBars(elId, rows, labelMap){
  if (!Array.isArray(rows) || !rows.length){ $('#'+elId).innerHTML = '<p class="text-[13px] text-gray-400">Data yoxdur.</p>'; return; }
  const sorted = [...rows].sort((a,b)=> (b.leads||0)-(a.leads||0));
  const maxLeads = Math.max(...sorted.map(r=>r.leads||0), 1);
  $('#'+elId).innerHTML = sorted.map(r=>{
    const w = Math.max(2, Math.round(((r.leads||0)/maxLeads)*100));
    const cpl = r.leads ? money(r.cpl) : '—';
    const lbl = (labelMap?.[r.key]) || r.key || '—';
    return `<div>
      <div class="flex items-center justify-between text-[13px] mb-1">
        <span class="font-medium">${lbl}</span>
        <span class="num text-gray-500">${nf(r.leads||0)} lead · ${money(r.spend||0)} · CPL ${cpl}</span>
      </div>
      <div class="h-2.5 rounded-full bg-gray-100 overflow-hidden"><div class="h-full rounded-full" style="width:${w}%;background:linear-gradient(90deg,${COLORS.blue},#60A5FA)"></div></div>
    </div>`;
  }).join('');
}

function renderRegions(rows){
  if (!Array.isArray(rows) || !rows.length){ $('#seg-region').innerHTML = '<p class="text-[13px] text-gray-400">Data yoxdur.</p>'; return; }
  const top = [...rows].filter(r=> (r.leads||0)>0 || (r.spend||0)>0)
    .sort((a,b)=>(b.spend||0)-(a.spend||0)).slice(0,10);
  if (!top.length){ $('#seg-region').innerHTML = '<p class="text-[13px] text-gray-400">Lead/xərc qeyd olunmuş region yoxdur.</p>'; return; }
  const maxSpend = Math.max(...top.map(r=>r.spend||0),1);
  $('#seg-region').innerHTML = top.map(r=>{
    const w = Math.max(2, Math.round(((r.spend||0)/maxSpend)*100));
    return `<div>
      <div class="flex items-center justify-between text-[13px] mb-1">
        <span class="font-medium">${r.key||'—'}</span>
        <span class="num text-gray-500">${money(r.spend||0)} · ${nf(r.leads||0)} lead · CPL ${r.leads?money(r.cpl):'—'}</span>
      </div>
      <div class="h-2 rounded-full bg-gray-100 overflow-hidden"><div class="h-full rounded-full" style="width:${w}%;background:${COLORS.amber}"></div></div>
    </div>`;
  }).join('');
}

// ---------- KREATİV tab ----------
async function loadCreative(){
  const account = state.account;
  try {
    const [diag, vid, camp] = await Promise.all([
      fetch(`/api/diagnostics?month=${state.month}&account=${encodeURIComponent(account)}`).then(r=>r.json()),
      fetch(`/api/video?month=${state.month}&account=${encodeURIComponent(account)}`).then(r=>r.json()),
      fetch(`/api/campaigns?month=${state.month}&account=${encodeURIComponent(account)}&limit=10`).then(r=>r.json()),
    ]);
    if (state.last?.analytics?.fatigue) renderFatigue(state.last.analytics.fatigue);
    renderHealth(diag.health);
    renderDiagRows(diag.ads);
    renderVideo(vid);
    renderCampaigns(camp);
    state.loaded.creative = true;
  } catch(e){ console.error(e); }
}

function renderFatigue(f){
  const el = $('#fatigue-status'); const c = STATUS[f.status] || COLORS.gray;
  el.style.background = c+'22'; el.style.color = c;
  el.textContent = f.status==='good'?'sağlam':f.status==='warn'?'izlə':'yorğun';
  $('#fatigue-verdict').textContent = f.verdict || '';
  if (!f.signals?.length){ $('#fatigue-signals').innerHTML = '<p class="text-[13px] text-gray-400">Aktiv siqnal yoxdur.</p>'; return; }
  $('#fatigue-signals').innerHTML = f.signals.map(s=>{
    const sc = STATUS[s.severity] || COLORS.gray;
    return `<div class="border-l-[3px] rounded-lg p-3" style="border-color:${sc};background:${sc}0a">
      <div class="flex items-baseline gap-2"><span class="font-semibold text-[14px]">${s.name}</span><span class="num text-[12px] font-bold ml-auto" style="color:${sc}">${s.value}</span></div>
      <div class="text-[12.5px] text-gray-600 mt-1">${s.detail}</div>
    </div>`;
  }).join('');
}

function renderHealth(h){
  const score = h.score;
  let bg = COLORS.gray, label = 'data yoxdur';
  if (score !== null && score !== undefined){
    if (score >= 1.2){ bg = COLORS.green; label = 'güclü'; }
    else if (score >= 0.4){ bg = COLORS.amber; label = 'orta'; }
    else { bg = COLORS.red; label = 'aşağı'; }
  }
  const badge = $('#health-score-badge');
  badge.style.background = bg+'22'; badge.style.color = bg;
  badge.textContent = score !== null && score !== undefined ? `skor ${score.toFixed(2)} · ${label}` : label;
  $('#health-verdict').textContent = h.verdict || '';

  const b = h.ranking_breakdown || {};
  const cards = [
    ['Quality', b.quality_ranking],
    ['Engagement', b.engagement_rate_ranking],
    ['Conversion', b.conversion_rate_ranking],
  ];
  $('#health-breakdown').innerHTML = cards.map(([name, t])=>{
    if(!t) return '';
    const total = (t.above_average||0)+(t.average||0)+(t.below||0);
    return `<div class="border border-surface-line rounded-xl p-3">
      <div class="text-[12px] text-gray-500 uppercase tracking-wide mb-1">${name}</div>
      <div class="num text-lg font-bold">${total} reklam</div>
      <div class="mt-2 space-y-1 text-[12px]">
        <div class="flex justify-between"><span>Yuxarı orta</span><span class="num font-semibold" style="color:${COLORS.green}">${t.above_average||0}</span></div>
        <div class="flex justify-between"><span>Orta</span><span class="num font-semibold" style="color:${COLORS.amber}">${t.average||0}</span></div>
        <div class="flex justify-between"><span>Aşağı</span><span class="num font-semibold" style="color:${COLORS.red}">${t.below||0}</span></div>
        ${t.missing?`<div class="flex justify-between text-gray-400"><span>Data yoxdur</span><span class="num">${t.missing}</span></div>`:''}
      </div>
    </div>`;
  }).join('');
}

function rankPill(r){
  if(!r) return '<span class="rank-pill" style="background:#F1F5F9;color:#94A3B8">—</span>';
  const c = RANK_COLOR[r] || COLORS.gray;
  return `<span class="rank-pill" style="background:${c}22;color:${c}">${RANK_LABEL[r]||r}</span>`;
}
function renderDiagRows(ads){
  if (!ads?.length){ $('#diag-rows').innerHTML = '<tr><td colspan="7" class="px-5 py-8 text-center text-gray-400">Diaqnostik göstərici üçün kifayət qədər data toplanmış reklam yoxdur.</td></tr>'; return; }
  $('#diag-rows').innerHTML = ads.map(a=>`
    <tr class="hover:bg-gray-50">
      <td class="px-5 py-3 text-[13px] max-w-[260px] truncate" title="${a.ad_name}">${a.ad_name}</td>
      <td class="px-3 py-3">${rankPill(a.quality_ranking)}</td>
      <td class="px-3 py-3">${rankPill(a.engagement_rate_ranking)}</td>
      <td class="px-3 py-3">${rankPill(a.conversion_rate_ranking)}</td>
      <td class="px-3 py-3 num text-right text-gray-600">${nf(a.impressions)}</td>
      <td class="px-3 py-3 num text-right">${money(a.spend)}</td>
      <td class="px-5 py-3 num text-right font-semibold">${a.leads?money(a.cpl):'—'}</td>
    </tr>`).join('');
}

function renderVideo(v){
  const block = $('#video-block');
  if (!v?.metrics?.has_video){
    block.innerHTML = '<p class="text-sm text-gray-500">Bu dövrdə video reklam aşkarlanmadı.</p>';
    return;
  }
  const m = v.metrics, ver = v.verdict;
  const stat = (s)=>STATUS[s]||COLORS.gray;
  block.innerHTML = `
    <div class="grid grid-cols-2 gap-3">
      <div class="p-3 rounded-xl" style="background:${stat(ver.hook.status)}10;border:1px solid ${stat(ver.hook.status)}40">
        <div class="text-[11px] text-gray-500 uppercase tracking-wide">Hook rate</div>
        <div class="num text-2xl font-bold" style="color:${stat(ver.hook.status)}">${m.hook_rate}%</div>
        <div class="text-[12px] text-gray-500">${ver.hook.label} · benchmark 25%+</div>
      </div>
      <div class="p-3 rounded-xl" style="background:${stat(ver.hold.status)}10;border:1px solid ${stat(ver.hold.status)}40">
        <div class="text-[11px] text-gray-500 uppercase tracking-wide">Hold rate</div>
        <div class="num text-2xl font-bold" style="color:${stat(ver.hold.status)}">${m.hold_rate}%</div>
        <div class="text-[12px] text-gray-500">${ver.hold.label} · benchmark 15%+</div>
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3 mt-3 text-[13px]">
      <div class="text-gray-500">3 san. baxış: <span class="num font-semibold text-brand-ink">${nf(m.three_sec_views)}</span></div>
      <div class="text-gray-500">ThruPlay: <span class="num font-semibold text-brand-ink">${nf(m.thruplays)}</span></div>
      <div class="text-gray-500">Oynatma: <span class="num font-semibold text-brand-ink">${nf(m.plays)}</span></div>
      <div class="text-gray-500">Orta baxış: <span class="num font-semibold text-brand-ink">${m.avg_watch_seconds}san</span></div>
    </div>`;
}

function renderCampaigns(list){
  if(!list?.length){ $('#campaigns-list').innerHTML = '<p class="text-sm text-gray-400">Kampaniya yoxdur.</p>'; return; }
  const max = Math.max(...list.map(c=>c.spend||0), 1);
  $('#campaigns-list').innerHTML = list.map((c,i)=>{
    const w = Math.round((c.spend||0)/max*100);
    return `<div class="border-b border-gray-100 pb-2 last:border-0">
      <div class="flex items-baseline justify-between gap-2">
        <span class="text-[13px] font-medium truncate" title="${c.campaign_name}">${i+1}. ${c.campaign_name}</span>
        <span class="num text-[12px] text-gray-500 whitespace-nowrap">${money(c.spend)} · ${nf(c.leads)} lead · CPL ${c.leads?money(c.cpl):'—'}</span>
      </div>
      <div class="h-1.5 mt-1 rounded-full bg-gray-100 overflow-hidden"><div class="h-full rounded-full" style="width:${w}%;background:${COLORS.red}"></div></div>
    </div>`;
  }).join('');
}

// ---------- SOSİAL PERFORMANS tab (üzvi / organic) ----------
function statCard(label, value, sub, color){
  return `<div class="border border-surface-line rounded-xl p-3 fade-in">
    <div class="text-[11px] text-gray-500 uppercase tracking-wide">${label}</div>
    <div class="num font-extrabold text-xl mt-0.5" style="color:${color||'#1C1B17'}">${value}</div>
    <div class="text-[11px] text-gray-400 mt-0.5">${sub||'&nbsp;'}</div>
  </div>`;
}
function permNote(elId, msg){
  const el = $('#'+elId);
  if (!msg){ el.classList.add('hidden'); el.textContent=''; return; }
  el.classList.remove('hidden');
  el.innerHTML = `<strong>İcazə çatışmır.</strong> ${msg.replace(/^insufficient_permission:\s*/,'')}`;
}
async function loadSocial(){
  try{
    const d = await (await fetch('/api/organic?days=30')).json();
    renderFacebookOrganic(d.facebook);
    renderInstagramOrganic(d.instagram);
    state.loaded.social = true;
  }catch(e){ console.error(e); }
}
function renderFacebookOrganic(fb){
  if (!fb || !fb.configured){
    $('#fb-name').textContent = 'Konfiqurasiya olunmayıb (META_FACEBOOK_PAGE_IDS yoxdur).';
    $('#fb-cards').innerHTML=''; return;
  }
  if (fb.error){ $('#fb-name').textContent = 'Xəta: ' + fb.error; $('#fb-cards').innerHTML=''; return; }
  $('#fb-name').textContent = fb.name || '—';
  $('#fb-cards').innerHTML = [
    statCard('İzləyici (fan)', nf(fb.fan_count), 'canlı', COLORS.blue),
    statCard('Gündəlik baxış', fb.daily?.length ? nf(fb.daily.reduce((s,d)=>s+(d.page_views_total||0),0)) : '—', '30 gün cəmi', COLORS.green),
  ].join('');
  const wrap = $('#fb-trend-wrap');
  if (fb.daily && fb.daily.length){
    wrap.classList.remove('hidden');
    mkChart('ch-fb-trend',{ type:'line',
      data:{ labels: fb.daily.map(d=>+d.date.split('-')[2]), datasets:[
        { label:'Baxış', data: fb.daily.map(d=>d.page_views_total||0), borderColor:COLORS.blue, backgroundColor:'rgba(37,99,235,.08)', fill:true, tension:.35, pointRadius:0, borderWidth:2 },
        { label:'Engagement', data: fb.daily.map(d=>d.page_post_engagements||0), borderColor:COLORS.green, fill:false, tension:.35, pointRadius:0, borderWidth:2 },
      ]},
      options:{ maintainAspectRatio:false, responsive:true, interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:true,position:'top',align:'end',labels:{boxWidth:10,usePointStyle:true}}},
        scales:{ y:{grid:{color:'#f1f3f5'},beginAtZero:true} } }});
  } else { wrap.classList.add('hidden'); }
  permNote('fb-note', fb.insights_error);
}
function renderInstagramOrganic(ig){
  if (!ig || !ig.configured){
    $('#ig-name').textContent = 'Konfiqurasiya olunmayıb (META_INSTAGRAM_BUSINESS_IDS yoxdur).';
    $('#ig-cards').innerHTML=''; return;
  }
  if (ig.error){ $('#ig-name').textContent = 'Xəta: ' + ig.error; $('#ig-cards').innerHTML=''; return; }
  $('#ig-name').textContent = ig.username ? '@'+ig.username : '—';
  $('#ig-cards').innerHTML = [
    statCard('İzləyici', nf(ig.followers_count), 'canlı', COLORS.pink),
    statCard('Media sayı', nf(ig.media_count), 'cəmi', COLORS.purple),
  ].join('');
  const wrap = $('#ig-trend-wrap');
  if (ig.daily && ig.daily.length){
    wrap.classList.remove('hidden');
    mkChart('ch-ig-trend',{ type:'line',
      data:{ labels: ig.daily.map(d=>+d.date.split('-')[2]), datasets:[
        { label:'Reach', data: ig.daily.map(d=>d.reach||0), borderColor:COLORS.pink, backgroundColor:'rgba(219,39,119,.08)', fill:true, tension:.35, pointRadius:0, borderWidth:2 },
      ]},
      options:{ maintainAspectRatio:false, responsive:true,
        plugins:{legend:{display:false}},
        scales:{ y:{grid:{color:'#f1f3f5'},beginAtZero:true} } }});
  } else { wrap.classList.add('hidden'); }
  permNote('ig-note', ig.insights_error);
}

// ---------- payments ----------
function renderPayments(r){
  const inv=r.invoices, spend=r.combined_totals.spend;
  $('#pay-cards').innerHTML = [
    kpiCard('pc1','','#DBEAFE',COLORS.blue,'Qəbz sayı',nf(inv.count),'Gmail-dən',null),
    kpiCard('pc2','','#DCFCE7',COLORS.green,'Ümumi məbləğ',money(inv.total),'fakturalanmış',null),
    kpiCard('pc3','','#FEF3C7',COLORS.amber,'Fakturalanmamış',money(inv.unbilled||0),'hələ qəbz yoxdur',null),
  ].join('');
  const ok = (inv.unbilled||0) <= 0.01;
  const col = ok?COLORS.green:COLORS.amber;
  $('#recon').style.borderLeft=`3px solid ${col}`;
  $('#recon').innerHTML = `<span class="font-semibold" style="color:${col}">Üzləşmə:</span>
     Hesablanan xərc <span class="num font-semibold">${money(spend)}</span> ·
     Fakturalanmış <span class="num font-semibold">${money(inv.total)}</span> ·
     Fərq <span class="num font-semibold" style="color:${col}">${money(inv.unbilled||0)}</span>
     ${ok?'(tam üzləşir)':'(hələ fakturalanmayıb)'}`;
  $('#pay-rows').innerHTML = inv.rows.map(row=>`
    <tr class="hover:bg-gray-50"><td class="px-5 py-3 num text-gray-600 whitespace-nowrap">${azDate(row.date)}</td>
    <td class="px-5 py-3 num font-semibold">${money(row.amount)}</td>
    <td class="px-5 py-3 text-gray-500 text-[13px]">${row.detail}</td></tr>`).join('')
    || `<tr><td colspan="3" class="px-5 py-8 text-center text-gray-400">Bu ay üçün qəbz yoxdur (real Gmail invoyslar üçün cache lazımdır).</td></tr>`;
}

// ---------- sales ----------
function renderSales(r){
  const s=r.sales, spend=r.combined_totals.spend;
  const cps = s.total ? spend/s.total : 0;
  $('#sales-cards').innerHTML = [
    kpiCard('sc1','','#FEE2E2',COLORS.red,'Reklam xərci',money(spend),'Meta Ads',null),
    kpiCard('sc2','','#DBEAFE',COLORS.blue,'Digital satış',nf(s.total),'bu ay',null),
    kpiCard('sc3','','#DCFCE7',COLORS.green,'Satış başına xərc',money(cps),'xərc ÷ satış',null),
  ].join('');
  const palette=[COLORS.blue,COLORS.green,COLORS.amber,COLORS.red,COLORS.purple];
  mkChart('ch-sales',{ type:'bar',
    data:{ labels:s.by_channel.map(c=>c.channel), datasets:[{ data:s.by_channel.map(c=>c.count), backgroundColor:palette, borderRadius:8 }]},
    options:{ ...noLegend, scales:{ y:{grid:{color:'#f1f3f5'},beginAtZero:true}, x:{grid:{display:false}} } }});
  $('#sales-bars').innerHTML = s.by_channel.map((c,i)=>`
    <div class="flex items-center gap-3">
      <span class="w-2.5 h-2.5 rounded-full" style="background:${palette[i%palette.length]}"></span>
      <span class="text-[14px] flex-1">${c.channel}</span>
      <span class="num font-bold">${c.count}</span>
      <div class="w-28 h-2 rounded-full bg-gray-100 overflow-hidden"><div class="h-full rounded-full" style="width:${c.pct}%;background:${palette[i%palette.length]}"></div></div>
      <span class="num text-gray-400 text-[12px] w-9 text-right">${c.pct}%</span>
    </div>`).join('');
}

// ---------- assistant ----------
function toggleAsst(open){
  $('#asst-panel').classList.toggle('hidden',!open); $('#asst-panel').classList.toggle('flex',open);
  $('#asst-fab').classList.toggle('hidden',open);
  if(open && !$('#asst-log').dataset.greeted){
    pushMsg('bot', `Salam! ${state.last?.report.period.label} dövrünün rəqəmləri üzrə sual verin.`);
    $('#asst-log').dataset.greeted='1';
  }
}
function pushMsg(who,text){
  const log=$('#asst-log');
  const cls = who==='user' ? 'ml-auto bg-brand-red text-white' : 'mr-auto bg-white border border-surface-line';
  log.insertAdjacentHTML('beforeend', `<div class="max-w-[85%] ${cls} rounded-2xl px-3.5 py-2 whitespace-pre-line fade-in">${mdLite(text)}</div>`);
  log.scrollTop=log.scrollHeight;
}
async function onAsk(e){
  e.preventDefault();
  const inp=$('#asst-input'); const q=inp.value.trim(); if(!q) return;
  inp.value=''; pushMsg('user',q);
  const log=$('#asst-log');
  log.insertAdjacentHTML('beforeend',`<div id="typing" class="mr-auto bg-white border border-surface-line rounded-2xl px-3.5 py-2 text-gray-400">yazır…</div>`);
  log.scrollTop=log.scrollHeight;
  try{
    const r = await (await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q,month:state.month,platform:state.platform,account:state.account})})).json();
    $('#typing')?.remove(); pushMsg('bot', r.text);
  }catch(err){ $('#typing')?.remove(); pushMsg('bot','Bağışlayın, cavab alınmadı.'); }
}

function printPdf(){ $$('.tabpanel').forEach(p=>p.classList.remove('hidden')); window.print(); }

init();
