#!/usr/bin/env python3
"""Render the six headline figures to PNG and write viewers/figures/results_figures.md.

Reads viewers/figures/headline_figures.html (build it first, with the label positions baked
in from viewers/figures/headline_labels.json), cuts one figure per page, and screenshots each
with headless Google Chrome at 2x. Every figure is trimmed to its drawn content by the page's
own script, so a label dragged inward leaves no gutter.

  uv run python viewers/build_headline_figures.py && uv run python viewers/render_headline_pngs.py
"""
import json
import re
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIG = ROOT / "viewers" / "figures"
SRC = FIG / "headline_figures.html"
MD = FIG / "results_figures.md"
from browser_executable import find_chromium
WIDTH = 1000          # cost figures
WIDTH_INDEX = 800     # index figures, whose plot is narrower
SCALE = 2

# figure id in the page -> output stem and the caption the markdown carries
FIGS = [
    ("C1", "results_fig1_combined_vs_aa_index",
     "Combined score (0.7 × finding coverage + 0.3 × holistic TL;DR score) against the Artificial Analysis Intelligence Index. "
     "Hollow to solid marks are 10, 30 and 120 minutes; small dots are individual runs behind the top mark."),
    ("C2", "results_fig2_combined_vs_cost",
     "Combined score against estimated cost per run at list prices, log scale. Dotted lines join a model's three budgets; "
     "the solid line is the efficient frontier. Subscription runs are priced as if paid per token."),
    ("S1", "results_fig3_coverage_vs_aa_index", "Finding coverage alone (the strict v2 score) against the Artificial Analysis index."),
    ("S2", "results_fig4_coverage_vs_cost", "Finding coverage alone against cost per run."),
    ("T1", "results_fig5_tldr_vs_aa_index", "Holistic TL;DR score alone against the Artificial Analysis index."),
    ("T2", "results_fig6_tldr_vs_cost", "Holistic TL;DR score alone against cost per run."),
]
HIDE = ("h1,.lede,h2.group,#groupC,#groupS,#groupT,.tools,details,.eyebrow,h2,.read,.cap{display:none!important}"
        "html,body{background:#F6F6F2}main{padding:6px 8px;max-width:%dpx}")


def notes_for(fid: str, html: str) -> list[str]:
    """Footnotes under the panel: which runs a fallback model finished, with counts, read from the page's data."""
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))
    out = []
    for m in data["models"]:
        fb = m.get("fallback") or {}
        if not fb:
            continue
        parts = [f"{f['n']} of {f['of']} runs at {b} min" for b, f in sorted(fb.items(), key=lambda kv: int(kv[0]))]
        to = next(iter(fb.values()))["to"]
        mark = "" if fid == "C2" else "† "     # the combined cost figure carries no dagger on its label
        out.append(f"{mark}{m['model']}: {' and '.join(parts)} switched to {to} after a safeguard refusal.")
    return out

def width_for(fid: str) -> int:
    return WIDTH_INDEX if fid.endswith("1") else WIDTH


def page_for(fid: str, html: str) -> str:
    """The whole page with every figure but `fid` hidden, forced light, footnotes under the panel, and a height probe."""
    css = (f"<style>section.fig{{display:none}}section.fig:has(#fig{fid}){{display:block}}{HIDE % (width_for(fid) + 16)}"
           ".note{color:#5F636A;font-size:12.5px;margin:6px 4px 0;font-family:'Public Sans',system-ui,sans-serif}</style>")
    note = "".join(f'<div class="note" id="note{fid}">{n}</div>' for n in notes_for(fid, html))
    html = html.replace(f'<div class="panel" id="fig{fid}"></div>', f'<div class="panel" id="fig{fid}"></div>{note}', 1)
    probe = ("<script>document.fonts.ready.then(()=>{const p=document.getElementById('fig%s');"
             "const n=[...document.querySelectorAll('#note%s')].pop()||p;document.documentElement.dataset.h=String(Math.ceil(n.getBoundingClientRect().bottom+8))})</script>" % (fid, fid))
    out = html.replace('<html lang="en">', '<html lang="en" data-theme="light">', 1)
    out = out.replace("</head>", css + "</head>", 1)
    return out.replace("</body>", probe + "</body>", 1)


def chrome(*args: str) -> str:
    cmd = [find_chromium(), "--headless=new", "--hide-scrollbars", "--disable-gpu", "--virtual-time-budget=6000", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120).stdout


def render(html_path: pathlib.Path, png_path: pathlib.Path, width: int) -> int:
    url = html_path.resolve().as_uri()
    dom = chrome(f"--window-size={width + 32},600", "--dump-dom", url)
    m = re.search(r'data-h="(\d+)"', dom)
    if not m:
        raise SystemExit(f"could not measure {html_path}")
    h = int(m.group(1))
    chrome(f"--window-size={width + 32},{h}", f"--force-device-scale-factor={SCALE}", f"--screenshot={png_path}", url)
    return h


def main() -> None:
    html = SRC.read_text()
    work = FIG / "_render"
    work.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    md = ["# Round 4 results figures", "",
          "Built by `viewers/build_headline_figures.py` and rendered by `viewers/render_headline_pngs.py`; "
          "label positions come from `viewers/figures/headline_labels.json`. "
          "Combined score = 0.7 × finding coverage + 0.3 × holistic TL;DR score, both Fable 5.1's grades over the same round-4 reports.", ""]
    for i, (fid, stem, cap) in enumerate(FIGS, 1):
        png = FIG / f"{stem}.png"
        if not only or fid in only or stem in only:
            hp = work / f"{stem}.html"
            hp.write_text(page_for(fid, html))
            h = render(hp, png, width_for(fid))
            print(f"wrote {png.name} ({width_for(fid)}x{h} css px at {SCALE}x)", file=sys.stderr)
        md += [f"![Figure {i}]({png.name})", "", f"Figure {i}: {cap}", ""]
    MD.write_text("\n".join(md))
    print(f"wrote {MD}", file=sys.stderr)


if __name__ == "__main__":
    main()
