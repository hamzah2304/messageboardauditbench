#!/usr/bin/env python3
"""Render AI Village pilot reports into one page with a tab per run.

    viewers/build_aivillage_reports.py OUT.html RUN_DIR [RUN_DIR ...]

Each RUN_DIR is a finished trial under runs/. The page shows the run's model,
harness, data variant, budget and report length above the report, and renders
record citations such as [chat:<id>] as compact id chips.
"""
import html
import json
import sys
from pathlib import Path


def run_info(d):
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
    cfg = json.loads((d / "config.rendered.json").read_text()) if (d / "config.rendered.json").exists() else {}
    report = (d / "report.md").read_text() if (d / "report.md").exists() else "*No report was written.*"
    cli = (d / "cli.version.txt").read_text().strip() if (d / "cli.version.txt").exists() else ""
    variant = meta.get("data_variant") or cfg.get("data_variant") or ""
    reasoning = "without reasoning traces" if "noreasoning" in d.name else "with reasoning traces"
    return {
        "id": d.name.split("_")[-1][:8],
        "model": meta.get("model", d.name.split("_")[2]),
        "agent": meta.get("agent", d.name.split("_")[1]),
        "started": meta.get("started", d.name[:16]),
        "budget": meta.get("budget_min", cfg.get("budget_min", "")),
        "variant": variant,
        "reasoning": reasoning,
        "cli": cli,
        "words": len(report.split()),
        "run": d.name,
        "markdown": report,
    }


PAGE = """<title>AI Village Pilot Reports</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap">
<style>
:root {
  --bg: #f5f6f8; --surface: #ffffff; --ink: #1b2230; --muted: #5b6576; --rule: #dde2ea;
  --accent: #2f5d8a; --chip: #e6ecf3; --chip-ink: #2a4a6e; --warn: #8a5a12; --warn-bg: #f7eedd;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --body: "Source Serif 4", Georgia, "Times New Roman", serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #12161d; --surface: #181d26; --ink: #e4e8ee; --muted: #9aa4b2; --rule: #2a3240;
    --accent: #7fa8d6; --chip: #1f2a38; --chip-ink: #a9c4e4; --warn: #e2b46a; --warn-bg: #2b2418;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #12161d; --surface: #181d26; --ink: #e4e8ee; --muted: #9aa4b2; --rule: #2a3240;
  --accent: #7fa8d6; --chip: #1f2a38; --chip-ink: #a9c4e4; --warn: #e2b46a; --warn-bg: #2b2418;
}
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 17px; line-height: 1.6; padding-inline: 16px; padding-block: 0 64px; }
.wrap { max-width: 760px; margin: 0 auto; }
header.top { padding-block: 32px 12px; }
.eyebrow { font-family: var(--display); text-transform: uppercase; letter-spacing: .08em; font-size: 12px; color: var(--muted); }
h1.page { font-family: var(--display); font-weight: 600; font-size: 30px; line-height: 1.15; margin: 6px 0 8px; text-wrap: balance; }
.lede { color: var(--muted); font-size: 15px; margin: 0; }
nav.tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-block: 20px 0; }
nav.tabs button { font-family: var(--display); font-size: 14px; font-weight: 500; border: 1px solid var(--rule); background: var(--surface); color: var(--ink); border-radius: 6px; padding: 7px 12px; cursor: pointer; }
nav.tabs button[aria-selected="true"] { border-color: var(--accent); color: var(--accent); box-shadow: inset 0 -2px 0 var(--accent); }
nav.tabs button:focus-visible, .cite:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
dl.meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px 20px; margin: 20px 0 8px; padding: 14px 16px; background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; }
dl.meta div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
dl.meta dt { font-family: var(--display); font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
dl.meta dd { margin: 0; font-family: var(--mono); font-size: 13px; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.note { font-size: 14px; color: var(--warn); background: var(--warn-bg); border-radius: 6px; padding: 8px 12px; margin: 8px 0 0; }
article { margin-top: 28px; }
article h1 { font-family: var(--display); font-weight: 600; font-size: 26px; line-height: 1.2; margin: 0 0 12px; text-wrap: balance; }
article h2 { font-family: var(--display); font-weight: 600; font-size: 21px; margin: 40px 0 10px; padding-top: 14px; border-top: 1px solid var(--rule); text-wrap: balance; }
article h3 { font-family: var(--display); font-weight: 600; font-size: 18px; margin: 30px 0 8px; text-wrap: balance; }
article p, article li { max-width: 68ch; }
article ul, article ol { padding-left: 1.3em; }
article li + li { margin-top: 6px; }
article code { font-family: var(--mono); font-size: .82em; background: var(--chip); color: var(--chip-ink); padding: 1px 4px; border-radius: 3px; overflow-wrap: anywhere; }
article strong { font-weight: 600; }
.cite { font-family: var(--mono); font-size: 11.5px; background: var(--chip); color: var(--chip-ink); border-radius: 4px; padding: 1px 5px; white-space: nowrap; cursor: help; }
.cite b { font-weight: 500; opacity: .7; }
q.cq { font-style: italic; color: var(--muted); }
footer { margin-top: 48px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--rule); padding-top: 12px; }
@media (max-width: 480px) { body { font-size: 16px; } h1.page { font-size: 25px; } }
</style>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">MessageBoardAuditBench · AI Village pilot</div>
    <h1 class="page">What went wrong in the AI Village</h1>
    <p class="lede">Reports written by agents that investigated the full AI Village export (April 2025 to September 2026) in a network-isolated sandbox. The prompt asked what went wrong, for AI safety researchers. These are unvalidated model outputs: citations have not been checked against the records.</p>
    <nav class="tabs" role="tablist" id="tabs"></nav>
  </header>
  <main id="panel"></main>
  <footer>Citation chips show the record type and the first 8 characters of its id; hover or focus a chip for the full id. Use the page's comment button to leave feedback on any passage.</footer>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<script>
const RUNS = __RUNS__;
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function cites(htmlText) {
  return htmlText.replace(/\\[(chat|event|session|turn|memory|transcript|claude_code):([^\\]\\s"&]+)(?:\\s+(?:"|&quot;|&#34;)(.*?)(?:"|&quot;|&#34;))?\\]/g, (m, kind, id, quote) =>
    `<span class="cite" tabindex="0" title="${esc(kind + ':' + id)}"><b>${kind}</b> ${esc(id.slice(0, 8))}</span>` + (quote ? ` <q class="cq">${quote}</q>` : ''));
}
function render(i) {
  const r = RUNS[i];
  document.querySelectorAll('#tabs button').forEach((b, j) => b.setAttribute('aria-selected', String(j === i)));
  const notes = (r.notes || []).map(n => `<p class="note">${esc(n)}</p>`).join('');
  document.getElementById('panel').innerHTML = `
    <dl class="meta">
      <div><dt>Model</dt><dd>${esc(r.model)}</dd></div>
      <div><dt>Harness</dt><dd>${esc(r.agent)} · ${esc(r.cli)}</dd></div>
      <div><dt>Data</dt><dd>${esc(r.reasoning)}</dd></div>
      <div><dt>Budget</dt><dd>${esc(String(r.budget))} min</dd></div>
      <div><dt>Report</dt><dd>${r.words.toLocaleString('en')} words</dd></div>
      <div><dt>Run</dt><dd>${esc(r.id)}</dd></div>
    </dl>${notes}
    <article>${cites(marked.parse(r.markdown))}</article>`;
  try { localStorage.setItem('tab', String(i)); } catch (e) {}
}
const tabs = document.getElementById('tabs');
RUNS.forEach((r, i) => {
  const b = document.createElement('button');
  b.type = 'button'; b.setAttribute('role', 'tab'); b.id = 'tab-' + i;
  b.textContent = r.label || `${r.model} · ${r.reasoning.replace(' traces', '')}`;
  b.addEventListener('click', () => render(i));
  tabs.appendChild(b);
});
let start = 0;
try { const s = Number(localStorage.getItem('tab')); if (s >= 0 && s < RUNS.length) start = s; } catch (e) {}
if (RUNS.length < 2) tabs.hidden = true;
render(start);
</script>
"""


def main():
    out = Path(sys.argv[1])
    runs = [run_info(d) for d in sys.argv[2:]]
    notes = json.loads(Path(out.with_suffix(".notes.json")).read_text()) if out.with_suffix(".notes.json").exists() else {}
    for r in runs:
        extra = notes.get(r["run"], {})
        r["notes"] = extra.get("notes", [])
        r["label"] = extra.get("label", "")
    out.write_text(PAGE.replace("__RUNS__", json.dumps(runs).replace("</", "<\\/")))
    print(out, len(runs), "runs")


if __name__ == "__main__":
    main()
