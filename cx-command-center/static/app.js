const state = {
  meta: null,
  integrations: null,
  report: null,
  complaints: [],
  chart: null,
};

const $ = (s) => document.querySelector(s);
const nf = (n) => new Intl.NumberFormat('az-AZ').format(Math.round(n || 0));
const severityColor = {
  critical: '#B91C1C',
  high: '#E31E24',
  medium: '#F59E0B',
  low: '#2563EB',
};
const statusLabel = {
  new: 'Yeni',
  triaged: 'Triaged',
  in_progress: 'İcrada',
  waiting_customer: 'Müştəri gözlənilir',
  resolved: 'Həll edildi',
  closed: 'Bağlandı',
};
const categoryLabel = {
  claims: 'Ödəniş / hadisə',
  price: 'Qiymət',
  service_quality: 'Xidmət',
  delay: 'Gecikmə',
  staff_behavior: 'Personal davranışı',
  digital_issue: 'Rəqəmsal problem',
  policy_terms: 'Müqavilə şərtləri',
  branch_experience: 'Filial təcrübəsi',
  sales_followup: 'Satış geri dönüşü',
  reputation_risk: 'Reputasiya riski',
  other: 'Digər',
};

async function init() {
  const [meta, integrations] = await Promise.all([
    fetch('/api/meta').then((r) => r.json()),
    fetch('/api/integrations/status').then((r) => r.json()),
  ]);
  state.meta = meta;
  state.integrations = integrations;
  $('#brand-name').textContent = state.meta.account;
  $('#brand-tagline').textContent = state.meta.tagline;
  $('#mode-badge').textContent = state.meta.data_mode;
  renderIntegrationHealth();
  fillFilters();
  bind();
  await loadAll();
  lucide.createIcons();
}

function renderIntegrationHealth() {
  const channels = state.integrations?.channels || {};
  const rows = [
    ['Public URL', { configured: Boolean(state.integrations?.public_webhooks_ready), detail: state.integrations?.public_base_url || 'External HTTPS webhook URL' }, 'Meta/Chatplace callback URL'],
    ['Meta webhook', channels.meta_webhook, 'Instagram/Facebook realtime'],
    ['Meta pull', channels.meta_graph_pull, 'Owned social comments'],
    ['Chatplace', channels.chatplace_webhook, 'External API webhook'],
    ['Google reviews', channels.google_reviews, 'Business Profile reviews'],
    ['Telegram alerts', channels.telegram_alerts, 'Critical/high alerts'],
    ['Auto sync', { configured: (state.integrations?.auto_sync_interval_seconds || 0) > 0, detail: `${state.integrations?.auto_sync_interval_seconds || 0}s interval` }, 'Background pull loop'],
  ];
  $('#integration-health').innerHTML = rows.map(([label, info, fallback]) => {
    const ok = Boolean(info?.configured);
    const hint = info?.detail || fallback;
    const missing = info?.missing?.length ? ` Missing: ${info.missing.join(', ')}` : '';
    return `
    <div class="card p-3 flex items-center gap-3">
      <span class="w-8 h-8 rounded-lg flex items-center justify-center ${ok ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}">
        <i data-lucide="${ok ? 'check-circle-2' : 'circle-dashed'}" class="w-4 h-4"></i>
      </span>
      <div class="min-w-0">
        <div class="text-sm font-bold">${label}</div>
        <div class="text-xs text-gray-500 truncate">${escapeHtml(hint + missing)}</div>
      </div>
    </div>`;
  }).join('');
}

function fillFilters() {
  $('#status').innerHTML += state.meta.statuses.map((s) => `<option value="${s}">${statusLabel[s] || s}</option>`).join('');
  $('#channel').innerHTML += state.meta.channels.map((c) => `<option value="${c.id}">${c.label}</option>`).join('');
}

function bind() {
  $('#refresh').addEventListener('click', loadAll);
  $('#sync-all').addEventListener('click', syncAll);
  ['q', 'status', 'severity', 'channel'].forEach((id) => {
    const ev = id === 'q' ? 'input' : 'change';
    $('#' + id).addEventListener(ev, debounce(loadComplaints, 250));
  });
  $('#ask-form').addEventListener('submit', onAsk);
}

async function syncAll() {
  const btn = $('#sync-all');
  btn.disabled = true;
  btn.classList.add('opacity-60');
  toast('Live channel sync started...');
  try {
    const res = await fetch('/api/sync/all?max_pages=1', { method: 'POST' });
    const data = await res.json();
    const totals = data.totals || {};
    const message = `Sync: ${totals.received || 0} received, ${totals.new || 0} new, ${totals.updated || 0} updated`;
    toast(data.ok ? message : `${message}, ${totals.errors || 0} error`);
    state.integrations = await fetch('/api/integrations/status').then((r) => r.json());
    renderIntegrationHealth();
    await loadAll();
  } catch (err) {
    toast('Sync failed');
  } finally {
    btn.disabled = false;
    btn.classList.remove('opacity-60');
    lucide.createIcons();
  }
}

async function loadAll() {
  const [report] = await Promise.all([fetch('/api/report?days=30').then((r) => r.json())]);
  state.report = report;
  renderReport(report);
  await loadComplaints();
}

async function loadComplaints() {
  const params = new URLSearchParams({
    status: $('#status').value,
    severity: $('#severity').value,
    channel: $('#channel').value,
    q: $('#q').value,
    days: '30',
  });
  const data = await (await fetch('/api/complaints?' + params.toString())).json();
  state.complaints = data.items || [];
  renderComplaints();
}

function renderReport(report) {
  const t = report.totals;
  $('#kpis').innerHTML = [
    kpi('Messages', nf(t.messages), 'inbox', '#2563EB'),
    kpi('Open', nf(t.open), 'circle-dot', '#F59E0B'),
    kpi('Critical', nf(t.critical_open), 'siren', '#E31E24'),
    kpi('Overdue', nf(t.overdue), 'timer-off', '#B91C1C'),
    kpi('Resolved', nf(t.resolved), 'check-circle-2', '#16A34A'),
    kpi('Rating', t.avg_rating ? t.avg_rating.toFixed(2) : '-', 'star', '#2B2A29'),
  ].join('');

  const brief = report.brief;
  $('#brief-title').textContent = brief.title;
  $('#brief-text').textContent = brief.text;
  $('#brief-dot').style.background = brief.level === 'red' ? '#E31E24' : brief.level === 'amber' ? '#F59E0B' : '#16A34A';
  $('#risk-score').textContent = t.risk_score;
  $('#risk-bar').style.width = `${Math.min(t.risk_score, 100)}%`;
  $('#risk-bar').style.background = t.risk_score >= 70 ? '#B91C1C' : t.risk_score >= 45 ? '#F59E0B' : '#16A34A';
  renderOverdue(report.overdue_queue);
  renderRootCauses(report.root_causes, t.messages);
  renderChannelChart(report.breakdowns.channel);
  lucide.createIcons();
}

function kpi(label, value, icon, color) {
  return `<div class="card p-4 fade">
    <div class="flex items-center justify-between mb-3">
      <span class="w-8 h-8 rounded-lg flex items-center justify-center" style="background:${color}14;color:${color}">
        <i data-lucide="${icon}" class="w-4 h-4"></i>
      </span>
    </div>
    <div class="text-[11px] uppercase font-semibold text-gray-500">${label}</div>
    <div class="num text-2xl font-extrabold leading-tight">${value}</div>
  </div>`;
}

function renderComplaints() {
  $('#queue-count').textContent = `${state.complaints.length} siqnal`;
  if (!state.complaints.length) {
    $('#complaints').innerHTML = `<div class="text-sm text-gray-500 py-8 text-center">Filterə uyğun siqnal yoxdur.</div>`;
    return;
  }
  $('#complaints').innerHTML = state.complaints.map(complaintCard).join('');
  document.querySelectorAll('[data-status-id]').forEach((btn) => {
    btn.addEventListener('click', () => updateStatus(btn.dataset.statusId, btn.dataset.nextStatus));
  });
  lucide.createIcons();
}

function complaintCard(c) {
  const color = severityColor[c.severity] || '#6B7280';
  const author = c.author_name || c.author_handle || 'Naməlum müştəri';
  const due = relativeTime(c.sla_due_at);
  const next = c.status === 'resolved' ? 'closed' : c.status === 'closed' ? 'closed' : 'resolved';
  return `<article class="border border-surface-line rounded-lg p-3 fade">
    <div class="flex flex-wrap items-start gap-2">
      <span class="chip text-[11px] font-bold px-2 py-1 text-white" style="background:${color}">${c.severity}</span>
      <span class="chip text-[11px] font-semibold px-2 py-1 bg-gray-100 text-gray-700">${channelName(c.channel)}</span>
      <span class="chip text-[11px] font-semibold px-2 py-1 bg-gray-100 text-gray-700">${categoryLabel[c.category] || c.category}</span>
      <span class="ml-auto text-[11px] text-gray-500 num">SLA ${due}</span>
    </div>
    <div class="mt-2 flex gap-3">
      <div class="w-9 h-9 rounded-lg bg-gray-100 flex items-center justify-center text-xs font-bold shrink-0">${initials(author)}</div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <h3 class="font-bold truncate">${escapeHtml(author)}</h3>
          <span class="text-xs text-gray-400">${statusLabel[c.status] || c.status}</span>
        </div>
        <p class="text-sm text-gray-700 mt-1 leading-relaxed">${escapeHtml(c.text)}</p>
        <div class="mt-3 bg-gray-50 border border-gray-100 rounded-lg p-3">
          <div class="text-[11px] uppercase font-bold text-gray-400 mb-1">AI draft</div>
          <div class="text-sm text-gray-700">${escapeHtml(c.recommended_reply)}</div>
        </div>
        <div class="flex flex-wrap gap-2 mt-3">
          <button data-status-id="${c.id}" data-next-status="in_progress" class="btn border border-surface-line hover:border-brand-red px-3 py-1.5 text-xs flex items-center gap-1">
            <i data-lucide="play" class="w-3 h-3"></i>İcraya al
          </button>
          <button data-status-id="${c.id}" data-next-status="${next}" class="btn bg-brand-ink text-white hover:bg-brand-charcoal px-3 py-1.5 text-xs flex items-center gap-1">
            <i data-lucide="check" class="w-3 h-3"></i>${next === 'closed' ? 'Bağla' : 'Həll et'}
          </button>
          ${c.url ? `<a href="${escapeAttr(c.url)}" target="_blank" class="btn border border-surface-line px-3 py-1.5 text-xs flex items-center gap-1"><i data-lucide="external-link" class="w-3 h-3"></i>Mənbə</a>` : ''}
        </div>
      </div>
    </div>
  </article>`;
}

function renderOverdue(items) {
  if (!items || !items.length) {
    $('#overdue').innerHTML = `<div class="text-sm text-gray-500">Gecikən SLA yoxdur.</div>`;
    return;
  }
  $('#overdue').innerHTML = items.slice(0, 5).map((i) => `
    <div class="border border-red-100 bg-red-50 rounded-lg p-3">
      <div class="text-xs font-bold text-red-700">${channelName(i.channel)} - #${i.id}</div>
      <div class="text-sm text-gray-800 mt-1">${escapeHtml(i.ai_summary)}</div>
    </div>`).join('');
}

function renderRootCauses(rows, total) {
  if (!rows || !rows.length) {
    $('#root-causes').innerHTML = `<div class="text-sm text-gray-500">Data yoxdur.</div>`;
    return;
  }
  $('#root-causes').innerHTML = rows.map((r) => {
    const pct = total ? Math.round((r.count / total) * 100) : 0;
    return `<div>
      <div class="flex justify-between text-sm mb-1">
        <span class="font-semibold">${categoryLabel[r.category] || r.category}</span>
        <span class="num text-gray-500">${r.count}</span>
      </div>
      <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div class="h-full bg-brand-red rounded-full" style="width:${pct}%"></div>
      </div>
      <div class="text-[11px] text-gray-400 mt-1">${r.team}</div>
    </div>`;
  }).join('');
}

function renderChannelChart(rows) {
  const el = $('#channel-chart');
  if (state.chart) state.chart.destroy();
  state.chart = new Chart(el, {
    type: 'doughnut',
    data: {
      labels: rows.map((r) => channelName(r.key)),
      datasets: [{
        data: rows.map((r) => r.count),
        backgroundColor: ['#E31E24', '#2563EB', '#16A34A', '#F59E0B', '#2B2A29', '#64748B', '#0D9488', '#B3171C'],
        borderWidth: 0,
      }],
    },
    options: {
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } } },
      maintainAspectRatio: false,
      cutout: '62%',
    },
  });
}

async function updateStatus(id, status) {
  await fetch(`/api/complaints/${id}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, owner: 'Operator', note: 'Dashboard action' }),
  });
  toast(`Status yeniləndi: ${statusLabel[status] || status}`);
  await loadAll();
}

async function onAsk(e) {
  e.preventDefault();
  const question = $('#ask').value.trim();
  if (!question) return;
  $('#answer').innerHTML = `<div class="skeleton h-4 rounded w-full"></div>`;
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, days: 30 }),
  });
  const data = await res.json();
  $('#answer').textContent = data.answer;
}

function channelName(id) {
  return state.meta?.channels?.find((c) => c.id === id)?.label || id;
}

function initials(name) {
  return (name || '?').split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase();
}

function relativeTime(iso) {
  const then = new Date(iso).getTime();
  const diff = then - Date.now();
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  if (mins < 60) return diff < 0 ? `${mins} dəq gecikib` : `${mins} dəq`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return diff < 0 ? `${hours} saat gecikib` : `${hours} saat`;
  const days = Math.round(hours / 24);
  return diff < 0 ? `${days} gün gecikib` : `${days} gün`;
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/`/g, '&#96;');
}

function debounce(fn, wait) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function toast(text) {
  const el = $('#toast');
  el.textContent = text;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 2200);
}

init();
