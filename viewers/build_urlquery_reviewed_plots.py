#!/usr/bin/env python3
"""Build separate URLQuery cost plots for the latest and previous graded rounds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_urlquery_usd_figure import PRICE_SOURCE, ROOT, cost_of, read_json

from messageboard_audit_bench.benchmarks import primary_root

FIGURES = ROOT / "viewers" / "figures"
RUNS = ROOT / "runs" / "urlquery"
TEMPLATE = ROOT / "viewers" / "templates" / "urlquery_usd_figure.html"
OLD = FIGURES / "urlquery_usd_rescored_figure.json"
LABELS = {
    "gpt-6-astra": "GPT-6 Astra",
    "gpt-6-luna": "GPT-6 Luna",
    "gpt-6-sol": "GPT-6 Sol · Codex",
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4-8": "Opus 4.8",
    "claude-opus-5": "Opus 5",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "google/gemini-3.8-flash": "Gemini 3.8 Flash",
    "meta/muse-spark-1.3": "Muse Spark 1.3",
    "moonshotai/kimi-k3": "Kimi K3",
    "z-ai/glm-5.3": "GLM 5.3",
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
    "openai/gpt-6-sol": "GPT-6 Sol · ReAct",
}
PROVIDERS = {
    "gpt-6": "openai", "openai/": "openai", "claude-": "anthropic",
    "google/": "google", "meta/": "meta", "moonshotai/": "moonshot",
    "z-ai/": "zai", "deepseek/": "deepseek",
}


def write_plot(name: str, payload: dict) -> Path:
    path = FIGURES / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    html = path.with_suffix(".html")
    html.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
    return html


def latest(state_path: Path) -> Path:
    state = read_json(state_path)
    rows = []
    excluded = []
    stamps = set()
    for run in state["runs"]:
        name = run["name"]
        meta = read_json(RUNS / name / "meta.json")
        minimum = meta.get("minimum_runtime_seconds", .75 * run["budget_min"] * 60)
        if (meta.get("termination") not in ("normal", "active_time_limit")
                or meta.get("minimum_runtime_reached") is not True
                or meta.get("wall_seconds", 0) < minimum
                or meta.get("report_length_compliant") is not True):
            raise ValueError(f"latest graded run fails eligibility: {name}")
        if meta.get("model_fallback") or (meta.get("model_served") and
                                          meta["model_served"] != meta["model"]):
            excluded.append({"run_dir": name, "model": run["model"],
                             "budget_min": run["budget_min"], "replicate": meta["replicate"],
                             "reasons": ["model_fallback"],
                             "served_model": meta.get("model_served")})
            continue
        grades = []
        for transport in ("batch", "sync"):
            path = (primary_root() / "reports" / "urlquery" / "graded"
                    / f"judge_gpt_6_astra_high_openai_{transport}" / f"{name}.json")
            if path.exists() and (grade := read_json(path)).get("n_scored") == 13:
                grades.append(grade)
        if len(grades) != 1:
            raise ValueError(f"need exactly one complete grade for {name}: {len(grades)}")
        grade = grades[0]
        report = (RUNS / name / "report.md").read_bytes()
        if (hashlib.sha256(report).hexdigest() != grade["report_sha256"]
                or grade["report_sha256"] != run["report_sha256"]
                or set(grade["findings"]) != {f"F{i}" for i in range(1, 14)}
                or any(f["status"] != "ok" for f in grade["findings"].values())):
            raise ValueError(f"inconsistent grade for {name}")
        stamps.add(tuple(grade[field] for field in
                         ("judge", "effort", "prompt_sha256", "findings_sha256", "article_sha256")))
        model = run["model"]
        usage_path = RUNS / name / "usage.json"
        usage = read_json(usage_path) if usage_path.exists() else {}
        cost, source = cost_of(model, usage)
        if cost is None:
            raise ValueError(f"no cost for {name}")
        provider = next(value for prefix, value in PROVIDERS.items() if model.startswith(prefix))
        rows.append({"run_dir": name, "model": model, "label": LABELS[model],
                     "provider": provider, "harness": run["agent"],
                     "budget_min": run["budget_min"], "replicate": meta["replicate"],
                     "status": "complete", "cost_usd": cost, "cost_source": source,
                     "performance": grade["score_mean"]})
    if len(rows) != 24 or len(excluded) != 2 or len(stamps) != 1:
        raise ValueError(f"expected 24 eligible reports, 2 fallbacks; got {len(rows)}, {len(excluded)}")
    judge, effort, prompt_hash, findings_hash, article_hash = stamps.pop()
    payload = {"benchmark": "urlquery", "version": "agents-v6-latest",
               "measure": "finding_score_mean", "finding_count": 13,
               "figure_title": "URLQuery: latest round · performance against cost",
               "figure_subtitle": "Latest v6 round · one report per model and time limit",
               "expected_reports_per_model": 2,
               "label_storage_key": "urlquery-latest-reviewed-zero-axis-labels-v1",
               "grade_source": {"judge": judge, "effort": effort, "prompt_sha256": prompt_hash,
                                "findings_sha256": findings_hash, "article_sha256": article_hash,
                                "grade_count": len(rows)},
               "excluded_runs": excluded,
               "cost_note": "USD per run. Codex values estimate Standard short-context API list-price token equivalents; other values come from usage.json cost_usd. Subscription charges and judge costs are excluded.",
               "openai_price_source": PRICE_SOURCE, "runs": rows}
    return write_plot("urlquery_latest_reviewed_figure", payload)


def previous_filtered() -> Path:
    payload = read_json(OLD)
    excluded = list(payload["excluded_runs"])
    keep = []
    for row in payload["runs"]:
        name = row["run_dir"]
        if not name:
            continue
        meta = read_json(RUNS / name / "meta.json")
        reasons = []
        if row["model"] == "claude-sonnet-5":
            reasons.append("dropped_model")
        if meta.get("model_fallback") or (meta.get("model_served") and
                                          meta["model_served"] != meta["model"]):
            reasons.append("model_fallback")
        minimum = meta.get("minimum_runtime_seconds", .75 * row["budget_min"] * 60)
        if meta.get("minimum_runtime_reached") is False or meta.get("wall_seconds", 0) < minimum:
            reasons.append("below_minimum_runtime")
        if reasons:
            excluded.append({"run_dir": name, "model": row["model"],
                             "budget_min": row["budget_min"], "replicate": row["replicate"],
                             "reasons": reasons})
        else:
            keep.append(row)
    payload["runs"] = keep
    payload["excluded_runs"] = excluded
    payload["figure_title"] = "URLQuery: previous round · eligible reports"
    payload["figure_subtitle"] = "Previous v6 round · dropped model and early exits removed"
    payload["label_storage_key"] = "urlquery-previous-filtered-zero-axis-labels-v1"
    payload["grade_source"]["grade_count"] = len(keep)
    if len(keep) != 39 or len(excluded) != 9:
        raise ValueError(f"unexpected previous-round exclusions: {len(keep)} kept, {len(excluded)} excluded")
    return write_plot("urlquery_previous_filtered_figure", payload)


def combined() -> Path:
    previous = read_json(FIGURES / "urlquery_previous_filtered_figure.json")
    recent = read_json(FIGURES / "urlquery_latest_reviewed_figure.json")
    fields = ("effort", "prompt_sha256", "findings_sha256", "article_sha256")
    if any(previous["grade_source"][field] != recent["grade_source"][field] for field in fields):
        raise ValueError("cannot combine different grading specifications")
    if previous["finding_count"] != recent["finding_count"]:
        raise ValueError("cannot combine different finding counts")
    older_rows = [dict(row) for row in previous["runs"]]
    for row in older_rows:
        if row["model"] == "gpt-6-sol":
            row["label"] = "GPT-6 Sol · Codex"
    rows = older_rows + recent["runs"]
    names = [row["run_dir"] for row in rows]
    if len(names) != len(set(names)) or len(rows) != 63:
        raise ValueError(f"expected 63 unique eligible reports, got {len(rows)}")
    planned = {label: (2 if label in ("Sonnet 5.5", "GPT-6 Sol · ReAct") else 6)
               for label in {row["label"] for row in rows}}
    payload = {**recent,
               "version": "agents-v6-combined",
               "figure_title": "URLQuery: combined rounds · performance against cost",
               "figure_subtitle": "Sunday and latest v6 rounds · same reviewed grading specification",
               "label_storage_key": "urlquery-combined-reviewed-zero-axis-labels-v1",
               "expected_reports_by_model": planned,
               "excluded_runs": previous["excluded_runs"] + recent["excluded_runs"],
               "runs": rows,
               "grade_source": {**recent["grade_source"], "grade_count": len(rows)}}
    if len(payload["excluded_runs"]) != 11:
        raise ValueError("unexpected combined exclusion count")
    return write_plot("urlquery_combined_reviewed_figure", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    args = parser.parse_args()
    print(latest(args.state))
    print(previous_filtered())
    print(combined())


if __name__ == "__main__":
    main()
