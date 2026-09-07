#!/usr/bin/env python3
"""Build viewers/performance_v2.html — round-4 performance on the v2 rubric.

Seventy-nine reports graded by Fable 5.1 against 38 rubric points, scored under the
auditor's strict transform max(2s - 1, 0). The transform is the point of the page:
it discards everything at or below the rubric midpoint, so three of the six anchors
the judge can award collapse to zero, and a report that gestures at every point
scores nothing while one that nails a few scores well.

Four things this page shows that the round-3 page does not.

  1. Budget is confounded with prompt. Each budget ran a different prompt, so any
     gap between budgets is prompt and budget together. Nothing draws a trend line
     across budgets.
  2. Per-point difficulty over all 79 reports, ranked, and split by budget — "hard"
     and "unreachable" are the same number when the budgets are pooled.
  3. Raw against strict per model, so the reader sees who loses most to the cut.
  4. Model names normalised, so a model is one entity and the harness stays separate.

The strict transform is imported from scripts/report_performance.py rather than
restated here, so the page cannot drift from the reference implementation.

Self-contained: inline SVG, no libraries.
"""
import json, re, statistics as st, sys, pathlib
from collections import defaultdict

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
from paths import GRADED, GRADED_INPUTS, VIEWERS
from report_performance import strict, NAMES as REF_NAMES   # the reference transform

OUT = VIEWERS / "performance_v2.html"
GDIR = GRADED / "judge_claude_fable_5_1" / "v2"
INDEX_DIRS = ["round4_blind10", "round4_blind30", "round4_blind120"]
BUDGETS = [10, 30, 120]

# The reference map, plus the two strings it does not carry. `react` serves GPT-6
# Astra under an `openai_`-prefixed id while `codex` serves it bare, which split one
# model across two rows in the reference report; folding them here makes the model
# one entity and leaves the harness to distinguish the rows.
NAMES = dict(REF_NAMES)
NAMES["openai_gpt_6_astra"] = "GPT-6 Astra"

# the `_p<id>` suffix marks a report run on a prompt other than its budget's default;
# the reference regex does not carry it, so it is added here rather than upstream.
RX = re.compile(
    r"graded_(r4b(\d+))_(claude|codex|react)_(.+?)_rep(\d)"
    r"(?:_served_([a-z0-9_]+?))?(?:_p([0-9a-f]+))?\.json$")


def prompt_index():
    """graded-file stem -> prompt_id, joined through each round's _index.jsonl."""
    out = {}
    for d in INDEX_DIRS:
        f = GRADED_INPUTS / d / "_index.jsonl"
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            key = r["graded_input"][:-3].replace("__", "_").replace("-", "_").replace(".", "_")
            out[key] = r["prompt_id"]
    return out


def load():
    pidx, rows, grader, rubric = prompt_index(), [], None, None
    for p in sorted(GDIR.glob("graded_*.json")):
        m = RX.search(p.name)
        if not m:
            raise SystemExit(f"filename does not parse: {p.name}")
        g = json.loads(p.read_text())
        grader = grader or g.get("grader")
        rubric = rubric or g.get("rubric")
        stem = p.stem[len("graded_"):]
        scores = {k: v["score"] for k, v in g["scores"].items()}
        vals = list(scores.values())
        rows.append({
            "key": stem, "budget": int(m.group(2)), "harness": m.group(3),
            "model": NAMES.get(m.group(4), m.group(4)), "rep": int(m.group(5)),
            "served": NAMES.get(m.group(6), m.group(6)) if m.group(6) else None,
            "prompt": pidx.get(stem),
            "raw": st.mean(vals), "strict": st.mean(strict(v) for v in vals),
            "scores": scores,
        })
    return rows, grader, rubric


def main():
    rows, grader, rubric = load()
    for r in rows:
        r["pair"] = f"{r['harness']} · {r['model']}"
    nominal = [r for r in rows if not r["served"]]

    cells = defaultdict(lambda: {"raw": [], "strict": []})
    for r in nominal:
        c = cells[(r["pair"], r["budget"])]
        c["raw"].append(r["raw"])
        c["strict"].append(r["strict"])
    pairs = sorted({r["pair"] for r in nominal})

    # per-point: pooled mean strict over every report, and the same split by budget.
    # Ten points are zero at 10 minutes; only two of those are zero at every budget, so
    # the pooled number alone cannot separate "hard" from "unreachable".
    pooled, by_bud = defaultdict(list), defaultdict(lambda: defaultdict(list))
    for r in rows:
        for cid, s in r["scores"].items():
            pooled[cid].append(s)
            by_bud[cid][r["budget"]].append(s)
    points = []
    for cid in sorted(pooled):
        allv = pooled[cid]
        pb = {b: st.mean(strict(v) for v in by_bud[cid][b]) for b in BUDGETS if by_bud[cid][b]}
        points.append({
            "id": cid,
            "strict": st.mean(strict(v) for v in allv),
            "raw": st.mean(allv),
            "max_raw": max(allv),
            "n_above": sum(1 for v in allv if strict(v) > 0),
            "by_budget": pb,
            "dead": all(strict(v) == 0 for v in allv),
            "dead_at": [b for b in BUDGETS if b in pb and pb[b] == 0],
            "alive_at": [b for b in BUDGETS if pb.get(b, 0) > 0],
        })

    # prompt per budget, read from the run index rather than assumed
    prompts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        prompts[r["budget"]][r["prompt"]] += 1

    data = {
        "grader": grader, "rubric": rubric, "n_reports": len(rows),
        "n_nominal": len(nominal), "n_points": len(pooled), "budgets": BUDGETS,
        "pairs": pairs,
        "cells": {f"{k[0]}|{k[1]}": v for k, v in cells.items()},
        "models": sorted({r["model"] for r in nominal}),
        "reports": [{k: r[k] for k in
                     ("key", "budget", "harness", "model", "pair", "rep", "served",
                      "prompt", "raw", "strict")} for r in rows],
        "points": points,
        "prompts": {str(b): dict(v) for b, v in prompts.items()},
        "budget_strict": {str(b): st.mean(r["strict"] for r in rows if r["budget"] == b)
                          for b in BUDGETS},
        "budget_raw": {str(b): st.mean(r["raw"] for r in rows if r["budget"] == b)
                       for b in BUDGETS},
        "switched": [{"pair": r["pair"], "served": r["served"], "budget": r["budget"],
                      "raw": r["raw"], "strict": r["strict"]} for r in rows if r["served"]],
    }
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    dead = [p["id"] for p in points if p["dead"]]
    print(f"{OUT}: {len(rows)} reports, {len(pairs)} harness/model pairs, "
          f"{len(pooled)} points, judge {grader}, rubric {rubric}")
    print(f"  mean strict overall {st.mean(r['strict'] for r in rows):.3f}; "
          f"by budget " + ", ".join(f"{b} min {data['budget_strict'][str(b)]:.3f}" for b in BUDGETS))
    print(f"  points dead everywhere: {', '.join(dead) or 'none'}")
    print(f"  points dead at 10 min but alive at 120: "
          f"{', '.join(p['id'] for p in points if 10 in p['dead_at'] and 120 in p['alive_at'])}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Strict performance, v2 rubric — MessageBoardAuditBench</title>
<style>
:root{
  --paper:#F4F3EE; --surface:#FFFFFF; --line:#E0DDD4; --ink:#1A1A1A; --ink2:#666666; --ink3:#999999;
  --accent:#C15F3C; --accent-deep:#8C3F22; --accent-soft:#FDF2EC; --grey:#C9C6BC; --grid:#EAE7DF;
  --warn-bg:#FEF3C7; --warn-ink:#92400E; --dead-bg:#FEE2E2; --dead-ink:#991B1B;
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
.warn{background:var(--warn-bg);border:1px solid #E7CE8E;border-radius:8px;padding:12px 16px;margin:10px 0;
  color:var(--warn-ink);font-size:13px}
.warn b{color:#6B3306}
.anchors{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 2px}
.anc{border:1px solid var(--line);border-radius:6px;padding:6px 10px;background:var(--surface);
  font-size:12px;font-variant-numeric:tabular-nums}
.anc.zero{background:var(--dead-bg);border-color:#F0B9B9;color:var(--dead-ink)}
.anc .a{font-weight:600}
svg{display:block;max-width:100%;overflow:visible}
text{font-family:inherit}
.axis{fill:var(--ink2);font-size:11px}
.tick{stroke:var(--grid);stroke-width:1}
.axline{stroke:var(--line);stroke-width:1}
.lab{fill:var(--ink);font-size:12px}
.lab.dead{fill:var(--dead-ink);font-weight:600}
.val{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}
.small{fill:var(--ink3);font-size:10.5px}
.panels{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:10px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:9px 10px 6px}
.panel h3{margin:0;font-size:12.5px;font-weight:600}
.panel .m{font-size:11px;color:var(--ink3);margin-bottom:2px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin:0 0 10px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:-1px}
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
  <h1>Strict performance, v2 rubric</h1>
  <p class="sub" id="sub"></p>
  <div class="kpis" id="kpis"></div>

  <h2>What the strict transform does</h2>
  <p class="note">A point is scored <b>max(2s &minus; 1, 0)</b>, then averaged over a report&rsquo;s
    points. Three of the six anchors the judge can award collapse to zero, so a report that gestures
    at everything scores nothing and only substantive coverage counts. Raw is kept alongside
    throughout, never as the headline.</p>
  <div class="anchors" id="anchors"></div>

  <h2>Ranked at the two-hour budget</h2>
  <p class="note" id="rank-note"></p>
  <div class="card" id="bars"></div>

  <h2>Across budgets</h2>
  <div class="warn" id="confound"></div>
  <p class="note">One panel per harness and model, same scale. Bars, not a line: a gap between two
    budgets is prompt and budget together and nothing interpolates between them. A hollow marker is
    a single replicate.</p>
  <div class="panels" id="panels"></div>

  <h2>What each model loses to the transform</h2>
  <p class="note">The pale bar is the raw mean, the coral bar the strict mean, and the gap between
    them is the credit the transform discards. A model that touches many points loses more of its
    raw score than one that covers a few properly. Pooled over every budget, so read the level
    against the confound above.</p>
  <div class="card" id="drop"></div>

  <h2>Which points carry the rubric</h2>
  <p class="note" id="pts-note"></p>
  <div class="legend" id="pts-legend"></div>
  <div class="card" id="points"></div>

  <details>
    <summary>The numbers</summary>
    <div class="card" id="table"></div>
    <div class="card" id="ptable"></div>
  </details>
</main>
<div id="tip"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const BUD = D.budgets, NS = 'http://www.w3.org/2000/svg';
const cell = (p, b) => D.cells[p + '|' + b] || null;
const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
const fmt = v => v.toFixed(3);
const strict = s => Math.max(2 * s - 1, 0);

function el(t, c, txt) { const x = document.createElement(t); if (c) x.className = c; if (txt != null) x.textContent = txt; return x; }
function s(t, a) { const x = document.createElementNS(NS, t); for (const k in a) if (a[k] != null) x.setAttribute(k, a[k]); return x; }

document.getElementById('sub').textContent =
  `${D.n_reports} round-4 reports scored on ${D.n_points} rubric points by ${D.grader}, `
  + `rubric ${D.rubric}. Strict score throughout unless a chart says raw.`;

/* ---------- headline numbers ---------- */
(function () {
  const all = D.reports.map(r => r.strict);
  const at120 = D.pairs.map(p => [p, cell(p, 120)]).filter(x => x[1]);
  const best = at120.map(([p, c]) => [mean(c.strict), p]).sort((a, b) => b[0] - a[0])[0];
  const dead = D.points.filter(p => p.dead);
  const k = [[fmt(mean(all)), 'mean strict, all reports'],
             [fmt(mean(D.reports.map(r => r.raw))), 'mean raw, all reports'],
             [fmt(best[0]), best[1] + ' at 2 h'],
             [String(dead.length), 'points no report reaches: ' + dead.map(p => p.id).join(', ')]];
  document.getElementById('kpis').replaceChildren(...k.map(([v, l]) => {
    const d = el('div', 'kpi'); d.append(el('div', 'v', v), el('div', 'l', l)); return d;
  }));
})();

/* ---------- the six anchors ---------- */
(function () {
  const box = document.getElementById('anchors');
  [1.0, 0.9, 0.7, 0.5, 0.3, 0.0].forEach(a => {
    const t = strict(a), d = el('div', 'anc' + (t === 0 ? ' zero' : ''));
    d.append(el('span', 'a', a.toFixed(1)), document.createTextNode(' → ' + t.toFixed(2)));
    box.append(d);
  });
})();

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

/* ---------- the prompt/budget confound ---------- */
(function () {
  const parts = BUD.map(b => {
    const ps = Object.entries(D.prompts[String(b)]).sort((x, y) => y[1] - x[1]);
    return `<b>${b} min</b> on ${ps.map(([id, n]) => id + (ps.length > 1 ? ` (${n})` : '')).join(' and ')}`;
  });
  document.getElementById('confound').innerHTML =
    'Each budget ran a <b>different prompt</b>: ' + parts.join(', ')
    + '. A difference between two budgets is therefore prompt and budget together, and this page '
    + 'draws no line implying a smooth budget trend. Only comparisons <i>within</i> one budget hold '
    + 'the prompt fixed.';
})();

/* ---------- ranked bars at 120 min ---------- */
(function () {
  const rows = D.pairs.map(p => ({p, c: cell(p, 120)})).filter(r => r.c)
    .map(r => ({...r, m: mean(r.c.strict), raw: mean(r.c.raw), v: r.c.strict.slice().sort((a, b) => a - b)}))
    .sort((a, b) => b.m - a.m);
  const missing = D.pairs.filter(p => !cell(p, 120));
  const top = Math.max(...rows.map(r => Math.max(r.m, ...r.v)));
  const X1 = Math.min(1, Math.ceil((top + 0.06) * 10) / 10);
  document.getElementById('rank-note').innerHTML =
    `Strict score at the two-hour budget, where all ${D.prompts['120'] ? Object.values(D.prompts['120']).reduce((a, b) => a + b, 0) : ''} `
    + `reports share one prompt, so this is the one chart where the comparison is clean. Each `
    + `replicate is a dot; the bar is their mean. Axis stops at ${X1.toFixed(1)}, not 1.0.`
    + (missing.length ? ` <b>${missing.length}</b> pair${missing.length > 1 ? 's have' : ' has'} no `
      + `two-hour run and ${missing.length > 1 ? 'are' : 'is'} left out: ` + missing.join(', ') + '.' : '');
  const L = 176, R = 62, T = 22, rowH = 30, H = T + rows.length * rowH + 26, W = 940, IW = W - L - R;
  const x = v => L + v / X1 * IW;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
                        role: 'img', 'aria-label': 'Strict score at the two-hour budget, ranked'});
  for (let t = 0; t <= X1 + 1e-9; t += 0.1) {
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
    svg.append(s('rect', {x: L, y, width: 4, height: bh, fill: 'var(--accent)'}));
    r.v.forEach(v => svg.append(s('circle', {cx: x(v), cy: y + bh / 2, r: 4.5,
                                             fill: 'var(--accent-deep)', stroke: 'var(--surface)', 'stroke-width': 2})));
    const vl = s('text', {x: Math.max(x(r.m), Math.max(...r.v.map(x))) + 10, y: y + bh - 3, class: 'val'});
    vl.textContent = fmt(r.m); svg.append(vl);
    const hit = s('rect', {x: 0, y: y - 4, width: W, height: rowH, class: 'hit'});
    hover(hit, `<b>${r.p}</b> · 2 h<br>strict ${fmt(r.m)} · raw ${fmt(r.raw)}`
      + `<br>${r.v.length} run${r.v.length > 1 ? 's' : ''}: ` + r.v.map(fmt).join(' · '));
    svg.append(hit);
  });
  document.getElementById('bars').replaceChildren(svg);
})();

/* ---------- small multiples: strict by budget, as bars ---------- */
(function () {
  const box = document.getElementById('panels');
  const order = D.pairs.map(p => {
    const vs = BUD.map(b => cell(p, b)).filter(Boolean);
    return {p, top: Math.max(...vs.map(c => mean(c.strict)))};
  }).sort((a, b) => b.top - a.top).map(o => o.p);
  const YMAX = 0.6;
  const W = 215, H = 122, L = 30, R = 10, T = 10, B = 26, IW = W - L - R, IH = H - T - B;
  const bw = IW / 3 * 0.54;
  const cx = b => L + IW * (BUD.indexOf(b) + 0.5) / 3;
  const y = v => T + IH - Math.min(v, YMAX) / YMAX * IH;
  for (const p of order) {
    const card = el('div', 'panel');
    const pts = BUD.map(b => ({b, c: cell(p, b)})).filter(o => o.c);
    const best = Math.max(...pts.map(o => mean(o.c.strict)));
    card.append(el('h3', null, p), el('div', 'm', `best ${fmt(best)}`));
    const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%',
                          role: 'img', 'aria-label': `${p}: strict score by budget`});
    [0, 0.2, 0.4, 0.6].forEach(t => {
      svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
      const lb = s('text', {x: L - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'axis'});
      lb.textContent = t.toFixed(1); svg.append(lb);
    });
    svg.append(s('line', {x1: L, x2: W - R, y1: y(0), y2: y(0), class: 'axline'}));
    BUD.forEach(b => {
      const lb = s('text', {x: cx(b), y: H - 12, 'text-anchor': 'middle', class: 'axis'});
      lb.textContent = b; svg.append(lb);
    });
    const ax = s('text', {x: L + IW / 2, y: H - 1, 'text-anchor': 'middle', class: 'small'});
    ax.textContent = 'minutes (each a different prompt)'; svg.append(ax);
    pts.forEach(o => {
      const v = o.c.strict.slice().sort((a, b) => a - b), m = mean(v), single = v.length === 1;
      svg.append(s('rect', {x: cx(o.b) - bw / 2, y: y(m), width: bw, height: Math.max(1, y(0) - y(m)),
                            rx: 2, ry: 2, fill: single ? 'none' : 'var(--accent)',
                            stroke: 'var(--accent)', 'stroke-width': single ? 1.5 : 0,
                            'stroke-dasharray': single ? '3 2' : null}));
      if (!single) v.forEach(q => svg.append(s('circle', {cx: cx(o.b), cy: y(q), r: 2.4,
        fill: 'var(--surface)', stroke: 'var(--accent-deep)', 'stroke-width': 1.2})));
      const hit = s('rect', {x: cx(o.b) - IW / 6, y: T, width: IW / 3, height: IH, class: 'hit'});
      hover(hit, `<b>${p}</b> · ${o.b} min<br>strict ${fmt(m)} · raw ${fmt(mean(o.c.raw))}`
        + (single ? '<br>one replicate' : `<br>${v.length} runs: ` + v.map(fmt).join(' · ')));
      svg.append(hit);
    });
    const miss = BUD.filter(b => !cell(p, b));
    card.append(svg);
    if (miss.length) card.append(el('div', 'm', 'no run at ' + miss.join(', ') + ' min'));
    box.append(card);
  }
})();

/* ---------- raw against strict, per model ---------- */
(function () {
  const by = {};
  for (const r of D.reports) {
    if (r.served) continue;
    (by[r.model] = by[r.model] || {raw: [], strict: [], pairs: new Set()});
    by[r.model].raw.push(r.raw); by[r.model].strict.push(r.strict); by[r.model].pairs.add(r.harness);
  }
  const rows = Object.entries(by).map(([m, v]) => ({
    m, raw: mean(v.raw), strict: mean(v.strict), n: v.raw.length,
    harnesses: [...v.pairs].sort()
  })).map(r => ({...r, drop: r.raw - r.strict})).sort((a, b) => b.strict - a.strict);
  const X1 = Math.min(1, Math.ceil((Math.max(...rows.map(r => r.raw)) + 0.06) * 10) / 10);
  const L = 150, R = 130, T = 26, rowH = 28, H = T + rows.length * rowH + 26, W = 940, IW = W - L - R;
  const x = v => L + v / X1 * IW;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
                        role: 'img', 'aria-label': 'Raw against strict score, per model'});
  for (let t = 0; t <= X1 + 1e-9; t += 0.1) {
    svg.append(s('line', {x1: x(t), x2: x(t), y1: T - 8, y2: H - 24, class: 'tick'}));
    const lb = s('text', {x: x(t), y: H - 8, 'text-anchor': 'middle', class: 'axis'});
    lb.textContent = t.toFixed(1); svg.append(lb);
  }
  svg.append(s('line', {x1: L, x2: L, y1: T - 8, y2: H - 24, class: 'axline'}));
  const key = s('text', {x: L, y: 12, class: 'small'});
  key.textContent = 'pale = raw   ·   coral = strict   ·   label = credit discarded';
  svg.append(key);
  rows.forEach((r, i) => {
    const y = T + i * rowH, bh = 15;
    const nm = s('text', {x: L - 10, y: y + bh - 3, 'text-anchor': 'end', class: 'lab'});
    nm.textContent = r.m; svg.append(nm);
    svg.append(s('rect', {x: L, y, width: Math.max(1, x(r.raw) - L), height: bh,
                          rx: 3, ry: 3, fill: 'var(--accent-soft)', stroke: 'var(--accent)',
                          'stroke-width': 1}));
    svg.append(s('rect', {x: L, y, width: Math.max(1, x(r.strict) - L), height: bh,
                          rx: 3, ry: 3, fill: 'var(--accent)'}));
    const vl = s('text', {x: x(r.raw) + 10, y: y + bh - 3, class: 'val'});
    vl.textContent = `−${fmt(r.drop)}  (${Math.round(r.drop / r.raw * 100)}%)`;
    svg.append(vl);
    const hit = s('rect', {x: 0, y: y - 3, width: W, height: rowH, class: 'hit'});
    hover(hit, `<b>${r.m}</b><br>raw ${fmt(r.raw)} → strict ${fmt(r.strict)}`
      + `<br>discarded ${fmt(r.drop)}, ${Math.round(r.drop / r.raw * 100)}% of raw`
      + `<br>${r.n} report${r.n > 1 ? 's' : ''} under ${r.harnesses.join(' + ')}`);
    svg.append(hit);
  });
  document.getElementById('drop').replaceChildren(svg);
})();

/* ---------- per-point difficulty ---------- */
(function () {
  const pts = D.points.slice().sort((a, b) => b.strict - a.strict);
  const dead = pts.filter(p => p.dead);
  const zero10 = pts.filter(p => p.dead_at.includes(10));
  const recover = zero10.filter(p => p.alive_at.includes(120));
  const only30 = zero10.filter(p => !p.dead && !p.alive_at.includes(120));
  const names = a => a.map(p => p.id).join(', ');
  document.getElementById('pts-note').innerHTML =
    `All ${D.n_points} rubric points over all ${D.n_reports} reports, ranked by pooled mean strict `
    + `score. <b>${zero10.length}</b> are zero at 10 minutes, and the pooled bar alone cannot tell `
    + `those apart from genuinely unreachable, so each row also carries its three per-budget means as `
    + `ticks. They split three ways. <b>${dead.length}</b> — ${names(dead)} — are zero for every `
    + `report at every budget and are shown in red with a &times;; no report anywhere scores either `
    + `above the 0.5 cut. <b>${recover.length}</b> recover by 120 minutes (${names(recover)}), `
    + `${recover.filter(q => q.n_above === 1).length} of them on a single report out of ${D.n_reports}.`
    + (only30.length ? ` And ${names(only30)} is non-zero at 30 minutes only, on one report, and back `
      + `to zero at 120 — near-dead rather than dead, and worth not mistaking for either.` : '');
  const leg = document.getElementById('pts-legend');
  [['var(--accent)', 'pooled mean strict'], ['var(--grey)', 'per-budget mean: 10 / 30 / 120 min'],
   ['var(--dead-ink)', 'zero everywhere']].forEach(([c, t]) => {
    const d = el('span'); const i = el('i'); i.style.background = c; d.append(i, document.createTextNode(t)); leg.append(d);
  });
  const X1 = Math.min(1, Math.ceil((Math.max(...pts.map(p => Math.max(p.strict, ...Object.values(p.by_budget)))) + 0.05) * 20) / 20);
  const L = 58, R = 60, T = 24, rowH = 21, H = T + pts.length * rowH + 26, W = 940, IW = W - L - R;
  const x = v => L + v / X1 * IW;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
                        role: 'img', 'aria-label': 'Rubric points ranked by mean strict score'});
  for (let t = 0; t <= X1 + 1e-9; t += 0.1) {
    svg.append(s('line', {x1: x(t), x2: x(t), y1: T - 8, y2: H - 24, class: 'tick'}));
    const lb = s('text', {x: x(t), y: H - 8, 'text-anchor': 'middle', class: 'axis'});
    lb.textContent = t.toFixed(1); svg.append(lb);
  }
  svg.append(s('line', {x1: L, x2: L, y1: T - 8, y2: H - 24, class: 'axline'}));
  pts.forEach((p, i) => {
    const y = T + i * rowH, bh = 11, mid = y + bh / 2;
    const nm = s('text', {x: L - 10, y: y + bh - 1, 'text-anchor': 'end',
                          class: 'lab' + (p.dead ? ' dead' : '')});
    nm.textContent = p.id; svg.append(nm);
    if (p.dead) {
      const xm = s('text', {x: L + 6, y: y + bh - 1, class: 'lab dead'});
      xm.textContent = '×  zero for all ' + D.n_reports + ' reports (highest raw '
        + p.max_raw.toFixed(1) + ', below the 0.5 cut)';
      svg.append(xm);
    } else {
      svg.append(s('rect', {x: L, y, width: Math.max(1, x(p.strict) - L), height: bh,
                            rx: 2, ry: 2, fill: 'var(--accent)'}));
      BUD.forEach(b => {
        if (!(b in p.by_budget)) return;
        const v = p.by_budget[b];
        svg.append(s('line', {x1: x(v), x2: x(v), y1: mid - 7.5, y2: mid + 7.5,
                              stroke: v === 0 ? 'var(--dead-ink)' : 'var(--grey)', 'stroke-width': 1.5}));
      });
      const vl = s('text', {x: x(Math.max(p.strict, ...Object.values(p.by_budget))) + 9, y: y + bh - 1, class: 'val'});
      vl.textContent = fmt(p.strict); svg.append(vl);
    }
    const hit = s('rect', {x: 0, y: y - 4, width: W, height: rowH, class: 'hit'});
    hover(hit, `<b>${p.id}</b><br>pooled strict ${fmt(p.strict)} · raw ${fmt(p.raw)}`
      + `<br>${p.n_above} of ${D.n_reports} reports score above the 0.5 cut`
      + '<br>' + BUD.map(b => `${b} min ${b in p.by_budget ? fmt(p.by_budget[b]) : '—'}`).join(' · ')
      + (p.dead ? '<br><i>zero everywhere; highest raw score anywhere is ' + p.max_raw.toFixed(1) + '</i>' : ''));
    svg.append(hit);
  });
  document.getElementById('points').replaceChildren(svg);
})();

/* ---------- tables ---------- */
(function () {
  const t = document.createElement('table');
  const hd = t.insertRow();
  ['harness · model', '10 min', '30 min', '120 min', 'raw (all)', 'runs'].forEach(h => {
    const th = document.createElement('th'); th.textContent = h; hd.append(th);
  });
  const order = D.pairs.map(p => ({
    p, top: Math.max(...BUD.map(b => cell(p, b)).filter(Boolean).map(c => mean(c.strict)))
  })).sort((a, b) => b.top - a.top);
  for (const {p} of order) {
    const r = t.insertRow(); r.insertCell().textContent = p;
    let n = 0, raws = [];
    for (const b of BUD) {
      const c = cell(p, b); n += c ? c.strict.length : 0; if (c) raws.push(...c.raw);
      r.insertCell().textContent = c ? fmt(mean(c.strict)) + (c.strict.length === 1 ? ' *' : '') : '—';
    }
    r.insertCell().textContent = fmt(mean(raws));
    r.insertCell().textContent = n;
  }
  const foot = t.insertRow();
  const fc = foot.insertCell(); fc.textContent = 'all reports, strict'; fc.style.fontWeight = '600';
  BUD.forEach(b => { const c = foot.insertCell(); c.textContent = fmt(D.budget_strict[String(b)]); c.style.fontWeight = '600'; });
  foot.insertCell().textContent = fmt(mean(D.reports.map(r => r.raw)));
  foot.insertCell().textContent = D.n_reports;
  const cap = el('div', 'note', '* one replicate. Strict columns are means over that cell’s '
    + 'replicates; the last row pools every report at that budget, including the switched runs. '
    + 'Runs where the harness switched model after a refusal sit outside the per-pair rows: '
    + D.switched.map(x => `${x.pair} → ${x.served} (${x.budget} min, strict ${fmt(x.strict)})`).join('; ') + '.');
  document.getElementById('table').replaceChildren(el('h3', null, 'Harness and model'), t, cap);

  const u = document.createElement('table');
  const uh = u.insertRow();
  ['point', 'strict', 'raw', '10 min', '30 min', '120 min', 'above cut'].forEach(h => {
    const th = document.createElement('th'); th.textContent = h; uh.append(th);
  });
  for (const p of D.points.slice().sort((a, b) => b.strict - a.strict)) {
    const r = u.insertRow();
    const c0 = r.insertCell(); c0.textContent = p.id + (p.dead ? '  ×' : '');
    if (p.dead) { c0.style.color = 'var(--dead-ink)'; c0.style.fontWeight = '600'; }
    r.insertCell().textContent = fmt(p.strict);
    r.insertCell().textContent = fmt(p.raw);
    BUD.forEach(b => { r.insertCell().textContent = b in p.by_budget ? fmt(p.by_budget[b]) : '—'; });
    r.insertCell().textContent = `${p.n_above} / ${D.n_reports}`;
  }
  document.getElementById('ptable').replaceChildren(
    el('h3', null, 'Rubric points'), u,
    el('div', 'note', '× marks a point no report scores above the 0.5 cut on, at any budget.'));
})();
</script></body></html>'''

if __name__ == "__main__":
    main()
