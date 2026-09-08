#!/usr/bin/env python3
"""Build viewers/figures/combined_score.html — the 70/30 composite of the two measures.

Finding coverage (the strict v2 score, the y-axis of headline Figure 1) asks how much of
the incident a report pinned down. The holistic TL;DR score asks whether a reader of the
summary alone would come away holding the story. They are different questions and a report
can be strong on one and weak on the other, so the composite is

    combined = 0.7 x coverage + 0.3 x TL;DR

Both parts are Fable 5.1's grades over the same 113 round-4 reports, so nothing here is
averaging two different samples. Conventions follow build_headline_figures.py exactly, so
this page can be read beside Figure 1: the strict transform from report_performance,
Epoch index values from benchmark/figures/headline_eci.json, a model run under more than
one harness shown under codex, and a run finished by a fallback model still counted as the
model that started it.

Three panels: the composite against the index (Figure 1's shape), the two measures against
each other so the reports that lead with what they found separate from those that bury it,
and the table with every number and how the ranking moves.
"""
import json, re, statistics as st, sys, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from paths import GRADED, VIEWERS, BENCH
from report_performance import strict, NAMES as REF_NAMES

OUT = VIEWERS / "figures" / "combined_score.html"
# the numbers on their own, next to headline_eci.{json,csv}, so the composite can be read
# and plotted without running this build
DATA_JSON = BENCH / "figures" / "combined_score.json"
DATA_CSV = BENCH / "figures" / "combined_score.csv"
HEADLINE = BENCH / "figures" / "headline_eci.json"
GDIR = GRADED / "judge_claude_fable_5_1"
BUDGETS = [10, 30, 120]
PRIMARY = "codex"
W_COV, W_TLDR = 0.7, 0.3
NAMES = dict(REF_NAMES); NAMES.setdefault("openai_gpt_6_astra", "GPT-6 Astra")
RX = re.compile(r"graded_(r4b(\d+))_(claude|codex|react)_(.+?)_rep(\d)"
                r"(?:_served_([a-z0-9_]+?))?(?:_p([0-9a-f]+))?\.json$")
PROVIDER = {"Opus 5": "anthropic", "Opus 4.8": "anthropic", "Sonnet 5": "anthropic", "Haiku 4.5": "anthropic",
            "GPT-5.6 Sol": "openai", "GPT-5.6 Luna": "openai", "GPT-5.6 Terra": "openai", "GPT-6 Astra": "openai",
            "Gemini 3.8 Flash": "google", "Muse Spark 1.3": "meta", "Kimi K3": "moonshot", "GLM 5.3": "zai"}


def per_run(rubric, transform):
    """(model, budget, harness, rep) -> score, for one rubric."""
    out = {}
    for p in sorted((GDIR / rubric).glob("graded_r4b*.json")):
        m = RX.search(p.name)
        if not m:
            raise SystemExit(f"filename does not parse: {p.name}")
        g = json.loads(p.read_text())
        vals = [v["score"] for v in g["scores"].values()]
        # the prompt id belongs in the key: one cell can hold two runs at the same model,
        # budget, harness and replicate that differ only by which prompt they were given
        key = (NAMES.get(m.group(4), m.group(4)), int(m.group(2)), m.group(3),
               int(m.group(5)), m.group(7) or "")
        if key in out:
            raise SystemExit(f"two grades collide on {key}: {p.name}")
        out[key] = (transform(vals), NAMES.get(m.group(6)) if m.group(6) else None)
    return out


def main():
    cov = per_run("v2", lambda v: st.mean(strict(x) for x in v))
    tld = per_run("tldrh", lambda v: st.mean(v))
    if set(cov) != set(tld):
        raise SystemExit(f"the two rubrics cover different reports: "
                         f"{len(set(cov) ^ set(tld))} keys differ — regrade before combining")
    H = json.loads(HEADLINE.read_text())
    eci = {M["model"]: M for M in H["models"]}

    harnesses = defaultdict(set)
    for (model, b, h, r, pid) in cov:
        harnesses[model].add(h)
    cells = defaultdict(list)
    for k, (c, served) in cov.items():
        model, b, h, r, pid = k
        if len(harnesses[model]) > 1 and h != PRIMARY:
            continue                       # one harness per model in the figures, as Figure 1 does
        cells[(model, b)].append({"rep": r, "harness": h, "prompt": pid, "cov": c, "tldr": tld[k][0],
                                  "comb": W_COV * c + W_TLDR * tld[k][0], "served": served})

    models = []
    for name, M in sorted(eci.items(), key=lambda kv: -kv[1]["eci"]):
        buds = {}
        for b in BUDGETS:
            rs = cells.get((name, b))
            if rs:
                buds[str(b)] = {"cov": st.mean(r["cov"] for r in rs), "tldr": st.mean(r["tldr"] for r in rs),
                                "comb": st.mean(r["comb"] for r in rs), "n": len(rs),
                                "n_fallback": sum(1 for r in rs if r["served"]),
                                "runs": sorted(rs, key=lambda r: r["comb"])}
        if not buds:
            continue
        models.append({"model": name, "provider": PROVIDER[name], "eci": M["eci"],
                       "eci_exact": M["eci_exact"], "eci_model": M["eci_model"],
                       "harness": PRIMARY if len(harnesses[name]) > 1 else next(iter(harnesses[name])),
                       "top": max(int(b) for b in buds), "budgets": buds})

    data = {"models": models, "weights": {"cov": W_COV, "tldr": W_TLDR}, "budgets": BUDGETS,
            "primary": PRIMARY, "judge": H["judge"], "transform": H["transform"],
            "eci_source": H["eci_source"], "n_reports": len(cov), "caveats": H["caveats"]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    cols = ["model", "provider", "eci", "eci_exact", "budget_min", "n_runs", "n_fallback",
            "coverage", "tldr", "combined"]
    lines = [",".join(cols)]
    for m in models:
        for b in BUDGETS:
            q = m["budgets"].get(str(b))
            if not q:
                continue
            lines.append(",".join(str(x) for x in [
                f'"{m["model"]}"', m["provider"], m["eci"], m["eci_exact"], b, q["n"],
                q["n_fallback"], round(q["cov"], 4), round(q["tldr"], 4), round(q["comb"], 4)]))
    DATA_CSV.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}, {DATA_JSON.name} and {DATA_CSV.name} — {len(models)} models over {len(cov)} reports, "
          f"combined = {W_COV:g}x coverage + {W_TLDR:g}x TL;DR")
    for b in BUDGETS:
        rank_cov = sorted((m for m in models if str(b) in m["budgets"]),
                          key=lambda m: -m["budgets"][str(b)]["cov"])
        rank_com = sorted((m for m in models if str(b) in m["budgets"]),
                          key=lambda m: -m["budgets"][str(b)]["comb"])
        moved = [f"{m['model']} {rank_cov.index(m)+1}->{i+1}"
                 for i, m in enumerate(rank_com) if rank_cov.index(m) != i]
        print(f"  {b:3d} min: top is {rank_com[0]['model']} at {rank_com[0]['budgets'][str(b)]['comb']:.3f}"
              + (f"; moved: {', '.join(moved)}" if moved else "; ranking unchanged"))


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Combined score — coverage and the TL;DR</title>
<style>
:root{--bg:#F4F3EE;--card:#FFF;--bd:#E0DDD4;--ink:#1A1A1A;--sec:#666;--mut:#999;
--acc:#C15F3C;--soft:#FDF2EC;--row:#FAFAF7;--grid:#EDEAE2;
--p-anthropic:#D97757;--p-openai:#1A1A1A;--p-google:#2E9E4F;--p-meta:#0668E1;
--p-moonshot:#C2185B;--p-zai:#00897B}
*{box-sizing:border-box}
body{margin:0 auto;max-width:1180px;padding:26px 30px 60px;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px}
h1{font-size:21px;color:var(--acc);margin:0 0 4px}
h2{font-size:15px;color:var(--acc);margin:0 0 10px}
.sub{color:var(--sec);margin:0 0 22px;line-height:1.55;max-width:78ch}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:18px 20px;margin-bottom:20px}
.cap{color:var(--sec);font-size:12.5px;line-height:1.5;margin:10px 0 0;max-width:88ch}
svg{display:block;width:100%;height:auto;overflow:visible}
.axname{font-size:11px;fill:var(--sec)}
.tick{font-size:10px;fill:var(--mut)}
.mlab{font-size:10.5px;fill:var(--ink)}
.gl{stroke:var(--grid);stroke-width:1}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0 0;font-size:12px;color:var(--sec);align-items:center}
.legend span{display:inline-flex;align-items:center;gap:5px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:5px 7px;border-bottom:1px solid var(--bd);text-align:right}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);font-weight:600}
tbody tr:hover{background:var(--row)}
td.comb{font-weight:700;color:var(--acc)}
td.up{color:#065F46}td.down{color:#991B1B}
.tabs{display:flex;gap:5px;margin-bottom:12px}
.tab{border:1px solid var(--bd);background:transparent;border-radius:6px;padding:4px 12px;font:inherit;
font-size:12px;color:var(--sec);cursor:pointer}
.tab.on{background:var(--acc);border-color:var(--acc);color:#fff}
.note{font-size:12px;color:var(--sec);background:var(--soft);border:1px solid #F0D9CC;border-radius:6px;
padding:9px 12px;line-height:1.5;margin-top:14px}
</style></head>
<body>
<h1>Combined score</h1>
<p class="sub" id="lede"></p>
<div class="panel"><h2>The composite against general capability</h2><div id="fig1"></div>
  <div class="legend" id="leg1"></div><p class="cap" id="cap1"></p></div>
<div class="panel"><h2>What a report found, against what it led with</h2>
  <div class="tabs" id="tabs"></div><div id="fig2"></div><p class="cap" id="cap2"></p></div>
<div class="panel"><h2>Every number</h2><div id="tbl"></div><p class="cap" id="cap3"></p></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const s = (t, a) => { const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c;
  if (x != null) e.textContent = x; return e; };
const f3 = v => v == null ? '—' : v.toFixed(3);
const col = m => `var(--p-${m.provider})`;
const BUD = D.budgets;
/* Labels in a crowded band have to move off each other, and a label that has moved is no
   longer obviously attached to its mark — so anything nudged more than a few pixels gets a
   hairline back to the point it belongs to. */
function place(svg, x, y, text, colour, taken) {
  let ly = y + 3.5;
  while (taken.some(p => Math.abs(p - ly) < 11)) ly += 11;
  taken.push(ly);
  if (Math.abs(ly - (y + 3.5)) > 4)
    svg.append(s('line', {x1: x + 2, y1: y, x2: x + 7, y2: ly - 3.5, stroke: colour,
      'stroke-width': .8, opacity: .45}));
  const t = s('text', {x: x + 9, y: ly, class: 'mlab'});
  t.textContent = text; svg.append(t);
}
/* hollow to solid as the budget grows: the same encoding headline Figure 1 uses */
const FILL = {10: 0.0, 30: 0.45, 120: 1.0};

document.getElementById('lede').textContent =
  `Finding coverage asks how much of the incident a report pinned down; the TL;DR score asks whether a `
  + `reader of the summary alone would come away holding the story. The composite is `
  + `${D.weights.cov} x coverage + ${D.weights.tldr} x TL;DR, both from ${D.judge} over the same `
  + `${D.n_reports} round-4 reports.`;

/* ---------- Figure 1: composite against the Epoch index ---------- */
function fig1() {
  const W = 1080, H = 430, L = 62, R = 150, T = 18, B = 46;
  const IW = W - L - R, IH = H - T - B;
  const ex = D.models.map(m => m.eci);
  const x0 = Math.floor(Math.min(...ex) - 2), x1 = Math.ceil(Math.max(...ex) + 2);
  const ys = D.models.flatMap(m => Object.values(m.budgets).flatMap(q => q.runs.map(r => r.comb)));
  const y1 = Math.ceil(Math.max(...ys) * 10) / 10;
  const X = v => L + (v - x0) / (x1 - x0) * IW;
  const Y = v => T + IH - v / y1 * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'combined score against the Epoch Capabilities Index'});
  for (let v = 0; v <= y1 + 1e-9; v += 0.1) {
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'gl'}));
    const t = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'tick', 'text-anchor': 'end'});
    t.textContent = v.toFixed(1); svg.append(t);
  }
  for (let v = Math.ceil(x0 / 5) * 5; v <= x1; v += 5) {
    const t = s('text', {x: X(v), y: T + IH + 17, class: 'tick', 'text-anchor': 'middle'});
    t.textContent = v; svg.append(t);
  }
  const ax = s('text', {x: L + IW / 2, y: H - 8, class: 'axname', 'text-anchor': 'middle'});
  ax.textContent = 'Epoch Capabilities Index'; svg.append(ax);
  const ay = s('text', {x: 15, y: T + IH / 2, class: 'axname', 'text-anchor': 'middle',
    transform: `rotate(-90 15 ${T + IH / 2})`});
  ay.textContent = `combined score (${D.weights.cov} coverage + ${D.weights.tldr} TL;DR)`; svg.append(ay);

  const placed = [];
  D.models.forEach(m => {
    const px = X(m.eci), c = col(m);
    const pts = BUD.filter(b => m.budgets[b]).map(b => ({b, q: m.budgets[b]}));
    if (pts.length > 1) svg.append(s('line', {x1: px, x2: px, y1: Y(pts[0].q.comb),
      y2: Y(pts[pts.length - 1].q.comb), stroke: c, 'stroke-width': 1, opacity: .3}));
    pts.forEach(({b, q}) => {
      q.runs.forEach(r => svg.append(s('circle', {cx: px, cy: Y(r.comb), r: 1.8, fill: c, opacity: .4})));
      svg.append(s('circle', {cx: px, cy: Y(q.comb), r: 5, fill: c, 'fill-opacity': FILL[b],
        stroke: c, 'stroke-width': 2}));
    });
    const top = pts[pts.length - 1];
    place(svg, px, Y(top.q.comb), m.model + (m.eci_exact ? '' : ' *'), c, placed);
  });
  document.getElementById('fig1').replaceChildren(svg);
  const leg = document.getElementById('leg1');
  leg.replaceChildren();
  BUD.forEach(b => {
    const box = el('span'); const sv = s('svg', {width: 14, height: 14, style: 'vertical-align:-2px'});
    sv.append(s('circle', {cx: 7, cy: 7, r: 5, fill: 'var(--sec)', 'fill-opacity': FILL[b],
      stroke: 'var(--sec)', 'stroke-width': 2}));
    box.append(sv, document.createTextNode(' ' + b + ' min')); leg.append(box);
  });
  [...new Set(D.models.map(m => m.provider))].forEach(p => {
    const sp = el('span'); const i = el('i'); i.style.background = `var(--p-${p})`;
    sp.append(i, document.createTextNode(p)); leg.append(sp);
  });
  document.getElementById('cap1').textContent =
    `One column per model at its index score; the three marks are its mean combined score at 10, 30 and `
    + `120 minutes, hollow to solid, with individual runs as small dots. A model run under more than one `
    + `harness is shown under ${D.primary}. A run finished by a fallback model after a refusal still counts `
    + `as the model that started it. * marks an index taken from the previous generation. `
    + `Index source: ${D.eci_source}.`;
}

/* ---------- Figure 2: the two measures against each other ---------- */
let budSel = BUD[BUD.length - 1];
function fig2() {
  const W = 1080, H = 400, L = 62, R = 160, T = 18, B = 46;
  const IW = W - L - R, IH = H - T - B;
  const rows = D.models.filter(m => m.budgets[budSel])
    .map(m => ({m, q: m.budgets[budSel]}));
  /* a scatter of two scores, so the axes fit the data rather than reaching for zero —
     an origin at 0,0 would push every model into one corner */
  const xs = rows.map(r => r.q.cov), ys = rows.map(r => r.q.tldr);
  const x0 = Math.floor(Math.min(...xs) * 20) / 20 - 0.02, x1 = Math.ceil(Math.max(...xs) * 20) / 20 + 0.02;
  const y0 = Math.floor(Math.min(...ys) * 20) / 20 - 0.03, y1 = Math.ceil(Math.max(...ys) * 20) / 20 + 0.03;
  const X = v => L + (v - x0) / (x1 - x0) * IW, Y = v => T + IH - (v - y0) / (y1 - y0) * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'TL;DR score against finding coverage'});
  for (let v = Math.ceil(y0 * 20) / 20; v <= y1 + 1e-9; v += 0.05) {
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'gl'}));
    const t = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'tick', 'text-anchor': 'end'});
    t.textContent = v.toFixed(2); svg.append(t);
  }
  for (let v = Math.ceil(x0 * 20) / 20; v <= x1 + 1e-9; v += 0.05) {
    const t = s('text', {x: X(v), y: T + IH + 17, class: 'tick', 'text-anchor': 'middle'});
    t.textContent = v.toFixed(2); svg.append(t);
  }
  const ax = s('text', {x: L + IW / 2, y: H - 8, class: 'axname', 'text-anchor': 'middle'});
  ax.textContent = 'finding coverage (strict score on the 38 points)'; svg.append(ax);
  const ay = s('text', {x: 15, y: T + IH / 2, class: 'axname', 'text-anchor': 'middle',
    transform: `rotate(-90 15 ${T + IH / 2})`});
  ay.textContent = 'holistic TL;DR score'; svg.append(ay);
  /* iso-composite lines: every model on one line scores the same combined value */
  const wc = D.weights.cov, wt = D.weights.tldr;
  const cid = 'clip' + budSel, defs = s('defs'), cp = s('clipPath', {id: cid});
  cp.append(s('rect', {x: L, y: T, width: IW, height: IH})); defs.append(cp); svg.append(defs);
  const iso = s('g', {'clip-path': `url(#${cid})`});
  for (let k = 0.05; k <= 1.0; k += 0.05) {
    iso.append(s('line', {x1: X(x0), y1: Y((k - wc * x0) / wt), x2: X(x1), y2: Y((k - wc * x1) / wt),
      stroke: 'var(--grid)', 'stroke-width': 1, 'stroke-dasharray': '3 4'}));
  }
  svg.append(iso);
  const placed = [];
  rows.forEach(({m, q}) => {
    svg.append(s('circle', {cx: X(q.cov), cy: Y(q.tldr), r: 5.5, fill: col(m), 'fill-opacity': .85,
      stroke: '#fff', 'stroke-width': 1.5}));
    place(svg, X(q.cov), Y(q.tldr), m.model, col(m), placed);
  });
  document.getElementById('fig2').replaceChildren(svg);
  document.getElementById('cap2').textContent =
    `Each mark is a model's mean at ${budSel} minutes. Dotted lines are iso-composite: every point on one `
    + `scores the same combined value, so a model up and to the right of another beats it. Above the run of `
    + `the lines a model leads with more than it found; below it, the report buries what it has.`;
}
function tabs() {
  const box = document.getElementById('tabs'); box.replaceChildren();
  BUD.forEach(b => {
    const t = el('button', 'tab' + (b === budSel ? ' on' : ''), b + ' min');
    t.onclick = () => { budSel = b; tabs(); fig2(); };
    box.append(t);
  });
}

/* ---------- the table ---------- */
function table() {
  const t = el('table'), hd = el('tr');
  ['model', 'index'].forEach(h => hd.append(el('th', null, h)));
  BUD.forEach(b => ['cov', 'tl;dr', 'comb', 'rank'].forEach(k =>
    hd.append(el('th', null, b + 'm ' + k))));
  const thead = el('thead'); thead.append(hd); t.append(thead);
  const body = el('tbody');
  const ranks = {};
  BUD.forEach(b => {
    const have = D.models.filter(m => m.budgets[b]);
    const byCov = [...have].sort((a, c) => c.budgets[b].cov - a.budgets[b].cov);
    const byCom = [...have].sort((a, c) => c.budgets[b].comb - a.budgets[b].comb);
    ranks[b] = new Map(have.map(m => [m.model, [byCov.indexOf(m) + 1, byCom.indexOf(m) + 1]]));
  });
  [...D.models].sort((a, c) => (c.budgets[120] || c.budgets[c.top]).comb
                             - (a.budgets[120] || a.budgets[a.top]).comb).forEach(m => {
    const r = el('tr');
    const n = el('td', null, m.model);
    const i = el('i'); i.style.background = col(m); i.style.display = 'inline-block';
    i.style.width = '8px'; i.style.height = '8px'; i.style.borderRadius = '50%';
    i.style.marginRight = '6px'; n.prepend(i);
    r.append(n, el('td', null, m.eci.toFixed(1) + (m.eci_exact ? '' : ' *')));
    BUD.forEach(b => {
      const q = m.budgets[b];
      if (!q) { r.append(el('td', null, '—'), el('td', null, '—'), el('td', null, '—'), el('td', null, '—')); return; }
      r.append(el('td', null, f3(q.cov)), el('td', null, q.tldr.toFixed(2)),
               el('td', 'comb', f3(q.comb)));
      const [rc, rk] = ranks[b].get(m.model), d = rc - rk;
      r.append(el('td', d > 0 ? 'up' : d < 0 ? 'down' : '',
                  '#' + rk + (d ? (d > 0 ? ' ▲' : ' ▼') + Math.abs(d) : '')));
    });
    body.append(r);
  });
  t.append(body);
  document.getElementById('tbl').replaceChildren(t);
  document.getElementById('cap3').innerHTML =
    'Sorted by the composite at the deepest budget. <b>cov</b> is the strict score on the 38 points — '
    + D.transform + ' — <b>tl;dr</b> is the holistic 0–1 grade of the summary alone, <b>comb</b> is '
    + D.weights.cov + ' x cov + ' + D.weights.tldr + ' x tl;dr. <b>rank</b> is the composite ranking at '
    + 'that budget; the arrow is how far the model moves from where finding coverage alone would put it.';
  const note = el('div', 'note');
  note.innerHTML = '<b>Caveats.</b> ' + D.caveats.join(' ');
  document.getElementById('tbl').append(note);
}
fig1(); tabs(); fig2(); table();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
