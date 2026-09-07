#!/usr/bin/env python3
"""Build viewers/openai_split.html — do OpenAI's models under-report OpenAI?

Two clusters ask the report to name OpenAI: Origin (the editors self-identify as OpenAI
agents, edits come from Azure, the scale implies an AI company, so probably an internal
OpenAI deployment) and OpenAI response (activity collapsed around 22 June, probably
because OpenAI intervened). If a model is reluctant to name its own developer, that is
where it shows.

SSH tunnelling is the control. It is a cluster of comparable difficulty that has nothing
to do with attribution, so a gap there would mean the OpenAI models are simply weaker or
more cautious in general, and no gap means the attribution result is about attribution.

Scores are the raw per-point means over round 4, judged by Fable 5.1 on the v2 rubric,
not the strict transform: the question is whether the finding is reached at all, and
transforming would discard the partial credit that carries the answer.

Intervals are a percentile bootstrap, 10,000 resamples. Both are computed and both are
drawn, because they answer different questions. Resampling reports asks how stable the
number is given these models; resampling models asks whether it would survive a different
choice of models, which is the question a reader actually has, and is much the wider
interval. The four OpenAI models are not four independent draws from a population of
OpenAI models, so even the model-level interval understates the real uncertainty.
"""
import json, glob, collections, random, statistics as st, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from paths import GRADED, VIEWERS
from report_performance import NAMES, RX

OUT = VIEWERS / "openai_split.html"
CLUSTERS = {"Origin": ["N07", "N08", "N09", "N10"],
            "OpenAI response": ["N37", "N38"],
            "SSH tunnelling": ["N34", "N35", "N36"]}
SPEC = ["N07", "N08", "N09", "N10", "N37", "N38"]
OPENAI = {"GPT-5.6 Sol", "GPT-5.6 Luna", "GPT-5.6 Terra", "GPT-6 Astra"}
N_BOOT = 10000
SEED = 0


def boot(vals, n=N_BOOT):
    """Percentile bootstrap over a list of per-report values."""
    if not vals:
        return None
    draws = sorted(st.mean(random.choices(vals, k=len(vals))) for _ in range(n))
    return [round(draws[int(0.025 * n)], 4), round(draws[int(0.975 * n)], 4)]


def boot_by_model(rows, key, n=N_BOOT):
    """Resample whole models, keeping each model's reports together."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["model"]].append(r[key])
    keys = list(by)
    if len(keys) < 2:
        return None
    draws = sorted(st.mean(v for k in random.choices(keys, k=len(keys)) for v in by[k])
                   for _ in range(n))
    return [round(draws[int(0.025 * n)], 4), round(draws[int(0.975 * n)], 4)]


def load():
    rows = []
    for f in sorted(glob.glob(str(GRADED / "judge_claude_fable_5_1" / "v2" / "graded_r4b*.json"))):
        m = RX.search(pathlib.Path(f).name)
        d = json.loads(pathlib.Path(f).read_text())
        mod = NAMES.get(m.group(5), m.group(5))
        s = d["scores"]
        rows.append({"model": mod, "openai": mod in OPENAI, "budget": int(m.group(3)),
                     **{k: st.mean(s[c]["score"] for c in ids) for k, ids in CLUSTERS.items()},
                     "Speculate OpenAI": st.mean(s[c]["score"] for c in SPEC),
                     "tun_any": any(s[c]["score"] > 0 for c in CLUSTERS["SSH tunnelling"])})
    return rows


def main():
    rows = load()
    by = collections.defaultdict(list)
    for r in rows:
        by[r["model"]].append(r)
    models = [{"model": m, "openai": v[0]["openai"], "n": len(v),
               **{k: round(st.mean(x[k] for x in v), 4)
                  for k in list(CLUSTERS) + ["Speculate OpenAI"]}}
              for m, v in by.items()]
    models.sort(key=lambda m: -m["Speculate OpenAI"])
    random.seed(SEED)
    groups = []
    for label, sel in (("OpenAI models", True), ("Non-OpenAI models", False)):
        v = [r for r in rows if r["openai"] is sel]
        g = {"label": label, "openai": sel, "n_reports": len(v),
             "n_models": len({r["model"] for r in v}),
             "models": sorted({r["model"] for r in v}),
             "tun_any": round(sum(x["tun_any"] for x in v) / len(v), 4)}
        for k in list(CLUSTERS) + ["Speculate OpenAI"]:
            g[k] = round(st.mean(x[k] for x in v), 4)
            g[k + " ci_report"] = boot([x[k] for x in v])
            g[k + " ci_model"] = boot_by_model(v, k)
        groups.append(g)
    data = {"groups": groups, "models": models, "clusters": CLUSTERS, "n_boot": N_BOOT,
            "n_reports": len(rows), "judge": "claude-fable-5-1"}
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    a, b = groups
    print(f"{OUT}: {len(rows)} reports, {len(models)} models")
    print(f"  speculate-OpenAI  {a['label']} {a['Speculate OpenAI']:.3f}  vs  {b['label']} {b['Speculate OpenAI']:.3f}")
    print(f"  SSH tunnelling    {a['label']} {a['SSH tunnelling']:.3f}  vs  {b['label']} {b['SSH tunnelling']:.3f}")
    for g in groups:
        print(f"    {g['label']:<18} speculate {g['Speculate OpenAI']:.3f} "
              f"reports {g['Speculate OpenAI ci_report']}  models {g['Speculate OpenAI ci_model']}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Do OpenAI's models name OpenAI?</title>
<style>
:root{--paper:#F4F3EE;--surface:#FFF;--line:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--ink3:#999;
 --accent:#C15F3C;--grey:#B9B5AA;--grid:#EAE7DF}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:28px 32px 72px}
h1{color:var(--accent);font-size:23px;margin:0 0 2px}
h2{font-size:16px;margin:30px 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 4px}
.note{color:var(--ink3);font-size:12px;margin:2px 0 12px;max-width:74ch}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:8px 0}
svg{display:block;max-width:100%;overflow:visible}
.axis{fill:var(--ink2);font-size:11px}
.tick{stroke:var(--grid);stroke-width:1}
.axline{stroke:var(--line);stroke-width:1}
.lab{fill:var(--ink);font-size:13px}
.val{fill:var(--ink);font-size:13px;font-variant-numeric:tabular-nums;font-weight:600}
.small{fill:var(--ink3);font-size:10.5px}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums;margin-top:4px}
th,td{text-align:right;padding:5px 9px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
th{color:var(--ink2);font-weight:600}
tr.oa td{background:#FDF2EC}
.key{font-size:11.5px;color:var(--ink2);margin:6px 0 0}
.key i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px;vertical-align:-1px}
</style></head><body>
<main>
  <h1>Do OpenAI's models name OpenAI?</h1>
  <p class="sub" id="sub"></p>

  <h2>Speculating that this was OpenAI</h2>
  <p class="note">The Origin and OpenAI-response clusters, six points, which together ask a report to
   conclude the editors were OpenAI agents on Azure and that OpenAI stopped them.</p>
  <div class="card" id="c1"></div>

  <h2>SSH tunnelling — the control</h2>
  <p class="note">Three points of comparable difficulty with nothing to do with attribution. A gap
   here would mean the OpenAI models are simply weaker or more cautious across the board; no gap
   means the difference above is about naming OpenAI, not about caution in general.</p>
  <div class="card" id="c2"></div>

  <h2>By model</h2>
  <div class="card" id="tbl"></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const s = (t, a) => { const x = document.createElementNS(NS, t); for (const k in a) x.setAttribute(k, a[k]); return x; };
const el = (t, c, txt) => { const x = document.createElement(t); if (c) x.className = c; if (txt != null) x.textContent = txt; return x; };
document.getElementById('sub').textContent =
  `${D.n_reports} round-4 reports, ${D.models.length} models, judged by ${D.judge} on the 38-point rubric. Mean point score, 0 to 1.`;

/* Vertical bars, one hue, two groups: a magnitude comparison, not two identities.
   The whisker is the model-level bootstrap, because the claim is about kinds of model
   rather than about these particular reports — reports from one model are not
   independent draws. The report-level interval is drawn faintly behind it so the
   difference between the two questions is visible rather than hidden. */
function bars(host, key, extra) {
  const g = D.groups, W = 620, H = 330, T = 18, B = 62, L = 54, R = 18;
  const IH = H - T - B, slot = (W - L - R) / g.length;
  const hi = Math.max(...g.map(r => (r[key + ' ci_model'] || [0, r[key]])[1]), ...g.map(r => r[key]));
  const max = Math.max(0.6, hi * 1.18);
  const y = v => T + IH - v / max * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', height: H, role: 'img',
                        'aria-label': key + ' by group, with bootstrap intervals'});
  for (let t = 0; t <= max + 1e-9; t += 0.1) {
    svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
    const lb = s('text', {x: L - 8, y: y(t) + 4, 'text-anchor': 'end', class: 'axis'});
    lb.textContent = t.toFixed(1); svg.append(lb);
  }
  svg.append(s('line', {x1: L, x2: W - R, y1: y(0), y2: y(0), class: 'axline'}));
  g.forEach((row, i) => {
    const cx = L + slot * (i + 0.5), bw = Math.min(120, slot * 0.44);
    const col = row.openai ? 'var(--accent)' : 'var(--grey)';
    const dark = row.openai ? '#8C3F22' : '#6F6A5F';
    svg.append(s('rect', {x: cx - bw / 2, y: y(row[key]), width: bw, height: y(0) - y(row[key]),
                          rx: 4, ry: 4, fill: col}));
    svg.append(s('rect', {x: cx - bw / 2, y: y(0) - 4, width: bw, height: 4, fill: col}));
    /* faint report-level interval behind, then the model-level whisker in front */
    const cr = row[key + ' ci_report'], cm = row[key + ' ci_model'];
    if (cr) svg.append(s('line', {x1: cx, x2: cx, y1: y(cr[0]), y2: y(cr[1]),
                                  stroke: dark, 'stroke-width': 7, opacity: .18,
                                  'stroke-linecap': 'round'}));
    if (cm) {
      svg.append(s('line', {x1: cx, x2: cx, y1: y(cm[0]), y2: y(cm[1]), stroke: dark, 'stroke-width': 2}));
      for (const v of cm) svg.append(s('line', {x1: cx - 9, x2: cx + 9, y1: y(v), y2: y(v),
                                                stroke: dark, 'stroke-width': 2}));
    }
    /* every model in the group, so the spread behind the mean is visible */
    D.models.filter(m => m.openai === row.openai).forEach((m, j, arr) => {
      const off = (j - (arr.length - 1) / 2) * Math.min(11, (bw + 46) / arr.length);
      svg.append(s('circle', {cx: cx + bw / 2 + 26 + off * 0, cy: y(m[key]), r: 3.4, fill: '#fff',
                              stroke: dark, 'stroke-width': 1.5, opacity: .9}));
    });
    const vl = s('text', {x: cx, y: y(row[key]) - (cm ? 0 : 8), 'text-anchor': 'middle', class: 'val'});
    vl.setAttribute('y', y(cm ? cm[1] : row[key]) - 9);
    vl.textContent = row[key].toFixed(3); svg.append(vl);
    const nm = s('text', {x: cx, y: H - 38, 'text-anchor': 'middle', class: 'lab'});
    nm.textContent = row.label; svg.append(nm);
    const sub = s('text', {x: cx, y: H - 22, 'text-anchor': 'middle', class: 'small'});
    sub.textContent = `${row.n_models} models · ${row.n_reports} reports`; svg.append(sub);
  });
  host.replaceChildren(svg);
  const k = el('p', 'key');
  k.textContent = 'bar = group mean; whisker = 95% bootstrap over models (' + D.n_boot.toLocaleString()
    + ' resamples); pale band behind = the same over reports; dots to the right = individual models'
    + (extra ? '.  ' + extra : '');
  host.append(k);
}
bars(document.getElementById('c1'), 'Speculate OpenAI');
bars(document.getElementById('c2'), 'SSH tunnelling',
     `any credit on a tunnelling point: OpenAI ${(100 * D.groups[0].tun_any).toFixed(0)}%, non-OpenAI ${(100 * D.groups[1].tun_any).toFixed(0)}%`);

(function () {
  const t = document.createElement('table');
  const hd = t.insertRow();
  ['model', 'Origin', 'OpenAI response', 'Speculate OpenAI', 'SSH tunnelling', 'reports'].forEach(h => {
    const th = document.createElement('th'); th.textContent = h; hd.append(th);
  });
  for (const m of D.models) {
    const r = t.insertRow(); if (m.openai) r.className = 'oa';
    r.insertCell().textContent = m.model + (m.openai ? '  ·  OpenAI' : '');
    for (const k of ['Origin', 'OpenAI response', 'Speculate OpenAI', 'SSH tunnelling'])
      r.insertCell().textContent = m[k].toFixed(2);
    r.insertCell().textContent = m.n;
  }
  document.getElementById('tbl').replaceChildren(t);
})();
</script></body></html>'''

if __name__ == "__main__":
    main()
