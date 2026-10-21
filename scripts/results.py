#!/usr/bin/env python3
"""Tabulate and plot the standard condition: every run, every cell, with 95% intervals.

    uv run python scripts/results.py --grades logs/standard-grades

Reads the standard runs (configs/standard.toml) under the primary checkout's runs/ and the
grade logs in --grades (the *_report_grade tasks, run with runs=*_<eval>-std-* and the standard
judge). Writes benchmarks/results/standard/runs.jsonl (one row per run, eligible or not),
cells.json (per eval x model x budget: mean of eligible scored runs, bootstrap 95% interval,
counts of runs, eligible and safety-flagged) and docs/figures/standard_results.{svg,png}.

Grade the runs with, per eval (German wiki takes two rubrics):
  uv run inspect eval slopvestigator_bench/german_wiki_report_grade -T runs='*_wiki-std-*' -T rubric=v2 \\
      -T judge=openai/gpt-6.1-sol -T judge_effort=high --log-dir logs/standard-grades
  (and -T rubric=tldrh; transluce_report_grade and aivillage_report_grade with runs='*_<prefix>-std-*')
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "viewers"))
from slopvestigator_bench import lineup, results, standard  # noqa: E402
from slopvestigator_bench.benchmarks import primary_root  # noqa: E402

TITLES = {"messageboard": "German wiki", "urlquery": "Transluce", "aivillage": "AI Village"}


def figure(cells: list[dict]) -> str:
    benches = [b for b in standard.benchmark_ids() if any(c["benchmark_id"] == b for c in cells)]
    order = [m.id for m in lineup.models()]
    models = sorted({c["model"] for c in cells}, key=lambda m: order.index(m) if m in order else len(order))
    left, col_w, gap, top, row_h = 200, 260, 40, 92, 34
    width = left + len(benches) * (col_w + gap) + 20
    height = top + row_h * len(models) + 80

    def x(col, v):
        return left + col * (col_w + gap) + v / 0.7 * col_w

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           'font-family="-apple-system, Helvetica, Arial, sans-serif"><rect width="100%" height="100%" fill="#fff"/>']
    for c_i, bench in enumerate(benches):
        out.append(f'<text x="{x(c_i, 0.35)}" y="40" text-anchor="middle" font-size="17" font-weight="600">{TITLES[bench]}</text>')
        for t in (0, 0.2, 0.4, 0.6):
            out.append(f'<line x1="{x(c_i, t)}" y1="{top - 16}" x2="{x(c_i, t)}" y2="{top + row_h * len(models) - 16}" stroke="#e5e5ea"/>')
            out.append(f'<text x="{x(c_i, t)}" y="{top + row_h * len(models) + 6}" text-anchor="middle" font-size="12" fill="#6e6e73">{round(t * 100)}%</text>')
    for r_i, model_id in enumerate(models):
        y = top + r_i * row_h
        try:
            m = lineup.model(model_id)
            label, colour = m.label, m.colour
        except KeyError:
            label, colour = model_id, "#6e6e73"
        out.append(f'<text x="{left - 16}" y="{y}" text-anchor="end" dominant-baseline="middle" font-size="14" font-weight="600" fill="{colour}">{escape(label)}</text>')
        for c_i, bench in enumerate(benches):
            for cell in (c for c in cells if c["benchmark_id"] == bench and c["model"] == model_id):
                dy = -6 if cell["budget"] == 10 else 6
                if cell["score"] is None:
                    continue
                if cell["ci_low"] is not None:
                    out.append(f'<line x1="{x(c_i, cell["ci_low"])}" y1="{y + dy}" x2="{x(c_i, cell["ci_high"])}" y2="{y + dy}" stroke="{colour}" stroke-width="2" stroke-opacity="0.5"/>')
                fill = "#fff" if cell["budget"] == 10 else colour
                out.append(f'<circle cx="{x(c_i, cell["score"])}" cy="{y + dy}" r="5" fill="{fill}" stroke="{colour}" stroke-width="2"/>')
    out.append(f'<text x="{left}" y="{height - 24}" font-size="12" fill="#6e6e73">Hollow: 10 minutes; filled: 30 minutes. '
               'Mean of eligible runs with a 95% bootstrap interval; each eval has its own score and rubric.</text></svg>')
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grades", type=Path, default=Path("logs/standard-grades"))
    ap.add_argument("--out", type=Path, default=ROOT / "benchmarks" / "results" / "standard")
    args = ap.parse_args()
    primary = primary_root()
    grades = args.grades if args.grades.is_absolute() else primary / args.grades
    table = results.rows(primary, grades)
    runs_path, cells_path = results.write(table, args.out)
    cells = results.cells(table)
    print(f"{len(table)} runs, {sum(r.eligible for r in table)} eligible, {sum(r.score is not None for r in table)} scored "
          f"-> {runs_path}, {cells_path}")
    if not any(c["score"] is not None for c in cells):
        return 0
    svg = figure(cells)
    fig_dir = ROOT / "docs" / "figures"
    (fig_dir / "standard_results.svg").write_text(svg)
    from browser_executable import find_chromium

    w, h = svg.split('width="', 1)[1].split('"')[0], svg.split('height="', 1)[1].split('"')[0]
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "f.html"
        page.write_text(f'<!doctype html><meta charset="utf-8"><style>body{{margin:0}}</style>{svg}')
        subprocess.run([find_chromium(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}",
                        "--force-device-scale-factor=2", f"--screenshot={fig_dir / 'standard_results.png'}", page.as_uri()],
                       check=True, capture_output=True)
    print(f"figure -> {(fig_dir / 'standard_results.png').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
