#!/usr/bin/env python3
"""Plot AI Village answer-key score against cost per run, with and without subagents.

Score is a report's mean finding score over every answer-key finding (0 to 1),
before contradiction penalties. Cost comes from scripts/aivillage_run_costs.py.
Refuses to draw unless every report in the costs file is fully graded.

  uv run python scripts/aivillage_run_costs.py --manifest benchmark/incidents/aivillage/benchmark-2026-10-04-runs.md \
      --out runs/aivillage-costs-20261004
  uv run --with matplotlib python viewers/build_aivillage_cost_figure.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
OUT = ROOT / "benchmark" / "incidents" / "aivillage" / "figures"
NAMES = {
    "claude-opus-5": "Opus 5", "claude-opus-4-8": "Opus 4.8", "claude-sonnet-5-5": "Sonnet 5.5",
    "gpt-6-astra": "GPT-6 Astra", "gpt-6.1-sol": "GPT-6.1 Sol", "gpt-6-luna": "GPT-6 Luna",
    "google/gemini-3.8-flash": "Gemini 3.8 Flash", "meta/muse-spark-1.3": "Muse Spark 1.3",
    "moonshotai/kimi-k3": "Kimi K3", "z-ai/glm-5.3": "GLM 5.3",
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
}
# Default categorical slots 1 and 2 (validated all-pairs), chart ink from the dataviz palette.
COLORS = {False: "#2a78d6", True: "#eb6834"}
# Label offsets (points) where the default, right of the mark, collides.
LABEL_OFFSETS = {
    ("z-ai/glm-5.3", False): (0, 7, "center"),
    ("claude-sonnet-5-5", False): (8, 3, "left"),
    ("moonshotai/kimi-k3", False): (7, -11, "left"),
    ("claude-opus-5", False): (-7, 4, "right"),
    ("gpt-6.1-sol", False): (-7, -11, "right"),
}
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def load_grades(path: Path | None) -> tuple[Path, dict]:
    if path is None:
        pointer = json.loads((RUNS / "aivillage-grading-medium" / "latest-plan.json").read_text())
        path = Path(pointer["plan"]).parent / "grades.json"
    return path, json.loads(path.read_text())


def build_rows(grades: dict, costs: dict) -> list[dict]:
    reports = {r["report_id"]: r for r in grades["reports"]}
    sizes = {len(r["scores"]) for r in reports.values()}
    rows = []
    for c in costs["runs"]:
        r = reports.get(c["run"])
        if r is None or not r["complete"] or r["mean_coverage"] is None:
            raise SystemExit(f"not fully graded yet: {c['run']}")
        rows.append({"run": c["run"], "model": c["model"], "name": NAMES[c["model"]],
                     "subagents": c["subagents"], "replicate": c["replicate"],
                     "usd": round(c["usd"], 4), "score": round(r["mean_coverage"], 4),
                     "contradiction_flags": len(r["main_contradiction_flags"])})
    if len(sizes) != 1:
        raise SystemExit(f"reports were graded against different numbers of findings: {sizes}")
    return rows


def groups(rows: list[dict]) -> list[dict]:
    out = {}
    for row in rows:
        key = (row["model"], row["subagents"])
        g = out.setdefault(key, {"model": row["model"], "name": row["name"],
                                 "subagents": row["subagents"], "usd": [], "score": []})
        g["usd"].append(row["usd"])
        g["score"].append(row["score"])
    for g in out.values():
        g["mean_usd"] = sum(g["usd"]) / len(g["usd"])
        g["mean_score"] = sum(g["score"]) / len(g["score"])
    return list(out.values())


def draw(rows: list[dict], n_findings: int, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(10, 6.2), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    gs = groups(rows)
    by_model = {}
    for g in gs:
        by_model.setdefault(g["model"], {})[g["subagents"]] = g
    for pair in by_model.values():
        if len(pair) == 2:
            ax.plot([pair[False]["mean_usd"], pair[True]["mean_usd"]],
                    [pair[False]["mean_score"], pair[True]["mean_score"]],
                    color=AXIS, lw=1.5, zorder=1)
    for g in gs:
        color = COLORS[g["subagents"]]
        ax.scatter(g["usd"], g["score"], s=18, color=color, alpha=0.45, lw=0, zorder=2)
        ax.scatter([g["mean_usd"]], [g["mean_score"]], s=70, color=color,
                   edgecolor=SURFACE, linewidth=2, zorder=3)
        dx, dy, ha = LABEL_OFFSETS.get((g["model"], g["subagents"]), (7, -3, "left"))
        ax.annotate(g["name"], (g["mean_usd"], g["mean_score"]), xytext=(dx, dy), ha=ha,
                    textcoords="offset points", fontsize=8.5, color=INK2, zorder=4)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}"))
    ax.set_xlabel("Cost per run (USD, log scale, list prices)", color=INK2)
    ax.set_ylabel(f"Answer-key score (mean over {n_findings} findings)", color=INK2)
    ax.set_ylim(bottom=0)
    ax.grid(True, which="major", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2)
    ax.set_title("AI Village, 30 minutes: score against cost, with and without subagents",
                 loc="left", color=INK, fontsize=12, pad=12)
    handles = [Line2D([], [], marker="o", ls="", color=COLORS[False], label="No subagents"),
               Line2D([], [], marker="o", ls="", color=COLORS[True], label="Subagents"),
               Line2D([], [], marker="o", ls="", color=MUTED, alpha=0.45, markersize=4,
                      label="Single run (large mark = mean of 2)")]
    ax.legend(handles=handles, frameon=False, loc="upper left", labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--grades", type=Path)
    parser.add_argument("--costs", type=Path, default=RUNS / "aivillage-costs-20261004" / "costs.json")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    grades_path, grades = load_grades(args.grades)
    costs = json.loads(args.costs.read_text())
    rows = build_rows(grades, costs)
    n_findings = len(grades["reports"][0]["scores"])
    args.out.mkdir(parents=True, exist_ok=True)
    draw(rows, n_findings, args.out / "score_vs_cost.png")
    (args.out / "score_vs_cost.json").write_text(json.dumps(
        {"grades": str(grades_path.relative_to(ROOT) if grades_path.is_relative_to(ROOT) else grades_path),
         "judge": f"{grades.get('model')} ({grades.get('effort')})", "findings": n_findings,
         "score": "mean finding score over all answer-key findings, before contradiction penalties",
         "costs": costs["price_source"], "runs": rows,
         "groups": [{k: g[k] for k in ("name", "subagents", "mean_usd", "mean_score")}
                    for g in groups(rows)]}, indent=1) + "\n")
    for g in sorted(groups(rows), key=lambda g: -g["mean_score"]):
        print(f"{g['name']:18s} {'sub' if g['subagents'] else '   '}  ${g['mean_usd']:6.2f}  {g['mean_score']:.3f}")


if __name__ == "__main__":
    main()
