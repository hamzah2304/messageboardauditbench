#!/usr/bin/env python3
"""Build viewers/performance.html — model recall from the GPT-5.6 Sol grading.

Two views of the same 76 round-3 reports. A ranked bar chart at the 2-hour budget,
where every replicate is drawn as a dot so the reader sees the spread rather than a
mean that hides it; and small multiples, one panel per harness/model pair, showing
recall against wall-clock budget. Fourteen pairs is far past the point where colour
can carry identity, so identity comes from the panel, and colour carries magnitude
only: one hue, plus grey for the reference.

Runs from grades in benchmark/graded/graded_r3b*.json. Self-contained: inline SVG,
no libraries.
"""
import json, re, statistics as st, sys, pathlib
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import GRADED, VIEWERS

OUT = VIEWERS / "performance.html"
NAMES = {"gpt_5_6_sol": "GPT-5.6 Sol", "openai_gpt_5_6_sol": "GPT-5.6 Sol",
         "gpt_5_6_luna": "GPT-5.6 Luna", "gpt_5_6_terra": "GPT-5.6 Terra",
         "gpt_6_astra": "GPT-6 Astra", "google_gemini_3_8_flash": "Gemini 3.8 Flash",
         "meta_muse_spark_1_3": "Muse Spark 1.3", "moonshotai_kimi_k3": "Kimi K3",
         "z_ai_glm_5_3": "GLM 5.3", "claude_opus_5": "Opus 5", "claude_opus_4_8": "Opus 4.8",
         "claude_sonnet_5": "Sonnet 5", "claude_haiku_4_5": "Haiku 4.5",
         "claude_fable_5_1": "Fable 5.1"}
RX = re.compile(r"graded_(r3b(\d+))_(claude|codex|react)_(.+?)_rep(\d)(?:_served_(.+))?\.json$")
BUDGETS = [10, 30, 120]


def load():
    rows, grader = [], None
    for p in sorted(GRADED.glob("graded_r3b*.json")):
        m = RX.search(p.name)
        d = json.loads(p.read_text())
        grader = grader or d.get("grader")
        rows.append({"budget": int(m.group(2)), "agent": m.group(3),
                     "model": NAMES.get(m.group(4), m.group(4)), "rep": int(m.group(5)),
                     "served": NAMES.get(m.group(6)) if m.group(6) else None,
                     "acc": d["accuracy"]})
    return rows, grader


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    rows, grader = load()
    nominal = [r for r in rows if not r["served"]]
    cells = defaultdict(list)
    for r in nominal:
        cells[(f"{r['agent']} · {r['model']}", r["budget"])].append(r["acc"])
    pairs = sorted({k[0] for k in cells})
    data = {
        "grader": grader, "n_reports": len(rows), "n_nominal": len(nominal),
        "pairs": pairs,
        "cells": {f"{k[0]}|{k[1]}": sorted(v) for k, v in cells.items()},
        "switched": [{"nominal": f"{r['agent']} · {r['model']}", "served": r["served"],
                      "budget": r["budget"], "acc": r["acc"]} for r in rows if r["served"]],
    }
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    best = max(st.mean(v) for k, v in cells.items() if k[1] == 120)
    print(f"{OUT}: {len(rows)} reports, {len(pairs)} harness/model pairs, judge {grader}; "
          f"best at 120 min {best:.3f}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Model recall — MessageBoardAuditBench</title>
<style>
:root{
  --paper:#F4F3EE; --surface:#FFFFFF; --line:#E0DDD4; --ink:#1A1A1A; --ink2:#666666; --ink3:#999999;
  --accent:#C15F3C; --accent-soft:#FDF2EC; --grey:#C9C6BC; --grid:#EAE7DF;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 32px 72px}
h1{color:var(--accent);font-size:24px;margin:0 0 2px}
h2{font-size:16px;margin:34px 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 6px}
.note{color:var(--ink3);font-size:12px;margin:2px 0 14px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 4px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:150px}
.kpi .v{font-size:28px;font-weight:600;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.kpi .l{font-size:12px;color:var(--ink2);margin-top:1px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:10px 0}
svg{display:block;max-width:100%;overflow:visible}
text{font-family:inherit}
.axis{fill:var(--ink2);font-size:11px}
.tick{stroke:var(--grid);stroke-width:1}
.axline{stroke:var(--line);stroke-width:1}
.lab{fill:var(--ink);font-size:12px}
.val{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}
.small{fill:var(--ink3);font-size:10.5px}
.panels{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:10px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:9px 10px 6px}
.panel h3{margin:0;font-size:12.5px;font-weight:600}
.panel .m{font-size:11px;color:var(--ink3);margin-bottom:2px}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
th{color:var(--ink2);font-weight:600}
details{margin-top:12px}
summary{cursor:pointer;color:var(--accent);font-size:13px;font-weight:600}
#tip{position:fixed;pointer-events:none;background:#2B2622;color:#F6F1EA;padding:6px 9px;border-radius:6px;
  font-size:12px;line-height:1.4;opacity:0;transition:opacity .08s;z-index:9;white-space:nowrap}
.hit{fill:transparent;cursor:pointer}
</style></head><body>
<main>
  <h1>Model recall</h1>
  <p class="sub" id="sub"></p>
  <div class="kpis" id="kpis"></div>

  <h2>At the two-hour budget</h2>
  <p class="note">Each replicate is a dot; the bar is their mean. Four pairs have no two-hour run and are left out.</p>
  <div class="card" id="bars"></div>

  <h2>Recall against time budget</h2>
  <p class="note">One panel per harness and model, same scale throughout. A hollow marker is a single replicate.</p>
  <div class="panels" id="panels"></div>

  <details>
    <summary>The numbers</summary>
    <div class="card" id="table"></div>
  </details>
</main>
<div id="tip"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const BUD = [10, 30, 120], NS = 'http://www.w3.org/2000/svg';
const cell = (p, b) => D.cells[p + '|' + b] || null;
const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
const fmt = v => v.toFixed(3);

document.getElementById('sub').textContent =
  `${D.n_reports} round-3 reports, ${D.pairs.length} harness and model pairs, graded by ${D.grader}.`;

/* ---------- headline numbers ---------- */
(function () {
  const at120 = D.pairs.map(p => [p, cell(p, 120)]).filter(x => x[1]);
  const best = at120.map(([p, v]) => [mean(v), p]).sort((a, b) => b[0] - a[0])[0];
  const all = D.pairs.flatMap(p => BUD.flatMap(b => cell(p, b) || []));
  const sds = D.pairs.flatMap(p => BUD.map(b => cell(p, b)).filter(v => v && v.length > 1)
    .map(v => { const m = mean(v); return Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / (v.length - 1)); }));
  const k = [[fmt(best[0]), best[1] + ' at 2 h'],
             [fmt(mean(all)), 'mean, all runs'],
             [sds.sort((a, b) => a - b)[Math.floor(sds.length / 2)].toFixed(3), 'median spread between replicates']];
  document.getElementById('kpis').replaceChildren(...k.map(([v, l]) => {
    const d = el('div', 'kpi'); d.append(el('div', 'v', v), el('div', 'l', l)); return d;
  }));
})();

function el(t, c, txt) { const x = document.createElement(t); if (c) x.className = c; if (txt != null) x.textContent = txt; return x; }
function s(t, a) { const x = document.createElementNS(NS, t); for (const k in a) x.setAttribute(k, a[k]); return x; }

/* ---------- tooltip ---------- */
const tip = document.getElementById('tip');
function hover(node, html) {
  node.addEventListener('mousemove', e => {
    tip.innerHTML = html; tip.style.opacity = 1;
    const w = tip.offsetWidth, x = Math.min(e.clientX + 14, innerWidth - w - 8);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY - 34) + 'px';
  });
  node.addEventListener('mouseleave', () => { tip.style.opacity = 0; });
}

/* ---------- ranked bars at 120 min ---------- */
(function () {
  const rows = D.pairs.map(p => ({p, v: cell(p, 120)})).filter(r => r.v)
    .map(r => ({...r, m: mean(r.v)})).sort((a, b) => b.m - a.m);
  const L = 176, R = 54, T = 22, rowH = 30, H = T + rows.length * rowH + 26;
  const W = Math.min(1100, 940), IW = W - L - R;
  const x = v => L + v * IW;                       // recall runs 0..1
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
                        role: 'img', 'aria-label': 'Recall at the two-hour budget, ranked'});
  for (let t = 0; t <= 1.0001; t += 0.2) {
    svg.append(s('line', {x1: x(t), x2: x(t), y1: T - 6, y2: H - 24, class: 'tick'}));
    const lb = s('text', {x: x(t), y: H - 8, 'text-anchor': 'middle', class: 'axis'});
    lb.textContent = t.toFixed(1); svg.append(lb);
  }
  svg.append(s('line', {x1: L, x2: L, y1: T - 6, y2: H - 24, class: 'axline'}));
  rows.forEach((r, i) => {
    const y = T + i * rowH, bh = 16;
    const nm = s('text', {x: L - 10, y: y + bh - 3, 'text-anchor': 'end', class: 'lab'});
    nm.textContent = r.p; svg.append(nm);
    svg.append(s('rect', {x: L, y, width: Math.max(1, x(r.m) - L), height: bh,
                          rx: 4, ry: 4, fill: 'var(--accent)'}));
    svg.append(s('rect', {x: L, y, width: 4, height: bh, fill: 'var(--accent)'})); // square at the baseline
    r.v.forEach(v => {
      svg.append(s('circle', {cx: x(v), cy: y + bh / 2, r: 4.5,
                              fill: '#8C3F22', stroke: 'var(--surface)', 'stroke-width': 2}));
    });
    const vl = s('text', {x: x(r.m) + 10, y: y + bh - 3, class: 'val'});
    vl.textContent = fmt(r.m); svg.append(vl);
    const hit = s('rect', {x: 0, y: y - 4, width: W, height: rowH, class: 'hit'});
    hover(hit, `<b>${r.p}</b><br>mean ${fmt(r.m)} over ${r.v.length} run${r.v.length > 1 ? 's' : ''}<br>`
      + r.v.map(fmt).join(' · '));
    svg.append(hit);
  });
  document.getElementById('bars').replaceChildren(svg);
})();

/* ---------- small multiples ---------- */
(function () {
  const box = document.getElementById('panels');
  const order = D.pairs.map(p => {
    const vs = BUD.map(b => cell(p, b)).filter(Boolean);
    return {p, top: Math.max(...vs.map(mean))};
  }).sort((a, b) => b.top - a.top).map(o => o.p);
  const W = 215, H = 118, L = 30, R = 12, T = 10, B = 22, IW = W - L - R, IH = H - T - B;
  const xs = {10: L, 30: L + IW * 0.42, 120: L + IW};      // compressed log-ish spacing
  const y = v => T + IH - v * IH;                           // 0..1
  for (const p of order) {
    const card = el('div', 'panel');
    const pts = BUD.map(b => ({b, v: cell(p, b)})).filter(o => o.v);
    const top = Math.max(...pts.map(o => mean(o.v)));
    card.append(el('h3', null, p), el('div', 'm', `best ${fmt(top)}`));
    const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%',
                          role: 'img', 'aria-label': `${p}: recall against budget`});
    [0, 0.25, 0.5, 0.75, 1].forEach(t => {
      svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
      if (t === 0 || t === 0.5 || t === 1) {
        const lb = s('text', {x: L - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'axis'});
        lb.textContent = t.toFixed(1); svg.append(lb);
      }
    });
    BUD.forEach(b => {
      const lb = s('text', {x: xs[b], y: H - 7, 'text-anchor': 'middle', class: 'axis'});
      lb.textContent = b; svg.append(lb);
    });
    const seq = pts.map(o => `${xs[o.b]},${y(mean(o.v))}`).join(' ');
    if (pts.length > 1) svg.append(s('polyline', {points: seq, fill: 'none', stroke: 'var(--accent)',
                                                  'stroke-width': 2, 'stroke-linejoin': 'round',
                                                  'stroke-linecap': 'round'}));
    pts.forEach(o => {
      const m = mean(o.v), single = o.v.length === 1;
      o.v.forEach(v => { if (!single) svg.append(s('circle', {cx: xs[o.b], cy: y(v), r: 2.6, fill: 'var(--grey)'})); });
      svg.append(s('circle', {cx: xs[o.b], cy: y(m), r: 4.5, fill: single ? 'var(--surface)' : 'var(--accent)',
                              stroke: single ? 'var(--accent)' : 'var(--surface)', 'stroke-width': 2}));
      const hit = s('rect', {x: xs[o.b] - 22, y: T, width: 44, height: IH, class: 'hit'});
      hover(hit, `<b>${p}</b> · ${o.b} min<br>mean ${fmt(m)}` +
        (single ? '<br>one replicate' : `<br>${o.v.length} runs: ` + o.v.map(fmt).join(' · ')));
      svg.append(hit);
    });
    const miss = BUD.filter(b => !cell(p, b));
    card.append(svg);
    if (miss.length) card.append(el('div', 'm', 'no run at ' + miss.join(', ') + ' min'));
    box.append(card);
  }
})();

/* ---------- table ---------- */
(function () {
  const t = document.createElement('table');
  const hd = t.insertRow();
  ['harness · model', '10 min', '30 min', '120 min', 'runs'].forEach(h => {
    const th = document.createElement('th'); th.textContent = h; hd.append(th);
  });
  const order = D.pairs.map(p => ({p, top: Math.max(...BUD.map(b => cell(p, b)).filter(Boolean).map(mean))}))
    .sort((a, b) => b.top - a.top);
  for (const {p} of order) {
    const r = t.insertRow(); r.insertCell().textContent = p;
    let n = 0;
    for (const b of BUD) {
      const v = cell(p, b); n += v ? v.length : 0;
      r.insertCell().textContent = v ? fmt(mean(v)) + (v.length === 1 ? ' *' : '') : '—';
    }
    r.insertCell().textContent = n;
  }
  const cap = el('div', 'note', '* one replicate. Runs where the harness switched model after a refusal are excluded: '
    + D.switched.map(s => `${s.nominal} → ${s.served} (${s.budget} min, ${fmt(s.acc)})`).join('; ') + '.');
  document.getElementById('table').replaceChildren(t, cap);
})();
</script></body></html>'''

if __name__ == "__main__":
    main()
