#!/usr/bin/env python3
"""Build viewers/figures/headline_figures.html: the round-4 headline figures on one page.

  Six main figures: three measures (combined score, finding coverage, holistic TL;DR score),
  each against the Artificial Analysis index (one column per model, three marks per column for
  the 10-, 30- and 120-minute budgets) and against cost per run (one polyline per model).
  Combined = 0.7 x finding coverage (strict v2) + 0.3 x holistic TL;DR (tldrh), the same
  composite build_combined_figure.py publishes; the build aborts if the two disagree.
  Supplementary: coverage against the Epoch index, against time budget per model, and the
  harness comparison.

Sources (all settled on main, cross-checked here):
  benchmark/figures/headline_eci.json               index, fallbacks, caveats, per-budget means
  benchmark/graded/judge_claude_fable_5_1/v2/       per-report grades (Fable 5.1, v2 rubric, 38 points)
  benchmark/graded/judge_claude_fable_5_1/tldrh/    per-report holistic TL;DR grade (Fable 5.1, one 0-1 score)
  benchmark/graded_inputs/round4_blind*/_index.jsonl  per-report token usage, joined by graded filename
  benchmark/prices.json                             list prices, USD per million tokens (OpenRouter, 2026-09-07)
The strict transform max(2s - 1, 0) is imported from scripts/report_performance.py. The build
aborts if a per-budget mean differs from the JSON, and prints how the computed cost of the
Claude Code runs compares with the cost Claude Code itself reported.

Label positions: drag them on the page; "copy positions" puts JSON on the clipboard. Save it
as viewers/figures/headline_labels.json and rebuild to bake the positions in.
"""
import json, re, statistics as st, sys, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from paths import GRADED, GRADED_INPUTS, VIEWERS, BENCH
from report_performance import strict, NAMES as REF_NAMES

OUT = VIEWERS / "figures" / "headline_figures.html"
LABELS = VIEWERS / "figures" / "headline_labels.json"
HEADLINE = BENCH / "figures" / "headline_eci.json"
AA_FILE = BENCH / "aa_index.json"
PRICES = BENCH / "prices.json"
GDIR = GRADED / "judge_claude_fable_5_1" / "v2"
TDIR = GRADED / "judge_claude_fable_5_1" / "tldrh"      # the holistic TL;DR grade, one 0-1 score per report
COMBINED = BENCH / "figures" / "combined_score.json"   # Hasan's 70/30 composite, cross-checked against ours
W_COV, W_TLDR = 0.7, 0.3
BUDGETS = [10, 30, 120]
PRIMARY = "codex"       # a model run under more than one harness is shown under this one in figures 1-3
NAMES = dict(REF_NAMES); NAMES.setdefault("openai_gpt_6_astra", "GPT-6 Astra")
RX = re.compile(r"graded_(r4b(\d+))_(claude|codex|react)_(.+?)_rep(\d)"
                r"(?:_served_([a-z0-9_]+?))?(?:_p([0-9a-f]+))?\.json$")
PROVIDER = {"Opus 5": "anthropic", "Opus 4.8": "anthropic", "Sonnet 5": "anthropic", "Haiku 4.5": "anthropic",
            "GPT-5.6 Sol": "openai", "GPT-5.6 Luna": "openai", "GPT-5.6 Terra": "openai", "GPT-6 Astra": "openai",
            "Gemini 3.8 Flash": "google", "Muse Spark 1.3": "meta", "Kimi K3": "moonshot", "GLM 5.3": "zai"}
# run-index model id -> price-table id
PRICE_ID = {"claude-opus-5": "anthropic/claude-opus-5", "claude-opus-4-8": "anthropic/claude-opus-4.8",
            "claude-sonnet-5": "anthropic/claude-sonnet-5", "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
            "gpt-5.6-sol": "openai/gpt-5.6-sol", "gpt-5.6-luna": "openai/gpt-5.6-luna",
            "gpt-5.6-terra": "openai/gpt-5.6-terra", "gpt-6-astra": "openai/gpt-6-astra",
            "openai/gpt-5.6-sol": "openai/gpt-5.6-sol", "openai/gpt-6-astra": "openai/gpt-6-astra",
            "google/gemini-3.8-flash": "google/gemini-3.8-flash", "meta/muse-spark-1.3": "meta/muse-spark-1.3",
            "moonshotai/kimi-k3": "moonshotai/kimi-k3", "z-ai/glm-5.3": "z-ai/glm-5.3"}


def usage_index():
    """graded stem -> run-index row (usage, served model, wall time)."""
    out = {}
    for d in GRADED_INPUTS.glob("round4_blind*"):
        for line in (d / "_index.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            key = r["graded_input"][:-3].replace("__", "_").replace("-", "_").replace(".", "_")
            out[key] = r
    return out


def cost_of(u, price):
    """USD for one run: recorded cache tokens at cache rates, the rest at list."""
    c = (u["input_tokens_uncached"] * price["input"] + u["cache_read_tokens"] * price["cache_read"]
         + (u.get("cache_write_tokens") or 0) * price["cache_write"] + u["output_tokens"] * price["output"]) / 1e6
    nocache = (u["input_tokens"] * price["input"] + u["output_tokens"] * price["output"]) / 1e6
    return c, nocache


def main():
    H = json.loads(HEADLINE.read_text())
    prices = json.loads(PRICES.read_text())
    uidx = usage_index()
    runs = defaultdict(lambda: defaultdict(list))      # model -> budget -> runs (this model's own)
    served = defaultdict(lambda: defaultdict(list))    # model -> budget -> runs served by another model
    ratios = []
    for p in sorted(GDIR.glob("graded_r4b*.json")):   # round 4 only; other rounds share the directory
        m = RX.search(p.name)
        if not m:
            raise SystemExit(f"filename does not parse: {p.name}")
        g = json.loads(p.read_text())
        vals = [v["score"] for v in g["scores"].values()]
        tp = TDIR / p.name
        if not tp.exists():
            raise SystemExit(f"no holistic TL;DR grade for {p.name}; grade with tldrh before building")
        tldr = float(json.loads(tp.read_text())["total"])
        sc = st.mean(strict(v) for v in vals)
        stem = p.stem[len("graded_"):]
        row = uidx.get(stem)
        if row is None:
            raise SystemExit(f"no usage row for {stem}")
        u = row["usage"]
        price = prices["models"][PRICE_ID[row["model_served"] or row["model"]]]
        cost, nocache = cost_of(u, price)
        if u.get("cost_usd"):
            ratios.append(cost / u["cost_usd"])
        rec = {"harness": m.group(3), "rep": int(m.group(5)), "strict": sc, "tldr": tldr,
               "comb": W_COV * sc + W_TLDR * tldr,
               "raw": st.mean(vals), "cost": cost, "cost_nocache": nocache,
               "wall_min": round(row["wall_seconds"] / 60, 1),
               "tokens": {k: u.get(k) for k in ("input_tokens", "input_tokens_uncached", "cache_read_tokens",
                                                 "cache_write_tokens", "output_tokens", "reasoning_tokens")},
               "served": NAMES.get(m.group(6)) if m.group(6) else None}
        model = NAMES.get(m.group(4), m.group(4))
        runs[model][int(m.group(2))].append(rec)          # a fallback-served run still counts as the model's
        if m.group(6):
            served[model][int(m.group(2))].append(rec)

    models = []
    for M in H["models"]:
        name = M["model"]; buds = {}
        harnesses = sorted({r["harness"] for b in runs[name] for r in runs[name][b]})
        multi = len(harnesses) > 1
        for b in BUDGETS:
            rs = runs[name].get(b, [])
            own = [r for r in rs if not r["served"]]
            if own:   # the settled JSON counts the model's own runs over every harness; check against that
                mean_own = st.mean(r["strict"] for r in own)
                if abs(mean_own - M["all_budgets"][str(b)]) > 1e-3:
                    raise SystemExit(f"{name} at {b} min: computed {mean_own:.4f}, JSON says {M['all_budgets'][str(b)]}")
            if multi:
                rs = [r for r in rs if r["harness"] == PRIMARY]
            if rs:
                mean = st.mean(r["strict"] for r in rs)
                buds[str(b)] = {"mean": mean, "mean_tldr": st.mean(r["tldr"] for r in rs), "mean_comb": st.mean(r["comb"] for r in rs),
                                "n_fallback": len(rs) - len(own), "cost": st.mean(r["cost"] for r in rs),
                                "cost_nocache": st.mean(r["cost_nocache"] for r in rs),
                                "runs": sorted(rs, key=lambda r: r["strict"])}
        top = max(int(b) for b in buds)
        fb = {str(b): {"n": len(rs), "of": len(runs[name][b]), "to": rs[0]["served"],
                       "trigger": "one safeguard refusal per run, classed 'cyber'"} for b, rs in served[name].items()}
        models.append({"model": name, "provider": PROVIDER[name], "eci": M["eci"], "eci_exact": M["eci_exact"],
                       "eci_model": M["eci_model"], "top": top, "truncated": top != max(BUDGETS),
                       "why": M["excluded_note"] if top != max(BUDGETS) else "", "budgets": buds, "fallback": fb,
                       "harness": PRIMARY if multi else harnesses[0], "multi": multi})
    # cost figure: one series per model and harness, so a scaffold's token habits are not averaged into a CLI's
    series = []
    for M in models:
        name = M["model"]
        for h in sorted({r["harness"] for b in runs[name] for r in runs[name][b]}):
            buds = {}
            for b in BUDGETS:
                rs = [r for r in runs[name].get(b, []) if r["harness"] == h]
                if rs:
                    buds[str(b)] = {"mean": st.mean(r["strict"] for r in rs), "mean_tldr": st.mean(r["tldr"] for r in rs),
                                    "mean_comb": st.mean(r["comb"] for r in rs), "cost": st.mean(r["cost"] for r in rs),
                                    "cost_nocache": st.mean(r["cost_nocache"] for r in rs), "runs": sorted(rs, key=lambda r: r["strict"])}
            series.append({"model": name, "harness": h, "provider": M["provider"], "fallback": M["fallback"],
                           "multi": len({r["harness"] for b in runs[name] for r in runs[name][b]}) > 1, "budgets": buds})
    if COMBINED.exists():   # the composite must agree with the one build_combined_figure.py publishes
        C = {(m["model"], b): q for m in json.loads(COMBINED.read_text())["models"] for b, q in m["budgets"].items()}
        for M in models:
            for b, q in M["budgets"].items():
                c = C.get((M["model"], b))
                if c and abs(c["comb"] - q["mean_comb"]) > 1e-3:
                    raise SystemExit(f"{M['model']} at {b} min: combined {q['mean_comb']:.4f} here, {c['comb']:.4f} in {COMBINED.name}")
    aa = json.loads(AA_FILE.read_text())
    for M in models:
        a = aa["models"].get(M["model"])
        M["aa"] = a["aa"] if a else None; M["aa_variant"] = a["variant"] if a else None; M["aa_exact"] = a["exact"] if a else None
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    data = {"models": models, "series": [x for x in series if x["multi"]], "primary": PRIMARY, "caveats": H["caveats"], "judge": H["judge"], "rubric": H["rubric"],
            "transform": H["transform"], "eci_source": H["eci_source"], "eci_checked": "2026-09-07",
            "prices": prices, "labels": labels, "aa_source": aa["source"], "weights": {"cov": W_COV, "tldr": W_TLDR},
            "cost_check": {"n": len(ratios), "median_ratio": st.median(ratios) if ratios else None}}
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    n = sum(len(b["runs"]) for m in models for b in m["budgets"].values())
    print(f"{OUT}: {len(models)} models, {n} runs; computed cost / Claude Code's own cost, median over "
          f"{len(ratios)} runs = {st.median(ratios):.3f}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Bench Figures</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{--ground:#F6F6F2;--surface:#FFFFFF;--ink:#17181A;--ink2:#5F636A;--ink3:#8E939B;--line:#DEDFD9;--grid:#ECECE7;
  --p-anthropic:#D97757;--p-openai:#1A1A1A;--p-google:#2E9E4F;--p-meta:#0668E1;--p-moonshot:#C2185B;--p-zai:#00897B;
  --tip-bg:#22252B;--tip-ink:#F2F2EE}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#15171B;--surface:#1E2126;--ink:#ECEDE9;--ink2:#A6ABB3;--ink3:#7B8088;--line:#33373E;--grid:#272A30;
  --p-openai:#F0F0EC;--p-anthropic:#E8906F;--p-google:#4DBF6C;--p-meta:#5B9BF0;--p-moonshot:#E0568A;--p-zai:#2FB8A6;--tip-bg:#F2F2EE;--tip-ink:#17181A}}
:root[data-theme="dark"]{--ground:#15171B;--surface:#1E2126;--ink:#ECEDE9;--ink2:#A6ABB3;--ink3:#7B8088;--line:#33373E;--grid:#272A30;
  --p-openai:#F0F0EC;--p-anthropic:#E8906F;--p-google:#4DBF6C;--p-meta:#5B9BF0;--p-moonshot:#E0568A;--p-zai:#2FB8A6;--tip-bg:#F2F2EE;--tip-ink:#17181A}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:15px/1.55 "Public Sans",system-ui,sans-serif}
main{max-width:1040px;margin:0 auto;padding:36px 28px 80px}
h1{font:600 30px/1.15 "Source Serif 4",Georgia,serif;margin:0 0 6px;text-wrap:balance}
.lede{color:var(--ink2);max-width:66ch;margin:0 0 36px}
.fig{margin:0 0 44px}
.eyebrow{font:500 11px/1 "JetBrains Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);margin:0 0 6px}
h2{font:600 22px/1.2 "Source Serif 4",Georgia,serif;margin:0 0 6px;text-wrap:balance}
.read{color:var(--ink2);max-width:70ch;margin:0 0 12px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px 10px}
.cap{color:var(--ink3);font-size:12.5px;margin:8px 0 0;max-width:80ch}
.cap b{color:var(--ink2);font-weight:600}
svg{display:block;max-width:100%;overflow:visible}
text{font-family:"Public Sans",system-ui,sans-serif}
.num,.axis{font-family:"JetBrains Mono",monospace;font-variant-numeric:tabular-nums}
.axis{fill:var(--ink2);font-size:10.5px}.axname{fill:var(--ink2);font-size:11.5px}
.tick{stroke:var(--grid);stroke-width:1}.axline{stroke:var(--line);stroke-width:1}
.lab{fill:var(--ink);font-size:11.5px;cursor:grab;user-select:none}.lab.trunc{fill:var(--ink2)}
.lab:active{cursor:grabbing}
.leader{stroke:var(--ink3);stroke-width:.8;fill:none;opacity:.7}
.hit{fill:transparent;cursor:pointer}
.tools{display:flex;gap:8px;align-items:center;margin:8px 0 0;font-size:12px;color:var(--ink3)}
button{font:500 12px "Public Sans",system-ui,sans-serif;color:var(--ink2);background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:3px 9px;cursor:pointer}
button:hover{color:var(--ink)} button:focus-visible{outline:2px solid var(--p-meta);outline-offset:1px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media (max-width:700px){.grid2{grid-template-columns:1fr}}
.cell .sub2{font:11px "Public Sans",system-ui,sans-serif;color:var(--ink2);margin:0 0 4px}
@media (max-width:820px){.grid{grid-template-columns:repeat(3,1fr)}}
@media (max-width:600px){.grid{grid-template-columns:repeat(2,1fr)}}
.cell{padding:8px 8px 4px;border:1px solid var(--line);border-radius:4px;background:var(--surface)}
.cell h3{margin:0;font:600 12.5px/1.2 "Public Sans",system-ui,sans-serif}
.cell .m{font:11px "JetBrains Mono",monospace;color:var(--ink3);margin:1px 0 2px}
#tip{position:fixed;pointer-events:none;background:var(--tip-bg);color:var(--tip-ink);padding:7px 10px;border-radius:5px;
  font-size:12px;line-height:1.45;opacity:0;transition:opacity .08s;z-index:9;white-space:nowrap;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.tbl{overflow-x:auto}
details{margin-top:10px}summary{cursor:pointer;color:var(--ink2);font-size:13px;font-weight:500}
h2.group{font-size:18px;margin:8px 0 4px;padding-top:18px;border-top:1px solid var(--line)}
details.supp{margin-top:24px}details.supp>summary{font-size:15px;padding:8px 0}details.supp .fig{margin-top:24px}
ul.cav{color:var(--ink2);font-size:13px;padding-left:18px;margin:6px 0;max-width:80ch}ul.cav li{margin:3px 0}
@media (prefers-reduced-motion:reduce){#tip{transition:none}}
</style></head><body>
<main>
  <h1>Round 4: capability, time and cost</h1>
  <p class="lede" id="lede"></p>
  <div class="tools" style="margin:-24px 0 28px"><button id="copyall">copy all label positions</button><span>every figure at once, as headline_labels.json</span></div>

  <h2 class="group">Combined score</h2>
  <p class="read" id="groupC"></p>
  <section class="fig">
    <p class="eyebrow">Figure 1</p>
    <h2>General capability barely predicts performance inside the frontier</h2>
    <p class="read" id="readC1"></p>
    <div class="panel" id="figC1"></div>
    <div class="tools"><button id="alignC1">align columns</button><button id="copyC1">copy label positions</button><button id="resetC1">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capC1"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesC1"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblC1"></div></details>
  </section>

  <section class="fig">
    <p class="eyebrow">Figure 2</p>
    <h2>Combined score against what a run costs</h2>
    <p class="read" id="readC2"></p>
    <div class="panel" id="figC2"></div>
    <div class="tools"><button id="alignC2">align columns</button><button id="copyC2">copy label positions</button><button id="resetC2">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capC2"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesC2"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblC2"></div></details>
  </section>

  <h2 class="group">Finding coverage alone</h2>
  <p class="read" id="groupS"></p>
  <section class="fig">
    <p class="eyebrow">Figure 3</p>
    <h2>Finding coverage against the Artificial Analysis index</h2>
    <p class="read" id="readS1"></p>
    <div class="panel" id="figS1"></div>
    <div class="tools"><button id="alignS1">align columns</button><button id="copyS1">copy label positions</button><button id="resetS1">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capS1"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesS1"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblS1"></div></details>
  </section>

  <section class="fig">
    <p class="eyebrow">Figure 4</p>
    <h2>Finding coverage against cost</h2>
    <p class="read" id="readS2"></p>
    <div class="panel" id="figS2"></div>
    <div class="tools"><button id="alignS2">align columns</button><button id="copyS2">copy label positions</button><button id="resetS2">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capS2"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesS2"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblS2"></div></details>
  </section>

  <h2 class="group">Holistic TL;DR score alone</h2>
  <p class="read" id="groupT"></p>
  <section class="fig">
    <p class="eyebrow">Figure 5</p>
    <h2>TL;DR score against the Artificial Analysis index</h2>
    <p class="read" id="readT1"></p>
    <div class="panel" id="figT1"></div>
    <div class="tools"><button id="alignT1">align columns</button><button id="copyT1">copy label positions</button><button id="resetT1">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capT1"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesT1"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblT1"></div></details>
  </section>

  <section class="fig">
    <p class="eyebrow">Figure 6</p>
    <h2>TL;DR score against cost</h2>
    <p class="read" id="readT2"></p>
    <div class="panel" id="figT2"></div>
    <div class="tools"><button id="alignT2">align columns</button><button id="copyT2">copy label positions</button><button id="resetT2">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capT2"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesT2"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblT2"></div></details>
  </section>

  <details class="supp"><summary>Supplementary: Epoch index, time budget and harness (finding coverage)</summary>
  <section class="fig">
    <p class="eyebrow">Figure S1</p>
    <h2>Finding coverage against the Epoch Capabilities Index</h2>
    <p class="read" id="readE"></p>
    <div class="panel" id="figE"></div>
    <div class="tools"><button id="alignE">align columns</button><button id="copyE">copy label positions</button><button id="resetE">reset labels</button><span>drag a label to move it</span></div>
    <p class="cap" id="capE"></p>
    <details><summary>Notes and sources</summary><p class="cap" id="notesE"></p></details>
    <details><summary>Numbers</summary><div class="tbl" id="tblE"></div></details>
  </section>

  <section class="fig">
    <p class="eyebrow">Figure S2</p>
    <h2>Every model climbs with time; none has levelled off at two hours</h2>
    <p class="read" id="read2"></p>
    <div class="grid" id="fig2"></div>
    <p class="cap" id="cap2"></p>
  </section>

  <section class="fig">
    <p class="eyebrow">Figure S3</p>
    <h2>Same model, two harnesses</h2>
    <p class="read" id="read4"></p>
    <div class="grid2" id="fig4"></div>
    <p class="cap" id="cap4"></p>
  </section>
  </details>

  <details><summary>Caveats carried from the data file</summary><ul class="cav" id="cav"></ul></details>
</main>
<div id="tip"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent), NS = 'http://www.w3.org/2000/svg';
const BUD = [10, 30, 120];
/* the three y-axis measures; `mean` is the per-budget field, `key` the per-run field, `suffix` keys the saved label positions */
const MET = {
  comb:   {key: 'comb',   mean: 'mean_comb', suffix: '_comb', label: 'combined score',   short: 'combined'},
  strict: {key: 'strict', mean: 'mean',      suffix: '',      label: 'finding coverage', short: 'coverage'},
  tldr:   {key: 'tldr',   mean: 'mean_tldr', suffix: '_tldr', label: 'TL;DR score',      short: 'TL;DR'},
};
const WC = D.weights.cov, WT = D.weights.tldr;
const LAYERS = {};   /* figure key -> current label offsets; "copy all" gathers them into one headline_labels.json */
const fmt = v => v.toFixed(3), usd = v => v >= 100 ? '$' + v.toFixed(0) : v >= 10 ? '$' + v.toFixed(1) : '$' + v.toFixed(2);
const kfmt = n => n == null ? '—' : n >= 1e9 ? (n / 1e9).toFixed(2) + 'B' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(0) + 'k' : String(n);
const s = (t, a) => { const x = document.createElementNS(NS, t); for (const k in a) x.setAttribute(k, a[k]); return x; };
const el = (t, c, txt) => { const x = document.createElement(t); if (c) x.className = c; if (txt != null) x.textContent = txt; return x; };
const col = m => `var(--p-${m.provider})`;
const HN = {claude: 'Claude Code', codex: 'Codex CLI', react: 'ReAct'};
const PNAME = {anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', meta: 'Meta', moonshot: 'Moonshot', zai: 'Z.ai'};
const hasFb = m => Object.keys(m.fallback).length > 0;
const name1 = m => m.model + (m.eci_exact ? '' : '*') + (hasFb(m) ? '†' : '');   /* figure 1 only */
const name = m => m.model + (hasFb(m) ? '†' : '');
const fbText = m => Object.entries(m.fallback).map(([b, f]) => `${f.n} of ${f.of} runs at ${b} min`).join(' and ');
const fbNoteAll = D.models.filter(hasFb).map(m => `${fbText(m)} switched to ${Object.values(m.fallback)[0].to} after a safeguard refusal and are counted in ${m.model}’s mean`).join('. ');
const fallbacks = D.models.filter(m => !m.eci_exact);
const fbNote = fallbacks.map(m => `${m.model} uses ${m.eci_model} (${m.eci.toFixed(2)})`).join('; ');
const tip = document.getElementById('tip');
function hover(node, html) {
  node.addEventListener('mousemove', e => { tip.innerHTML = html; tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY - 34) + 'px'; });
  node.addEventListener('mouseleave', () => { tip.style.opacity = 0; });
}
/* a budget mark: hollow at 10, tinted at 30, solid at 120, in the provider's hue */
function mark(svg, cx, cy, b, c, r) {
  r = r || 5;
  if (b === 10) return svg.appendChild(s('circle', {cx, cy, r: r - .5, fill: 'var(--surface)', stroke: c, 'stroke-width': 1.8}));
  if (b === 30) return svg.appendChild(s('circle', {cx, cy, r, fill: c, 'fill-opacity': .4, stroke: c, 'stroke-width': 1.5}));
  return svg.appendChild(s('circle', {cx, cy, r: r + .5, fill: c, stroke: 'var(--surface)', 'stroke-width': 1.8}));
}
function budgetLegend(svg, x0, y0, c) {
  let lx = x0;
  [[10, '10 min'], [30, '30 min'], [120, '120 min']].forEach(([b, t]) => {
    mark(svg, lx + 6, y0, b, c || 'var(--ink2)');
    const tx = s('text', {x: lx + 16, y: y0 + 4, class: 'axis'}); tx.textContent = t; svg.append(tx); lx += 72;
  });
  return lx;
}
function providerLegend(svg, x0, y0) {
  let lx = x0;
  Object.keys(PNAME).forEach(p => {
    svg.append(s('rect', {x: lx, y: y0 - 5, width: 10, height: 10, rx: 2, fill: `var(--p-${p})`}));
    const tx = s('text', {x: lx + 15, y: y0 + 4, class: 'axis'}); tx.textContent = PNAME[p]; svg.append(tx);
    lx += 30 + PNAME[p].length * 6.6;
  });
}
function tipFor(m) {
  let h = `<b>${m.model}</b> · ${PNAME[m.provider]} · index ${m.eci.toFixed(2)}` + (m.eci_exact ? '' : ` <i>(score of ${m.eci_model})</i>`);
  BUD.forEach(b => { const q = m.budgets[b]; if (!q) return;
    h += `<br>${b} min: combined <b>${fmt(q.mean_comb)}</b> = ${WC} × coverage ${fmt(q.mean)} + ${WT} × TL;DR ${fmt(q.mean_tldr)}; ${q.runs.length} run${q.runs.length > 1 ? 's' : ''}, mean ${usd(q.cost)}`; });
  Object.entries(m.fallback).forEach(([b, f]) => { h += `<br><i>${b} min: ${f.n} of ${f.of} runs finished by ${f.to} after a refusal, counted</i>`; });
  return h;
}

/* ---- draggable labels: default placement, then the user's offsets, persisted per figure ---- */
function labelLayer(svg, items, key, bounds) {
  const store = 'mbab_labels_' + key;
  let saved = {}; try { saved = JSON.parse(localStorage.getItem(store) || 'null') || (D.labels[key] || {}); } catch (e) { saved = D.labels[key] || {}; }
  const GAP = bounds.mode === 'spread' ? 18 : 15;
  items.forEach(it => { it.w = it.text.length * 6.4 + 6; });
  const spread = (arr, y0, y1) => {       /* stack a group vertically at >= GAP, kept inside [y0, y1] */
    arr.sort((a, b) => a.py - b.py); let prev = -1e9;
    arr.forEach(it => { it.ly = Math.max(it.py, prev + GAP); prev = it.ly; });
    const over = arr.length ? arr[arr.length - 1].ly - y1 : 0; if (over > 0) arr.forEach(it => { it.ly -= over; });
    const under = arr.length ? y0 - arr[0].ly : 0; if (under > 0) arr.forEach(it => { it.ly += under; });
  };
  if (bounds.mode === 'sides') {
    /* two columns, left and right of the plot, each spread vertically; every label gets a leader */
    const left = items.filter(it => it.px < bounds.mid), right = items.filter(it => it.px >= bounds.mid);
    spread(left, bounds.y0, bounds.y1); spread(right, bounds.y0, bounds.y1);
    left.forEach(it => { it.dx = bounds.x0 + 8 - it.px; it.dy = it.ly - it.py; });
    right.forEach(it => { it.dx = bounds.x1 - 4 - it.w - it.px; it.dy = it.ly - it.py; });
  } else {
    /* spread: alternate above and below the point, then push apart anything still within GAP */
    /* outward: each label sits on the ray from the plot centre through its mark, 34 px beyond it */
    const cx0 = (bounds.x0 + bounds.x1) / 2, cy0 = (bounds.y0 + bounds.y1) / 2;
    items.forEach(it => {
      const vx = it.px - cx0, vy = it.py - cy0, n = Math.hypot(vx, vy) || 1, ux = vx / n, uy = vy / n;
      const ox = ux * 44, oy = uy * 44;
      it.dx = ox + (ux > 0.3 ? 0 : ux < -0.3 ? -it.w : -it.w / 2);
      it.dy = oy + (uy > 0.3 ? 10 : uy < -0.3 ? 0 : 4);
    });
    /* then push apart any two labels whose boxes overlap, along the axis that separates them soonest */
    for (let pass = 0; pass < 60; pass++) {
      let moved = false;
      for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        const ax = a.px + a.dx, bx = b.px + b.dx, ay = a.py + a.dy, by = b.py + b.dy;
        const ox2 = Math.min(ax + a.w, bx + b.w) - Math.max(ax, bx) + 6, oy2 = GAP - Math.abs(ay - by);
        if (ox2 > 0 && oy2 > 0) {
          moved = true;
          if (oy2 < ox2 / 3) { const sh = oy2 / 2 + .5; if (ay <= by) { a.dy -= sh; b.dy += sh; } else { a.dy += sh; b.dy -= sh; } }
          else { const sh = ox2 / 2 + .5; if (ax <= bx) { a.dx -= sh; b.dx += sh; } else { a.dx += sh; b.dx -= sh; } }
        }
      }
      if (!moved) break;
    }
    for (let pass = 0; pass < 30; pass++) {
      let moved = false;
      for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j], ax = a.px + a.dx + a.w / 2, bx = b.px + b.dx + b.w / 2, ay = a.py + a.dy, by = b.py + b.dy;
        if (Math.abs(ax - bx) < (a.w + b.w) / 2 + 4 && Math.abs(ay - by) < GAP) { const sh = (GAP - Math.abs(ay - by)) / 2 + .5; if (ay <= by) { a.dy -= sh; b.dy += sh; } else { a.dy += sh; b.dy -= sh; } moved = true; }
      }
      if (!moved) break;
    }
    items.forEach(it => { const lx = it.px + it.dx; if (lx < bounds.x0 + 4) it.dx += bounds.x0 + 4 - lx; if (lx + it.w > bounds.x1 - 4) it.dx -= lx + it.w - (bounds.x1 - 4); });
  }
  items.forEach(it => { if (saved[it.id]) { it.dx = saved[it.id][0]; it.dy = saved[it.id][1]; } });
  const g = s('g', {}); svg.append(g);
  /* one text and one leader per label, created once; dragging only moves them */
  const place = it => {
    const lx = it.px + it.dx, ly = it.py + it.dy;
    it.t.setAttribute('x', lx); it.t.setAttribute('y', ly);
    const w = it.t.getComputedTextLength ? (it.t.getComputedTextLength() || it.w) : it.w; it.w = w;
    if (Math.hypot(it.dx, it.dy) <= 16) { it.l.setAttribute('visibility', 'hidden'); return; }
    it.l.setAttribute('visibility', 'visible');
    /* leader ends at whichever edge of the label box is nearest the mark */
    const side = it.px < lx ? -1 : it.px > lx + w ? 1 : 0, above = it.py < ly - 12, below = it.py > ly + 2;
    const ex = side < 0 ? lx - 3 : side > 0 ? lx + w + 3 : it.px;
    const ey = side !== 0 ? ly - 4 : (above ? ly - 12 : below ? ly + 3 : ly - 4);
    it.l.setAttribute('x1', it.px); it.l.setAttribute('y1', it.py); it.l.setAttribute('x2', ex); it.l.setAttribute('y2', ey);
  };
  items.forEach(it => {
    it.l = s('line', {class: 'leader'}); g.append(it.l);
    it.t = s('text', {class: 'lab' + (it.cls ? ' ' + it.cls : '')}); it.t.textContent = it.text; g.append(it.t);
    hover(it.t, it.tip);
    it.t.addEventListener('pointerdown', e => {
      e.preventDefault(); e.stopPropagation(); it.t.setPointerCapture(e.pointerId);
      const k = svg.viewBox.baseVal.width / svg.getBoundingClientRect().width;
      const ox = it.dx - e.clientX * k, oy = it.dy - e.clientY * k;
      const mv = ev => { it.dx = ox + ev.clientX * k; it.dy = oy + ev.clientY * k; place(it); };
      const up = () => { it.t.removeEventListener('pointermove', mv); saved[it.id] = [Math.round(it.dx), Math.round(it.dy)];
        try { localStorage.setItem(store, JSON.stringify(saved)); } catch (e2) {} };
      it.t.addEventListener('pointermove', mv); it.t.addEventListener('pointerup', up, {once: true}); it.t.addEventListener('pointercancel', up, {once: true});
    });
  });
  items.forEach(place);
  LAYERS[key] = () => { const out = {}; items.forEach(it => { out[it.id] = [Math.round(it.dx), Math.round(it.dy)]; }); return out; };
  return {
    copy: () => { const out = {}; items.forEach(it => { out[it.id] = [Math.round(it.dx), Math.round(it.dy)]; });
      navigator.clipboard.writeText(JSON.stringify({[key]: out}, null, 1)).catch(() => {}); },
    reset: () => { try { localStorage.removeItem(store); } catch (e) {} location.reload(); },
    /* labels whose left edges lie within TOL px form a column; each column shares one edge,
       the left edge for columns on the left half, the right edge on the right half */
    align: () => {
      const TOL = 40, mid = (bounds.x0 + bounds.x1) / 2;
      const sorted = items.slice().sort((a, b) => (a.px + a.dx) - (b.px + b.dx));
      const groups = []; sorted.forEach(it => { const g2 = groups[groups.length - 1];
        if (g2 && (it.px + it.dx) - (g2[g2.length - 1].px + g2[g2.length - 1].dx) <= TOL) g2.push(it); else groups.push([it]); });
      groups.forEach(g2 => {
        if (g2.length < 2) return;
        const cx = g2.reduce((a, it) => a + it.px + it.dx + it.w / 2, 0) / g2.length;
        if (cx < mid) { const L2 = Math.min(...g2.map(it => it.px + it.dx)); g2.forEach(it => { it.dx = L2 - it.px; }); }
        else { const R2 = Math.max(...g2.map(it => it.px + it.dx + it.w)); g2.forEach(it => { it.dx = R2 - it.w - it.px; }); }
      });
      items.forEach(it => { place(it); saved[it.id] = [Math.round(it.dx), Math.round(it.dy)]; });
      try { localStorage.setItem(store, JSON.stringify(saved)); } catch (e) {}
    },
  };
}

document.getElementById('lede').textContent =
  `Twelve models on the round-4 blind prompt at 10, 30 and 120 minutes, graded by ${D.judge} on the ${D.rubric} rubric. `
  + 'Finding coverage is the strict transform: each rubric point scored s in [0, 1] becomes max(2s − 1, 0), so anything at or below the midpoint counts as nothing, then the mean over points. '
  + `The headline measure is the combined score, ${WC} × finding coverage + ${WT} × holistic TL;DR score; Figures 3 to 6 show each part alone on the same axes. `
  + `${D.models.filter(m => m.multi).map(m => m.model).join(' and ')} ran under both Codex CLI and the ReAct scaffold; the main figures show their ${HN[D.primary]} runs and Figure S3 compares the two. Runs in which Claude Code switched to a fallback model after a safeguard refusal stay with the model that was asked for, marked †.`;

/* ================= Figures 1 and 1b: a capability index against strict score ================= */
function capabilityFigure(o) {
  const M = D.models.filter(m => m[o.key] != null).map(m => Object.assign({}, m)).sort((a, b) => a[o.key] - b[o.key]);
  const K = o.key, mt = MET[o.metric || 'strict'];
  /* a broken x scale: stretches of index with nothing in them are compressed to a fixed gap,
     marked on the axis, so one outlier does not hand 40% of the width to empty space */
  const GAPMIN = 6, GAPPX = 26, PAD = 1.2;
  const segs = []; let cur = [M[0][K] - PAD, M[0][K] + PAD];
  M.slice(1).forEach(m => { if (m[K] - cur[1] > GAPMIN) { segs.push(cur); cur = [m[K] - PAD, m[K] + PAD]; } else cur[1] = m[K] + PAD; });
  segs.push(cur);
  const GUT = 150;                               /* label gutters either side of the plot */
  const W = 860, Hh = 520, L = 54 + GUT, R = 24 + GUT, T = 16, AXB = o.axisSub ? 58 : 46, B = AXB + 44, IW = W - L - R, IH = Hh - T - B;
  const span = segs.reduce((a, g) => a + g[1] - g[0], 0), pxPerUnit = (IW - GAPPX * (segs.length - 1)) / span;
  const segX0 = []; let acc = L; segs.forEach(g => { segX0.push(acc); acc += (g[1] - g[0]) * pxPerUnit + GAPPX; });
  const x = v => { for (let i = 0; i < segs.length; i++) if (v <= segs[i][1] + 1e-9 || i === segs.length - 1) return segX0[i] + (v - segs[i][0]) * pxPerUnit; };
  const ys = M.flatMap(m => Object.values(m.budgets).flatMap(q => q.runs.map(r => r[mt.key])));
  const Y1 = Math.ceil((Math.max(...ys) + 0.03) * 10) / 10;
  const y = v => T + IH - v / Y1 * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${Hh}`, width: '100%', role: 'img', 'aria-label': mt.label + ' at three budgets against ' + o.axis});
  for (let t = 0; t <= Y1 + 1e-9; t += 0.1) {
    svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
    const lb = s('text', {x: L - 8, y: y(t) + 3.5, 'text-anchor': 'end', class: 'axis'}); lb.textContent = Math.round(t * 100) + '%'; svg.append(lb);
  }
  segs.forEach((g, i) => {
    let ticks = []; for (let v = Math.ceil(g[0] / 5) * 5; v <= g[1]; v += 5) ticks.push(v);
    if (!ticks.length) ticks = [Math.round((g[0] + g[1]) / 2)];   /* a narrow segment still gets one labelled tick */
    ticks.forEach(v => {
      svg.append(s('line', {x1: x(v), x2: x(v), y1: T, y2: T + IH, class: 'tick'}));
      const lb = s('text', {x: x(v), y: T + IH + 16, 'text-anchor': 'middle', class: 'axis'}); lb.textContent = v; svg.append(lb);
    });
    const xe = segX0[i] + (g[1] - g[0]) * pxPerUnit;
    svg.append(s('line', {x1: segX0[i], x2: xe, y1: y(0), y2: y(0), class: 'axline'}));
    if (i < segs.length - 1) {   /* the break glyph */
      const bx = xe + GAPPX / 2;
      svg.append(s('rect', {x: bx - 6, y: y(0) - 8, width: 12, height: 16, fill: 'var(--surface)'}));
      [bx - 3, bx + 3].forEach(cx => svg.append(s('line', {x1: cx - 3, x2: cx + 3, y1: y(0) + 6, y2: y(0) - 6, stroke: 'var(--ink3)', 'stroke-width': 1.2})));
    }
  });
  const ax = s('text', {x: L + IW / 2, y: T + IH + 34, 'text-anchor': 'middle', class: 'axname'}); ax.textContent = o.axis; svg.append(ax);
  if (o.axisSub) { const sub = s('text', {x: L + IW / 2, y: T + IH + 49, 'text-anchor': 'middle', class: 'axis'}); sub.textContent = '(' + o.axisSub + ')'; svg.append(sub); }
  const ay = s('text', {x: 13, y: T + IH / 2, class: 'axname', transform: `rotate(-90 13 ${T + IH / 2})`, 'text-anchor': 'middle'}); ay.textContent = 'score'; svg.append(ay);

  /* dodge columns that would overlap; hairline-free, so the true position is only in the tooltip */
  const MINSEP = 18; M.forEach(m => { m.px = x(m[K]); });
  for (let pass = 0; pass < 40; pass++) { let moved = false;
    for (let i = 1; i < M.length; i++) { const d = M[i].px - M[i - 1].px; if (d < MINSEP) { const sh = (MINSEP - d) / 2; M[i].px += sh; M[i - 1].px -= sh; moved = true; } }
    if (!moved) break; }
  const maxNudge = Math.max(...M.map(m => Math.abs(m.px - x(m[K])))) / pxPerUnit;

  const items = [];
  M.forEach(m => {
    const c = col(m), pts = BUD.filter(b => m.budgets[b]).map(b => ({b, q: m.budgets[b]}));
    const top = pts[pts.length - 1];
    /* the column spans the lowest to the highest budget mean, whichever budgets those are */
    if (pts.length > 1) svg.append(s('line', {x1: m.px, x2: m.px, y1: y(Math.min(...pts.map(p => p.q[mt.mean]))), y2: y(Math.max(...pts.map(p => p.q[mt.mean]))), stroke: c, 'stroke-width': 1.2, opacity: .35}));
    top.q.runs.forEach(r => svg.append(s('circle', {cx: m.px, cy: y(r[mt.key]), r: 1.8, fill: c, opacity: .45})));
    pts.forEach(p => mark(svg, m.px, y(p.q[mt.mean]), p.b, c));
    const hit = s('rect', {x: m.px - 9, y: y(Y1), width: 18, height: IH, class: 'hit'}); hover(hit, o.tip(m)); svg.append(hit);
    items.push({id: m.model, text: o.name(m), px: m.px, py: y(top.q[mt.mean]), cls: '', tip: o.tip(m)});
  });
  /* legend below the axis, so it never sits over a column */
  budgetLegend(svg, L + 10, T + IH + AXB + 8);
  providerLegend(svg, L + 10, T + IH + AXB + 30);
  const lab = labelLayer(svg, items, o.key + mt.suffix, {x0: L - GUT + 4, x1: W - 24, y0: T + 6, y1: T + IH - 6, mode: 'sides', mid: M.map(m => m.px).sort((a, b) => a - b)[Math.ceil(M.length / 2)]});
  document.getElementById(o.ids.copy).onclick = lab.copy; document.getElementById(o.ids.reset).onclick = lab.reset; document.getElementById(o.ids.align).onclick = lab.align;
  document.getElementById(o.ids.fig).replaceChildren(svg);

  /* trim: fit the viewBox to the drawn content, labels included, with a small margin */
  try {
    /* the y-axis name sits just left of whatever is leftmost, labels included, instead of at a fixed margin */
    ay.remove(); const b0 = svg.getBBox(); const ax0 = b0.x - 10;
    ay.setAttribute('x', ax0); ay.setAttribute('transform', `rotate(-90 ${ax0} ${T + IH / 2})`); svg.append(ay);
    const bb = svg.getBBox(), PADV = 8;
    svg.setAttribute('viewBox', `${bb.x - PADV} ${bb.y - PADV} ${bb.width + 2 * PADV} ${bb.height + 2 * PADV}`); } catch (e) {}
  o.captions(maxNudge);
  const t = document.createElement('table'), hd = t.insertRow();
  ['model', 'provider', o.axisShort, '10 min', '30 min', '120 min'].forEach(h => hd.append(el('th', null, h)));
  M.slice().sort((a, b) => b[K] - a[K]).forEach(m => {
    const r = t.insertRow(); r.insertCell().textContent = o.name(m) + (m.truncated ? ' ‡' : ''); r.insertCell().textContent = PNAME[m.provider];
    r.insertCell().textContent = o.fmtx(m);
    BUD.forEach(b => { const q = m.budgets[b]; r.insertCell().textContent = q ? fmt(q[mt.mean]) + ` (${q.runs.map(x => fmt(x[mt.key])).join(', ')})` : '—'; });
  });
  document.getElementById(o.ids.tbl).replaceChildren(t, el('p', 'cap', '‡ did not reach 120 min. Parentheses: individual runs. ' + o.tableNote));
}


const trunc = D.models.filter(m => m.truncated);
const aaName = m => m.model + (hasFb(m) ? '†' : '');
const aaTip = m => `<b>${m.model}</b> · Artificial Analysis index ${m.aa} <i>(${m.aa_variant})</i>` + tipFor(m).slice(tipFor(m).indexOf('<br>'));
const aaFb = D.models.filter(m => m.aa != null && !m.aa_exact).map(m => `${m.model}: Artificial Analysis lists only its ${m.aa_variant.split(' (')[1].split(')')[0]} variant, so that is the value used`).join('; ');
const fbCap = (fbNoteAll ? `<b>†</b> ${fbNoteAll}. ` : '') + (trunc.length ? trunc.map(m => `${m.model}: ${m.why}.`).join(' ') : '');
/* where the highest-index model lands, on a metric, ranking every model by its mean at the deepest budget it reached */
const placing = (mt, key) => {
  const M = D.models.filter(m => m[key] != null), order = M.slice().sort((a, b) => b.budgets[b.top][mt.mean] - a.budgets[a.top][mt.mean]);
  const top = M.reduce((a, b) => b[key] > a[key] ? b : a), lowest = M.slice().sort((a, b) => a[key] - b[key]).slice(0, Math.floor(M.length / 2));
  const ord = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');
  const bestLow = lowest.reduce((a, b) => order.indexOf(b) < order.indexOf(a) ? b : a);
  return `${top.model}, the highest on the index, places ${ord(order.indexOf(top) + 1)} of ${M.length}; ${bestLow.model}, in the bottom half of the index, places ${ord(order.indexOf(bestLow) + 1)}.`;
};
const MARKS = 'The three marks are its score at 10, 30 and 120 minutes, hollow to solid. Small dots are the individual runs behind the top mark. ';
const aaFig = (metric, id, read) => capabilityFigure({
  key: 'aa', metric, axis: 'Artificial Analysis Intelligence Index v4.3', axisSub: 'highest listed reasoning effort per model', axisShort: 'AA index', name: aaName, tip: aaTip, fmtx: m => String(m.aa),
  ids: {fig: 'fig' + id, copy: 'copy' + id, reset: 'reset' + id, align: 'align' + id, tbl: 'tbl' + id},
  tableNote: aaFb ? '* ' + aaFb + '.' : '',
  captions: maxNudge => {
    document.getElementById('read' + id).textContent = read + ' ' + placing(MET[metric], 'aa');
    document.getElementById('cap' + id).innerHTML = (aaFb ? `${aaFb}. ` : '') + fbCap;
    document.getElementById('notes' + id).innerHTML =
      `Columns that would overlap are nudged apart by at most ${maxNudge.toFixed(2)} index points; hover for the true value. Source: ${D.aa_source}`;
  },
});
const COMBDEF = `Combined score is ${WC} × finding coverage + ${WT} × holistic TL;DR score.`;
document.getElementById('groupC').textContent =
  `${COMBDEF} Finding coverage is the strict v2 score: how much of the incident the report pinned down. The TL;DR score is one 0 to 1 judgement of whether a reader of the summary alone would come away with the story. Both are ${D.judge}'s grades over the same reports.`;
document.getElementById('groupS').textContent = 'The previous headline measure on its own: the strict v2 finding-coverage score, same axes as above.';
document.getElementById('groupT').textContent = 'The holistic TL;DR score on its own, same axes as above.';
aaFig('comb', 'C1', 'One column per model at its index score. ' + MARKS + COMBDEF);
aaFig('strict', 'S1', 'Finding coverage: the strict score as a percentage of the rubric. ' + MARKS);
aaFig('tldr', 'T1', 'The holistic TL;DR score: would a reader of the 200-word summary alone come away with the story, 0 to 1. ' + MARKS);
capabilityFigure({
  key: 'eci', metric: 'strict', axis: 'Epoch Capabilities Index', axisShort: 'index', name: name1, tip: tipFor, fmtx: m => m.eci.toFixed(2),
  ids: {fig: 'figE', copy: 'copyE', reset: 'resetE', align: 'alignE', tbl: 'tblE'},
  tableNote: '* ' + fbNote + '.',
  captions: maxNudge => {
    document.getElementById('readE').textContent = 'Finding coverage placed by the Epoch Capabilities Index instead. ' + MARKS + placing(MET.strict, 'eci');
    document.getElementById('capE').innerHTML =
      `<b>*</b> Epoch has no score for the model itself; the previous generation’s is used (${fbNote}). ` + fbCap;
    document.getElementById('notesE').innerHTML =
      `Columns that would overlap are nudged apart by at most ${maxNudge.toFixed(2)} index points; hover for the true value. `
      + `Epoch’s 95% intervals are about ±2.5 points and overlap for most of the field. Epoch’s table was rechecked on ${D.eci_checked}. Index source: ${D.eci_source}.`;
  },
});

/* ================= Figure 2: time budget, one panel per model ================= */
(function () {
  const box = document.getElementById('fig2');
  const order = D.models.slice().sort((a, b) => {
    const ta = a.budgets[a.top].mean, tb = b.budgets[b.top].mean; return tb - ta; });
  const W = 230, Hh = 150, L = 30, R = 10, T = 12, B = 24, IW = W - L - R, IH = Hh - T - B;
  const Y1 = 0.5, lx = v => L + (Math.log10(v) - 1) / (Math.log10(120) - 1) * IW, y = v => T + IH - v / Y1 * IH;
  order.forEach(m => {
    const c = col(m), card = el('div', 'cell');
    const meta = BUD.map(b => m.budgets[b] ? `${b}m ${fmt(m.budgets[b].mean)}` : null).filter(Boolean).join(' · ');
    card.append(el('h3', null, name(m)), el('div', 'm', meta));
    const svg = s('svg', {viewBox: `0 0 ${W} ${Hh}`, width: '100%', role: 'img', 'aria-label': `${m.model}: strict score against time budget`});
    [0, .1, .2, .3, .4, .5].forEach(t => { svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
      if (t === 0 || t === .25 || t === .5 || t === .5) { const lb = s('text', {x: L - 5, y: y(t) + 3.5, 'text-anchor': 'end', class: 'axis'}); lb.textContent = t.toFixed(1); svg.append(lb); } });
    BUD.forEach(b => { const lb = s('text', {x: lx(b), y: Hh - 8, 'text-anchor': 'middle', class: 'axis'}); lb.textContent = b + 'm'; svg.append(lb); });
    const pts = BUD.filter(b => m.budgets[b]).map(b => ({b, q: m.budgets[b]}));
    if (pts.length > 1) svg.append(s('polyline', {points: pts.map(p => `${lx(p.b)},${y(p.q.mean)}`).join(' '), fill: 'none', stroke: c, 'stroke-width': 1.8, 'stroke-linejoin': 'round'}));
    pts.forEach(p => { p.q.runs.forEach(r => {
        const cx = lx(p.b), cy = y(r.strict);
        svg.append(s('circle', {cx, cy, r: 2, fill: c, opacity: .45}));
        if (r.served) svg.append(s('path', {d: `M${cx - 3.5},${cy - 3.5}L${cx + 3.5},${cy + 3.5}M${cx - 3.5},${cy + 3.5}L${cx + 3.5},${cy - 3.5}`, stroke: 'var(--ink2)', 'stroke-width': 1.2}));
      }); mark(svg, lx(p.b), y(p.q.mean), p.b, c, 4.5); });
    const hit = s('rect', {x: L, y: T, width: IW, height: IH, class: 'hit'}); hover(hit, tipFor(m)); svg.append(hit);
    card.append(svg);
    const notes = [];
    Object.entries(m.fallback).forEach(([b, f]) => notes.push(`× ${f.n} of ${f.of} at ${b} min finished by ${f.to}`));
    BUD.filter(b => !m.budgets[b]).forEach(b => notes.push(`no run at ${b} min`));
    if (notes.length) card.append(el('div', 'm', notes.join('; ')));
    box.append(card);
  });
  document.getElementById('read2').textContent =
    'Panels ordered by score at the deepest budget reached. Same vertical scale throughout; the time axis is logarithmic. '
    + 'The line joins the per-budget means; small dots are individual runs.';
  document.getElementById('cap2').innerHTML =
    'Each budget ran a different prompt, so a step between budgets is prompt and time together. <b>×</b> a run finished by a fallback model after a safeguard refusal, counted in the mean.';
})();

/* ================= cost against a metric ================= */
function costFigure(o) {
  const mt = MET[o.metric];
  const M = D.models.map(m => Object.assign({}, m)).sort((a, b) => a.eci - b.eci);
  M.forEach(m => { m.label = o.dagger === false ? m.model : name(m); m.id = m.model; });
  const pts = M.flatMap(m => BUD.filter(b => m.budgets[b]).map(b => ({m, b, q: m.budgets[b]})));
  const cs = pts.map(p => p.q.cost);
  const X0 = Math.pow(10, Math.floor(Math.log10(Math.min(...cs)))), X1 = Math.pow(10, Math.ceil(Math.log10(Math.max(...cs))));
  const Y1 = Math.ceil((Math.max(...pts.map(p => p.q[mt.mean])) + 0.04) * 10) / 10;
  const W = 980, Hh = 520, L = 54, R = 24, T = 16, B = 46, IW = W - L - R, IH = Hh - T - B;
  const x = v => L + (Math.log10(v) - Math.log10(X0)) / (Math.log10(X1) - Math.log10(X0)) * IW, y = v => T + IH - v / Y1 * IH;
  const svg = s('svg', {viewBox: `0 0 ${W} ${Hh}`, width: '100%', role: 'img', 'aria-label': mt.label + ' against estimated cost per run'});
  for (let t = 0; t <= Y1 + 1e-9; t += 0.1) { svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
    const lb = s('text', {x: L - 8, y: y(t) + 3.5, 'text-anchor': 'end', class: 'axis'}); lb.textContent = Math.round(t * 100) + '%'; svg.append(lb); }
  for (let d = X0; d <= X1; d *= 10) {
    [1, 2, 5].forEach(k => { const v = d * k; if (v > X1) return;
      svg.append(s('line', {x1: x(v), x2: x(v), y1: T, y2: T + IH, class: 'tick', opacity: k === 1 ? 1 : .6}));
      const lb = s('text', {x: x(v), y: Hh - 24, 'text-anchor': 'middle', class: 'axis'}); lb.textContent = v >= 1 ? '$' + v : '$' + v.toFixed(2).replace(/0+$/, ''); svg.append(lb); });
  }
  svg.append(s('line', {x1: L, x2: W - R, y1: y(0), y2: y(0), class: 'axline'}));
  const ax = s('text', {x: L + IW / 2, y: Hh - 6, 'text-anchor': 'middle', class: 'axname'}); ax.textContent = 'estimated cost per run, USD at list price (log scale)'; svg.append(ax);
  const ay = s('text', {x: 13, y: T + IH / 2, class: 'axname', transform: `rotate(-90 13 ${T + IH / 2})`, 'text-anchor': 'middle'}); ay.textContent = 'score'; svg.append(ay);
  /* Pareto frontier over every model-budget mark: a mark is on it when no other mark costs the same
     or less and scores the same or more. Drawn as a staircase: from each frontier mark, flat to the
     right until the next one's cost, then up. The flat run says "at this price, this is the best
     score seen"; a sloped line would claim scores nobody measured. */
  /* the efficient frontier as an upper convex hull in (log cost, score): the marks you cannot beat
     by mixing two others, joined by straight segments, from the cheapest hull mark to the best score */
  const P = pts.map(p => ({p, X: Math.log10(p.q.cost), Y: p.q[mt.mean]})).sort((a, b) => a.X - b.X || a.Y - b.Y);
  const cross = (o, a, b) => (a.X - o.X) * (b.Y - o.Y) - (a.Y - o.Y) * (b.X - o.X);
  const hull = [];
  P.forEach(q => { while (hull.length >= 2 && cross(hull[hull.length - 2], hull[hull.length - 1], q) >= 0) hull.pop(); hull.push(q); });
  const best = P.reduce((a, b) => b.Y > a.Y ? b : a);
  let front = hull.slice(0, hull.findIndex(h => h === best) + 1);
  const start = front.findIndex((h, i) => front.slice(i + 1).every(o => o.Y > h.Y));   /* drop any cheap tail that something later dominates */
  front = front.slice(Math.max(0, start)).map(h => h.p);
  svg.append(s('polyline', {points: front.map(p => `${x(p.q.cost)},${y(p.q[mt.mean])}`).join(' '), fill: 'none', stroke: 'var(--ink2)', 'stroke-width': 1.2, opacity: .9}));
  const fa = front[Math.floor((front.length - 1) / 2)], fb2 = front[Math.floor((front.length - 1) / 2) + 1] || fa;
  const ft = s('text', {x: (x(fa.q.cost) + x(fb2.q.cost)) / 2 - 8, y: (y(fa.q[mt.mean]) + y(fb2.q[mt.mean])) / 2 - 8, 'text-anchor': 'end', class: 'axis'}); ft.textContent = 'efficient frontier'; svg.append(ft);

  const items = [];
  M.forEach(m => {
    const c = col(m), mp = BUD.filter(b => m.budgets[b]).map(b => ({b, q: m.budgets[b]}));
    if (mp.length > 1) svg.append(s('polyline', {points: mp.map(p => `${x(p.q.cost)},${y(p.q[mt.mean])}`).join(' '), fill: 'none', stroke: c, 'stroke-width': 1.4, 'stroke-dasharray': '2 4', 'stroke-linecap': 'round', opacity: .8}));
    mp.forEach(p => {
      mark(svg, x(p.q.cost), y(p.q[mt.mean]), p.b, c);
      const r = p.q.runs, tk = k => kfmt(r.reduce((a, z) => a + (z.tokens[k] || 0), 0) / r.length);
      const hit = s('circle', {cx: x(p.q.cost), cy: y(p.q[mt.mean]), r: 9, class: 'hit'});
      hover(hit, `<b>${m.model}</b> · ${HN[m.harness]} · ${p.b} min · ${mt.short} ${fmt(p.q[mt.mean])} over ${r.length} run${r.length > 1 ? 's' : ''}`
        + `<br>mean cost <b>${usd(p.q.cost)}</b> with the recorded caching · ${usd(p.q.cost_nocache)} if nothing were cached`
        + `<br>mean tokens: input ${tk('input_tokens')} (uncached ${tk('input_tokens_uncached')}, cache read ${tk('cache_read_tokens')}, cache write ${tk('cache_write_tokens')}), output ${tk('output_tokens')} (reasoning ${tk('reasoning_tokens')})`
        + `<br>per run: ${r.map(z => usd(z.cost)).join(' · ')}`);
      svg.append(hit);
    });
    const top = mp[mp.length - 1];
    const onFront = front.some(p => p.m === m && p.b === top.b);      /* the budget is named only on frontier marks */
    const tp = D.models.find(q => q.model === m.model);
    items.push({id: m.id, text: onFront ? `${m.label} ${top.b}m` : m.label, px: x(top.q.cost), py: y(top.q[mt.mean]), tip: tipFor(tp)});
    front.filter(p => p.m === m && p.b !== top.b).forEach(p =>          /* frontier marks at a shorter budget get their own label */
      items.push({id: `${m.id}@${p.b}`, text: `${m.label} ${p.b}m`, px: x(p.q.cost), py: y(p.q[mt.mean]), tip: tipFor(tp)}));
  });
  budgetLegend(svg, L + 10, T + 10);
  providerLegend(svg, L + 10, T + 32);
  const lab = labelLayer(svg, items, 'cost' + mt.suffix, {x0: L, x1: W - R, y0: T + 50, y1: T + IH - 6, mode: 'spread'});
  document.getElementById(o.ids.copy).onclick = lab.copy; document.getElementById(o.ids.reset).onclick = lab.reset; document.getElementById(o.ids.align).onclick = lab.align;
  document.getElementById(o.ids.fig).replaceChildren(svg);
  const PR = D.prices.models, cc = D.cost_check;
  try {
    ay.remove(); const b0 = svg.getBBox(); const ax0 = b0.x - 10;
    ay.setAttribute('x', ax0); ay.setAttribute('transform', `rotate(-90 ${ax0} ${T + IH / 2})`); svg.append(ay);
    const bb = svg.getBBox(), PADV = 8;
    svg.setAttribute('viewBox', `${bb.x - PADV} ${bb.y - PADV} ${bb.width + 2 * PADV} ${bb.height + 2 * PADV}`); } catch (e) {}
  o.captions(front);
  const t = document.createElement('table'), hd = t.insertRow();
  ['model', 'budget', mt.short, 'coverage', 'TL;DR', 'runs', 'mean cost', 'no-cache cost', 'input tokens', 'cache read', 'output', 'wall min'].forEach(h => hd.append(el('th', null, h)));
  M.slice().sort((a, b) => b.budgets[b.top].mean - a.budgets[a.top].mean).forEach(m => BUD.filter(b => m.budgets[b]).forEach(b => {
    const q = m.budgets[b], r = t.insertRow(), avg = k => kfmt(q.runs.reduce((a, z) => a + (z.tokens[k] || 0), 0) / q.runs.length);
    [`${name(m)} · ${HN[m.harness]}`, b, fmt(q[mt.mean]), fmt(q.mean), fmt(q.mean_tldr), q.runs.length, usd(q.cost), usd(q.cost_nocache), avg('input_tokens'), avg('cache_read_tokens'), avg('output_tokens'),
     (q.runs.reduce((a, z) => a + z.wall_min, 0) / q.runs.length).toFixed(0)].forEach(v => r.insertCell().textContent = v);
  }));
  document.getElementById(o.ids.tbl).replaceChildren(t);
}

const costFig = (metric, id, read, extra) => costFigure({
  ...(extra || {}), metric, ids: {fig: 'fig' + id, copy: 'copy' + id, reset: 'reset' + id, align: 'align' + id, tbl: 'tbl' + id},
  captions: front => {
    const PR = D.prices.models, cc = D.cost_check, mt = MET[metric];
    document.getElementById('read' + id).textContent = read
      + ' Each mark is a model at one budget: mean score against mean estimated cost per run. Dotted lines join a model’s three budgets; the label sits at the deepest. The solid line is the efficient frontier: the marks no mix of two others can beat on both cost and score, labelled with their time limit.';
    document.getElementById('cap' + id).innerHTML =
      `Cost is each run’s recorded uncached-input, cache-read, cache-write and output tokens at the served model’s direct-API list rate, as if every harness ran on an API key; hover a mark for the no-cache figure. `
      + `<b>Frontier on ${mt.label}:</b> ${front.map(p => `${p.m.label} ${p.b}m`).join(' → ')}. `
      + `Cost is mostly turns times context, so it belongs to the harness as much as the model; ${D.models.filter(m => m.multi).map(m => m.model).join(' and ')} are shown under ${HN[D.primary]} here and compared across harnesses in Figure S3.`
      + (fbNoteAll ? ` <b>†</b> ${fbNoteAll}.` : '');
    document.getElementById('notes' + id).innerHTML =
      `Prices: ${D.prices.source} Reasoning tokens are billed as output and sit inside the output count. Subscription-CLI runs are priced as if paid per token; fallback runs at the model that served them. `
      + (cc.median_ratio ? `Check: over the ${cc.n} Claude Code runs, which report their own cost, this estimate is ${(cc.median_ratio * 100).toFixed(0)}% of that figure (median). ` : '')
      + `Rates, $ per million input / cache read / output: ` + Object.entries(PR).map(([k, v]) => `${k.split('/')[1]} ${v.input}/${v.cache_read}/${v.output}`).join('; ') + '.';
  },
});
costFig('comb', 'C2', COMBDEF, {dagger: false});   /* the fallback note stays in the caption; no mark on the label */
costFig('strict', 'S2', 'Finding coverage against cost.');
costFig('tldr', 'T2', 'Holistic TL;DR score against cost.');

/* ================= Figure 4: harness comparison for models run under two ================= */
(function () {
  const box = document.getElementById('fig4');
  const byModel = {};
  D.series.forEach(sr => { (byModel[sr.model] = byModel[sr.model] || []).push(sr); });
  const DASH = {codex: '2 4', react: '7 4', claude: ''};
  const W = 470, Hh = 240, L = 40, R = 14, T = 14, B = 30, IW = W - L - R, IH = Hh - T - B, Y1 = 0.5;
  const y = v => T + IH - v / Y1 * IH;
  Object.entries(byModel).forEach(([model, chains]) => {
    const prov = chains[0].provider, c = `var(--p-${prov})`;
    /* left: score against time; right: score against cost. Same two chains in both. */
    [['time', 'strict score against time budget', v => L + (Math.log10(v) - 1) / (Math.log10(120) - 1) * IW],
     ['cost', 'strict score against estimated cost per run', null]].forEach(([kind, title, lx]) => {
      const card = el('div', 'cell'); card.append(el('h3', null, `${model}: ${title}`));
      const allc = chains.flatMap(ch => Object.values(ch.budgets).map(q => q.cost));
      const X0 = Math.pow(10, Math.floor(Math.log10(Math.min(...allc)))), X1 = Math.pow(10, Math.ceil(Math.log10(Math.max(...allc))));
      const xc = v => L + (Math.log10(v) - Math.log10(X0)) / (Math.log10(X1) - Math.log10(X0)) * IW;
      const svg = s('svg', {viewBox: `0 0 ${W} ${Hh}`, width: '100%', role: 'img', 'aria-label': `${model}: ${title}, by harness`});
      [0, .1, .2, .3, .4, .5].forEach(t => { svg.append(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), class: 'tick'}));
        const lb = s('text', {x: L - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'axis'}); lb.textContent = t.toFixed(1); svg.append(lb); });
      if (kind === 'time') BUD.forEach(b => { const lb = s('text', {x: lx(b), y: Hh - 10, 'text-anchor': 'middle', class: 'axis'}); lb.textContent = b + 'm'; svg.append(lb); });
      else for (let d = X0; d <= X1; d *= 10) [1, 2, 5].forEach(k => { const v = d * k; if (v > X1) return;
        svg.append(s('line', {x1: xc(v), x2: xc(v), y1: T, y2: T + IH, class: 'tick', opacity: k === 1 ? 1 : .5}));
        const lb = s('text', {x: xc(v), y: Hh - 10, 'text-anchor': 'middle', class: 'axis'}); lb.textContent = '$' + (v >= 1 ? v : v.toFixed(2).replace(/0+$/, '')); svg.append(lb); });
      svg.append(s('line', {x1: L, x2: W - R, y1: y(0), y2: y(0), class: 'axline'}));
      chains.forEach(ch => {
        const mp = BUD.filter(b => ch.budgets[b]).map(b => ({b, q: ch.budgets[b]}));
        const px = p => kind === 'time' ? lx(p.b) : xc(p.q.cost);
        if (mp.length > 1) svg.append(s('polyline', {points: mp.map(p => `${px(p)},${y(p.q.mean)}`).join(' '), fill: 'none', stroke: c, 'stroke-width': 1.6, 'stroke-dasharray': DASH[ch.harness], 'stroke-linecap': 'round', opacity: .85}));
        mp.forEach(p => {
          p.q.runs.forEach(r => svg.append(s('circle', {cx: kind === 'time' ? lx(p.b) : xc(r.cost), cy: y(r.strict), r: 2, fill: c, opacity: .4})));
          mark(svg, px(p), y(p.q.mean), p.b, c, 4.5);
          const hit = s('circle', {cx: px(p), cy: y(p.q.mean), r: 9, class: 'hit'});
          hover(hit, `<b>${model}</b> · ${HN[ch.harness]} · ${p.b} min<br>strict ${fmt(p.q.mean)} over ${p.q.runs.length} run${p.q.runs.length > 1 ? 's' : ''}: ${p.q.runs.map(r => fmt(r.strict)).join(' · ')}<br>mean cost ${usd(p.q.cost)}: ${p.q.runs.map(r => usd(r.cost)).join(' · ')}`);
          svg.append(hit);
        });
        const last = mp[mp.length - 1];
        const lb = s('text', {x: px(last) + (kind === 'time' ? -8 : 9), y: y(last.q.mean) + (kind === 'time' ? -9 : 4), 'text-anchor': kind === 'time' ? 'end' : 'start', class: 'axis'});
        lb.textContent = HN[ch.harness]; svg.append(lb);
      });
      /* legend: the two dash patterns */
      let gx = L + 8; chains.forEach(ch => {
        svg.append(s('line', {x1: gx, x2: gx + 26, y1: T + 6, y2: T + 6, stroke: c, 'stroke-width': 1.6, 'stroke-dasharray': DASH[ch.harness]}));
        const t2 = s('text', {x: gx + 31, y: T + 10, class: 'axis'}); t2.textContent = HN[ch.harness]; svg.append(t2); gx += 31 + HN[ch.harness].length * 6.6 + 14; });
      card.append(svg); box.append(card);
    });
  });
  document.getElementById('read4').textContent =
    `${Object.keys(byModel).join(' and ')} ran under Codex CLI and under the ReAct scaffold, the model-neutral tool loop over OpenRouter. Left: score against time budget. Right: score against cost. Same marks as above; small dots are individual runs.`;
  document.getElementById('cap4').innerHTML =
    'The harness sets how many turns a model takes and how much context each turn re-reads, which is most of the cost. ReAct keeps an append-only conversation, so its context only grows. A Codex CLI run and a ReAct run of the same model are different systems, and the main figures use the Codex CLI runs for these two models.';
})();

document.getElementById('copyall').onclick = () => {
  const out = {}; Object.keys(LAYERS).sort().forEach(k => { out[k] = LAYERS[k](); });
  navigator.clipboard.writeText(JSON.stringify(out, null, 1)).catch(() => {});
};
document.getElementById('cav').replaceChildren(...D.caveats.map(c => el('li', null, c)));
</script></body></html>'''

if __name__ == "__main__":
    main()
