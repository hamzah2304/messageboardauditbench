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
import json, random, re, statistics as st, sys, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "viewers"))
from paths import BENCH, CLAIMS, GRADED, VIEWERS
import figure_chrome as chrome
from report_performance import strict, NAMES as REF_NAMES

OUT = VIEWERS / "figures" / "followup_5k.html"
DATA_JSON = BENCH / "figures" / "followup_5k.json"
DATA_CSV = BENCH / "figures" / "followup_5k.csv"
GDIR = GRADED / "judge_claude_fable_5_1" / "v2"
TDIR = GRADED / "judge_claude_fable_5_1" / "tldrh"
NAMES = dict(REF_NAMES); NAMES.setdefault("openai_gpt_6_astra", "GPT-6 Astra")
RX_PARENT = re.compile(r"graded_(r4b(\d+)_(claude|codex|react)_(.+?)_rep(\d))"
                       r"(?:_served_([a-z0-9_]+?))?(?:_p[0-9a-f]+)?\.json$")
RX_FOLLOW = re.compile(r"graded_fu5kb(\d+)_(claude|codex|react)_(.+?)_rep(\d)\.json$")
# A model wears its provider's colour, the same one it wears in the headline figures, so
# the two pages can be read side by side. Identity never rests on colour alone: every mark
# is directly labelled and every value is repeated in the Numbers table.
PROVIDER = {"GPT-5.6 Sol": "openai", "GPT-5.6 Luna": "openai", "GPT-5.6 Terra": "openai",
            "GPT-6 Astra": "openai", "Gemini 3.8 Flash": "google", "Muse Spark 1.3": "meta",
            "Kimi K3": "moonshot", "GLM 5.3": "zai", "Opus 5": "anthropic",
            "Opus 4.8": "anthropic", "Sonnet 5": "anthropic", "Haiku 4.5": "anthropic"}
CAVEATS = [
    "Each follow-up expands its own parent run, so length is isolated from every other "
    "difference between models and budgets.",
    "Kimi K3 contributes six pairs and Astra ten; no model has more than seventeen, so the "
    "per-model intervals are wide and the ordering below Astra is not resolved.",
    "Heartbeats and XSS are two findings and one; cluster means over so few findings move "
    "a long way on one judgement.",
    "Scores are Fable 5.1 on the v2 sheets under the strict transform, the same measure as "
    "the headline figures.",
]
FILL = {10: 0.0, 30: 0.5, 120: 1.0}      # hollow to solid, as the headline figures do


def ci(values, n=10000, seed=5):
    """Percentile interval over a group's own matched pairs.

    Deliberately bootstrapped over pairs rather than reported as a bare mean: several
    groups here have six to ten pairs, and without the interval a two-run cell looks as
    settled as a seventeen-run one.
    """
    if len(values) < 2:
        return None, None
    rnd = random.Random(seed)
    means = sorted(st.mean(rnd.choices(values, k=len(values))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


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
    clusters = defaultdict(list)
    for c in claims.values():
        clusters[c["section"]].append(c["id"])

    # Cluster-level change for Astra against everything else. Astra gains twice what any
    # other model does, and the question is where — a cluster mean over 2-6 findings is
    # steadier than any single finding, and the comparison series says whether a gain is
    # Astra's or just what more words do.
    FOCUS = "GPT-6 Astra"
    grouped = defaultdict(lambda: defaultdict(list))
    for r in pairs:
        grp = FOCUS if r["model"] == FOCUS else "every other model"
        for sec, ids in clusters.items():
            # collect() already applied the strict transform
            before = st.mean(pc_short[r["parent"]][i] for i in ids)
            after = st.mean(pc_long[r["follow"]][i] for i in ids)
            grouped[grp][sec].append(after - before)
    cluster_delta = []
    for sec, ids in clusters.items():
        row = {"cluster": sec, "k": len(ids)}
        for grp in (FOCUS, "every other model"):
            ds = grouped[grp][sec]
            lo, hi = ci(ds)
            row[grp] = {"delta": st.mean(ds), "lo": lo, "hi": hi, "n": len(ds)}
        cluster_delta.append(row)
    cluster_delta.sort(key=lambda r: -r[FOCUS]["delta"])
    top_bottom = cluster_delta[:3] + cluster_delta[-3:]
    deltas = sorted(
        ({"id": cid, "section": claims[cid]["section"], "claim": claims[cid]["claim"],
          "short": st.mean(a for a, b in v), "long": st.mean(b for a, b in v),
          "delta": st.mean(b - a for a, b in v),
          "n_up": sum(1 for a, b in v if b > a), "n_down": sum(1 for a, b in v if b < a)}
         for cid, v in claim_delta.items()),
        key=lambda d: -d["delta"])

    by_model = defaultdict(list)
    for r in pairs:
        by_model[r["model"]].append(r["long"] - r["short"])
    model_delta = []
    for mo, ds in by_model.items():
        lo, hi = ci(ds)
        model_delta.append({"model": mo, "n": len(ds), "delta": st.mean(ds),
                            "lo": lo, "hi": hi,
                            "up": sum(1 for d in ds if d > 0), "down": sum(1 for d in ds if d < 0)})
    model_delta.sort(key=lambda m: -m["delta"])

    models = sorted({p["model"] for p in points})
    data = {"points": points, "deltas": deltas, "pairs": pairs, "model_delta": model_delta,
            "cluster_delta": cluster_delta, "top_bottom": top_bottom,
            "groups": ["GPT-6 Astra", "every other model"],
            "models": models,
            "fill": {str(k): v for k, v in FILL.items()},
            "n_pairs": len(pairs), "n_claims": len(deltas),
            "provider": PROVIDER, "caveats": CAVEATS,
            "overall": {"short": st.mean(p["short"] for p in pairs),
                        "long": st.mean(p["long"] for p in pairs),
                        "up": sum(1 for p in pairs if p["long"] > p["short"]),
                        "flat": sum(1 for p in pairs if p["long"] == p["short"]),
                        "down": sum(1 for p in pairs if p["long"] < p["short"])}}
    # Raw data beside benchmark/figures/headline_eci.{json,csv}: one row per matched pair,
    # which is the grain everything on the page is aggregated from, so anyone can rebuild
    # any of the four figures without running this script.
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    cols = ["model", "provider", "parent_budget_min", "rep", "agent", "parent_key",
            "followup_key", "recall_short", "recall_long", "recall_delta",
            "tldr_short", "tldr_long"]
    lines = [",".join(cols)]
    for r in sorted(pairs, key=lambda r: (r["model"], r["budget"], r["rep"])):
        lines.append(",".join(str(x) for x in [
            f'"{r["model"]}"', PROVIDER[r["model"]], r["budget"], r["rep"], r["agent"],
            r["parent"], r["follow"], round(r["short"], 4), round(r["long"], 4),
            round(r["long"] - r["short"], 4),
            "" if r["short_tldr"] is None else r["short_tldr"],
            "" if r["long_tldr"] is None else r["long_tldr"]]))
    DATA_CSV.write_text("\n".join(lines) + "\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    o = data["overall"]
    print(f"wrote {OUT}, {DATA_CSV.name} and {DATA_JSON.name} — {len(pairs)} matched pairs, {len(points)} model-budget cells")
    print(f"  {o['short']:.3f} -> {o['long']:.3f}  ({o['up']} up, {o['flat']} flat, {o['down']} down)")
    print("  clusters, Astra top/bottom: "
          + ", ".join(f"{r['cluster']} {r['GPT-6 Astra']['delta']:+.3f}" for r in top_bottom))
    print("  by model: " + ", ".join(f"{m['model']} {m['delta']:+.3f}" for m in model_delta[:3])
          + f" ... {model_delta[-1]['model']} {model_delta[-1]['delta']:+.3f}")
    print(f"  biggest claim gains: " + ", ".join(f"{d['id']} {d['delta']:+.3f}" for d in deltas[:4]))
    print(f"  unmoved: " + ", ".join(d["id"] for d in deltas if abs(d["delta"]) < 0.005))
COPY = ('<button class="csv" data-csv="%s">copy CSV</button>'
        '<span>or benchmark/figures/followup_5k.csv</span>')

BODY = """<main>
  <h1>What another 2,000 words buys</h1>
  <p class="lede" id="lede"></p>
  <div class="hero" id="hero"></div>
__FIGS__
  <details><summary>Caveats</summary><ul class="cav" id="cav"></ul></details>
</main>"""

FIGS = "\n\n".join([
    chrome.figure(1, "Twice the length, almost the same report", "fig1",
                  legend_id="leg1", table_id="tbl1", notes_id="notes1",
                  tools=COPY % "cells"),
    chrome.figure(2, "Only Astra gains more than a rounding error", "fig3",
                  table_id="tbl3", tools=COPY % "models"),
    chrome.figure(3, "Astra&rsquo;s gains are mechanism, not attribution", "fig4",
                  legend_id="leg4", table_id="tbl4", tools=COPY % "clusters"),
    chrome.figure(4, "What the extra length surfaced, finding by finding", "fig2",
                  table_id="tbl2", tools=COPY % "findings"),
])

JS = r"""
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const s = (t, a) => { const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c;
  if (x != null) e.textContent = x; return e; };
const f3 = v => v == null ? '—' : v.toFixed(3);
const col = m => `var(--p-${D.provider[m]})`;
/* the two-series cluster figure: the focus model in its provider colour, the rest neutral */
const gcol = g => g === D.groups[0] ? col(D.groups[0]) : 'var(--ink3)';

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
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'tick'}));
    svg.append(s('line', {x1: X(v), x2: X(v), y1: T, y2: T + IH, class: 'tick'}));
    const a = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'axis num', 'text-anchor': 'end'});
    a.textContent = v.toFixed(2); svg.append(a);
    const b = s('text', {x: X(v), y: T + IH + 17, class: 'axis num', 'text-anchor': 'middle'});
    b.textContent = v.toFixed(2); svg.append(b);
  }
  /* the line of no change: a mark above it gained, below it lost */
  svg.append(s('line', {x1: X(lo), y1: Y(lo), x2: X(hi), y2: Y(hi),
    stroke: 'var(--ink2)', 'stroke-width': 1, 'stroke-dasharray': '4 4', opacity: .55}));
  const nc = s('text', {x: X(hi) - 4, y: Y(hi) + 14, class: 'axis num', 'text-anchor': 'end'});
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
    const t = s('text', {x: colX, y: ly, class: 'lab'});
    t.textContent = `${p.model} · ${p.budget}m`; svg.append(t);
  });
  document.getElementById('fig1').replaceChildren(svg);
  const leg = document.getElementById('leg1'); leg.replaceChildren();
  /* colour is the provider, not the model — four OpenAI models share a hue, and listing
     them separately in the legend would imply the reader can tell them apart by colour.
     Every mark carries its own label, which is what identifies it. */
  [...new Set(D.models.map(m => D.provider[m]))].sort().forEach(pv => {
    const sp = el('span'); const i = el('i'); i.style.background = `var(--p-${pv})`;
    sp.append(i, document.createTextNode(pv)); leg.append(sp);
  });
  [10, 30, 120].forEach(b => {
    const sp = el('span'); const sv = s('svg', {width: 15, height: 15, style: 'vertical-align:-3px'});
    sv.append(s('circle', {cx: 7.5, cy: 7.5, r: 5.5, fill: 'var(--ink2)',
      'fill-opacity': D.fill[b], stroke: 'var(--ink2)', 'stroke-width': 2}));
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
    svg.append(s('line', {x1: X(v), x2: X(v), y1: T, y2: T + rows.length * rowH, class: 'tick'}));
    const t = s('text', {x: X(v), y: H - B + 18, class: 'axis num', 'text-anchor': 'middle'});
    t.textContent = '+' + v.toFixed(2); svg.append(t);
  }
  rows.forEach((r, i) => {
    const y = T + i * rowH;
    /* one series, so one hue; the bar's length is the whole message */
    const w = Math.max(0, X(r.delta) - X(0));   /* three findings move by -0.003; drawn as nil */
    svg.append(s('rect', {x: X(0), y: y + 2, width: Math.max(w, 0.4), height: rowH - 5,
      fill: 'var(--p-openai)', 'fill-opacity': r.delta < 0.005 ? .22 : .85, rx: 2}));
    const id = s('text', {x: L - 8, y: y + rowH - 4, class: 'lab', 'text-anchor': 'end'});
    id.textContent = `${r.id}  ${r.section}`; svg.append(id);
    const lab = s('text', {x: Math.max(X(r.delta), X(0)) + 8, y: y + rowH - 4, class: 'lab'});
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

/* ---------- Figure 4: Astra's best and worst clusters ---------- */
function fig4() {
  const rows = D.top_bottom, G = D.groups;
  const W = 1080, H = 400, L = 62, R = 20, T = 26, B = 74;
  const IW = W - L - R, IH = H - T - B, band = IW / rows.length;
  const all = rows.flatMap(r => G.flatMap(g => [r[g].lo, r[g].hi, r[g].delta]));
  const lo = Math.min(0, ...all) - 0.005, hi = Math.max(...all) + 0.012;
  const Y = v => T + IH - (v - lo) / (hi - lo) * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': "Astra's best and worst three clusters against every other model"});
  for (let v = Math.ceil(lo / 0.05) * 0.05; v <= hi + 1e-9; v += 0.05) {
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'tick'}));
    const t = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'axis num', 'text-anchor': 'end'});
    t.textContent = (v > 0 ? '+' : '') + v.toFixed(2); svg.append(t);
  }
  svg.append(s('line', {x1: L, x2: L + IW, y1: Y(0), y2: Y(0),
    stroke: 'var(--ink2)', 'stroke-width': 1, opacity: .5}));
  /* the three best and the three worst sit next to each other, so mark the seam */
  const seam = L + band * 3;
  svg.append(s('line', {x1: seam, x2: seam, y1: T, y2: T + IH, stroke: 'var(--line)',
    'stroke-width': 1, 'stroke-dasharray': '3 3'}));
  const ay = s('text', {x: 15, y: T + IH / 2, class: 'axname', 'text-anchor': 'middle',
    transform: `rotate(-90 15 ${T + IH / 2})`});
  ay.textContent = 'mean change in strict recall'; svg.append(ay);

  const bw = Math.min(band * 0.36, 44);
  rows.forEach((r, i) => {
    const cx = L + band * (i + 0.5);
    G.forEach((g, j) => {
      const x = cx + (j === 0 ? -bw - 2 : 2), v = r[g].delta;
      const top = Y(Math.max(v, 0)), bot = Y(Math.min(v, 0));
      svg.append(s('rect', {x, y: top, width: bw, height: Math.max(bot - top, 1),
        fill: gcol(g), 'fill-opacity': .85, rx: 3}));
      const mx = x + bw / 2;
      if (r[g].lo != null) {
        svg.append(s('line', {x1: mx, x2: mx, y1: Y(r[g].lo), y2: Y(r[g].hi),
          stroke: 'var(--ink)', 'stroke-width': 1.1, opacity: .5}));
        [r[g].lo, r[g].hi].forEach(w => svg.append(s('line', {x1: mx - 4, x2: mx + 4,
          y1: Y(w), y2: Y(w), stroke: 'var(--ink)', 'stroke-width': 1.1, opacity: .5})));
      }
      const t = s('text', {x: mx, y: Y(Math.max(v, 0)) - 6, class: 'lab', 'text-anchor': 'middle',
        stroke: 'var(--surface)', 'stroke-width': 3, 'paint-order': 'stroke',
        'stroke-linejoin': 'round'});
      t.textContent = (v >= 0 ? '+' : '') + v.toFixed(3); svg.append(t);
    });
    const nm = s('text', {x: cx, y: T + IH + 18, class: 'lab', 'text-anchor': 'middle'});
    nm.textContent = r.cluster; svg.append(nm);
    const k = s('text', {x: cx, y: T + IH + 31, class: 'axis num', 'text-anchor': 'middle'});
    k.textContent = `${r.k} finding${r.k > 1 ? 's' : ''}`; svg.append(k);
  });
  ['Astra\u2019s best three', 'and worst three'].forEach((txt, i) => {
    const t = s('text', {x: L + band * (i ? 4.5 : 1.5), y: T - 8, class: 'axis num',
      'text-anchor': 'middle'});
    t.textContent = txt; svg.append(t);
  });
  document.getElementById('fig4').replaceChildren(svg);
  const leg = document.getElementById('leg4'); leg.replaceChildren();
  G.forEach(g => { const sp = el('span'); const i = el('i');
    i.style.background = gcol(g); sp.append(i, document.createTextNode(g)); leg.append(sp); });
  document.getElementById('cap4').textContent =
    `The three clusters Astra gained most on and the three it gained least on, each against every `
    + `other model on the same cluster. Whiskers are 95% percentile intervals over the matched pairs `
    + `in each group (Astra ${rows[0][G[0]].n}, others ${rows[0][G[1]].n}). Astra's gains are in `
    + `mechanism the other models cannot move; what it does not gain on is who the agents were.`;
}

/* ---------- Figure 3: average delta per model ---------- */
function fig3() {
  const rows = D.model_delta;
  const W = 1080, H = 400, L = 62, R = 20, T = 26, B = 76;
  const IW = W - L - R, IH = H - T - B, band = IW / rows.length;
  const lo = Math.min(0, ...rows.map(r => r.lo == null ? r.delta : r.lo)) - 0.005;
  const hi = Math.max(...rows.map(r => r.hi == null ? r.delta : r.hi)) + 0.008;
  const Y = v => T + IH - (v - lo) / (hi - lo) * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'average change in recall per model'});
  for (let v = Math.ceil(lo / 0.02) * 0.02; v <= hi + 1e-9; v += 0.02) {
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'tick'}));
    const t = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'axis num', 'text-anchor': 'end'});
    t.textContent = (v > 0 ? '+' : '') + v.toFixed(2); svg.append(t);
  }
  svg.append(s('line', {x1: L, x2: L + IW, y1: Y(0), y2: Y(0),
    stroke: 'var(--ink2)', 'stroke-width': 1, opacity: .5}));
  const ay = s('text', {x: 15, y: T + IH / 2, class: 'axname', 'text-anchor': 'middle',
    transform: `rotate(-90 15 ${T + IH / 2})`});
  ay.textContent = 'mean change in strict recall'; svg.append(ay);

  rows.forEach((r, i) => {
    const cx = L + band * (i + 0.5), bw = Math.min(band * 0.82, 100);
    const top = Y(Math.max(r.delta, 0)), bot = Y(Math.min(r.delta, 0));
    /* a 4px rounded end sits at the value; the bar is anchored to the zero line */
    svg.append(s('rect', {x: cx - bw / 2, y: top, width: bw, height: Math.max(bot - top, 1),
      fill: col(r.model), 'fill-opacity': .85, rx: 4}));
    if (r.lo != null) {   /* 95% percentile interval over that model's own runs */
      svg.append(s('line', {x1: cx, x2: cx, y1: Y(r.lo), y2: Y(r.hi),
        stroke: 'var(--ink)', 'stroke-width': 1.2, opacity: .55}));
      [r.lo, r.hi].forEach(v => svg.append(s('line', {x1: cx - 5, x2: cx + 5, y1: Y(v), y2: Y(v),
        stroke: 'var(--ink)', 'stroke-width': 1.2, opacity: .55})));
    }
    /* the value sits on the bar, not on top of the whisker: Kimi's interval is ten times
       its bar, and a label floating at the whisker's end reads as a tall bar */
    const val = s('text', {x: cx, y: Y(Math.max(r.delta, 0)) - 7, class: 'lab',
      'text-anchor': 'middle', stroke: 'var(--surface)', 'stroke-width': 3,
      'paint-order': 'stroke', 'stroke-linejoin': 'round'});
    val.textContent = (r.delta >= 0 ? '+' : '') + r.delta.toFixed(3); svg.append(val);
    /* model names are long for eight bands, so they wrap rather than tilt */
    const parts = r.model.split(' ');
    const lines = parts.length > 2 ? [parts.slice(0, -1).join(' '), parts[parts.length - 1]] : [r.model];
    lines.forEach((ln, k) => {
      const t = s('text', {x: cx, y: T + IH + 18 + k * 12, class: 'lab', 'text-anchor': 'middle'});
      t.textContent = ln; svg.append(t);
    });
    const n = s('text', {x: cx, y: T + IH + 18 + lines.length * 12 + 2, class: 'axis num',
      'text-anchor': 'middle'});
    n.textContent = `${r.up}/${r.n} up`; svg.append(n);
  });
  document.getElementById('fig3').replaceChildren(svg);
  document.getElementById('cap3').textContent =
    `One bar per model: the mean of (long - short) over that model's own matched pairs, so each `
    + `model is its own control. Whiskers are a 95% percentile interval bootstrapped over those `
    + `pairs - wide, because no model has more than ${Math.max(...rows.map(r => r.n))} of them. `
    + `Seven of the eight intervals exclude zero, but only Astra's sits clear of the rest; the `
    + `others are a cluster around +0.02 that these sample sizes cannot separate. Kimi K3's `
    + `spans zero - six pairs, one of which swings hard.`;
}

/* ---------- Numbers tables, one per figure, and copy-CSV ---------- */
function table(mount, cols, rows) {
  const t = el('table'), head = el('tr');
  cols.forEach((c, i) => head.append(el('th', i === 0 ? 'l' : '', c)));
  const th = el('thead'); th.append(head); t.append(th);
  const tb = el('tbody');
  rows.forEach(r => { const tr = el('tr');
    r.forEach((v, i) => tr.append(el('td', i === 0 ? 'l' : 'num', v))); tb.append(tr); });
  t.append(tb);
  document.getElementById(mount).replaceChildren(t);
}
const CSV = {};
function csv(name, cols, rows) {
  CSV[name] = [cols.join(','), ...rows.map(r => r.map(v =>
    /[",]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : v).join(','))].join('\n');
}
function wireCopy() {
  document.querySelectorAll('button.csv').forEach(b => {
    b.onclick = () => {
      navigator.clipboard.writeText(CSV[b.dataset.csv] || '').then(
        () => { const was = b.textContent; b.textContent = 'copied';
                setTimeout(() => { b.textContent = was; }, 1200); }).catch(() => {});
    };
  });
}

function tables() {
  const cells = D.points.slice().sort((a, b) => (b.long - b.short) - (a.long - a.short))
    .map(p => [p.model, p.budget + 'm', p.n, f3(p.short), f3(p.long),
               (p.long - p.short >= 0 ? '+' : '') + (p.long - p.short).toFixed(3)]);
  table('tbl1', ['model', 'budget', 'runs', 'short', 'long', 'delta'], cells);
  csv('cells', ['model', 'budget_min', 'runs', 'recall_short', 'recall_long', 'delta'],
      D.points.map(p => [p.model, p.budget, p.n, p.short.toFixed(4), p.long.toFixed(4),
                         (p.long - p.short).toFixed(4)]));

  const md = D.model_delta.map(m => [m.model, m.n, (m.delta >= 0 ? '+' : '') + m.delta.toFixed(3),
    m.lo == null ? '—' : `${m.lo >= 0 ? '+' : ''}${m.lo.toFixed(3)}, ${m.hi >= 0 ? '+' : ''}${m.hi.toFixed(3)}`,
    `${m.up}/${m.n}`]);
  table('tbl3', ['model', 'pairs', 'delta', '95% CI', 'improved'], md);
  csv('models', ['model', 'pairs', 'delta', 'ci_low', 'ci_high', 'n_improved', 'n_worse'],
      D.model_delta.map(m => [m.model, m.n, m.delta.toFixed(4),
        m.lo == null ? '' : m.lo.toFixed(4), m.hi == null ? '' : m.hi.toFixed(4), m.up, m.down]));

  const G = D.groups;
  table('tbl4', ['cluster', 'findings', G[0], '95% CI', G[1], '95% CI'],
    D.cluster_delta.map(r => [r.cluster, r.k,
      (r[G[0]].delta >= 0 ? '+' : '') + r[G[0]].delta.toFixed(3),
      r[G[0]].lo == null ? '—' : `${r[G[0]].lo.toFixed(3)}, ${r[G[0]].hi.toFixed(3)}`,
      (r[G[1]].delta >= 0 ? '+' : '') + r[G[1]].delta.toFixed(3),
      r[G[1]].lo == null ? '—' : `${r[G[1]].lo.toFixed(3)}, ${r[G[1]].hi.toFixed(3)}`]));
  csv('clusters', ['cluster', 'findings', 'group', 'delta', 'ci_low', 'ci_high', 'pairs'],
      D.cluster_delta.flatMap(r => G.map(g => [r.cluster, r.k, g, r[g].delta.toFixed(4),
        r[g].lo == null ? '' : r[g].lo.toFixed(4), r[g].hi == null ? '' : r[g].hi.toFixed(4), r[g].n])));

  table('tbl2', ['finding', 'cluster', 'short', 'long', 'delta', 'up', 'down'],
    D.deltas.map(r => [r.id + ' · ' + r.claim, r.section, f3(r.short), f3(r.long),
      (r.delta >= 0 ? '+' : '') + r.delta.toFixed(3), r.n_up, r.n_down]));
  csv('findings', ['finding', 'cluster', 'claim', 'recall_short', 'recall_long', 'delta', 'n_up', 'n_down'],
      D.deltas.map(r => [r.id, r.section, r.claim, r.short.toFixed(4), r.long.toFixed(4),
        r.delta.toFixed(4), r.n_up, r.n_down]));

  const cav = document.getElementById('cav'); cav.replaceChildren();
  D.caveats.forEach(c => cav.append(el('li', null, c)));
}

fig1(); fig3(); fig4(); fig2(); tables(); wireCopy();
"""

TEMPLATE = (chrome.shell("What another 2,000 words buys", BODY.replace("__FIGS__", FIGS))
            + "<script>\n" + JS + "\n</script>\n</body></html>\n")

if __name__ == "__main__":
    main()
