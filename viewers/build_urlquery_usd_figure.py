#!/usr/bin/env python3
"""Build the URLQuery v6 performance-vs-USD figure from the final run archive.

Performance is deliberately null until URLQuery grades are approved. Existing
per-run performance entries in the output JSON survive a rebuild, keyed by run
directory name. The HTML also works while the batch is still running.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "urlquery"
OUT = ROOT / "viewers" / "figures" / "urlquery_usd_figure.json"
HTML = OUT.with_suffix(".html")
CONDITIONS = {10: "urlquery-agents-v6-10", 30: "urlquery-agents-v6-30"}
MODELS = [
    ("codex", "gpt-6-astra", "GPT-6 Astra", "openai"),
    ("codex", "gpt-6-sol", "GPT-6 Sol", "openai"),
    ("codex", "gpt-6-luna", "GPT-6 Luna", "openai"),
    ("claude", "claude-opus-5", "Opus 5", "anthropic"),
    ("claude", "claude-opus-4-8", "Opus 4.8", "anthropic"),
    ("claude", "claude-opus-4-6", "Opus 4.6", "anthropic"),
    ("claude", "claude-sonnet-5", "Sonnet 5", "anthropic"),
    ("react", "google/gemini-3.8-flash", "Gemini 3.8 Flash", "google"),
    ("react", "meta/muse-spark-1.3", "Muse Spark 1.3", "meta"),
    ("react", "moonshotai/kimi-k3", "Kimi K3", "moonshot"),
    ("react", "z-ai/glm-5.3", "GLM 5.3", "zai"),
    ("react", "deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", "deepseek"),
]
# Standard, short-context list prices per million tokens, checked 2026-09-27.
# Codex subscription use is shown as a token-equivalent API estimate.
OPENAI_PRICES = {
    "gpt-6-astra": (10.0, 1.0, 12.5, 50.0),
    "gpt-6-sol": (2.0, 0.2, 2.5, 10.0),
    "gpt-6-luna": (0.1, 0.01, 0.125, 0.5),
}
PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_grades(directory: Path, run_names: set[str]) -> tuple[dict, dict]:
    """Read one complete, internally consistent judge batch for these runs."""
    grades = {}
    stamp = None
    fields = ("judge", "effort", "prompt_sha256", "findings_sha256", "article_sha256")
    for path in sorted(directory.glob("*.json")):
        grade = read_json(path)
        name = grade.get("run")
        if name not in run_names:
            continue
        current = {field: grade.get(field) for field in fields}
        if stamp is None:
            stamp = current
        elif current != stamp:
            raise ValueError(f"judge provenance differs in {path}")
        if grade.get("n_scored") != grade.get("n_findings") or grade.get("n_findings") != 12:
            raise ValueError(f"incomplete grade: {path}")
        score = grade.get("score_mean")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError(f"invalid score: {path}")
        report = RUNS / name / "report.md"
        if not report.exists() or hashlib.sha256(report.read_bytes()).hexdigest() != grade.get("report_sha256"):
            raise ValueError(f"grade/report hash mismatch: {path}")
        if name in grades:
            raise ValueError(f"duplicate grade for {name}")
        grades[name] = score
    if set(grades) != run_names:
        missing = sorted(run_names - set(grades))
        raise ValueError(f"need one complete grade per final run: {len(grades)}/{len(run_names)}; missing {missing}")
    return grades, {**stamp, "grade_count": len(grades)}


def cost_of(model: str, usage: dict) -> tuple[float | None, str | None]:
    if model in OPENAI_PRICES:
        keys = ("input_tokens_uncached", "cache_read_tokens", "cache_write_tokens", "output_tokens")
        if any(not isinstance(usage.get(k), (int, float)) for k in keys):
            return None, None
        prices = OPENAI_PRICES[model]
        return round(sum(usage[k] * price for k, price in zip(keys, prices)) / 1e6, 6), "estimated_api_list"
    cost = usage.get("cost_usd")
    if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
        return round(cost, 6), "recorded_usage"
    return None, None


def exclusion_reasons(meta: dict) -> list[str]:
    """Apply the final batch's requested report length and runtime floor."""
    reasons = []
    if meta.get("data_manifest_status") != "verified":
        reasons.append("dataset_not_verified")
    words = meta.get("report_words")
    if not isinstance(words, int) or words < meta.get("report_min_words", 2400):
        reasons.append("below_requested_word_minimum")
    if not meta.get("report_length_compliant"):
        reasons.append("report_length_not_accepted")
    if meta.get("minimum_runtime_reached") is not True:
        reasons.append("below_minimum_runtime")
    if meta.get("termination") not in ("normal", "active_time_limit"):
        reasons.append("unexpected_termination")
    return reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--grades-dir", type=Path, help="import a complete, matching 48-run grade batch")
    args = parser.parse_args()
    old = read_json(OUT) if OUT.exists() else {}
    previous = {r["run_dir"]: r.get("performance") for r in old.get("runs", []) if r.get("run_dir")}
    found = {}
    for path in RUNS.glob("*/meta.json"):
        try:
            meta = read_json(path)
        except (OSError, ValueError):
            continue  # a running trial can still be writing its metadata
        if meta.get("condition") not in CONDITIONS.values():
            continue
        key = (meta.get("condition"), meta.get("agent"), meta.get("model"), meta.get("replicate"))
        if key in found:
            raise ValueError(f"duplicate final run for {key}: {found[key]} and {path.parent}")
        found[key] = path.parent

    grades, grade_source = load_grades(args.grades_dir, {p.name for p in found.values()}) if args.grades_dir else (None, old.get("grade_source"))

    rows, excluded = [], []
    for budget, condition in CONDITIONS.items():
        for agent, model, label, provider in MODELS:
            for replicate in (1, 2):
                path = found.get((condition, agent, model, replicate))
                usage_path = path / "usage.json" if path else None
                report = bool(path and (path / "report.md").exists())
                usage = read_json(usage_path) if report and usage_path and usage_path.exists() else {}
                cost, source = cost_of(model, usage) if report else (None, None)
                name = path.name if path else None
                if report:
                    reasons = exclusion_reasons(read_json(path / "meta.json"))
                    if reasons:
                        excluded.append({"run_dir": name, "model": model, "budget_min": budget,
                                         "replicate": replicate, "reasons": reasons})
                        continue
                performance = grades[name] if grades is not None else previous.get(name)
                if performance is not None and (not isinstance(performance, (int, float)) or
                                                not math.isfinite(performance) or not 0 <= performance <= 1):
                    raise ValueError(f"invalid performance for {name}: {performance}")
                rows.append({"run_dir": name, "model": model, "label": label, "provider": provider,
                             "harness": agent, "budget_min": budget, "replicate": replicate,
                             "status": "complete" if report else "running" if path else "not_started",
                             "cost_usd": cost, "cost_source": source, "performance": performance})

    payload = {"benchmark": "urlquery", "version": "agents-v6", "measure": "finding_score_mean",
               "measure_note": "0–1 mean of 12 URLQuery headline-finding grades over eligible runs; null means ungraded",
               "grade_source": grade_source,
               "excluded_runs": excluded,
               "cost_note": "USD per run. Codex values estimate Standard short-context API list-price token equivalents; other values come from usage.json cost_usd. Subscription charges and judge costs are excluded.",
               "openai_price_source": PRICE_SOURCE, "runs": rows}
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    template = (ROOT / "viewers" / "templates" / "urlquery_usd_figure.html").read_text()
    HTML.write_text(template.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
    print(f"{HTML}: {sum(r['status'] == 'complete' for r in rows)}/{len(rows)} eligible reports, "
          f"{len(excluded)} excluded, "
          f"{sum(r['cost_usd'] is not None for r in rows)} costs, "
          f"{sum(r['performance'] is not None for r in rows)} performance values")


if __name__ == "__main__":
    main()
