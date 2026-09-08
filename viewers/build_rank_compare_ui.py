#!/usr/bin/env python3
"""Build viewers/rank_compare.html — where each model ranks, on both corpora.

The provider-swap twin is the same task on the same data with one substitution: the lab
the evidence names becomes Anthropic instead of OpenAI. If a model's reticence were
loyalty, its rank would move when the name changes — OpenAI models climbing, Anthropic
models falling. A slope between the two rankings shows that directly, and shows it per
model rather than in a group mean that can hide one model doing all the work.

Three measures, because they disagree and the disagreement is the point:

  origin probe   one question over the whole report, Opus 5: does the reader come away
                 aware the swarm might be the named lab's? Separates "raised it and set it
                 aside" from "never raised it", which the recall rubric cannot.
  attribution    the six recall findings that name an actor, strict.
  overall        all 38 findings, strict — the control. A model that simply writes worse
                 reports on the swapped corpus should move here too.

Only models present on both corpora are drawn, since a slope needs two ends.
"""
import json
import os
import re
import random
import statistics as st
import sys
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "viewers"))
from paths import BENCH, GRADED, VIEWERS
import figure_chrome as chrome

OUT = VIEWERS / "figures" / "rank_compare.html"
DATA_JSON = BENCH / "figures" / "rank_compare.json"
DATA_CSV = BENCH / "figures" / "rank_compare.csv"
RECALL_JUDGE = os.getenv("RECALL_JUDGE", "claude-fable-5-1")
PROBE_JUDGE = os.getenv("PROBE_JUDGE", "claude-opus-5")
SIX = ["N07", "N08", "N09", "N10", "N37", "N38"]
NAMES = {"gpt_5_6_sol": "GPT-5.6 Sol", "openai_gpt_5_6_sol": "GPT-5.6 Sol",
         "gpt_6_astra": "GPT-6 Astra", "openai_gpt_6_astra": "GPT-6 Astra",
         "gpt_5_6_luna": "GPT-5.6 Luna", "gpt_5_6_terra": "GPT-5.6 Terra",
         "google_gemini_3_8_flash": "Gemini 3.8 Flash", "meta_muse_spark_1_3": "Muse Spark 1.3",
         "moonshotai_kimi_k3": "Kimi K3", "z_ai_glm_5_3": "GLM 5.3", "claude_opus_5": "Opus 5",
         "claude_opus_4_8": "Opus 4.8", "claude_sonnet_5": "Sonnet 5", "claude_haiku_4_5": "Haiku 4.5"}
OPENAI = {"GPT-5.6 Sol", "GPT-5.6 Luna", "GPT-5.6 Terra", "GPT-6 Astra"}
ANTH = {"Opus 5", "Opus 4.8", "Sonnet 5", "Haiku 4.5"}
# `_served_<model>` and `_p<hash>` suffixes are optional and must not swallow the model
RX = re.compile(r"graded_(?:r4b|psw)(\d+)_(?:claude|codex|react)_(.+?)_rep\d"
                r"(?:_+served_[a-z0-9_]+?)?(?:_+p[0-9a-f]+)?\.json$")
strict = lambda s: max(2 * s - 1, 0.0)  # noqa: E731


def boot_ci(per_model, n=10000, seed=7):
    """Percentile interval over models, not runs.

    Resampling reports would treat Sol's eighteen standard runs as eighteen independent
    observations of "an OpenAI model", which they are not; the group has four members and
    the interval should say so.
    """
    if len(per_model) < 2:
        return None, None
    rnd = random.Random(seed)
    means = sorted(st.mean([v for _ in per_model for v in rnd.choice(per_model)])
                   for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def group(model):
    return "OpenAI" if model in OPENAI else ("Anthropic" if model in ANTH else "neutral")


def scan(pattern, want_max, pick):
    """model -> [score]. `pick` turns one grade file's scores into a number."""
    out = defaultdict(list)
    for p in sorted(pathlib.Path().glob(pattern)):
        m = RX.search(p.name)
        if not m:
            print(f"  ! unparsed: {p.name}")
            continue
        g = json.loads(p.read_text())
        if g.get("max") != want_max:
            continue
        out[NAMES.get(m.group(2), m.group(2))].append(pick(g["scores"]))
    return out


def main():
    rj = re.sub(r"[^0-9a-zA-Z]+", "_", RECALL_JUDGE).strip("_")
    pj = re.sub(r"[^0-9a-zA-Z]+", "_", PROBE_JUDGE).strip("_")
    R = pathlib.Path(GRADED / f"judge_{rj}" / "v2").relative_to(pathlib.Path().resolve())
    P = pathlib.Path(GRADED / f"judge_{pj}" / "origin").relative_to(pathlib.Path().resolve())
    six = lambda S: st.mean(strict(S[i]["score"]) for i in SIX)      # noqa: E731
    allf = lambda S: st.mean(strict(v["score"]) for v in S.values())  # noqa: E731
    probe = lambda S: S["ORIGIN"]["score"]                            # noqa: E731

    measures = {
        "origin": {"label": "origin probe", "axis": "AI lab attribution surfaced",
                   "note": f"one question over the whole report, judged by {PROBE_JUDGE}",
                   "std": scan(f"{P}/graded_r4b*.json", 1, probe),
                   "twin": scan(f"{P}/variant_anthropic/graded_psw*.json", 1, probe)},
        "attribution": {"label": "attribution findings", "axis": "AI lab attribution coverage",
                        "note": "the six recall findings that name an actor, strict",
                        "std": scan(f"{R}/graded_r4b*.json", 38, six),
                        "twin": scan(f"{R}/variant_anthropic/graded_psw*.json", 38, six)},
        "overall": {"label": "overall recall", "axis": "overall finding coverage",
                    "note": "all 38 findings, strict — the control",
                    "std": scan(f"{R}/graded_r4b*.json", 38, allf),
                    "twin": scan(f"{R}/variant_anthropic/graded_psw*.json", 38, allf)},
    }
    data = {"measures": {}, "judges": {"recall": RECALL_JUDGE, "probe": PROBE_JUDGE}}
    for key, m in measures.items():
        both = sorted(set(m["std"]) & set(m["twin"]))
        rows = [{"model": mo, "group": group(mo),
                 "std": st.mean(m["std"][mo]), "twin": st.mean(m["twin"][mo]),
                 "n_std": len(m["std"][mo]), "n_twin": len(m["twin"][mo])} for mo in both]
        for field in ("std", "twin"):
            for i, r in enumerate(sorted(rows, key=lambda r: -r[field]), 1):
                r[f"rank_{field}"] = i
        rows.sort(key=lambda r: r["rank_std"])
        # OpenAI against everyone else, per corpus, with an interval bootstrapped over
        # models rather than reports: runs from one model are not independent, and Sol
        # alone contributes 18 of the standard corpus's OpenAI runs.
        def split(field, run_field):
            out = {}
            for side, want in (("OpenAI", True), ("non-OpenAI", False)):
                sel = [mo for mo in both if (group(mo) == "OpenAI") == want]
                per = {mo: m[run_field][mo] for mo in sel}
                lo, hi = boot_ci(list(per.values()))
                out[side] = {"mean": st.mean(st.mean(v) for v in per.values()),
                             "lo": lo, "hi": hi, "models": len(sel),
                             "runs": sum(len(v) for v in per.values()),
                             # one point per model, so the bar's spread is visible and a
                             # single model carrying the group cannot hide inside the mean
                             "points": sorted(({"model": mo, "mean": st.mean(v), "n": len(v)}
                                               for mo, v in per.items()),
                                              key=lambda d: -d["mean"])}
            return out
        data["measures"][key] = {"label": m["label"], "axis": m["axis"], "note": m["note"], "rows": rows,
                                 "n_std": sum(r["n_std"] for r in rows),
                                 "n_twin": sum(r["n_twin"] for r in rows),
                                 "split": {"standard": split("std", "std"),
                                           "twin": split("twin", "twin")}}
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    lines = ["measure,model,group,score_standard,score_twin,rank_standard,rank_twin,n_standard,n_twin"]
    for key, m in data["measures"].items():
        for r in m["rows"]:
            lines.append(",".join(str(x) for x in [
                key, f'"{r["model"]}"', r["group"], round(r["std"], 4), round(r["twin"], 4),
                r["rank_std"], r["rank_twin"], r["n_std"], r["n_twin"]]))
    DATA_CSV.write_text("\n".join(lines) + "\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"wrote {OUT}, {DATA_CSV.name} and {DATA_JSON.name}")
    for key, m in data["measures"].items():
        moved = [f"{r['model']} {r['rank_std']}->{r['rank_twin']}"
                 for r in m["rows"] if r["rank_std"] != r["rank_twin"]]
        print(f"  {m['label']:22s} {len(m['rows'])} models, {m['n_std']}+{m['n_twin']} reports")
        print(f"    {'; '.join(moved) if moved else 'ranking unchanged'}")


BODY = """<main>
  <h1>Where each model ranks, on both corpora</h1>
  <p class="lede" id="lede"></p>
  <div class="tools" id="tabs"></div>
__FIGS__
  <details><summary>How to read this</summary><ul class="cav" id="cav"></ul></details>
</main>"""

FIGS = "\n\n".join([
    chrome.figure(1, "OpenAI models against everyone else, before and after the swap", "fig0",
                  read_id="read0", cap_id="cap0", legend_id="leg0", table_id="tbl0"),
    chrome.figure(2, "The same ranking, twice", "fig1", legend_id="leg1",
                  read_id="read1", cap_id="cap1",
                  tools='<button class="csv" data-csv="ranks">copy CSV</button>'
                        '<span>or benchmark/figures/rank_compare.csv</span>',
                  table_id="tbl1"),
])

JS = r"""
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const s = (t, a) => { const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c;
  if (x != null) e.textContent = x; return e; };
/* group, not provider: the question is whether the lab being named is the model's own */
const COL = {OpenAI: 'var(--p-openai)', Anthropic: 'var(--p-anthropic)', neutral: 'var(--p-google)'};
let sel = 'origin';

document.getElementById('lede').textContent =
  'The modified Anthropic setting is the same task on the same data with one substitution: '
  + 'the lab the evidence names becomes Anthropic instead of OpenAI. If reticence were loyalty, ranks '
  + 'would move when the name changes — OpenAI models climbing, Anthropic models falling. '
  + 'Recall is judged by ' + D.judges.recall + ', the probe by ' + D.judges.probe + '.';

/* --- Figure 1: the group means, both corpora --- */
/* Both groups take tokens from the post's provider palette rather than ink greys, so the
   figure sits with the rest. OpenAI keeps the black it wears everywhere in the post. The
   other group is eight models from five providers, so its green denotes the group, not
   Google — which is why both bars are named on the axis and in the legend. */
const SIDE = {'OpenAI': 'var(--p-openai)', 'non-OpenAI': 'var(--p-google)'};
function fig0() {
  const M = D.measures[sel], sp = M.split;
  const corpora = [['standard', 'standard setting'], ['twin', 'modified Anthropic setting']];
  const sides = ['OpenAI', 'non-OpenAI'];
  const W = 1040, H = 372, L = 66, R = 20, T = 40, B = 62;
  const IW = W - L - R, IH = H - T - B;
  const all = corpora.flatMap(([c]) => sides.flatMap(k => [sp[c][k].mean, sp[c][k].lo, sp[c][k].hi]))
                     .filter(v => v != null);
  const hi = Math.max(...all) * 1.15;
  const Y = v => T + IH - v / hi * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'OpenAI and non-OpenAI model means on both corpora'});
  const step = hi > 0.4 ? 0.1 : 0.05;
  for (let v = 0; v <= hi; v += step) {
    svg.append(s('line', {x1: L, x2: L + IW, y1: Y(v), y2: Y(v), class: 'tick'}));
    const t = s('text', {x: L - 8, y: Y(v) + 3.5, class: 'axis num', 'text-anchor': 'end'});
    t.textContent = v.toFixed(2); svg.append(t);
  }
  svg.append(s('line', {x1: L, x2: L + IW, y1: Y(0), y2: Y(0), class: 'axline'}));
  const band = IW / corpora.length, bw = Math.min(band * 0.2, 62);
  corpora.forEach(([c, label], i) => {
    const cx = L + band * (i + 0.5);
    sides.forEach((k, j) => {
      const q = sp[c][k], x = cx + (j === 0 ? -bw - 14 : 14);
      svg.append(s('rect', {x, y: Y(q.mean), width: bw, height: Math.max(Y(0) - Y(q.mean), 1),
        fill: SIDE[k], 'fill-opacity': .3, stroke: SIDE[k], 'stroke-width': 1.4, rx: 4}));
      const mx = x + bw / 2;
      if (q.lo != null) {
        svg.append(s('line', {x1: mx, x2: mx, y1: Y(q.lo), y2: Y(q.hi), stroke: 'var(--ink)',
          'stroke-width': 1.2, opacity: .55}));
        [q.lo, q.hi].forEach(v => svg.append(s('line', {x1: mx - 5, x2: mx + 5, y1: Y(v), y2: Y(v),
          stroke: 'var(--ink)', 'stroke-width': 1.2, opacity: .55})));
      }
      /* one dot per model, nudged apart only when two would overlap, so a reader can see
         whether the bar is a consensus or one model dragging the rest */
      const placed = [];
      (q.points || []).forEach(pt => {
        let dx = 0;
        while (placed.some(v => Math.abs(v.y - Y(pt.mean)) < 7 && Math.abs(v.dx - dx) < 9))
          dx = dx <= 0 ? -dx + 9 : -dx;
        placed.push({y: Y(pt.mean), dx});
        const c = s('circle', {cx: mx + dx, cy: Y(pt.mean), r: 2.6, fill: SIDE[k],
          opacity: .75});
        c.append(s('title'));
        c.lastChild.textContent = `${pt.model}: ${pt.mean.toFixed(2)} over ${pt.n} run${pt.n > 1 ? 's' : ''}`;
        svg.append(c);
      });
      /* the mean sits inside the bar where there is room: above it, it lands in the middle
         of the dot cloud and the whisker, and no amount of halo makes that tidy */
      svg.append(s('line', {x1: x, x2: x + bw, y1: Y(q.mean), y2: Y(q.mean),
        stroke: SIDE[k], 'stroke-width': 2.2}));
      const t = s('text', {x: mx, y: Y(q.mean) - 10, class: 'lab num', 'text-anchor': 'middle',
        stroke: 'var(--surface)', 'stroke-width': 3, 'paint-order': 'stroke',
        'stroke-linejoin': 'round'});
      t.textContent = q.mean.toFixed(2); svg.append(t);
      /* the bar is 62px and "non-OpenAI models" is twice that; the legend carries the
         full names, so the axis carries the short ones */
      const n = s('text', {x: mx, y: Y(0) + 16, class: 'axis', 'text-anchor': 'middle'});
      n.textContent = k; svg.append(n);
    });
    const lb = s('text', {x: cx, y: Y(0) + 38, class: 'axname', 'text-anchor': 'middle'});
    lb.textContent = label; svg.append(lb);
  });
  const ay = s('text', {x: 16, y: T + IH / 2, class: 'axname', 'text-anchor': 'middle',
    transform: `rotate(-90 16 ${T + IH / 2})`});
  ay.textContent = M.axis + (sel === 'origin' ? ' (raw 0-1)' : ' (strict)'); svg.append(ay);
  document.getElementById('fig0').replaceChildren(svg);
  let lx = L + 6;
  sides.forEach(k => {
    svg.append(s('rect', {x: lx, y: T - 26, width: 9, height: 9, fill: SIDE[k],
      'fill-opacity': .3, stroke: SIDE[k], 'stroke-width': 1.4, rx: 2}));
    const t = s('text', {x: lx + 14, y: T - 18, class: 'axis'});
    t.textContent = k + ' models'; svg.append(t);
    lx += 26 + (k.length + 7) * 6.4;
  });
  svg.append(s('circle', {cx: lx + 4, cy: T - 21.5, r: 2.6, fill: 'var(--ink3)', opacity: .75}));
  const dl = s('text', {x: lx + 12, y: T - 18, class: 'axis'});
  dl.textContent = 'one model'; svg.append(dl);
  document.getElementById('leg0').replaceChildren();
  const d1 = sp.standard['OpenAI'].mean - sp.standard['non-OpenAI'].mean;
  const d2 = sp.twin['OpenAI'].mean - sp.twin['non-OpenAI'].mean;
  document.getElementById('read0').textContent =
    `Gap of ${d1.toFixed(2)} in the standard setting, ${d2.toFixed(2)} in the modified `
    + `Anthropic setting. If the deficit were loyalty it would close on the right.`;
  document.getElementById('cap0').textContent =
    `${M.label}: ${M.note}. Each model contributes once, so Sol's eighteen standard runs do `
    + `not outvote Haiku's six. Whiskers are 95% percentile intervals bootstrapped over `
    + `models — four in the OpenAI group and eight in the other — which is why they are wide. `
    + `Each dot is one model's own mean; hover for its name and run count. `
    + `The green denotes the group, not Google: it holds eight models from five providers. `
    + `Standard setting: ${sp.standard['OpenAI'].runs} and ${sp.standard['non-OpenAI'].runs} runs. `
    + `Modified: ${sp.twin['OpenAI'].runs} and ${sp.twin['non-OpenAI'].runs}.`;
  const t = el('table'), hd = el('tr');
  ['corpus', 'group', 'mean', '95% CI', 'models', 'runs'].forEach((h, i) =>
    hd.append(el('th', i < 2 ? 'l' : '', h)));
  const th = el('thead'); th.append(hd); t.append(th);
  const tb = el('tbody');
  corpora.forEach(([c, label]) => sides.forEach(k => {
    const q = sp[c][k], tr = el('tr');
    tr.append(el('td', 'l', label), el('td', 'l', k), el('td', 'num', q.mean.toFixed(2)),
      el('td', 'num', q.lo == null ? '—' : `${q.lo.toFixed(2)}, ${q.hi.toFixed(2)}`),
      el('td', 'num', q.models), el('td', 'num', q.runs));
    tb.append(tr);
  }));
  t.append(tb); document.getElementById('tbl0').replaceChildren(t);
}

function fig() {
  const M = D.measures[sel], rows = M.rows;
  const W = 1040, H = 60 + rows.length * 30, L = 250, R = 250, T = 40;
  const IH = H - T - 24, x0 = L, x1 = W - R;
  const y = r => T + (r - 1) / Math.max(1, rows.length - 1) * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'model ranks on the standard and swapped corpora'});
  [[x0, 'standard setting'], [x1, 'modified Anthropic setting']].forEach(([x, t]) => {
    const h = s('text', {x, y: T - 18, class: 'axname', 'text-anchor': 'middle'});
    h.textContent = t; svg.append(h);
    svg.append(s('line', {x1: x, x2: x, y1: T - 8, y2: T + IH + 8, class: 'axline'}));
  });
  rows.forEach(r => {
    const c = COL[r.group], ya = y(r.rank_std), yb = y(r.rank_twin);
    const moved = r.rank_twin - r.rank_std;
    svg.append(s('line', {x1: x0, y1: ya, x2: x1, y2: yb, stroke: c,
      'stroke-width': moved ? 2 : 1, opacity: moved ? .85 : .35}));
    [[x0, ya], [x1, yb]].forEach(([x, yy]) =>
      svg.append(s('circle', {cx: x, cy: yy, r: 4.5, fill: c, stroke: 'var(--surface)',
        'stroke-width': 1.5})));
    const la = s('text', {x: x0 - 12, y: ya + 4, class: 'lab', 'text-anchor': 'end'});
    la.textContent = `${r.rank_std}. ${r.model}  ${r.std.toFixed(2)}`; svg.append(la);
    const lb = s('text', {x: x1 + 12, y: yb + 4, class: 'lab'});
    lb.textContent = `${r.rank_twin}. ${r.model}  ${r.twin.toFixed(2)}`
      + (moved ? `  (${moved > 0 ? '▼' : '▲'}${Math.abs(moved)})` : '');
    svg.append(lb);
  });
  document.getElementById('fig1').replaceChildren(svg);
  const leg = document.getElementById('leg1'); leg.replaceChildren();
  Object.entries(COL).forEach(([g, c]) => {
    const sp = el('span'); const i = el('i'); i.style.background = c;
    sp.append(i, document.createTextNode(g + (g === 'neutral' ? ' (neither lab)' : ' models')));
    leg.append(sp);
  });
  const moved = rows.filter(r => r.rank_std !== r.rank_twin).length;
  document.getElementById('cap1').textContent =
    `${M.label}: ${M.note}. Rank 1 is best. ${rows.length} models present on both corpora, `
    + `${M.n_std} standard and ${M.n_twin} swapped reports. ${moved ? moved + ' models change rank' :
       'no model changes rank'}; a flat line is a model the swap did not move. Faded lines `
    + `did not move.`;
  const t = el('table'), hd = el('tr');
  ['model', 'group', 'standard', 'rank', 'twin', 'rank', 'move', 'runs'].forEach((h, i) =>
    hd.append(el('th', i < 2 ? 'l' : '', h)));
  const th = el('thead'); th.append(hd); t.append(th);
  const tb = el('tbody');
  rows.forEach(r => {
    const tr = el('tr'), mv = r.rank_std - r.rank_twin;
    tr.append(el('td', 'l', r.model), el('td', 'l', r.group),
      el('td', 'num', r.std.toFixed(2)), el('td', 'num', '#' + r.rank_std),
      el('td', 'num', r.twin.toFixed(2)), el('td', 'num', '#' + r.rank_twin),
      el('td', 'num', mv === 0 ? '—' : (mv > 0 ? '+' : '') + mv),
      el('td', 'num', `${r.n_std}/${r.n_twin}`));
    tb.append(tr);
  });
  t.append(tb);
  document.getElementById('tbl1').replaceChildren(t);
  CSV.ranks = ['measure,model,group,score_standard,rank_standard,score_twin,rank_twin,n_standard,n_twin',
    ...rows.map(r => [sel, r.model, r.group, r.std.toFixed(4), r.rank_std,
      r.twin.toFixed(4), r.rank_twin, r.n_std, r.n_twin].join(','))].join('\n');
}
const CSV = {};
function tabs() {
  const box = document.getElementById('tabs'); box.replaceChildren();
  Object.entries(D.measures).forEach(([k, m]) => {
    const b = el('button', k === sel ? 'on' : '', m.label);
    b.onclick = () => { sel = k; tabs(); fig0(); fig(); };
    box.append(b);
  });
  const c = el('button', 'csv', 'copy CSV'); c.dataset.csv = 'ranks';
  c.onclick = () => navigator.clipboard.writeText(CSV.ranks || '').then(() => {
    c.textContent = 'copied'; setTimeout(() => { c.textContent = 'copy CSV'; }, 1200); }).catch(() => {});
  box.append(c, el('span', null, 'or benchmark/figures/rank_compare.csv'));
}
const cav = document.getElementById('cav');
['A slope is one model’s rank on the standard corpus joined to its rank on the swapped '
 + 'one. Loyalty predicts OpenAI models rise and Anthropic models fall; the observed lines '
 + 'mostly stay flat.',
 'Ranks are over models present on both corpora, so a model missing from the twin is absent '
 + 'from both columns rather than shifting everyone below it.',
 'The twin has fewer runs per model than the standard corpus, so a single run moves a twin '
 + 'rank further than a standard one. The runs column gives both counts.',
 'Overall recall is the control: a model that simply writes worse reports on the swapped '
 + 'data should move there too, not only on the attribution measures.'
].forEach(t => cav.append(el('li', null, t)));
tabs(); fig0(); fig();
"""

TEMPLATE = (chrome.shell("Ranks on both corpora", BODY.replace("__FIGS__", FIGS))
            + "<script>\n" + JS + "\n</script>\n</body></html>\n")


if __name__ == "__main__":
    main()
