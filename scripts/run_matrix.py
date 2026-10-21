#!/usr/bin/env python3
"""Run the standard condition: lineup x evals x budgets x replicates, no retries.

    uv run python scripts/run_matrix.py --plan                          # list the trials and how many exist
    uv run python scripts/run_matrix.py --runs 5                        # run everything still missing
    uv run python scripts/run_matrix.py --evals aivillage --budgets 30 --models gpt-6-luna,claude-haiku-5-5 --runs 2

Every trial is sandbox/docker/run_trial.sh <harness> <model> <replicate> with CONFIG set to the
standard config (configs/standard.toml). A trial whose run directory already exists is skipped,
whatever its outcome: a failed run is a result, never retried (slopvestigator_bench/eligibility.py
says why it does not count). Trials are ordered replicate first, so each replicate is spread over
the whole batch instead of one replicate landing on one machine state.

Machine and concurrency: the rerun runs on one machine (the VM) at a low fixed concurrency, so
host load stays the same through the batch; wall time is not a constraint. --max-parallel trials at
once overall (default 3); each run records the concurrency at its launch and the host's load
averages at start and end (meta.json host_load). Claude trials alternate over --claude-tokens
(one OAuth token file per account) with at most --per-account in flight on each; Codex trials share
the one Codex login with at most --per-account in flight; ReAct trials (OpenRouter) are uncapped
beyond --max-parallel. Logs go to logs/matrix/<stamp>/.
"""

from __future__ import annotations

import argparse
import itertools
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopvestigator_bench import lineup, standard  # noqa: E402
from slopvestigator_bench.benchmarks import SPECS, primary_root  # noqa: E402


def trials(evals, budgets, models, runs):
    """(replicate, eval, budget, model) in replicate-major order."""
    return [(rep, ev, b, m) for rep in range(1, runs + 1) for ev in evals for b in budgets for m in models]


def existing(run_root: Path, model: lineup.Model, config: str, rep: int) -> list[Path]:
    slug = model.id.replace("/", "_")
    return sorted(p for p in run_root.glob(f"*_{model.harness}_{slug}_r{rep}_{config}_*") if finished(p))


def finished(run_dir: Path) -> bool:
    """The trial reached the model (it may still be running, or have died after). Such a run is a
    result and is never launched again. A launch that died before the model produced anything
    (credentials, preflight, an interrupted start) may be launched again."""
    meta = run_dir / "meta.json"
    if meta.is_file() and '"exit_code"' in meta.read_text():
        return True
    return reached_model(run_dir)


def reached_model(run_dir: Path) -> bool:
    """The agent produced output: a non-empty transcript (whole, or a part still being written).
    The runner logs cli_started just before docker run, so that event alone does not prove it."""
    return any(p.stat().st_size > 0 for p in run_dir.glob("transcript*.jsonl"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evals", default=",".join(standard.benchmark_ids()))
    ap.add_argument("--budgets", default=",".join(str(b) for b in standard.standard()["shared"]["budgets"]))
    ap.add_argument("--models", default="", help="comma-separated lineup ids (default: the whole lineup)")
    ap.add_argument("--runs", type=int, default=5, help="replicates per cell")
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--per-account", type=int, default=3)
    ap.add_argument("--claude-tokens", default="runs/.claude-oauth-token,runs/.claude-oauth-token.acct2")
    ap.add_argument("--plan", action="store_true", help="print the trials and stop")
    args = ap.parse_args()

    evals = args.evals.split(",")
    for ev in evals:
        if ev not in standard.benchmark_ids():
            raise SystemExit(f"unknown eval {ev!r}; choose from {standard.benchmark_ids()}")
    budgets = [int(b) for b in args.budgets.split(",")]
    models = [lineup.model(m) for m in args.models.split(",")] if args.models else list(lineup.models())
    primary = primary_root()
    todo, done = [], 0
    for rep, ev, budget, model in trials(evals, budgets, models, args.runs):
        config = standard.config_name(ev, budget)
        if existing(primary / SPECS[ev].run_root, model, config, rep):
            done += 1
        else:
            todo.append((rep, ev, budget, model, config))
    by_harness = {h: sum(1 for t in todo if t[3].harness == h) for h in lineup.HARNESSES}
    print(f"{done} trials already exist; {len(todo)} to run {by_harness}", flush=True)
    if args.plan:
        for rep, ev, budget, model, config in todo:
            print(f"  r{rep} {config:18} {model.harness:6} {model.id}")
        return 0

    tokens = [t for t in args.claude_tokens.split(",") if (ROOT / t).is_file()]
    if any(t[3].harness == "claude" for t in todo) and not tokens:
        raise SystemExit("no Claude token file found; see --claude-tokens")
    logs = ROOT / "logs" / "matrix" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logs.mkdir(parents=True, exist_ok=True)
    awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())]) if platform.system() == "Darwin" else None
    account = itertools.cycle(tokens or [""])
    running: list[tuple[subprocess.Popen, str]] = []  # (process, lane)

    def lane_count(lane):
        return sum(1 for p, ln in running if ln == lane and p.poll() is None)

    pending = list(todo)
    try:
        while pending or running:
            running = [(p, ln) for p, ln in running if p.poll() is None]
            for item in list(pending):
                if len(running) >= args.max_parallel:
                    break
                rep, ev, budget, model, config = item
                env = {**os.environ, "CONFIG": f"configs/{config}.toml",
                       "MBAB_BATCH_CONCURRENCY": str(len(running) + 1), "MBAB_BATCH_MAX_PARALLEL": str(args.max_parallel)}
                lane = model.harness
                if model.harness == "claude":
                    token = next(account)
                    lane = f"claude:{token}"
                    if lane_count(lane) >= args.per_account:
                        continue
                    env["MBAB_CLAUDE_TOKEN_FILE"] = token
                elif model.harness == "codex" and lane_count(lane) >= args.per_account:
                    continue
                log = logs / f"r{rep}_{config}_{model.id.replace('/', '_')}.log"
                cmd = ["sandbox/docker/run_trial.sh", model.harness, model.id, str(rep)]
                proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
                running.append((proc, lane))
                pending.remove(item)
                print(f"{datetime.now(UTC):%H:%M:%S} start r{rep} {config} {model.id}", flush=True)
                time.sleep(20)  # stagger container and proxy start-up
            time.sleep(10)
    finally:
        if awake:
            awake.terminate()
    print(f"finished; logs in {logs.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
