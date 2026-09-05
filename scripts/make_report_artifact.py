#!/usr/bin/env python3
"""Render a run's report.md into a self-contained, styled HTML page.

    scripts/make_report_artifact.py <run_dir> <out.html>

The markdown is rendered to HTML at build time (markdown-it-py) and embedded
directly, so the page is fully static with no runtime dependency. A metadata
strip at the top records the model, harness and run cost, so the page reads as a
baseline artefact, not as a real incident report.
"""
import json
import sys
from pathlib import Path

from markdown_it import MarkdownIt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from messageboard_audit.transcripts import parse  # noqa: E402

TEMPLATE = r"""<title>{title}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{
  --bg:#f6f4ef; --panel:#fffdf8; --ink:#20242c; --muted:#5c6472; --rule:#e0dccf;
  --accent:#7a2e2e; --accent-soft:#f0e2df; --chip:#ece7dd; --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{
  --bg:#15171c; --panel:#1c1f26; --ink:#e7e4dc; --muted:#9aa1ad; --rule:#30343d;
  --accent:#e08a7d; --accent-soft:#3a2422; --chip:#262a32;}}}}
:root[data-theme="dark"]{{
  --bg:#15171c; --panel:#1c1f26; --ink:#e7e4dc; --muted:#9aa1ad; --rule:#30343d;
  --accent:#e08a7d; --accent-soft:#3a2422; --chip:#262a32;}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.6}}
.wrap{{max-width:760px;margin:0 auto;padding:40px 22px 80px}}
.banner{{background:var(--accent-soft);border:1px solid var(--rule);border-left:3px solid var(--accent);
  border-radius:6px;padding:12px 16px;font-size:.85rem;color:var(--ink);margin-bottom:26px}}
.banner b{{color:var(--accent)}}
.meta{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:30px}}
.chip{{background:var(--chip);border:1px solid var(--rule);border-radius:999px;padding:4px 11px;font-size:.76rem;
  font-family:var(--mono);color:var(--muted);white-space:nowrap}}
.chip b{{color:var(--ink);font-weight:500}}
article{{font-family:"Newsreader",Georgia,serif;font-size:1.09rem}}
article h1{{font-size:1.9rem;font-weight:700;line-height:1.15;text-wrap:balance;margin:0 0 .5em}}
article h2{{font-size:1.4rem;font-weight:600;margin:1.7em 0 .5em;padding-bottom:.2em;border-bottom:1px solid var(--rule);color:var(--accent)}}
article h3{{font-size:1.15rem;font-weight:600;margin:1.4em 0 .4em}}
article p,article li{{max-width:68ch}}
article em{{color:var(--muted)}}
article strong{{color:var(--ink)}}
article a{{color:var(--accent)}}
code{{font-family:var(--mono);font-size:.82em;background:var(--panel);border:1px solid var(--rule);
  border-radius:3px;padding:.5px 5px;word-break:break-word}}
article table{{border-collapse:collapse;width:100%;font-family:"IBM Plex Sans",sans-serif;font-size:.9rem;margin:1em 0}}
article th{{text-align:left;font-size:.72rem;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);
  border-bottom:1px solid var(--rule);padding:7px 9px}}
article td{{border-bottom:1px solid var(--rule);padding:7px 9px;vertical-align:top}}
.tablewrap{{overflow-x:auto}}
details.prompt{{background:var(--panel);border:1px solid var(--rule);border-radius:6px;margin:0 0 30px;overflow:hidden}}
details.prompt summary{{cursor:pointer;padding:11px 16px;font-size:.78rem;letter-spacing:.05em;text-transform:uppercase;
  color:var(--muted);font-weight:600;user-select:none}}
details.prompt summary::marker{{color:var(--accent)}}
details.prompt .body{{padding:0 16px 14px;font-family:var(--mono);font-size:.82rem;white-space:pre-wrap;color:var(--ink);line-height:1.55}}
</style>
<div class="wrap">
  <div class="banner"><b>Benchmark baseline output.</b> This incident report was written by {model_h} running in {harness}, given a deliberately blind prompt and the redacted wiki edit logs with no web access. It is the model's own analysis, not a verified account. Part of MessageBoardAuditBench.</div>
  <details class="prompt" open>
    <summary>Prompt given to the agent</summary>
    <div class="body">{prompt}</div>
  </details>
  <div class="meta">
    <span class="chip">model <b>{model}</b></span>
    <span class="chip">harness <b>{harness}</b></span>
    <span class="chip">effort <b>{effort}</b></span>
    <span class="chip">turns <b>{turns}</b></span>
    <span class="chip">tool calls <b>{tools}</b></span>
    <span class="chip">output tokens <b>{out_tok:,}</b></span>
    <span class="chip">wall time <b>{mins}m {secs}s</b></span>
    <span class="chip">web access <b>none</b></span>
  </div>
  <article id="report">{body}</article>
</div>
"""

HARNESS = {"claude": "Claude Code", "codex": "Codex CLI", "react": "ReAct loop (OpenRouter)"}


def main() -> None:
    run = Path(sys.argv[1])
    out = Path(sys.argv[2])
    meta = json.loads((run / "meta.json").read_text())
    agent = meta["agent"]
    parsed = parse(agent, run / "transcript.jsonl")
    report = (run / "report.md").read_text()
    prompt_path = run / "work" / "prompt.txt"  # Docker launcher layout; baselines/ keep prompt.txt at the top
    if not prompt_path.exists():
        prompt_path = run / "prompt.txt"
    prompt = prompt_path.read_text().strip()
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    model = meta["model"]
    model_h = {"claude-opus-5": "Claude Opus 5", "gpt-5.6-sol": "GPT-5.6 Sol", "claude-haiku-4-5": "Claude Haiku 4.5", "gpt-5.6-luna": "GPT-5.6 Luna", "claude-sonnet-5": "Claude Sonnet 5", "gpt-5.6-terra": "GPT-5.6 Terra", "claude-fable-5-1": "Claude Fable 5.1"}.get(model, model)
    secs = meta["wall_seconds"]
    md = MarkdownIt("commonmark", {"linkify": True, "typographer": True}).enable("table")
    body = md.render(report)
    # tables get an overflow wrapper so wide ones scroll instead of the page
    body = body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
    html = TEMPLATE.format(
        title=f"{model_h} Wiki Audit",
        model=model, model_h=model_h,
        harness=HARNESS.get(agent, agent),
        effort=meta.get("effort", "medium"),
        turns=parsed.turns, tools=parsed.tool_calls, out_tok=parsed.output_tokens,
        mins=secs // 60, secs=secs % 60,
        prompt=esc(prompt),
        body=body,
    )
    out.write_text(html)
    print(f"wrote {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
