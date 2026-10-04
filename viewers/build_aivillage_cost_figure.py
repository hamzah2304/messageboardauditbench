#!/usr/bin/env python3
"""Plot AI Village answer-key score against cost per run, with and without subagents.

Score is the mean of a report's 20 highest finding scores against the answer
key (0 to 1), matching the 20 findings each report writes; no contradiction
penalties. Cost comes from scripts/aivillage_run_costs.py.
Refuses to draw unless every report in the costs file is fully graded.

Writes score_vs_cost.html (labels can be dragged; "Copy label positions" gives
JSON to paste into score_vs_cost_labels.json, which sets the defaults) and
score_vs_cost.png, a headless-Chrome screenshot of that page for the README.

  uv run python scripts/aivillage_run_costs.py --manifest benchmark/incidents/aivillage/benchmark-2026-10-04-runs.md \
      --out runs/aivillage-costs-20261004
  uv run python viewers/build_aivillage_cost_figure.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from browser_executable import find_chromium

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
TEMPLATE = ROOT / "viewers" / "templates" / "aivillage_cost_figure.html"
TOP_K = 20
OUT = ROOT / "benchmark" / "incidents" / "aivillage" / "figures"
NAMES = {
    "claude-opus-5": "Opus 5", "claude-opus-4-8": "Opus 4.8", "claude-sonnet-5-5": "Sonnet 5.5",
    "gpt-6-astra": "GPT-6 Astra", "gpt-6.1-sol": "GPT-6.1 Sol", "gpt-6-luna": "GPT-6 Luna",
    "google/gemini-3.8-flash": "Gemini 3.8 Flash", "meta/muse-spark-1.3": "Muse Spark 1.3",
    "moonshotai/kimi-k3": "Kimi K3", "z-ai/glm-5.3": "GLM 5.3",
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
}
# Vendor colours shared with the German wiki and URLQuery cost figures.
VENDOR = {
    "claude": ("Anthropic", "#d97757"), "gpt": ("OpenAI", "#202126"),
    "google": ("Google", "#2e9e4f"), "meta": ("Meta", "#0668e1"),
    "moonshotai": ("Moonshot", "#c2185b"), "z-ai": ("Z.ai", "#00897b"),
    "deepseek": ("DeepSeek", "#7c55b6"),
}
# One label per model: which point it names and its default offset from that
# mark in SVG units. score_vs_cost_labels.json, when present, overrides these.
LABELS = {
    "gpt-6-astra": (True, -10, -34), "gpt-6.1-sol": (True, -16, -6),
    "claude-sonnet-5-5": (True, 30, -30), "claude-opus-5": (True, 34, 34),
    "z-ai/glm-5.3": (False, -24, -46), "google/gemini-3.8-flash": (False, -50, 54),
    "moonshotai/kimi-k3": (False, -40, 50), "claude-opus-4-8": (False, 0, 46),
    "meta/muse-spark-1.3": (False, 40, 50), "gpt-6-luna": (False, 0, 46),
    "deepseek/deepseek-v4-flash": (False, 0, 46),
}


def vendor(model: str) -> tuple[str, str]:
    return VENDOR[model.replace("/", "-").split("-")[0] if "/" not in model else model.split("/")[0]]


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
        best = sorted((f["score"] for f in r["scores"].values()), reverse=True)[:TOP_K]
        rows.append({"run": c["run"], "model": c["model"], "name": NAMES[c["model"]],
                     "subagents": c["subagents"], "replicate": c["replicate"],
                     "usd": round(c["usd"], 4), "score": round(sum(best) / TOP_K, 4),
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


def frontier(gs: list[dict]) -> list[dict]:
    """Points no cheaper point beats on score."""
    best, out = -1.0, []
    for g in sorted(gs, key=lambda g: g["mean_usd"]):
        if g["mean_score"] > best:
            best = g["mean_score"]
            out.append(g)
    return out


def figure_data(rows: list[dict], n_findings: int, judge: str, labels: dict) -> dict:
    gs = groups(rows)
    models, vendors = {}, []
    for g in gs:
        name, color = vendor(g["model"])
        if {"name": name, "color": color} not in vendors:
            vendors.append({"name": name, "color": color})
        m = models.setdefault(g["model"], {"name": g["name"], "color": color, "points": {}})
        m["points"][str(g["subagents"]).lower()] = {"usd": g["mean_usd"], "score": g["mean_score"],
                                                    "n": len(g["usd"])}
        sub, dx, dy = LABELS[g["model"]]
        m["label"] = {"sub": str(sub).lower(), "dx": dx, "dy": dy}
    order = [v[0] for v in VENDOR.values()]
    vendors.sort(key=lambda v: order.index(v["name"]))
    return {
        "models": list(models.values()), "vendors": vendors,
        "frontier": [{"usd": g["mean_usd"], "score": g["mean_score"]} for g in frontier(gs)],
        "label_positions": labels, "label_storage_key": "aivillage-score-vs-cost-labels-v1",
        "y_label": f"score (mean of best {TOP_K} of {n_findings} findings)",
        "caption": (f"AI Village, 30 minutes. Score: mean of each report's {TOP_K} best finding scores "
                    f"against the {n_findings}-finding answer key (judge {judge}, no contradiction "
                    "penalties). Cost per run at list prices, subagents included. Each mark is the "
                    "mean of two runs; dashed lines join a model's runs without and with subagents."),
    }


def render_png(html: str, path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "figure.html"
        # Standalone page without the controls and value table.
        page.write_text('<!doctype html><meta charset="utf-8">'
                        + html.replace("</style>", ".controls,details{display:none}</style>"))
        subprocess.run([find_chromium(), "--headless=new", "--hide-scrollbars", "--disable-gpu",
                        "--virtual-time-budget=4000", "--window-size=1060,700",
                        "--force-device-scale-factor=2", f"--screenshot={path}", page.as_uri()],
                       check=True, capture_output=True)


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
    labels_file = args.out / "score_vs_cost_labels.json"
    labels = json.loads(labels_file.read_text()) if labels_file.exists() else {}
    judge = f"{grades.get('model')}, {grades.get('effort')} reasoning"
    data = figure_data(rows, n_findings, judge, labels)
    html = TEMPLATE.read_text().replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    (args.out / "score_vs_cost.html").write_text(html)
    render_png(html, args.out / "score_vs_cost.png")
    (args.out / "score_vs_cost.json").write_text(json.dumps(
        {"grades": str(grades_path.relative_to(ROOT) if grades_path.is_relative_to(ROOT) else grades_path),
         "judge": f"{grades.get('model')} ({grades.get('effort')})", "findings": n_findings,
         "score": f"mean of the {TOP_K} highest finding scores per report, no contradiction penalties",
         "costs": costs["price_source"], "runs": rows,
         "groups": [{k: g[k] for k in ("name", "subagents", "mean_usd", "mean_score")}
                    for g in groups(rows)]}, indent=1) + "\n")
    for g in sorted(groups(rows), key=lambda g: -g["mean_score"]):
        print(f"{g['name']:18s} {'sub' if g['subagents'] else '   '}  ${g['mean_usd']:6.2f}  {g['mean_score']:.3f}")


if __name__ == "__main__":
    main()
