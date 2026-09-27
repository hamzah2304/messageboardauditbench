#!/usr/bin/env python3
"""Turn local URLQuery run directories into labelled Inspect logs and open the viewer.

Usage:
    uv run python scripts/view_urlquery_runs.py            # build logs, then `inspect view`
    uv run python scripts/view_urlquery_runs.py --no-view  # build only
    uv run python scripts/view_urlquery_runs.py --since 20260927T06 --port 7577

Reads `runs/urlquery/<run>/` in the primary checkout (transcript, report, meta)
and writes one unscored Inspect log per prompt-and-budget group to
`logs/urlquery-runs/` (replacing the logs from the previous build), e.g. "urlquery-swarm-v4 · 10 min". No model is called.
Each sample is one run, named `<model> r<replicate>`, with the agent, model,
config, prompt hash, termination, report length and run directory in its
metadata, and report words / active minutes as sortable score columns.

The run directories and these logs are gitignored: transcripts contain raw
scan data, including recorded credentials. Share the logs only privately.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from messageboard_audit_bench.solver import replay
from messageboard_audit_bench.urlquery_data import primary_root


@scorer(metrics={"report_words": [mean()], "active_minutes": [mean()]})
def run_stats():
    """Report length and active runtime as sortable columns; not a grade."""

    async def score(state: TaskState, target: Target) -> Score:
        meta = state.metadata
        wall = meta.get("wall_seconds")
        return Score(
            value={
                "report_words": meta.get("report_words") or 0,
                "active_minutes": round(wall / 60, 1) if wall else 0,
            },
            explanation=f"termination={meta.get('termination')}; not a quality score",
        )

    return score


def _agent(meta: dict) -> str:
    return meta.get("agent") or "claude"


def collect(runs_root: Path, since: str | None) -> dict[tuple[str, int], list[Sample]]:
    groups: dict[tuple[str, int], list[Sample]] = defaultdict(list)
    for run in sorted(runs_root.iterdir()):
        if not run.is_dir() or (since and run.name < since):
            continue
        if not (run / "transcript.jsonl").is_file() or not (run / "meta.json").is_file():
            continue
        meta = json.loads((run / "meta.json").read_text())
        if meta.get("benchmark_id") != "urlquery":
            continue
        prompt = meta.get("prompt") or "unknown-prompt"
        budget = int(meta.get("budget_min") or 0)
        model, replicate = meta.get("model", "?"), meta.get("replicate", 1)
        prompt_file = run / "prompt.txt"
        groups[(prompt, budget)].append(Sample(
            id=f"{model} r{replicate} · {str(meta.get('run_id', run.name))[:6]}",
            input=prompt_file.read_text() if prompt_file.exists() else "",
            metadata={
                "run_dir": str(run),
                "agent": _agent(meta),
                "model": model,
                "replicate": replicate,
                "config": meta.get("config"),
                "prompt": prompt,
                "prompt_sha256": meta.get("prompt_sha256"),
                "budget_min": budget,
                "started": meta.get("started"),
                "termination": meta.get("termination"),
                "report_finalization": meta.get("report_finalization"),
                "report_words": meta.get("report_words"),
                "wall_seconds": meta.get("wall_seconds"),
                "minimum_runtime_reached": meta.get("minimum_runtime_reached"),
            },
        ))
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = primary_root()
    parser.add_argument("--runs", type=Path, default=root / "runs/urlquery")
    parser.add_argument("--out", type=Path, default=root / "logs/urlquery-runs",
                        help="log folder owned by this script; its previous .eval files are replaced")
    parser.add_argument("--since", help="only run directories whose name sorts at or after this (e.g. 20260927T06)")
    parser.add_argument("--no-view", action="store_true", help="build the logs without starting the viewer")
    parser.add_argument("--port", type=int, default=7575)
    args = parser.parse_args()

    groups = collect(args.runs, args.since)
    if not groups:
        print(f"no URLQuery runs found under {args.runs}", file=sys.stderr)
        return 1
    tasks = []
    for (prompt, budget), samples in sorted(groups.items()):
        name = f"{prompt} · {budget} min"
        tasks.append(Task(name=name, dataset=samples, solver=replay(), scorer=run_stats(),
                          metadata={"benchmark": "urlquery", "prompt": prompt, "budget_min": budget,
                                    "mode": "replay (unscored)"}))
        print(f"{name}: {len(samples)} runs")
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.eval"):
        old.unlink()
    eval(tasks, model="mockllm/model", log_dir=str(args.out), display="none", max_tasks=len(tasks))
    print(f"logs: {args.out}")
    if not args.no_view:
        inspect = Path(sys.executable).with_name("inspect")
        return subprocess.call([str(inspect), "view", "--log-dir", str(args.out), "--port", str(args.port)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
