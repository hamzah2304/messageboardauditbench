#!/usr/bin/env python3
"""Dot plot of AI Village score per report (mean of its 20 best finding scores), one row per model, coloured by subagent access.

    python3 viewers/build_aivillage_scores_figure.py benchmark/incidents/aivillage/results/scores-by-report.tsv \
        benchmark/incidents/aivillage/figures/scores_by_report.svg

Writes plain SVG (no plotting dependency); render to PNG with any SVG renderer.
"""
import csv
import sys
from collections import defaultdict
from html import escape

NAMES = {
    "gpt-6-astra": "GPT-6 Astra", "gpt-6.1-sol": "GPT-6.1 Sol", "gpt-6-luna": "GPT-6 Luna",
    "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-opus-5": "Claude Opus 5", "claude-opus-4-8": "Claude Opus 4.8",
    "z-ai/glm-5.3": "GLM 5.3", "google/gemini-3.8-flash": "Gemini 3.8 Flash", "moonshotai/kimi-k3": "Kimi K3",
    "meta/muse-spark-1.3": "Muse Spark 1.3", "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
}
WITH, WITHOUT = "#2a78d6", "#eb6834"  # reference categorical slots 1 and 2
INK, MUTED, GRID, SURFACE = "#1a1a19", "#6b6a63", "#e4e3dd", "#fcfcfb"


def main(src: str, dst: str) -> None:
    rows = list(csv.DictReader(open(src), delimiter="\t"))
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append((r["subagents"] == "yes", float(r["score_top20"]) * 100))
    def best_mean(m: str) -> float:  # rows sorted by the model's better condition
        means = [[v for s, v in by_model[m] if s == flag] for flag in (True, False)]
        return max(sum(vs) / len(vs) for vs in means if vs)

    order = sorted(by_model, key=lambda m: -best_mean(m))
    left, top, row_h, plot_w, xmax = 190, 92, 34, 560, 80
    width, height = left + plot_w + 40, top + row_h * len(order) + 70
    x = lambda v: left + v / xmax * plot_w  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="Liberation Sans, Arial, sans-serif">',
           f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
           f'<text x="24" y="34" font-size="19" font-weight="600" fill="{INK}">Five of the six models that could use subagents scored higher with them</text>',
           f'<text x="24" y="58" font-size="13.5" fill="{MUTED}">Mean of each report’s 20 best scores against the 96-finding rubric; one dot per report, bar = mean of two</text>']
    for v in range(0, xmax + 1, 10):
        out.append(f'<line x1="{x(v)}" y1="{top - 10}" x2="{x(v)}" y2="{top + row_h * len(order)}" stroke="{GRID}"/>')
        out.append(f'<text x="{x(v)}" y="{top + row_h * len(order) + 20}" font-size="12" fill="{MUTED}" text-anchor="middle">{v}%</text>')
    out.append(f'<text x="{left + plot_w / 2}" y="{top + row_h * len(order) + 44}" font-size="12.5" fill="{MUTED}" text-anchor="middle">Score (mean of the 20 best finding scores)</text>')
    for i, m in enumerate(order):
        cy = top + row_h * i + row_h / 2
        out.append(f'<text x="{left - 14}" y="{cy + 4.5}" font-size="13.5" fill="{INK}" text-anchor="end">{escape(NAMES.get(m, m))}</text>')
        for flag, color, dy in ((True, WITH, -6), (False, WITHOUT, 6)):
            vals = [v for s, v in by_model[m] if s == flag]
            if not vals:
                continue
            mean = sum(vals) / len(vals)
            out.append(f'<line x1="{x(mean)}" y1="{cy + dy - 6}" x2="{x(mean)}" y2="{cy + dy + 6}" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>')
            for v in vals:
                out.append(f'<circle cx="{x(v):.1f}" cy="{cy + dy}" r="4.5" fill="{color}" stroke="{SURFACE}" stroke-width="2"><title>{escape(NAMES.get(m, m))}, {"with" if flag else "without"} subagents: {v:.1f}%</title></circle>')
    lx = left
    for color, label in ((WITH, "with subagents"), (WITHOUT, "without subagents")):
        out.append(f'<circle cx="{lx + 5}" cy="76" r="4.5" fill="{color}"/><text x="{lx + 15}" y="80.5" font-size="12.5" fill="{INK}">{label}</text>')
        lx += 150
    out.append("</svg>")
    open(dst, "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
