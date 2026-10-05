#!/usr/bin/env python3
"""Plot AI Village score against cost per run and against Epoch's ECI.

The cost figure shows runs with and without subagents; the ECI figure shows
runs without subagents only, for models Epoch has scored (eci_snapshot.json).

Score is the mean of a report's 20 highest finding scores against the answer
key (0 to 1), matching the 20 findings each report writes; no contradiction
penalties. Cost comes from scripts/aivillage_run_costs.py.
Refuses to draw unless every report in the costs file is fully graded.

Writes score_vs_cost.html and score_vs_eci.html (labels can be dragged; "Copy
label positions" gives JSON to paste into <figure>_labels.json, which sets the
defaults) and a headless-Chrome PNG screenshot of each for the README.

  uv run python scripts/aivillage_run_costs.py --manifest benchmark/incidents/aivillage/benchmark-2026-10-04-runs.md \
      --out runs/aivillage-costs-20261004
  uv run python viewers/build_aivillage_figures.py
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
TEMPLATE = ROOT / "viewers" / "templates" / "aivillage_figure.html"
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
# mark in SVG units. <figure>_labels.json, when present, overrides these.
COST_LABELS = {
    "gpt-6-astra": (True, -10, -34), "gpt-6.1-sol": (True, -16, -6),
    "claude-sonnet-5-5": (True, 30, -30), "claude-opus-5": (True, 34, 34),
    "z-ai/glm-5.3": (False, -24, -46), "google/gemini-3.8-flash": (False, -50, 54),
    "moonshotai/kimi-k3": (False, -40, 50), "claude-opus-4-8": (False, 0, 46),
    "meta/muse-spark-1.3": (False, 18, 4), "gpt-6-luna": (False, 0, 46),
    "deepseek/deepseek-v4-flash": (False, 0, 46),
}
ECI_LABELS = {
    "gpt-6-astra": (False, 20, -34), "claude-sonnet-5-5": (False, -30, -40),
    "claude-opus-5": (False, 24, 50), "z-ai/glm-5.3": (False, -20, -40),
    "google/gemini-3.8-flash": (False, -80, 4), "moonshotai/kimi-k3": (False, 20, -40),
    "claude-opus-4-8": (False, 20, 46), "meta/muse-spark-1.3": (False, -40, 52),
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


def frontier(points: list[dict]) -> list[dict]:
    """Points no cheaper point beats on score."""
    best, out = -1.0, []
    for p in sorted(points, key=lambda p: p["x"]):
        if p["score"] > best:
            best = p["score"]
            out.append(p)
    return out


def figure_data(gs: list[dict], xs: dict, label_offsets: dict, *, x_axis: dict, title: str,
                aria: str, caption: str, y_label: str, x_head: str, describe, with_frontier: bool,
                labels_file: str, labels: dict) -> dict:
    """xs maps (model, subagents) to {"x": value, optional "ci": [lo, hi]}; groups without one are skipped."""
    models, vendors, points = {}, [], []
    for g in gs:
        key = (g["model"], g["subagents"])
        if key not in xs:
            continue
        name, color = vendor(g["model"])
        if {"name": name, "color": color} not in vendors:
            vendors.append({"name": name, "color": color})
        m = models.setdefault(g["model"], {"name": g["name"], "color": color, "points": {}})
        point = {**xs[key], "score": g["mean_score"], "n": len(g["score"])}
        point["title"] = describe(g, point)
        m["points"][str(g["subagents"]).lower()] = point
        points.append(point)
        sub, dx, dy = label_offsets[g["model"]]
        m["label"] = {"sub": str(sub).lower(), "dx": dx, "dy": dy}
    order = [v[0] for v in VENDOR.values()]
    vendors.sort(key=lambda v: order.index(v["name"]))
    rows = []
    for m in models.values():
        cells = [m["name"]]
        for sub in ("false", "true"):
            p = m["points"].get(sub)
            if with_frontier or sub == "false":
                cells += [x_axis["format"].format(p["x"]) if p else "–",
                          f"{p['score']:.1%}" if p else "–"]
        rows.append({"color": m["color"], "cells": cells})
    head = ["Model", f"{x_head}, no subagents", "Score, no subagents"]
    if with_frontier:
        head += [f"{x_head}, subagents", "Score, subagents"]
    return {
        "title": title, "aria": aria, "caption": caption, "y_label": y_label, "x_axis": x_axis,
        "models": list(models.values()), "vendors": vendors,
        "frontier": frontier(points) if with_frontier else [],
        "label_positions": labels, "labels_file": labels_file,
        "label_storage_key": f"aivillage-{labels_file.removesuffix('_labels.json')}-labels-v1",
        "table": {"head": head, "rows": rows},
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


def write_figure(out: Path, stem: str, data: dict) -> None:
    html = (TEMPLATE.read_text().replace("__TITLE__", data["title"])
            .replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
    (out / f"{stem}.html").write_text(html)
    render_png(html, out / f"{stem}.png")


def labels_for(out: Path, stem: str) -> tuple[str, dict]:
    path = out / f"{stem}_labels.json"
    return path.name, (json.loads(path.read_text()) if path.exists() else {})


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
    judge = f"{grades.get('model')}, {grades.get('effort')} reasoning"
    score = (f"Score: mean of each report's {TOP_K} best finding scores against the "
             f"{n_findings}-finding rubric (judge {judge}, no contradiction penalties).")
    y_label = f"score (mean of best {TOP_K} of {n_findings} findings)"
    gs = groups(rows)
    args.out.mkdir(parents=True, exist_ok=True)

    name, labels = labels_for(args.out, "score_vs_cost")
    write_figure(args.out, "score_vs_cost", figure_data(
        gs, {(g["model"], g["subagents"]): {"x": g["mean_usd"]} for g in gs}, COST_LABELS,
        x_axis={"log": True, "min": 0.1, "max": 100, "ticks": [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100],
                "prefix": "$", "format": "${:.2f}",
                "label": "estimated cost per run, USD at list price (log scale)"},
        title="AI Village Score vs Cost", aria="AI Village score against cost per run, with and without subagents",
        caption=(f"AI Village, 30 minutes. {score} Cost per run at list prices, subagents included. "
                 "Each mark is the mean of two runs; dashed lines join a model's runs without and with subagents."),
        y_label=y_label, x_head="Cost",
        describe=lambda g, p: (f"{g['name']}, {'subagents' if g['subagents'] else 'no subagents'}: "
                               f"${p['x']:.2f} per run, score {p['score']:.1%} (mean of {p['n']} runs)"),
        with_frontier=True, labels_file=name, labels=labels))

    eci = json.loads((args.out / "eci_snapshot.json").read_text())
    xs = {(m, False): {"x": e["eci"], "ci": e["ci"]} for m, e in eci["models"].items() if e}
    missing = [NAMES[m] for m, e in eci["models"].items() if not e]
    name, labels = labels_for(args.out, "score_vs_eci")
    write_figure(args.out, "score_vs_eci", figure_data(
        gs, xs, ECI_LABELS,
        x_axis={"log": False, "min": 144, "max": 172, "ticks": list(range(144, 173, 4)), "prefix": "",
                "format": "{:.1f}", "label": f"Epoch Capabilities Index (ECI), retrieved {eci['retrieved']}"},
        title="AI Village Score vs ECI", aria="AI Village score against Epoch Capabilities Index, runs without subagents",
        caption=(f"AI Village, 30 minutes, runs without subagents. {score} Each mark is the mean of two runs; "
                 "the faint bar is Epoch's 95% interval for the model's ECI. "
                 f"Not shown: {' and '.join(missing)}, which Epoch has not scored."),
        y_label=y_label, x_head="ECI",
        describe=lambda g, p: (f"{g['name']}: ECI {p['x']:.1f} ({p['ci'][0]:.1f} to {p['ci'][1]:.1f}), "
                               f"score {p['score']:.1%} (mean of {p['n']} runs)"),
        with_frontier=False, labels_file=name, labels=labels))

    (args.out / "score_vs_cost.json").write_text(json.dumps(
        {"grades": str(grades_path.relative_to(ROOT) if grades_path.is_relative_to(ROOT) else grades_path),
         "judge": judge, "findings": n_findings,
         "score": f"mean of the {TOP_K} highest finding scores per report, no contradiction penalties",
         "costs": costs["price_source"], "runs": rows,
         "groups": [{k: g[k] for k in ("name", "subagents", "mean_usd", "mean_score")} for g in gs]},
        indent=1) + "\n")
    for g in sorted(gs, key=lambda g: -g["mean_score"]):
        print(f"{g['name']:18s} {'sub' if g['subagents'] else '   '}  ${g['mean_usd']:6.2f}  {g['mean_score']:.3f}")


if __name__ == "__main__":
    main()
