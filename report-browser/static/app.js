/* urlquery report browser. Every piece of record data is inserted with
   textContent (via el()), never innerHTML: the records contain probe strings. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString());
const short = (s, n = 80) => (s && s.length > n ? s.slice(0, n) + '…' : s || '');
const ts = (s) => (s ? s.replace('T', ' ').replace('Z', '') : '');
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
}
const _seq = {};
function latest(key) { const n = (_seq[key] = (_seq[key] || 0) + 1); return () => _seq[key] === n; }
async function api(path, opts) {
  const r = await fetch(path, opts);
  const ct = r.headers.get('content-type') || '';
  const body = ct.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error(body.error || body || r.statusText);
  return body;
}
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

// ------------------------------------------------------------------ state
const ARRAY_KEYS = ['disposition', 'confidence', 'broad_class', 'source', 'submitted_fqdn', 'final_fqdn',
  'payload_sig', 'verdict', 'week', 'day', 'month', 'useragent', 'contacted', 'target'];
const DIMS = [
  ['source', 'Data source'], ['broad_class', 'Method class'], ['confidence', 'Confidence'],
  ['disposition', 'Disposition'], ['month', 'Month'], ['week', 'Week'], ['day', 'Day'],
  ['hour', 'UTC hour'], ['weekday', 'Weekday'], ['fetched', 'Fetched?'],
  ['submitted_fqdn', 'Submitted host (carrier)'], ['target', 'Payload target host'],
  ['contacted', 'Contacted host (HTTP)'], ['final_fqdn', 'Final host'], ['script', 'Script (md5)'],
  ['payload_sig', 'Payload program signature'], ['payload_kinds', 'Payload encoding'],
  ['verdict', 'urlquery verdict'], ['useragent', 'User agent'],
];
const DIM_LABEL = Object.fromEntries(DIMS);
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const S = {
  f: {},
  tab: 'timeline',
  offset: 0, pageSize: 100,
  selected: new Set(),
  golden: { incidents: [], findings: [] },
  incident: null,
  colorMaps: {},
};
try { Object.assign(S.f, JSON.parse(decodeURIComponent(location.hash.slice(1)) || '{}')); } catch { /* ignore */ }

function qs(extra = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...S.f, ...extra })) {
    if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue;
    p.set(k, Array.isArray(v) ? JSON.stringify(v) : v);
  }
  return p.toString();
}
function setFilter(k, v) {
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) delete S.f[k]; else S.f[k] = v;
  S.offset = 0; S.selected.clear();
  history.replaceState(null, '', '#' + encodeURIComponent(JSON.stringify(S.f)));
  refresh();
}
function toggleFilter(k, v) {
  if (v == null) return toast('Cannot filter on an empty value');
  if (ARRAY_KEYS.includes(k)) {
    const a = new Set(S.f[k] || []);
    a.has(v) ? a.delete(v) : a.add(v);
    setFilter(k, [...a]);
  } else if (['hour', 'weekday', 'script', 'fetched', 'host'].includes(k)) {
    setFilter(k, S.f[k] === String(v) ? null : String(v));
  } else toast(`${DIM_LABEL[k] || k} is not filterable`);
}

// ------------------------------------------------------------------ colors
const PALETTE = () => ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8'].map(css);
const FIXED = { confidence: { significant: 1, suggestive: 0 } };
function colorFor(dim, name) {
  if (name === 'Other' || name === '(none)' || name === 'null') return css('--text-muted');
  const m = (S.colorMaps[dim] ||= {});
  if (FIXED[dim] && name in FIXED[dim]) return PALETTE()[FIXED[dim][name]];
  if (!(name in m)) m[name] = Object.keys(m).length;
  return m[name] < 8 ? PALETTE()[m[name]] : css('--text-muted');
}
function dimValueLabel(dim, v) {
  if (v == null) return '(none)';
  if (dim === 'weekday') return WEEKDAYS[v] || v;
  if (dim === 'hour') return `${String(v).padStart(2, '0')}:00`;
  return String(v);
}

// ------------------------------------------------------------------ charts
const charts = {};
function chart(id) {
  if (!charts[id]) {
    charts[id] = echarts.init(document.getElementById(id), null, { renderer: 'canvas' });
    window.addEventListener('resize', () => charts[id].resize());
  }
  return charts[id];
}
function axisStyle() {
  return {
    axisLine: { lineStyle: { color: css('--border') } },
    axisLabel: { color: css('--text-secondary'), fontSize: 11 },
    splitLine: { lineStyle: { color: css('--surface-3') } },
    axisTick: { show: false },
  };
}
const tooltipStyle = () => ({
  backgroundColor: css('--surface-2'), borderColor: css('--border'),
  textStyle: { color: css('--text-primary'), fontSize: 12 }, confine: true,
});

// ------------------------------------------------------------------ sidebar
async function renderSidebar() {
  const s = await api('/api/summary?' + qs());
  const stats = $('#stats'); stats.replaceChildren(
    el('div', { class: 'stat' }, el('div', { class: 'v' }, fmt(s.n)), el('div', { class: 'l' }, 'reports in slice')),
    el('div', { class: 'stat' }, el('div', { class: 'v' }, fmt(s.fetched)), el('div', { class: 'l' }, 'raw fetched')),
    el('div', { class: 'stat', style: 'grid-column: span 2' }, el('div', { class: 'l' }, 'span'),
      el('div', { class: 'mono' }, `${ts(s.first) || '—'} → ${ts(s.last) || '—'}`)),
  );
  const box = $('#facets'); box.replaceChildren();
  for (const [dim, title] of [['disposition', 'Disposition'], ['confidence', 'Confidence'], ['broad_class', 'Method class'], ['fetched', 'Raw record'], ['source', 'Data source']]) {
    const items = s.facets[dim];
    const max = Math.max(1, ...items.map((i) => i.n));
    const list = el('div', { class: 'items' });
    const sel = dim === 'fetched' ? (S.f.fetched ? [S.f.fetched] : []) : (S.f[dim] || []);
    const draw = (needle = '') => {
      list.replaceChildren(...items.filter((i) => String(i.v).toLowerCase().includes(needle)).map((i) => el('div', {
        class: 'fitem' + (sel.includes(String(i.v)) ? ' on' : ''), title: String(i.v),
        onclick: () => toggleFilter(dim, i.v),
      }, el('span', { class: 'bar', style: `width:${(100 * i.n) / max}%` }),
      ['confidence', 'broad_class', 'disposition'].includes(dim) ? el('span', { class: 'sw', style: `background:${colorFor(dim, String(i.v ?? '(none)'))}` }) : el('span'),
      el('span', { class: 'name' }, dimValueLabel(dim, i.v)), el('span', { class: 'n' }, fmt(i.n)))));
    };
    draw();
    const head = el('h4', {}, title, sel.length ? el('button', { class: 'link', onclick: () => setFilter(dim, null) }, 'clear') : '');
    const f = el('div', { class: 'facet' }, head);
    if (items.length > 12) f.append(el('input', { class: 'fsearch', placeholder: `filter ${items.length}…`, oninput: (e) => draw(e.target.value.toLowerCase()) }));
    f.append(list); box.append(f);
  }
}

function renderChips() {
  const box = $('#chips'); box.replaceChildren();
  const label = { from: 'from', to: 'to', q: 'search', ids: 'ids', incident: 'incident evidence', finding: 'finding evidence' };
  for (const [k, v] of Object.entries(S.f)) {
    const vals = Array.isArray(v) ? v : [v];
    for (const one of vals) {
      let shown = k === 'ids' ? `${JSON.parse(one).length} reports` : dimValueLabel(k, one);
      if (k === 'incident') shown = S.golden.incidents.find((i) => i.id === one)?.name || one;
      box.append(el('span', { class: 'chip' }, el('b', {}, (label[k] || DIM_LABEL[k] || k) + ':'), el('span', { title: String(one) }, shown),
        el('button', { 'aria-label': 'remove', onclick: () => (Array.isArray(v) ? toggleFilter(k, one) : setFilter(k, null)) }, '✕')));
    }
  }
  if (Object.keys(S.f).length) box.append(el('span', { class: 'chip clear', onclick: () => { S.f = {}; setFilter('_', null); $('#q').value = ''; } }, 'clear all'));
}

// ------------------------------------------------------------------ timeline
async function renderTimeline() {
  const fresh = latest('renderTimeline');
  const bin = $('#ts-bin').value, stack = $('#ts-stack').value;
  const d = await api(`/api/timeseries?${qs({ bin, stack })}`);
  if (!fresh()) return;
  const c = chart('ts-chart');
  const order = Object.entries(d.totals).sort((a, b) => b[1] - a[1]).map((x) => x[0]);
  order.forEach((n) => colorFor(stack, n));
  const incidents = S.golden.incidents.filter((i) => i.start && i.end);
  const series = d.series.map((s, idx) => ({
    name: dimValueLabel(stack, s.name === 'null' ? null : s.name), type: 'bar', stack: 'x', data: s.data,
    itemStyle: { color: colorFor(stack, s.name), borderColor: css('--surface-1'), borderWidth: d.bins.length < 120 ? 1 : 0 },
    barCategoryGap: '10%', emphasis: { focus: 'series' },
    markArea: idx === 0 && incidents.length ? {
      silent: true, itemStyle: { color: 'rgba(200,200,190,0.08)', borderColor: css('--text-muted'), borderWidth: 1, borderType: 'dashed' },
      label: { color: css('--text-secondary'), fontSize: 11, position: 'insideTop' },
      data: incidents.map((i) => [{ name: i.key, xAxis: snapBin(i.start, bin, d.bins) }, { xAxis: snapBin(i.end, bin, d.bins) }]),
    } : undefined,
  }));
  c.setOption({
    animation: false,
    grid: { left: 50, right: 20, top: 40, bottom: 70 },
    legend: { top: 6, type: 'scroll', textStyle: { color: css('--text-secondary') }, inactiveColor: css('--border') },
    tooltip: { ...tooltipStyle(), trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const tot = ps.reduce((a, p) => a + (p.value || 0), 0);
        const lines = ps.filter((p) => p.value).sort((a, b) => b.value - a.value).map((p) => `${p.marker}${escapeText(p.seriesName)}&nbsp;&nbsp;<b>${fmt(p.value)}</b>`);
        return `<b>${escapeText(ps[0].axisValue)}</b> · ${fmt(tot)} reports<br>${lines.join('<br>')}`;
      } },
    xAxis: { type: 'category', data: d.bins, ...axisStyle() },
    yAxis: { type: 'value', ...axisStyle() },
    dataZoom: [{ type: 'inside', ...zoomStart(d.bins) }, { type: 'slider', ...zoomStart(d.bins), height: 22, bottom: 14, borderColor: css('--border'), textStyle: { color: css('--text-muted') } }],
    series,
  }, true);
  c.off('click');
  c.on('click', (p) => {
    const [from, to] = binRange(p.name, bin);
    S.f.from = from; setFilter('to', to);
  });
  renderClock();
}
function zoomStart(bins) {
  // the catalogue has a long sparse 2023–2025 tail; open on the activity window unless sliced
  if (S.f.from || bins.length < 60) return {};
  const i = bins.findIndex((b) => b >= '2025-10');
  return i > 0 ? { startValue: bins[i] } : {};
}
function escapeText(s) { return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function snapBin(date, bin, bins) {
  const d = date.slice(0, 10);
  if (bin === 'month') return d.slice(0, 7);
  if (bin === 'hour') return bins.find((b) => b >= d) || bins[bins.length - 1];
  if (bin === 'week') { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7)); return t.toISOString().slice(0, 10); }
  return d;
}
function binRange(b, bin) {
  if (bin === 'hour') return [`${b}:00:00Z`, `${b}:59:59Z`];
  if (bin === 'day') return [`${b}T00:00:00Z`, `${b}T23:59:59Z`];
  if (bin === 'month') { const [y, m] = b.split('-').map(Number); const end = new Date(Date.UTC(y, m, 0)); return [`${b}-01T00:00:00Z`, `${end.toISOString().slice(0, 10)}T23:59:59Z`]; }
  const t = new Date(b + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + 6);
  return [`${b}T00:00:00Z`, `${t.toISOString().slice(0, 10)}T23:59:59Z`];
}
$('#ts-apply-zoom').onclick = () => {
  const c = charts['ts-chart']; if (!c) return;
  const opt = c.getOption(); const bins = opt.xAxis[0].data; const z = opt.dataZoom[0];
  const a = bins[Math.max(0, Math.floor((z.start / 100) * (bins.length - 1)))];
  const b = bins[Math.min(bins.length - 1, Math.ceil((z.end / 100) * (bins.length - 1)))];
  const bin = $('#ts-bin').value;
  S.f.from = binRange(a, bin)[0]; setFilter('to', binRange(b, bin)[1]);
};

async function renderClock() {
  const d = await api('/api/clock?' + qs());
  const max = Math.max(1, ...d.cells.map((c) => c[2]));
  const c = chart('clock-chart');
  c.setOption({
    animation: false,
    grid: { left: 50, right: 90, top: 10, bottom: 30 },
    tooltip: { ...tooltipStyle(), formatter: (p) => `${WEEKDAYS[p.value[1]]} ${String(p.value[0]).padStart(2, '0')}:00 UTC<br><b>${fmt(p.value[2])}</b> reports` },
    xAxis: { type: 'category', data: [...Array(24).keys()].map((h) => String(h).padStart(2, '0')), ...axisStyle(), splitLine: { show: false } },
    yAxis: { type: 'category', data: WEEKDAYS, ...axisStyle(), inverse: true, splitLine: { show: false } },
    visualMap: { min: 0, max, calculable: true, orient: 'vertical', right: 10, top: 10, itemHeight: 140,
      inRange: { color: [css('--seq-lo'), css('--seq-hi')] }, textStyle: { color: css('--text-muted') } },
    series: [{ type: 'heatmap', data: d.cells, itemStyle: { borderColor: css('--surface-1'), borderWidth: 2, borderRadius: 3 } }],
  }, true);
  c.off('click');
  c.on('click', (p) => { S.f.hour = String(p.value[0]); setFilter('weekday', String(p.value[1])); });
}

// ------------------------------------------------------------------ groups
async function renderGroups() {
  const fresh = latest('renderGroups');
  const by = $('#g-by').value, by2 = $('#g-by2').value;
  const d = await api(`/api/groups?${qs({ by, by2 })}`);
  if (!fresh()) return;
  const max = Math.max(1, ...d.groups.map((g) => g.n));
  const t = el('table', { class: 'grid' }, el('thead', {}, el('tr', {},
    el('th', {}, DIM_LABEL[by]), el('th', {}, 'Reports'), el('th', {}, 'Significant'), el('th', {}, 'Active days'),
    el('th', {}, 'First'), el('th', {}, 'Last'), el('th', {}, 'Fetched'), by2 ? el('th', {}, DIM_LABEL[by2]) : null)));
  const tb = el('tbody');
  for (const g of d.groups) {
    const label = dimValueLabel(by, g.v);
    const info = g.info ? el('div', { class: 'hint mono' }, `${g.info.section}${g.info.inline ? ' inline' : ''} · ${fmt(g.info.size)} B · seen ${fmt(g.info.times_seen)}× on urlquery ${g.info.url ? '· ' + short(g.info.url, 70) : ''}`) : null;
    tb.append(el('tr', { class: 'click', onclick: () => toggleFilter(by, g.v) },
      el('td', { class: ['submitted_fqdn', 'target', 'contacted', 'final_fqdn', 'script', 'payload_sig', 'useragent'].includes(by) ? 'url' : '' }, label, info),
      el('td', {}, el('div', { class: 'nbar' }, el('i', { style: `width:${(120 * g.n) / max}px` }), fmt(g.n))),
      el('td', { class: 'num' }, fmt(g.sig)), el('td', { class: 'num' }, fmt(g.days)),
      el('td', { class: 'mono' }, ts(g.first)), el('td', { class: 'mono' }, ts(g.last)), el('td', { class: 'num' }, fmt(g.fetched)),
      by2 ? el('td', {}, el('div', { class: 'subs' }, (g.sub || []).map((s) => el('span', {
        class: 'pill', title: 'slice to both', onclick: (e) => { e.stopPropagation(); toggleFilter(by, g.v); toggleFilter(by2, s.v); },
      }, `${short(dimValueLabel(by2, s.v), 40)} ${fmt(s.n)}`)))) : null));
  }
  t.append(tb);
  $('#groups').replaceChildren(d.groups.length ? t : el('div', { class: 'empty' }, 'No groups. Domain, script and payload dimensions need fetched raw records.'));
}

// ------------------------------------------------------------------ bursts
async function renderBursts() {
  const fresh = latest('renderBursts');
  const d = await api(`/api/bursts?${qs({ gap: $('#b-gap').value, min: $('#b-min').value, order: $('#b-order').value })}`);
  if (!fresh()) return;
  $('#b-note').textContent = `${fmt(d.count)} bursts across ${fmt(d.reports)} reports. A burst is a run of reports with no gap longer than the threshold.`;
  const t = el('table', { class: 'grid' }, el('thead', {}, el('tr', {},
    ['Start', 'Duration', 'Reports', 'Significant', 'Sources', 'Carriers', 'Distinct programs', ''].map((h) => el('th', {}, h)))));
  const tb = el('tbody');
  for (const b of d.bursts) {
    tb.append(el('tr', { class: 'click', onclick: () => { S.f.from = b.start; setFilter('to', b.end); } },
      el('td', { class: 'mono' }, ts(b.start)), el('td', { class: 'num' }, b.minutes < 90 ? `${b.minutes} min` : `${(b.minutes / 60).toFixed(1)} h`),
      el('td', { class: 'num' }, fmt(b.n)), el('td', { class: 'num' }, fmt(b.significant)),
      el('td', {}, b.sources.map(([s, n]) => el('span', { class: 'pill' }, `${s} ${n}`))),
      el('td', { class: 'url' }, b.carriers.map(([s, n]) => `${s} (${n})`).join(', ') || el('span', { class: 'hint' }, 'not fetched')),
      el('td', { class: 'num' }, b.sigs || '—'),
      el('td', {}, el('button', { class: 'link', onclick: (e) => { e.stopPropagation(); openReport(b.first_id); } }, 'first report'))));
  }
  t.append(tb);
  $('#bursts').replaceChildren(d.bursts.length ? t : el('div', { class: 'empty' }, 'No bursts in this slice.'));
}

// ------------------------------------------------------------------ sites
let cy = null;
async function renderSites() {
  const kinds = [$('#s-payload').checked && 'payload', $('#s-http').checked && 'http'].filter(Boolean);
  if (!kinds.length) return;
  const [d, s] = await Promise.all([
    api(`/api/sites?${qs({ kinds: kinds.join(','), max: $('#s-max').value, minn: $('#s-minn').value, exclude: $('#s-exclude').value, bin: $('#s-bin').value })}`),
    api('/api/summary?' + qs()),
  ]);
  const banner = $('#s-banner');
  if (s.fetched < s.n) {
    banner.className = 'banner on';
    banner.replaceChildren(el('span', {}, `${fmt(s.fetched)} of ${fmt(s.n)} reports in this slice have raw records; the graph only covers those.`),
      el('button', { class: 'ghost', onclick: () => startFetch(Math.min(s.n - s.fetched, 2000)) }, `Fetch up to ${fmt(Math.min(s.n - s.fetched, 2000))}`));
  } else banner.className = 'banner';
  const role = (n) => (n.roles.includes('carrier') && n.roles.length > 1 ? 'both' : n.roles[0]);
  const roleColor = { carrier: css('--s1'), target: css('--s2'), contacted: css('--s3'), both: css('--s7') };
  $('#s-legend').replaceChildren(...Object.entries({ carrier: 'carrier (submitted host)', target: 'payload target', contacted: 'HTTP-contacted', both: 'carrier and target' })
    .map(([k, l]) => el('span', {}, el('span', { class: 'sw', style: `background:${roleColor[k]}` }), ' ', l)),
    el('span', {}, '— payload edge'), el('span', {}, '┄ HTTP edge'), el('span', { class: 'hint' }, `${d.nodes.length} hosts, ${d.edges.length} edges`));
  const maxN = Math.max(1, ...d.nodes.map((n) => n.n));
  const elements = [
    ...d.nodes.map((n) => ({ data: { id: n.id, label: n.id, n: n.n, role: role(n), size: 14 + 46 * Math.sqrt(n.n / maxN), raw: n } })),
    ...d.edges.map((e, i) => ({ data: { id: 'e' + i, source: e.a, target: e.b, kind: e.kind, n: e.n, w: 1 + Math.log2(e.n), raw: e } })),
  ];
  if (cy) cy.destroy();
  cy = cytoscape({
    container: $('#cy'), elements, wheelSensitivity: 0.25,
    style: [
      { selector: 'node', style: { 'background-color': (n) => roleColor[n.data('role')], width: 'data(size)', height: 'data(size)',
        label: 'data(label)', color: css('--text-secondary'), 'font-size': 9, 'text-valign': 'bottom', 'text-margin-y': 3,
        'border-width': 2, 'border-color': css('--surface-1'), 'min-zoomed-font-size': 7 } },
      { selector: 'edge', style: { width: 'data(w)', 'line-color': css('--border'), 'curve-style': 'bezier', 'target-arrow-shape': 'triangle',
        'target-arrow-color': css('--border'), 'arrow-scale': 0.7, opacity: 0.8 } },
      { selector: 'edge[kind = "http"]', style: { 'line-style': 'dashed' } },
      { selector: '.faded', style: { opacity: 0.12 } },
      { selector: 'node:selected', style: { 'border-color': css('--text-primary'), 'border-width': 3 } },
    ],
    layout: { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 90, numIter: 1500, randomize: true },
  });
  cy.on('tap', 'node', (ev) => {
    const n = ev.target; const raw = n.data('raw');
    cy.elements().addClass('faded'); n.closedNeighborhood().removeClass('faded');
    const out = n.connectedEdges().map((e) => e.data('raw')).sort((a, b) => b.n - a.n);
    $('#site-info').replaceChildren(el('h4', {}, raw.id), el('div', { class: 'hint' }, `${raw.roles.join(', ')} · ${fmt(raw.n)} report-edges`),
      el('div', { class: 'mono hint' }, `${ts(raw.first)} → ${ts(raw.last)}`),
      el('div', { class: 'btns' },
        raw.roles.includes('carrier') ? el('button', { class: 'ghost', onclick: () => toggleFilter('submitted_fqdn', raw.id) }, 'slice: submitted here') : null,
        raw.roles.includes('target') || raw.roles.includes('both') ? el('button', { class: 'ghost', onclick: () => toggleFilter('target', raw.id) }, 'slice: payload targets') : null,
        el('button', { class: 'ghost', onclick: () => setFilter('host', raw.id) }, 'slice: any contact')),
      el('table', { class: 'grid' }, el('tbody', {}, out.map((e) => el('tr', {},
        el('td', { class: 'url' }, e.a === raw.id ? `→ ${e.b}` : `← ${e.a}`), el('td', {}, e.kind), el('td', { class: 'num' }, fmt(e.n)))))));
  });
  cy.on('tap', (ev) => { if (ev.target === cy) cy.elements().removeClass('faded'); });
  // heatmap
  const hm = chart('heat-chart');
  const hmax = Math.max(1, ...d.heat.cells.map((c) => c[2]));
  hm.setOption({
    animation: false,
    grid: { left: 230, right: 90, top: 10, bottom: 60 },
    tooltip: { ...tooltipStyle(), formatter: (p) => `${escapeText(p.value[1])}<br>${escapeText(p.value[0])}: <b>${fmt(p.value[2])}</b> reports` },
    xAxis: { type: 'category', data: d.heat.bins, ...axisStyle(), splitLine: { show: false } },
    yAxis: { type: 'category', data: d.heat.hosts, inverse: true, ...axisStyle(), splitLine: { show: false }, axisLabel: { color: css('--text-secondary'), fontSize: 10, width: 210, overflow: 'truncate' } },
    visualMap: { min: 0, max: hmax, calculable: true, right: 10, top: 10, itemHeight: 160, inRange: { color: [css('--seq-lo'), css('--seq-hi')] }, textStyle: { color: css('--text-muted') } },
    dataZoom: [{ type: 'slider', xAxisIndex: 0, height: 18, bottom: 10, ...zoomStart(d.heat.bins) }],
    series: [{ type: 'heatmap', data: d.heat.cells, itemStyle: { borderColor: css('--surface-1'), borderWidth: 1 } }],
  }, true);
  hm.off('click');
  hm.on('click', (p) => { const [a, b] = binRange(p.value[0], $('#s-bin').value); S.f.from = a; S.f.to = b; setFilter('host', p.value[1]); });
}

// ------------------------------------------------------------------ table
async function renderTable() {
  const fresh = latest('renderTable');
  const d = await api(`/api/rows?${qs({ limit: S.pageSize, offset: S.offset, sort: $('#t-sort').value })}`);
  if (!fresh()) return;
  $('#t-count').textContent = `${fmt(d.total)} reports`;
  $('#t-page').textContent = `${fmt(S.offset + 1)}–${fmt(Math.min(S.offset + S.pageSize, d.total))}`;
  $('#t-prev').disabled = S.offset === 0; $('#t-next').disabled = S.offset + S.pageSize >= d.total;
  const all = el('input', { type: 'checkbox', onclick: (e) => { d.rows.forEach((r) => (e.target.checked ? S.selected.add(r.report_id) : S.selected.delete(r.report_id))); renderTable(); } });
  const t = $('#rows'); t.replaceChildren(el('thead', {}, el('tr', {}, el('th', {}, all),
    ['Time (UTC)', 'Source', 'Class', 'Conf.', 'Submitted URL / title', 'HTTP', 'JS', 'Payload', 'Why included'].map((h) => el('th', {}, h)))));
  const tb = el('tbody');
  for (const r of d.rows) {
    const cb = el('input', { type: 'checkbox', onclick: (e) => { e.stopPropagation(); e.target.checked ? S.selected.add(r.report_id) : S.selected.delete(r.report_id); updateSel(); } });
    cb.checked = S.selected.has(r.report_id);
    tb.append(el('tr', { class: 'click', onclick: () => openReport(r.report_id) },
      el('td', { onclick: (e) => e.stopPropagation() }, cb),
      el('td', { class: 'mono', style: 'white-space:nowrap' }, ts(r.ts)),
      el('td', {}, r.source), el('td', {}, el('span', { class: 'pill' }, r.broad_class)),
      el('td', {}, r.confidence ? el('span', { class: 'pill' + (r.confidence === 'significant' ? ' sig' : '') }, r.confidence) : el('span', { class: 'hint' }, r.disposition)),
      el('td', { class: 'url' }, short(r.submitted_url, 220) || el('span', { class: 'hint' }, r.fetch_error ? `fetch error: ${r.fetch_error}` : 'raw not fetched — open to fetch'),
        r.title && !(r.submitted_url || '').includes(r.title.slice(0, 30)) ? el('div', { class: 'hint' }, short(r.title, 90)) : null),
      el('td', { class: 'num' }, r.n_http ?? ''), el('td', { class: 'num' }, r.fetched ? (r.n_scripts || 0) + (r.n_eval || 0) : ''),
      el('td', {}, r.payload_kinds ? el('span', { class: 'pill' }, r.payload_kinds.split(',')[0]) : '', r.n_targets ? el('span', { class: 'hint' }, ` →${r.n_targets}`) : ''),
      el('td', { class: 'why' }, short(r.why_included, 110))));
  }
  t.append(tb); updateSel();
}
function updateSel() {
  $('#t-add').disabled = !S.selected.size || !$('#annot-target').value;
  $('#t-add').textContent = S.selected.size ? `Add ${S.selected.size} selected to finding` : 'Add selected to finding';
}
$('#t-prev').onclick = () => { S.offset = Math.max(0, S.offset - S.pageSize); renderTable(); };
$('#t-next').onclick = () => { S.offset += S.pageSize; renderTable(); };
$('#t-add').onclick = () => addEvidence([...S.selected]);
$('#t-fetch').onclick = async () => {
  const s = await api('/api/summary?' + qs());
  const missing = s.n - s.fetched;
  if (!missing) return toast('Everything in this slice is already fetched');
  const n = prompt(`Fetch raw urlquery JSON for how many of the ${missing} unfetched reports in this slice? (~5/s)`, String(Math.min(missing, 1000)));
  if (n) startFetch(parseInt(n, 10));
};
async function startFetch(limit) {
  await post('/api/fetch', { filters: S.f, limit, workers: 4 });
  toast(`Fetching ${limit} records…`); pollFetch();
}
async function pollFetch() {
  const jobs = await api('/api/fetch/status');
  const running = jobs.filter((j) => j.running);
  const box = $('#fetch-status');
  if (running.length) {
    const j = running[running.length - 1];
    box.replaceChildren(`fetching ${fmt(j.done)}/${fmt(j.total)} · ${j.rate}/s${j.errors ? ` · ${j.errors} errors` : ''} `,
      el('button', { class: 'link', onclick: () => post('/api/fetch/cancel', {}) }, 'stop'));
    setTimeout(pollFetch, 2500);
    if (j.done % 50 < 12) refreshLight();
  } else {
    if (box.textContent) { box.textContent = ''; refresh(); }
  }
}

// ------------------------------------------------------------------ report drawer
const D = { rid: null, data: null, tab: 'overview' };
async function openReport(rid, fetchIt = true) {
  D.rid = rid; D.tab = D.tab || 'overview';
  $('#drawer').hidden = false;
  $('#d-title').replaceChildren(el('div', { class: 'rid' }, rid), el('div', { class: 'hint' }, 'loading…'));
  $('#d-body').replaceChildren();
  try {
    D.data = await api(`/api/report/${rid}?fetch=${fetchIt ? 1 : 0}`);
  } catch (e) {
    D.data = await api(`/api/report/${rid}?fetch=0`);
    toast(`Raw fetch failed: ${e.message}`);
  }
  renderDrawer();
}
function renderDrawer() {
  const { catalog: c, raw } = D.data;
  $('#d-title').replaceChildren(
    el('div', { class: 'rid' }, c.report_id, ' · ', el('a', { href: c.url, target: '_blank', rel: 'noopener noreferrer' }, 'open on urlquery ↗')),
    el('div', {}, el('b', {}, ts(c.ts)), '  ', el('span', { class: 'pill' }, c.source), ' ', el('span', { class: 'pill' }, c.broad_class), ' ',
      c.confidence ? el('span', { class: 'pill' + (c.confidence === 'significant' ? ' sig' : '') }, c.confidence) : el('span', { class: 'pill' }, c.disposition)),
    raw ? el('div', { class: 'sub' }, raw.submitted) : null);
  const target = $('#annot-target').value;
  const f = S.golden.findings.find((x) => x.id === target);
  $('#d-actions').replaceChildren(
    f ? el('button', { onclick: () => addEvidence([c.report_id]) }, `Add to ${f.id}`) : el('span', { class: 'hint' }, 'Pick a finding in the header to annotate.'),
    el('button', { class: 'ghost', onclick: () => quickFinding(c.report_id) }, 'New finding from this report'),
    ...D.data.findings.map((x) => el('span', { class: 'pill sig', title: x.claim }, `evidence for ${x.id}`)),
    el('span', { style: 'flex:1' }),
    el('button', { class: 'ghost', onclick: () => navReport(-1) }, '‹ prev'), el('button', { class: 'ghost', onclick: () => navReport(1) }, 'next ›'));
  $$('#d-tabs button').forEach((b) => b.classList.toggle('on', b.dataset.dt === D.tab));
  const body = $('#d-body'); body.replaceChildren();
  if (!raw && D.tab !== 'overview' && D.tab !== 'graph') {
    body.append(el('div', { class: 'empty' }, 'Raw record not fetched. ', el('button', { onclick: () => openReport(D.rid, true) }, 'Fetch from urlquery')));
    return;
  }
  ({ overview: dOverview, payload: dPayload, http: dHttp, js: dJs, graph: dGraph, json: dJson })[D.tab](body);
}
async function navReport(step) {
  const d = await api(`/api/rows?${qs({ limit: 5000, sort: $('#t-sort').value })}`);
  const i = d.rows.findIndex((r) => r.report_id === D.rid);
  const n = d.rows[i + step]; if (n) openReport(n.report_id);
}
$$('#d-tabs button').forEach((b) => (b.onclick = () => { D.tab = b.dataset.dt; renderDrawer(); }));
$('#d-close').onclick = () => { $('#drawer').hidden = true; };
document.addEventListener('keydown', (e) => {
  if ($('#drawer').hidden || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
  if (e.key === 'Escape') $('#drawer').hidden = true;
  if (e.key === 'j') navReport(1);
  if (e.key === 'k') navReport(-1);
  if (e.key === 'a' && $('#annot-target').value) addEvidence([D.rid]);
});

function kv(pairs) {
  return el('dl', { class: 'kv' }, pairs.filter(([, v]) => v != null && v !== '').flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
}
function dOverview(body) {
  const { catalog: c, raw } = D.data;
  body.append(el('h3', { class: 'sub' }, 'Transluce catalogue'), kv([
    ['Disposition', c.disposition], ['Confidence', c.confidence], ['Method class', c.broad_class], ['Data source', c.source],
    ['Source basis', c.source_basis], ['Matched sources', c.matched_sources], ['Why included', c.why_included], ['Caveat', c.caveat],
  ]));
  if (!raw) {
    body.append(el('div', { class: 'empty' }, 'Raw record not cached. ', el('button', { onclick: () => openReport(D.rid, true) }, 'Fetch from urlquery')));
    return;
  }
  const hosts = {};
  raw.http.forEach((h) => (hosts[h.fqdn] = (hosts[h.fqdn] || 0) + 1));
  body.append(el('h3', { class: 'sub' }, 'urlquery record'), kv([
    ['Submitted', el('span', { class: 'mono' }, raw.submitted)], ['Final URL', el('span', { class: 'mono' }, raw.final)], ['Page title', raw.title],
    ['Scan IP', raw.ip && `${raw.ip.addr} · ${raw.ip.as} · ${raw.ip.country_code}`], ['User agent', raw.settings?.useragent],
    ['Access', raw.settings?.access], ['Expires', raw.settings?.expires_at], ['Tags', (raw.tags || []).map((t) => (typeof t === 'string' ? t : JSON.stringify(t))).join(', ')],
    ['urlquery alerts', (raw.urlquery_alerts || []).filter((a) => a.alert).map((a) => `${a.alert} (${a.verdict}, ${a.severity})`).join('; ')],
    ['HTTP transactions', raw.http.length], ['Scripts', raw.scripts.length],
    ['Decoded layers', raw.payload.nodes.length ? `${raw.payload.nodes.length} (${raw.payload.kinds.join(', ')})` : 'none'],
    ['Payload targets', raw.payload.targets.length ? el('span', {}, raw.payload.targets.map((t) => el('button', { class: 'link mono', style: 'margin-right:10px', onclick: () => toggleFilter('target', t) }, t))) : null],
    ['Program signature', raw.payload.sig && el('button', { class: 'link mono', onclick: () => toggleFilter('payload_sig', raw.payload.sig) }, `${raw.payload.sig} (slice to same program)`)],
  ]));
  body.append(el('h3', { class: 'sub' }, 'Hosts contacted'), el('div', { class: 'subs' }, Object.entries(hosts).sort((a, b) => b[1] - a[1])
    .map(([h, n]) => el('span', { class: 'pill', title: 'slice to reports contacting this host', onclick: () => toggleFilter('contacted', h) }, `${h} ${n}`))));
  if (raw.console && raw.console.length) body.append(el('h3', { class: 'sub' }, 'Console'), el('pre', { class: 'code' }, JSON.stringify(raw.console, null, 2).slice(0, 20000)));
}
function codeBlock(text, lang) {
  const code = el('code', { class: lang ? `language-${lang}` : '' });
  code.textContent = text;
  if (window.hljs && text.length < 150000) { try { hljs.highlightElement(code); } catch { /* plain */ } }
  return el('pre', { class: 'code' }, code);
}
function prettyJs(text) {
  if (text.length > 60000 || text.split('\n').length > 5) return text;
  // light reflow for one-line programs: break after ; { } so the logic is readable
  return text.replace(/;\s*/g, ';\n').replace(/\{\s*/g, '{\n').replace(/\}\s*/g, '}\n');
}
function dPayload(body) {
  const p = D.data.raw.payload;
  if (!p.nodes.length) { body.append(el('div', { class: 'empty' }, 'The submitted URL carries no decodable payload (no base64 path, data: URL, base64 query value or nested URL).')); return; }
  body.append(el('p', { class: 'hint' }, 'Layers unwrapped from the submitted URL. Nothing here is executed; it is decoded text. Indentation shows nesting.'));
  for (const n of p.nodes) {
    const lang = { html: 'xml', js: 'javascript', json: 'json' }[n.ctype];
    const text = n.ctype === 'js' ? prettyJs(n.text) : n.text;
    body.append(el('div', { class: 'pnode', style: `margin-left:${n.depth * 18}px` },
      el('div', { class: 'ph' }, el('span', { class: 'pill sig' }, n.kind), el('span', { class: 'mono hint' }, n.via), el('span', { class: 'pill' }, n.ctype), el('span', { class: 'hint' }, `${fmt(n.size)} chars`)),
      n.ctype === 'url' ? null : codeBlock(text, lang),
      n.urls.length ? el('ul', { class: 'urls' }, n.urls.map((u) => el('li', {}, el('span', {}, u)))) : null));
  }
}
function dHttp(body) {
  const hs = D.data.raw.http;
  const t0 = Math.min(...hs.map((h) => h.ts || Infinity)); const t1 = Math.max(...hs.map((h) => h.ts || 0));
  const span = Math.max(1, t1 - t0);
  const t = el('table', { class: 'grid' }, el('thead', {}, el('tr', {}, ['#', '+ms', 'Method', 'Status', 'Host', 'Path', 'Type', 'Size', 'Timeline'].map((x) => el('th', {}, x)))));
  const tb = el('tbody');
  hs.forEach((h, i) => {
    let path = h.url; try { const u = new URL(h.url); path = u.pathname + u.search; } catch { /* keep */ }
    const row = el('tr', { class: 'click' },
      el('td', { class: 'num' }, i + 1), el('td', { class: 'num' }, h.ts ? fmt(h.ts - t0) : ''), el('td', {}, h.method),
      el('td', {}, h.status ? el('span', { class: 'pill' + (h.status >= 400 ? ' crit' : h.status >= 300 ? ' warn' : '') }, h.status) : ''),
      el('td', { class: 'mono' }, h.fqdn), el('td', { class: 'url' }, short(path, 160)), el('td', {}, h.type || ''), el('td', { class: 'num' }, fmt(h.size)),
      el('td', {}, el('div', { class: 'wf' }, el('i', { style: `left:${(100 * ((h.ts || t0) - t0)) / span}%;width:3px` }))));
    row.onclick = () => {
      if (row.nextSibling && row.nextSibling.classList.contains('expand')) return row.nextSibling.remove();
      row.after(el('tr', { class: 'expand' }, el('td', { colspan: 9 },
        kv([['URL', el('span', { class: 'mono' }, h.url)], ['IP', `${h.ip || ''} ${h.asn || ''} ${h.country || ''}`], ['Mime', h.mime], ['Body sha256', h.sha256], ['Seen on urlquery', h.times_seen && `${fmt(h.times_seen)}×`]]),
        el('h4', {}, 'Request'), codeBlock(h.req_raw || '(empty)', 'http'), el('h4', {}, 'Response headers'), codeBlock(h.resp_raw || '(empty)', 'http'))));
    };
    tb.append(row);
  });
  t.append(tb); body.append(t);
}
function dJs(body) {
  const ss = D.data.raw.scripts;
  if (!ss.length) body.append(el('div', { class: 'empty' }, 'urlquery recorded no scripts. Check “Decoded payload” for programs carried in the URL.'));
  for (const s of ss) {
    const box = el('div');
    const load = async () => {
      box.replaceChildren(el('span', { class: 'hint' }, 'loading source from urlquery…'));
      try {
        const text = s.data || await api(`/api/js?report=${D.rid}&md5=${s.md5}&section=${s.section}`);
        box.replaceChildren(codeBlock(text.length < 60000 ? prettyJs(text) : text, 'javascript'));
      } catch (e) { box.replaceChildren(el('span', { class: 'hint' }, `failed: ${e.message}`)); }
    };
    body.append(el('div', { class: 'card' },
      el('div', { class: 'row' }, el('span', { class: 'pill sig' }, s.section), el('span', { class: 'pill' }, s.intro || ''), s.inline ? el('span', { class: 'pill' }, 'inline') : null,
        el('span', { class: 'hint' }, `${fmt(s.size)} B · seen ${fmt(s.times_seen)}× on urlquery since ${(s.first_seen || '').slice(0, 10)}`),
        el('span', { style: 'flex:1' }), el('button', { class: 'ghost', onclick: load }, 'show source'),
        el('button', { class: 'ghost', onclick: () => setFilter('script', s.md5) }, 'reports with this script')),
      s.url ? el('div', { class: 'url mono' }, s.url) : null, el('div', { class: 'mono hint' }, `md5 ${s.md5}`), box));
    if (s.times_seen < 50 && s.size < 20000) load();
  }
}
function dGraph(body) {
  body.append(el('p', { class: 'hint' }, 'urlquery’s Graphviz rendering of the domains this scan contacted (fetched once, then cached).'),
    el('img', { class: 'graph-img', src: `/api/report/${D.rid}/graph.gif`, alt: 'urlquery domain graph', onerror: (e) => e.target.replaceWith(el('div', { class: 'empty' }, 'Domain graph unavailable (report expired or urlquery unreachable).')) }));
}
function dJson(body) {
  const txt = JSON.stringify(D.data.full || D.data.raw, null, 2);
  body.append(el('p', { class: 'hint' }, `${fmt(txt.length)} chars${txt.length > 400000 ? ', showing first 400k' : ''}`), el('pre', { class: 'code nowrap' }, txt.slice(0, 400000)));
}

// ------------------------------------------------------------------ golden findings
async function loadGolden() {
  S.golden = await api('/api/golden');
  const sel = $('#annot-target'); const cur = sel.value || localStorage.getItem('annot') || '';
  sel.replaceChildren(el('option', { value: '' }, '— pick a finding —'));
  for (const inc of S.golden.incidents) {
    const g = el('optgroup', { label: `${inc.key} · ${inc.name || ''}` });
    S.golden.findings.filter((f) => f.incident_id === inc.id).forEach((f) => g.append(el('option', { value: f.id }, `${f.id} — ${short(f.claim || '(no claim yet)', 60)}`)));
    sel.append(g);
  }
  sel.value = S.golden.findings.some((f) => f.id === cur) ? cur : '';
  updateSel();
}
$('#annot-target').onchange = (e) => { try { localStorage.setItem('annot', e.target.value); } catch { /* ok */ } updateSel(); if (!$('#drawer').hidden && D.data) renderDrawer(); };
async function addEvidence(ids) {
  const fid = $('#annot-target').value;
  if (!fid) return toast('Pick a finding in the header first');
  S.golden = await post('/api/golden/finding', { id: fid, add_evidence: ids });
  toast(`Added ${ids.length} report${ids.length > 1 ? 's' : ''} to ${fid}`);
  await loadGolden();
  if (!$('#drawer').hidden && D.rid) { D.data.findings = (await api(`/api/report/${D.rid}?fetch=0`)).findings; renderDrawer(); }
  if (S.tab === 'findings') renderFindings();
}
async function quickFinding(rid) {
  let inc = S.incident && S.golden.incidents.find((i) => i.id === S.incident);
  if (!inc && S.golden.incidents.length === 1) inc = S.golden.incidents[0];
  if (!inc) { toast('Select or create an incident in the Golden findings tab first'); return switchTab('findings'); }
  const claim = prompt(`New finding for ${inc.key} (${inc.name}). Claim:`);
  if (!claim) return;
  const g = await post('/api/golden/finding', { incident_id: inc.id, claim, add_evidence: [rid] });
  const f = g.findings[g.findings.length - 1];
  await loadGolden(); $('#annot-target').value = f.id; updateSel();
  toast(`Created ${f.id}`); renderDrawer();
}
function incidentForm(inc) {
  const f = { name: el('input', { value: inc?.name || '', placeholder: 'e.g. AIHW dashboard escalation' }), key: el('input', { value: inc?.key || '', placeholder: 'AIHW', maxlength: 6 }),
    start: el('input', { type: 'date', value: inc?.start || '' }), end: el('input', { type: 'date', value: inc?.end || '' }),
    description: el('textarea', { rows: 3, placeholder: 'What this incident is, in one paragraph' }), status: el('select', {}, ['draft', 'reviewed', 'final'].map((s) => el('option', {}, s))) };
  f.description.value = inc?.description || ''; f.status.value = inc?.status || 'draft';
  const save = async () => {
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.value]));
    if (!body.name) return toast('Name required');
    if (S.f.from && !body.start) body.start = S.f.from.slice(0, 10);
    if (S.f.to && !body.end) body.end = S.f.to.slice(0, 10);
    const g = await post('/api/golden/incident', { ...(inc ? { id: inc.id } : {}), ...body });
    S.incident = inc ? inc.id : g.incidents[g.incidents.length - 1].id;
    await loadGolden(); renderFindings(); toast('Saved');
  };
  return el('div', { class: 'card' }, el('div', { class: 'form-grid' },
    el('label', {}, 'Name'), f.name, el('label', {}, 'Key (ID prefix)'), f.key, el('label', {}, 'Start'), f.start, el('label', {}, 'End'), f.end,
    el('label', {}, 'Status'), f.status, el('label', {}, 'Description'), f.description),
  el('div', { class: 'row', style: 'margin-top:8px' }, el('button', { onclick: save }, inc ? 'Save incident' : 'Create incident'),
    !inc && (S.f.from || S.f.to) ? el('span', { class: 'hint' }, 'Empty dates default to the current time slice.') : null));
}
$('#inc-new').onclick = () => { S.incident = null; $('#find-col').replaceChildren(el('h3', {}, 'New incident'), incidentForm(null)); };

function renderFindings() {
  const list = $('#inc-list'); list.replaceChildren();
  for (const inc of S.golden.incidents) {
    const fs = S.golden.findings.filter((f) => f.incident_id === inc.id);
    const ev = new Set(fs.flatMap((f) => f.evidence.map((e) => e.report_id)));
    list.append(el('div', { class: 'inc' + (S.incident === inc.id ? ' on' : ''), onclick: () => { S.incident = inc.id; renderFindings(); } },
      el('div', {}, el('b', {}, inc.name || '(unnamed)')), el('div', { class: 'k' }, `${inc.key} · ${inc.status || 'draft'} · ${fs.length} findings · ${ev.size} reports`),
      inc.start ? el('div', { class: 'hint' }, `${inc.start} → ${inc.end || '…'}`) : null));
  }
  if (!S.golden.incidents.length) list.append(el('p', { class: 'hint' }, 'No incidents yet.'));
  const inc = S.golden.incidents.find((i) => i.id === S.incident);
  if (!inc) return;
  const col = $('#find-col');
  const fs = S.golden.findings.filter((f) => f.incident_id === inc.id);
  col.replaceChildren(...[
    el('div', { class: 'row', style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' },
      el('h3', { style: 'margin:0' }, `${inc.key} · ${inc.name}`), el('span', { style: 'flex:1' }),
      el('button', { class: 'ghost', onclick: () => { setFilter('incident', inc.id); switchTab('table'); } }, 'Show evidence reports'),
      inc.start ? el('button', { class: 'ghost', onclick: () => { S.f.from = inc.start + 'T00:00:00Z'; setFilter('to', (inc.end || inc.start) + 'T23:59:59Z'); switchTab('timeline'); } }, 'Slice to incident window') : null,
      el('button', { class: 'ghost', onclick: () => exportInc(inc, false) }, 'Download answer key'),
      el('button', { class: 'ghost', onclick: () => exportInc(inc, true) }, 'Write eval corpus'),
      el('button', { class: 'ghost', onclick: async () => { if (confirm(`Delete incident ${inc.key} and its ${fs.length} findings?`)) { await post('/api/golden/delete_incident', { id: inc.id }); S.incident = null; await loadGolden(); renderFindings(); $('#find-col').replaceChildren(); } } }, 'Delete')),
    el('details', {}, el('summary', { class: 'hint' }, 'Edit incident'), incidentForm(inc)),
    inc.description ? el('p', { class: 'hint' }, inc.description) : null,
    ...fs.map(findingCard),
    el('button', { onclick: async () => { const g = await post('/api/golden/finding', { incident_id: inc.id, claim: '' }); await loadGolden(); $('#annot-target').value = g.findings[g.findings.length - 1].id; updateSel(); renderFindings(); } }, '+ Add finding')].filter(Boolean));
}
function findingCard(f) {
  const save = debounce(async (patch) => { S.golden = await post('/api/golden/finding', { id: f.id, ...patch }); loadGolden(); }, 400);
  const claim = el('textarea', { rows: 2, placeholder: 'The claim a good investigation report should make', oninput: (e) => save({ claim: e.target.value }) }); claim.value = f.claim;
  const note = el('textarea', { rows: 2, placeholder: 'Grading note: what earns full vs partial credit', oninput: (e) => save({ note: e.target.value }) }); note.value = f.note;
  const section = el('input', { value: f.section, placeholder: 'Section (Nature, Mechanism, Timeline…)', oninput: (e) => save({ section: e.target.value }), style: 'width:220px' });
  const mode = el('select', { onchange: (e) => save({ grading_mode: e.target.value }) }, ['recall_accuracy', 'recall_calibrated', 'holistic'].map((m) => el('option', {}, m))); mode.value = f.grading_mode;
  const conf = el('select', { onchange: (e) => save({ confidence: e.target.value }) }, ['low', 'medium', 'high'].map((m) => el('option', {}, m))); conf.value = f.confidence;
  const active = $('#annot-target').value === f.id;
  return el('div', { class: 'card', style: active ? `border-color:${css('--accent')}` : '' },
    el('div', { class: 'row' }, el('span', { class: 'fid' }, f.id), section, mode, el('label', { class: 'hint' }, 'confidence ', conf), el('span', { style: 'flex:1' }),
      el('button', { class: active ? '' : 'ghost', onclick: () => { $('#annot-target').value = f.id; localStorage.setItem('annot', f.id); updateSel(); renderFindings(); } }, active ? 'annotating' : 'annotate'),
      el('button', { class: 'ghost', onclick: () => { setFilter('finding', f.id); switchTab('table'); } }, `evidence (${f.evidence.length})`),
      el('button', { class: 'ghost', onclick: async () => { if (confirm(`Delete ${f.id}?`)) { await post('/api/golden/delete_finding', { id: f.id }); await loadGolden(); renderFindings(); } } }, '✕')),
    claim, note,
    f.evidence.map((e) => {
      const n = el('input', { value: e.note || '', placeholder: 'why this report supports the claim', oninput: (ev) => save({ evidence_notes: { [e.report_id]: ev.target.value } }) });
      return el('div', { class: 'ev' }, el('button', { class: 'link mono', onclick: () => openReport(e.report_id) }, e.report_id.slice(0, 8)),
        el('span', { class: 'hint mono' }, (e.added || '').slice(0, 16).replace('T', ' ')), n,
        el('button', { class: 'link', onclick: async () => { await post('/api/golden/finding', { id: f.id, remove_evidence: [e.report_id] }); await loadGolden(); renderFindings(); } }, 'remove'));
    }));
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
async function exportInc(inc, write) {
  if (write && !confirm(`Write answer_key.jsonl and ids.txt to report-eval-harness/corpora/<slug>/? Existing files there are overwritten.`)) return;
  const out = write ? await post('/api/golden/write_corpus', { id: inc.id }) : await api(`/api/golden/export/${inc.id}`);
  if (write) return toast(`Wrote ${out.written}`);
  const a = el('a', { href: URL.createObjectURL(new Blob([out.answer_key], { type: 'application/jsonl' })), download: `${out.slug}.answer_key.jsonl` });
  a.click();
}

// ------------------------------------------------------------------ wiring
function switchTab(tab) {
  S.tab = tab;
  $$('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === tab));
  $$('.tab').forEach((t) => t.classList.toggle('on', t.id === 'tab-' + tab));
  renderTab();
}
$$('#tabs button').forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
function renderTab() {
  const fn = { timeline: renderTimeline, groups: renderGroups, bursts: renderBursts, sites: renderSites, table: renderTable, findings: renderFindings }[S.tab];
  Promise.resolve(fn()).then(() => Object.values(charts).forEach((c) => c.resize())).catch((e) => toast(e.message));
}
function refresh() { renderChips(); renderSidebar().catch((e) => toast(e.message)); renderTab(); }
const refreshLight = debounce(() => { renderSidebar(); if (S.tab === 'table') renderTable(); }, 1000);

for (const sel of $$('.dim-select')) for (const [k, l] of DIMS) sel.append(el('option', { value: k }, l));
$('#ts-stack').value = 'confidence'; $('#g-by').value = 'source';
['#ts-bin', '#ts-stack'].forEach((s) => ($(s).onchange = renderTimeline));
['#g-by', '#g-by2'].forEach((s) => ($(s).onchange = renderGroups));
['#b-gap', '#b-min', '#b-order'].forEach((s) => ($(s).onchange = renderBursts));
['#s-payload', '#s-http', '#s-max', '#s-minn', '#s-exclude', '#s-bin'].forEach((s) => ($(s).onchange = renderSites));
$('#t-sort').onchange = () => { S.offset = 0; renderTable(); };
$('#q').value = S.f.q || '';
$('#q').addEventListener('input', debounce((e) => setFilter('q', e.target.value.trim()), 350));

loadGolden().then(() => { refresh(); pollFetch(); });
