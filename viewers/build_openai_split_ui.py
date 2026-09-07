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
"""
import json, glob, collections, statistics as st, sys, pathlib

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
    groups = []
    for label, sel in (("OpenAI models", True), ("Non-OpenAI models", False)):
        v = [r for r in rows if r["openai"] is sel]
        groups.append({"label": label, "openai": sel, "n_reports": len(v),
                       "n_models": len({r["model"] for r in v}),
                       "models": sorted({r["model"] for r in v}),
                       **{k: round(st.mean(x[k] for x in v), 4)
                          for k in list(CLUSTERS) + ["Speculate OpenAI"]},
                       "tun_any": round(sum(x["tun_any"] for x in v) / len(v), 4)})
    data = {"groups": groups, "models": models, "clusters": CLUSTERS,
            "n_reports": len(rows), "judge": "claude-fable-5-1"}
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    a, b = groups
    print(f"{OUT}: {len(rows)} reports, {len(models)} models")
    print(f"  speculate-OpenAI  {a['label']} {a['Speculate OpenAI']:.3f}  vs  {b['label']} {b['Speculate OpenAI']:.3f}")
    print(f"  SSH tunnelling    {a['label']} {a['SSH tunnelling']:.3f}  vs  {b['label']} {b['SSH tunnelling']:.3f}")


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

/* two bars, one hue: this is a magnitude comparison between two groups, not two identities */
function bars(host, key, extra) {
  const g = D.groups, W = 900, H = 190, L = 190, R = 90, T = 14, IW = W - L - R;
  const max = Math.max(0.6, ...g.map(x => x[key]) ) * 1.15;
  const x = v => L + v / max * IW;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', height: H, role: 'img',
                        'aria-label': key + ' by group'});
  for (let t = 0; t <= max; t += 0.1) {
    svg.append(s('line', {x1: x(t), x2: x(t), y1: T, y2: H - 34, class: 'tick'}));
    const lb = s('text', {x: x(t), y: H - 18, 'text-anchor': 'middle', class: 'axis'});
    lb.textContent = t.toFixed(1); svg.append(lb);
  }
  svg.append(s('line', {x1: L, x2: L, y1: T, y2: H - 34, class: 'axline'}));
  g.forEach((row, i) => {
    const y = T + 18 + i * 62, bh = 26;
    const nm = s('text', {x: L - 12, y: y + bh - 8, 'text-anchor': 'end', class: 'lab'});
    nm.textContent = row.label; svg.append(nm);
    const sub = s('text', {x: L - 12, y: y + bh + 8, 'text-anchor': 'end', class: 'small'});
    sub.textContent = `${row.n_models} models · ${row.n_reports} reports`; svg.append(sub);
    svg.append(s('rect', {x: L, y, width: Math.max(2, x(row[key]) - L), height: bh, rx: 4, ry: 4,
                          fill: row.openai ? 'var(--accent)' : 'var(--grey)'}));
    svg.append(s('rect', {x: L, y, width: 4, height: bh, fill: row.openai ? 'var(--accent)' : 'var(--grey)'}));
    const vl = s('text', {x: x(row[key]) + 10, y: y + bh - 7, class: 'val'});
    vl.textContent = row[key].toFixed(3); svg.append(vl);
    /* each model in the group as a dot, so the spread behind the mean is visible */
    D.models.filter(m => m.openai === row.openai).forEach(m => {
      svg.append(s('circle', {cx: x(m[key]), cy: y + bh / 2, r: 3.4, fill: '#fff',
                              stroke: row.openai ? '#8C3F22' : '#7C776C', 'stroke-width': 1.5}));
    });
  });
  host.replaceChildren(svg);
  const k = el('p', 'key');
  k.append(document.createTextNode('bar = group mean;  hollow dots = individual models'));
  if (extra) k.append(el('span', null, '   ' + extra));
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
