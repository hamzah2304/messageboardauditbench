#!/usr/bin/env python3
"""Build viewers/figures/followup_5k.html — what another 2,000 words buys.

Every model was handed back its own 2,500-3,000 word report and asked to expand it to
4,500-5,000, with the data unchanged and no extra investigation time. So each follow-up
has a natural control: the run it came from. That makes this a within-run before/after
rather than a comparison between models, and it isolates length from everything else.

Three panels:
  1. recall on the short report against recall on the long one, one mark per
     model-and-budget cell, with the line of no change. Points below it lost ground.
  2. the 38 findings ranked by how much the extra length surfaced them.
  3. the numbers.

Scores are Fable 5.1 on the v2 sheets, strict-transformed — max(2s - 1, 0) then the mean
over findings — the same measure as the headline figures.
"""
import json, re, statistics as st, sys, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from paths import CLAIMS, GRADED, VIEWERS
from report_performance import strict, NAMES as REF_NAMES

OUT = VIEWERS / "figures" / "followup_5k.html"
GDIR = GRADED / "judge_claude_fable_5_1" / "v2"
TDIR = GRADED / "judge_claude_fable_5_1" / "tldrh"
NAMES = dict(REF_NAMES); NAMES.setdefault("openai_gpt_6_astra", "GPT-6 Astra")
RX_PARENT = re.compile(r"graded_(r4b(\d+)_(claude|codex|react)_(.+?)_rep(\d))"
                       r"(?:_served_([a-z0-9_]+?))?(?:_p[0-9a-f]+)?\.json$")
RX_FOLLOW = re.compile(r"graded_fu5kb(\d+)_(claude|codex|react)_(.+?)_rep(\d)\.json$")
# validated with dataviz/scripts/validate_palette.js --mode light: lightness, chroma,
# normal-vision separation and contrast all pass; CVD adjacency sits at dE 7.0, which is
# legal only with secondary encoding, so every mark is also directly labelled and the
# table repeats every value.
PALETTE = ["#B4442F", "#2C63C8", "#2F8F45", "#C21E7B", "#1187A5", "#9A5F0A", "#7A4FCB", "#C77C00"]
FILL = {10: 0.0, 30: 0.5, 120: 1.0}      # hollow to solid, as the headline figures do


def scores(path, want_max):
    g = json.loads(path.read_text())
    return g if g.get("max") == want_max else None


def collect(gdir, want_max, transform):
    """(report key -> {claim: score}, report key -> report mean)."""
    per_claim, mean = {}, {}
    for p in sorted(gdir.glob("graded_*.json")):
        g = scores(p, want_max)
        if not g:
            continue
        vals = {k: transform(v["score"]) for k, v in g["scores"].items()}
        per_claim[g["report"]] = vals
        mean[g["report"]] = st.mean(vals.values())
    return per_claim, mean


def main():
    pc_short, m_short = collect(GDIR, 38, strict)
    pc_long, m_long = collect(GDIR, 38, strict)
    t_short = {k: v for k, v in collect(TDIR, 1, lambda s: s)[1].items()}

    pairs = []          # one row per matched run
    claim_delta = defaultdict(list)
    for key, follow_mean in m_long.items():
        m = RX_FOLLOW.match(f"graded_{key}.json")
        if not m:
            continue
        budget, agent, model, rep = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        parent = f"r4b{budget}_{agent}_{model}_rep{rep}"
        if parent not in m_short:
            continue
        pairs.append({"model": NAMES.get(model, model), "budget": budget, "rep": int(rep),
                      "agent": agent, "short": m_short[parent], "long": follow_mean,
                      "short_tldr": t_short.get(parent), "long_tldr": t_short.get(key),
                      "parent": parent, "follow": key})
        for cid, val in pc_long[key].items():
            claim_delta[cid].append((pc_short[parent][cid], val))

    if not pairs:
        raise SystemExit("no matched follow-up/parent pairs — is the grading finished?")

    cells = defaultdict(list)
    for r in pairs:
        cells[(r["model"], r["budget"])].append(r)
    points = [{"model": mo, "budget": b, "n": len(v),
               "short": st.mean(x["short"] for x in v), "long": st.mean(x["long"] for x in v),
               "runs": sorted(v, key=lambda x: x["rep"])}
              for (mo, b), v in sorted(cells.items())]

    claims = {c["id"]: c for c in json.loads((CLAIMS / "claims_v2.json").read_text())["claims"]}
    deltas = sorted(
        ({"id": cid, "section": claims[cid]["section"], "claim": claims[cid]["claim"],
          "short": st.mean(a for a, b in v), "long": st.mean(b for a, b in v),
          "delta": st.mean(b - a for a, b in v),
          "n_up": sum(1 for a, b in v if b > a), "n_down": sum(1 for a, b in v if b < a)}
         for cid, v in claim_delta.items()),
        key=lambda d: -d["delta"])

    models = sorted({p["model"] for p in points})
    data = {"points": points, "deltas": deltas, "pairs": pairs,
            "models": models, "colours": {m: PALETTE[i % len(PALETTE)] for i, m in enumerate(models)},
            "fill": {str(k): v for k, v in FILL.items()},
            "n_pairs": len(pairs), "n_claims": len(deltas),
            "overall": {"short": st.mean(p["short"] for p in pairs),
                        "long": st.mean(p["long"] for p in pairs),
                        "up": sum(1 for p in pairs if p["long"] > p["short"]),
                        "flat": sum(1 for p in pairs if p["long"] == p["short"]),
                        "down": sum(1 for p in pairs if p["long"] < p["short"])}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    o = data["overall"]
    print(f"wrote {OUT} — {len(pairs)} matched pairs, {len(points)} model-budget cells")
    print(f"  {o['short']:.3f} -> {o['long']:.3f}  ({o['up']} up, {o['flat']} flat, {o['down']} down)")
    print(f"  biggest claim gains: " + ", ".join(f"{d['id']} {d['delta']:+.3f}" for d in deltas[:4]))
    print(f"  unmoved: " + ", ".join(d["id"] for d in deltas if abs(d["delta"]) < 0.005))
TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>What another 2,000 words buys</title>
<style>
:root{--bg:#F4F3EE;--card:#FFF;--bd:#E0DDD4;--ink:#1A1A1A;--sec:#666;--mut:#999;
--acc:#C15F3C;--soft:#FDF2EC;--row:#FAFAF7;--grid:#EDEAE2}
*{box-sizing:border-box}
body{margin:0 auto;max-width:1180px;padding:26px 30px 60px;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px}
h1{font-size:21px;color:var(--acc);margin:0 0 4px}
h2{font-size:15px;color:var(--acc);margin:0 0 10px}
.sub{color:var(--sec);margin:0 0 22px;line-height:1.55;max-width:80ch}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:18px 20px;margin-bottom:20px}
.cap{color:var(--sec);font-size:12.5px;line-height:1.5;margin:10px 0 0;max-width:92ch}
svg{display:block;width:100%;height:auto;overflow:visible}
.axname{font-size:11px;fill:var(--sec)}
.tick{font-size:10px;fill:var(--mut)}
.mlab{font-size:10px;fill:var(--ink)}
.gl{stroke:var(--grid);stroke-width:1}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:12px;color:var(--sec);align-items:center}
.legend span{display:inline-flex;align-items:center;gap:5px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:5px 7px;border-bottom:1px solid var(--bd);text-align:right;vertical-align:top}
th:first-child,td:first-child,th.l,td.l{text-align:left;font-variant-numeric:normal}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);font-weight:600}
tbody tr:hover{background:var(--row)}
td.d{font-weight:700;color:var(--acc)}
td.zero{color:var(--mut);font-weight:400}
.hero{display:flex;gap:34px;flex-wrap:wrap;margin-bottom:18px}
.hero div{min-width:150px}
.hero b{display:block;font-size:26px;color:var(--acc);font-variant-numeric:tabular-nums;line-height:1.1}
.hero span{font-size:12px;color:var(--sec)}
</style></head>
<body>
<h1>What another 2,000 words buys</h1>
<p class="sub" id="lede"></p>
<div class="hero" id="hero"></div>
<div class="panel"><h2>The short report against the long one</h2><div id="fig1"></div>
  <div class="legend" id="leg1"></div><p class="cap" id="cap1"></p></div>
<div class="panel"><h2>Which findings the extra length surfaced</h2><div id="fig2"></div>
  <p class="cap" id="cap2"></p></div>
<div class="panel"><h2>Every finding</h2><div id="tbl2"></div></div>
<div class="panel"><h2>Every cell</h2><div id="tbl1"></div></div>
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
const col = m => D.colours[m];

const o = D.overall;
document.getElementById('lede').textContent =
  `Each model was handed back its own 2,500–3,000 word report and asked to expand it to 4,500–5,000, `
  + `with the data unchanged and no extra investigation time. Every follow-up is therefore matched to `
  + `the run it came from: ${D.n_pairs} pairs. Scores are Fable 5.1 on the 38 findings, strict.`;
[["+" + (o.long - o.short).toFixed(3), "mean change in recall"],
 [o.short.toFixed(3) + " → " + o.long.toFixed(3), "short report → long report"],
 [`${o.up} / ${o.flat} / ${o.down}`, "runs better / unchanged / worse"],
 [D.deltas.filter(d => Math.abs(d.delta) < 0.005).length + " of " + D.n_claims, "findings that did not move"]
].forEach(([b, t]) => { const d = el('div'); d.append(el('b', null, b), el('span', null, t));
  document.getElementById('hero').append(d); });

/* ---------- Figure 1: short against long ---------- */
function fig1() {
  const W = 1080, H = 560, L = 62, R = 215, T = 16, B = 46;
  const IW = W - L - R, IH = H - T - B;
  const vals = D.points.flatMap(p => [p.short, p.long]);
  const lo = Math.max(0, Math.floor(Math.min(...vals) * 20) / 20 - 0.02);
  const hi = Math.ceil(Math.max(...vals) * 20) / 20 + 0.02;
  const X = v => L + (v - lo) / (hi - lo) * IW, Y = v => T + IH - (v - lo) / (hi - lo) * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'recall on the long report against recall on the short report'});
  for (let v = Math.ceil(lo * 20) / 20; v <= hi + 1e-9; v += 0.05) {
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'gl'}));
    svg.append(s('line', {x1: X(v), x2: X(v), y1: T, y2: T + IH, class: 'gl'}));
    const a = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'tick', 'text-anchor': 'end'});
    a.textContent = v.toFixed(2); svg.append(a);
    const b = s('text', {x: X(v), y: T + IH + 17, class: 'tick', 'text-anchor': 'middle'});
    b.textContent = v.toFixed(2); svg.append(b);
  }
  /* the line of no change: a mark above it gained, below it lost */
  svg.append(s('line', {x1: X(lo), y1: Y(lo), x2: X(hi), y2: Y(hi),
    stroke: 'var(--sec)', 'stroke-width': 1, 'stroke-dasharray': '4 4', opacity: .55}));
  const nc = s('text', {x: X(hi) - 4, y: Y(hi) + 14, class: 'tick', 'text-anchor': 'end'});
  nc.textContent = 'no change'; svg.append(nc);
  const ax = s('text', {x: L + IW / 2, y: H - 8, class: 'axname', 'text-anchor': 'middle'});
  ax.textContent = 'recall on the 2,500–3,000 word report'; svg.append(ax);
  const ay = s('text', {x: 15, y: T + IH / 2, class: 'axname', 'text-anchor': 'middle',
    transform: `rotate(-90 15 ${T + IH / 2})`});
  ay.textContent = 'recall on the 4,500–5,000 word report'; svg.append(ay);

  /* Twenty-four marks in a narrow diagonal band: labels placed beside their own mark
     collide and the nudged ones drift far enough to look attached to a neighbour. So the
     labels go in a column down the right margin, ordered by the mark's height and spaced
     evenly, each with a leader back to its point. */
  const marks = D.points.slice().sort((a, b) => b.long - a.long);
  const GAP = 14, colX = L + IW + 16;
  const slots = marks.map(p => Y(p.long));
  for (let i = 1; i < slots.length; i++)
    if (slots[i] - slots[i - 1] < GAP) slots[i] = slots[i - 1] + GAP;
  const overflow = slots[slots.length - 1] - (T + IH);
  if (overflow > 0) for (let i = 0; i < slots.length; i++) slots[i] -= overflow;
  for (let i = slots.length - 2; i >= 0; i--)
    if (slots[i + 1] - slots[i] < GAP) slots[i] = slots[i + 1] - GAP;
  marks.forEach((p, i) => {
    const c = col(p.model), x = X(p.short), y = Y(p.long), ly = slots[i];
    svg.append(s('path', {d: `M${x + 7},${y} L${colX - 24},${y} L${colX - 8},${ly - 3.5} L${colX - 3},${ly - 3.5}`,
      fill: 'none', stroke: c, 'stroke-width': .9, opacity: .35}));
    svg.append(s('circle', {cx: x, cy: y, r: 6, fill: c, 'fill-opacity': D.fill[p.budget],
      stroke: c, 'stroke-width': 2}));
    const t = s('text', {x: colX, y: ly, class: 'mlab'});
    t.textContent = `${p.model} · ${p.budget}m`; svg.append(t);
  });
  document.getElementById('fig1').replaceChildren(svg);
  const leg = document.getElementById('leg1'); leg.replaceChildren();
  D.models.forEach(m => { const sp = el('span'); const i = el('i');
    i.style.background = col(m); sp.append(i, document.createTextNode(m)); leg.append(sp); });
  [10, 30, 120].forEach(b => {
    const sp = el('span'); const sv = s('svg', {width: 15, height: 15, style: 'vertical-align:-3px'});
    sv.append(s('circle', {cx: 7.5, cy: 7.5, r: 5.5, fill: 'var(--sec)',
      'fill-opacity': D.fill[b], stroke: 'var(--sec)', 'stroke-width': 2}));
    sp.append(sv, document.createTextNode(b + ' min')); leg.append(sp);
  });
  document.getElementById('cap1').textContent =
    `One mark per model and time budget; hollow to solid is 10, 30 and 120 minutes. Colour is the `
    + `model and every mark is labelled, so identity never rests on colour alone. The dashed line is `
    + `no change — a mark above it gained recall from the extra length. Both axes are the strict score `
    + `over the 38 findings.`;
}

/* ---------- Figure 2: claim deltas ---------- */
function fig2() {
  const rows = D.deltas;
  const rowH = 15, W = 1080, L = 210, R = 300, T = 14, B = 34;
  const H = T + rows.length * rowH + B, IW = W - L - R;
  const hi = Math.max(...rows.map(r => r.delta), 0.02);
  const X = v => L + v / hi * IW;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'findings ranked by how much the extra length surfaced them'});
  for (let v = 0; v <= hi + 1e-9; v += 0.02) {
    svg.append(s('line', {x1: X(v), x2: X(v), y1: T, y2: T + rows.length * rowH, class: 'gl'}));
    const t = s('text', {x: X(v), y: H - B + 18, class: 'tick', 'text-anchor': 'middle'});
    t.textContent = '+' + v.toFixed(2); svg.append(t);
  }
  rows.forEach((r, i) => {
    const y = T + i * rowH;
    /* one series, so one hue; the bar's length is the whole message */
    const w = Math.max(0, X(r.delta) - X(0));   /* three findings move by -0.003; drawn as nil */
    svg.append(s('rect', {x: X(0), y: y + 2, width: Math.max(w, 0.4), height: rowH - 5,
      fill: 'var(--acc)', 'fill-opacity': r.delta < 0.005 ? .22 : .85, rx: 2}));
    const id = s('text', {x: L - 8, y: y + rowH - 4, class: 'mlab', 'text-anchor': 'end'});
    id.textContent = `${r.id}  ${r.section}`; svg.append(id);
    const lab = s('text', {x: Math.max(X(r.delta), X(0)) + 8, y: y + rowH - 4, class: 'mlab'});
    lab.textContent = `${Math.abs(r.delta) < 0.005 ? 'no change' :
      (r.delta > 0 ? '+' : '') + r.delta.toFixed(3)} · `
      + `${r.short.toFixed(2)}→${r.long.toFixed(2)}`;
    svg.append(lab);
  });
  const ax = s('text', {x: L + IW / 2, y: H - 4, class: 'axname', 'text-anchor': 'middle'});
  ax.textContent = 'change in strict recall for that finding'; svg.append(ax);
  document.getElementById('fig2').replaceChildren(svg);
  document.getElementById('cap2').textContent =
    `All ${D.n_claims} findings, ranked. Faded bars are findings that moved by less than 0.005, `
    + `three of them fractionally negative (-0.003, one run each). What the extra length added was `
    + `task structure and mechanism. What it did not move is as clear: the inferences — who the `
    + `agents were (N09, N10), and why the activity stopped (N38) — sit flat at the bottom.`;
}

/* ---------- tables ---------- */
function tables() {
  const t2 = el('table'), h2 = el('tr');
  ['finding', 'cluster', 'short', 'long', 'delta', 'up', 'down'].forEach((h, i) => {
    const th = el('th', i < 2 ? 'l' : '', h); h2.append(th); });
  const th2 = el('thead'); th2.append(h2); t2.append(th2);
  const b2 = el('tbody');
  D.deltas.forEach(r => {
    const tr = el('tr');
    tr.append(el('td', 'l', r.id + ' · ' + r.claim), el('td', 'l', r.section),
      el('td', null, f3(r.short)), el('td', null, f3(r.long)),
      el('td', Math.abs(r.delta) < 0.005 ? 'zero' : 'd',
         (r.delta >= 0 ? '+' : '') + r.delta.toFixed(3)),
      el('td', null, r.n_up), el('td', null, r.n_down));
    b2.append(tr);
  });
  t2.append(b2); document.getElementById('tbl2').replaceChildren(t2);

  const t1 = el('table'), h1 = el('tr');
  ['model', 'budget', 'runs', 'short', 'long', 'delta'].forEach((h, i) =>
    h1.append(el('th', i < 1 ? 'l' : '', h)));
  const th1 = el('thead'); th1.append(h1); t1.append(th1);
  const b1 = el('tbody');
  D.points.slice().sort((a, b) => (b.long - b.short) - (a.long - a.short)).forEach(p => {
    const tr = el('tr');
    const n = el('td', 'l', p.model); const i = el('i');
    i.style.cssText = `display:inline-block;width:8px;height:8px;border-radius:50%;
      margin-right:6px;background:${col(p.model)}`;
    n.prepend(i);
    tr.append(n, el('td', null, p.budget + 'm'), el('td', null, p.n),
      el('td', null, f3(p.short)), el('td', null, f3(p.long)),
      el('td', 'd', (p.long - p.short >= 0 ? '+' : '') + (p.long - p.short).toFixed(3)));
    b1.append(tr);
  });
  t1.append(b1); document.getElementById('tbl1').replaceChildren(t1);
}
fig1(); fig2(); tables();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
