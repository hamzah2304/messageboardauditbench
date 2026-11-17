"""Results for the standard condition: one row per run, one cell per eval x model x budget.

Every run directory of a standard config becomes a row, graded or not: its eligibility
(slopvestigator_bench/eligibility.py), its cost, and its score from the newest grade log that
covers it. A cell's score is the mean over its eligible, scored runs, with a 95% bootstrap
interval over those runs; failures are counted beside it, never folded into the score.

Scores per eval, as published:
  messageboard  0.7 x strict coverage of the 38 v2 findings (max(2s - 1, 0) each) + 0.3 x tldrh
  urlquery      the weighted mean of the 13 reviewed headline findings
  aivillage     the mean of the report's 20 best finding scores of 96
"""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from slopvestigator_bench import eligibility, lineup, standard
from slopvestigator_bench.benchmarks import SPECS

W_COVERAGE, W_TLDR = 0.7, 0.3


@dataclass
class Row:
    benchmark_id: str
    model: str
    budget: int
    replicate: int
    run: str
    eligible: bool
    reasons: str
    safety_flags: int
    cost_usd: float | None
    score: float | None


def strict(s: float) -> float:
    return max(2 * s - 1, 0.0)


def run_cost(run_dir: Path, model_id: str) -> float | None:
    """The CLI's own cost when it reports one, else the lineup's list price times tokens."""
    path = run_dir / "usage.json"
    if not path.is_file():
        return None
    usage = json.loads(path.read_text())
    if usage.get("cost_usd") is not None:
        return float(usage["cost_usd"])
    try:
        m = lineup.model(model_id)
    except KeyError:
        return None
    uncached = usage.get("input_tokens_uncached", usage.get("input_tokens", 0)) + usage.get("cache_write_tokens", 0)
    cached = usage.get("cache_read_tokens", 0)
    return (uncached * m.price_in + 0.1 * cached * m.price_in + usage.get("output_tokens", 0) * m.price_out) / 1e6


def grades_from_logs(log_dir: Path) -> dict[tuple[str, str], dict]:
    """(benchmark_id, run name) -> {part: value}, newest log winning; NaN (unscored) kept as None."""
    from inspect_ai.log import list_eval_logs, read_eval_log

    found: dict[tuple[str, str], dict] = defaultdict(dict)
    logs = [read_eval_log(info) for info in list_eval_logs(str(log_dir))]
    for log in sorted(logs, key=lambda lg: lg.eval.created):
        meta = log.eval.metadata or {}
        bench = meta.get("benchmark_id")
        if meta.get("mode") != "grading" or bench not in SPECS:
            continue
        for sample in log.samples or []:
            run = (sample.metadata or {}).get("run")
            if not run or not sample.scores:
                continue
            score = next(iter(sample.scores.values()))
            if bench == "messageboard":
                rubric = meta.get("rubric")
                if math.isnan(_num(score.value)):
                    found[(bench, run)][rubric] = None
                elif rubric == "v2":
                    claims = (score.metadata or {}).get("grade", {}).get("scores", {})
                    found[(bench, run)]["v2"] = statistics.mean(strict(c["score"]) for c in claims.values())
                else:
                    found[(bench, run)][rubric] = _num(score.value)
            else:
                value = score.value["score"] if isinstance(score.value, dict) else score.value
                found[(bench, run)]["score"] = None if math.isnan(_num(value)) else _num(value)
    return found


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def combine(benchmark_id: str, parts: dict) -> float | None:
    if benchmark_id == "messageboard":
        if parts.get("v2") is None or parts.get("tldrh") is None:
            return None
        return W_COVERAGE * parts["v2"] + W_TLDR * parts["tldrh"]
    return parts.get("score")


def rows(primary: Path, log_dir: Path | None) -> list[Row]:
    grades = grades_from_logs(log_dir) if log_dir and log_dir.exists() else {}
    out = []
    for bench in standard.benchmark_ids():
        root = primary / SPECS[bench].run_root
        for config in standard.config_names(bench):
            for run_dir in sorted(root.glob(f"*_{config}_*")):
                meta_path = run_dir / "meta.json"
                if not meta_path.is_file():
                    continue
                meta = json.loads(meta_path.read_text())
                if not standard.same_condition(meta, config):  # an older version of this config name
                    continue
                started = any(p.stat().st_size > 0 for p in run_dir.glob("transcript*.jsonl"))
                if "exit_code" not in meta and not started:  # never reached the model (see run_matrix)
                    continue
                verdict = eligibility.check_meta(meta)
                score = combine(bench, grades.get((bench, run_dir.name), {}))
                out.append(Row(bench, meta.get("model", ""), int(meta.get("budget_min") or 0),
                               int(meta.get("replicate") or 0), run_dir.name, verdict.eligible,
                               ",".join(verdict.reasons), verdict.safety_flags,
                               run_cost(run_dir, meta.get("model", "")), score))
    return out


def bootstrap(values: list[float], draws: int = 10000, seed: int = 0) -> tuple[float, float] | None:
    """95% percentile interval of the mean, resampling runs."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(draws))
    return means[int(0.025 * draws)], means[int(0.975 * draws) - 1]


def cells(table: list[Row]) -> list[dict]:
    groups: dict[tuple, list[Row]] = defaultdict(list)
    for r in table:
        groups[(r.benchmark_id, r.model, r.budget)].append(r)
    out = []
    for (bench, model, budget), rs in sorted(groups.items()):
        scored = [r.score for r in rs if r.eligible and r.score is not None]
        costs = [r.cost_usd for r in rs if r.cost_usd is not None]
        ci = bootstrap(scored)
        out.append({"benchmark_id": bench, "model": model, "budget": budget, "runs": len(rs),
                    "eligible": sum(r.eligible for r in rs), "scored": len(scored),
                    "safety_flagged_runs": sum(r.safety_flags > 0 for r in rs),
                    "score": statistics.fmean(scored) if scored else None,
                    "ci_low": ci[0] if ci else None, "ci_high": ci[1] if ci else None,
                    "cost_usd": statistics.fmean(costs) if costs else None})
    return out


def write(table: list[Row], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path, cells_path = out_dir / "runs.jsonl", out_dir / "cells.json"
    runs_path.write_text("".join(json.dumps(asdict(r)) + "\n" for r in table))
    cells_path.write_text(json.dumps(cells(table), indent=1) + "\n")
    return runs_path, cells_path
