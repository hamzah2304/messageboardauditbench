#!/usr/bin/env python3
"""One figure across the three benchmarks: each model's score in each, at 30 minutes.

Reads the data behind each benchmark's published cost figure, so it reproduces from the
repository alone:

  German wiki   scripts/viewers/figures/headline_figures.html     headline score (70% finding
                coverage, strict transform; 30% TLDR), mean of 3 runs
  Transluce     scripts/viewers/figures/urlquery_final_balanced_figure.json   weighted mean of
                13 headline findings, judge GPT-6 Astra, mean of 3 runs
  AI Village    benchmarks/aivillage/figures/score_vs_cost.html   mean of the 20 best of 96
                findings, judge GPT-6.1 Sol, mean of 2 runs, no subagents

Models in at least two benchmarks get a row. Each benchmark keeps its own scale, so read
across a row for a model's relative standing, not to compare numbers between columns.

Writes docs/figures/benchmarks_by_model.svg and a headless-Chrome PNG beside it, and a
PNG of the published Transluce cost plot (the chart alone) for its README,
benchmarks/transluce/figures/score_vs_cost.png.

  uv run python scripts/viewers/build_benchmarks_figure.py
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import tempfile
from collections import defaultdict
from html import escape
from pathlib import Path

from browser_executable import find_chromium

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "scripts" / "viewers" / "figures"
OUT = ROOT / "docs" / "figures"
BUDGET = 30
# Vendor colours shared with each benchmark's cost figure.
COLOURS = {"anthropic": "#d97757", "openai": "#202126", "google": "#2e9e4f", "meta": "#0668e1",
           "moonshot": "#c2185b", "zai": "#00897b", "deepseek": "#7c55b6"}
VENDOR_BY_COLOUR = {v: k for k, v in COLOURS.items()}
COLUMNS = [("German wiki", "38 findings + TLDR"), ("Transluce", "13 findings"), ("AI Village", "96 findings")]


def embedded(path: Path) -> dict:
    return json.loads(re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', path.read_text(), re.S).group(1))


def german_wiki() -> dict[str, tuple[str, float]]:
    data = embedded(FIGURES / "headline_figures.html")
    return {m["model"]: (m["provider"], m["budgets"][str(BUDGET)]["mean_comb"])
            for m in data["models"] if str(BUDGET) in m["budgets"]}


def transluce() -> dict[str, tuple[str, float]]:
    data = json.loads((FIGURES / "urlquery_final_balanced_figure.json").read_text())
    runs = defaultdict(list)
    for r in data["runs"]:
        if r.get("budget_min") == BUDGET and r.get("performance") is not None and r.get("status", "complete") == "complete":
            runs[(r["label"].replace(" · Codex", ""), r["provider"])].append(r["performance"])
    return {name: (vendor, statistics.mean(v)) for (name, vendor), v in runs.items()}


def aivillage() -> dict[str, tuple[str, float]]:
    data = embedded(ROOT / "benchmarks" / "aivillage" / "figures" / "score_vs_cost.html")
    return {m["name"]: (VENDOR_BY_COLOUR[m["color"]], m["points"]["false"]["score"])
            for m in data["models"] if "false" in m["points"]}


def svg(rows: list[tuple[str, str, list[float | None]]]) -> str:
    left, col_w, gap, top, row_h = 190, 250, 40, 92, 34
    width = left + 3 * col_w + 2 * gap + 30
    height = top + row_h * len(rows) + 70
    x_max = 0.6

    def x(col: int, v: float) -> float:
        return left + col * (col_w + gap) + v / x_max * col_w

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>']
    for c, (name, sub) in enumerate(COLUMNS):
        x0 = x(c, 0)
        out.append(f'<text x="{x0 + col_w / 2}" y="34" text-anchor="middle" font-size="17" font-weight="600" fill="#1d1d1f">{name}</text>')
        out.append(f'<text x="{x0 + col_w / 2}" y="54" text-anchor="middle" font-size="13" fill="#6e6e73">{sub}</text>')
        for t in (0, 0.2, 0.4, 0.6):
            xt = x(c, t)
            out.append(f'<line x1="{xt}" y1="{top - 14}" x2="{xt}" y2="{top + row_h * len(rows) - 14}" stroke="#e5e5ea"/>')
            out.append(f'<text x="{xt}" y="{top + row_h * len(rows) + 6}" text-anchor="middle" font-size="12" fill="#6e6e73">{round(t * 100)}%</text>')
    for i, (name, vendor, scores) in enumerate(rows):
        y = top + i * row_h
        if i % 2 == 0:
            out.append(f'<rect x="10" y="{y - row_h / 2 - 3}" width="{width - 20}" height="{row_h}" fill="#f5f5f7"/>')
        colour = COLOURS[vendor]
        out.append(f'<text x="{left - 16}" y="{y + 1}" text-anchor="end" dominant-baseline="middle" font-size="14" fill="{colour}" font-weight="600">{escape(name)}</text>')
        for c, s in enumerate(scores):
            if s is None:
                out.append(f'<text x="{x(c, 0) + 6}" y="{y + 1}" dominant-baseline="middle" font-size="12" fill="#aeaeb2">not run</text>')
                continue
            out.append(f'<line x1="{x(c, 0)}" y1="{y}" x2="{x(c, s)}" y2="{y}" stroke="{colour}" stroke-opacity="0.35" stroke-width="2"/>')
            out.append(f'<circle cx="{x(c, s)}" cy="{y}" r="6" fill="{colour}"/>')
            out.append(f'<text x="{x(c, s) + 11}" y="{y + 1}" dominant-baseline="middle" font-size="12" fill="#3a3a3c">{round(s * 100)}%</text>')
    out.append(f'<text x="{left}" y="{height - 22}" font-size="12" fill="#6e6e73">30-minute runs, mean over replicates. Each benchmark has its own score and judge; '
               'compare a model across a row, not numbers between columns.</text>')
    out.append("</svg>")
    return "\n".join(out)


def screenshot(page: Path, png: Path, width: int, height: int) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_chromium(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={width},{height}", "--force-device-scale-factor=2",
                    f"--screenshot={png}", page.as_uri()], check=True, capture_output=True)


def transluce_plot() -> None:
    """The published Transluce plot without its page title, drag controls and table."""
    html = (FIGURES / "urlquery_final_balanced_figure.html").read_text()
    hide = ("<style>h1,#summary,h2,.tablewrap,.foot,#reset-labels,.key span:last-of-type{display:none!important}"
            "body{padding-top:0!important}</style></head>")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "figure.html"
        page.write_text(html.replace("</head>", hide, 1))
        screenshot(page, ROOT / "benchmarks" / "transluce" / "figures" / "score_vs_cost.png", 1100, 620)


def main() -> None:
    per = [german_wiki(), transluce(), aivillage()]
    names = {n for p in per for n in p}
    rows = []
    for n in names:
        scores = [p[n][1] if n in p else None for p in per]
        if sum(s is not None for s in scores) >= 2:
            vendor = next(p[n][0] for p in per if n in p)
            rows.append((n, vendor, scores))
    rows.sort(key=lambda r: -statistics.mean(s for s in r[2] if s is not None))
    OUT.mkdir(parents=True, exist_ok=True)
    image = svg(rows)
    (OUT / "benchmarks_by_model.svg").write_text(image)
    width, height = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', image).groups())
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "figure.html"
        page.write_text(f'<!doctype html><meta charset="utf-8"><style>body{{margin:0}}</style>{image}')
        screenshot(page, OUT / "benchmarks_by_model.png", width, height)
    transluce_plot()
    print(f"{len(rows)} models -> {OUT / 'benchmarks_by_model.png'}")


if __name__ == "__main__":
    main()
