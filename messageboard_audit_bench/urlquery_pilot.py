"""Plan/launch URLQuery subscription trials in batches on one pinned input.

The batch launcher for the `transluce_report` benchmark. Every trial goes through
the shared Docker runner (sandbox/docker/run_trial.sh), exactly as the Inspect task's
subscription backend does; this module adds what a large matrix needs on top: one
lane or queue per subscription, a stop on authentication/capacity failure for that
subscription, fail-closed validation of each run's record, and a plan.json per arm
that the batch grader (benchmarks/urlquery/judge/grade.py --batch/--launch) reads.

No model calls until --launch. Plans are exclusive-create artifacts and are never
silently resumed. `--batch` plans several configs (prompt/budget arms) at once and
runs all their trials from one queue with a fixed number in flight. Grade the results
with the batch grader or the `transluce_report_grade` Inspect task.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from messageboard_audit_bench.benchmarks import (
    default_config,
    primary_root,
    urlquery_dataset_dir,
    validate_trial_data,
)
from messageboard_audit_bench.configs import validate_config
from messageboard_audit_bench.dataset_manifest import file_sha256
from messageboard_audit_bench.runtime import repo_root

MATRIX = [("codex", "gpt-6-astra", 1), ("codex", "gpt-6-sol", 1),
          ("claude", "claude-opus-5-5", 1), ("claude", "claude-opus-5-5", 2)]
AGENTS = ("codex", "claude", "react")
# ReAct models are OpenRouter ids such as google/gemini-3.8-flash.
MODEL_ID = re.compile(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)?")
OVERRIDES = ("PROMPT", "BUDGET_MIN", "TIMEOUT", "DATA_DIR", "DATA_DIR_OVERRIDE", "EFFORT",
             "MIN_RUNTIME_FRACTION", "MBAB_MIN_RUNTIME_FRACTION", "RESUME_FROM")


def load_matrix(path: Path | None) -> list[tuple[str, str, int]]:
    if path is None:
        return MATRIX
    return validate_matrix(tomllib.loads(path.read_text()).get("trials"))


def validate_matrix(trials) -> list[tuple[str, str, int]]:
    if not isinstance(trials, list) or not trials:
        raise ValueError("matrix config requires nonempty [[trials]]")
    result = []
    for row in trials:
        if not isinstance(row, dict) or set(row) != {"agent", "model", "replicate"}:
            raise ValueError("matrix trial requires agent, model, replicate only")
        a, m, r = row["agent"], row["model"], row["replicate"]
        if a not in AGENTS or not isinstance(m, str) or not MODEL_ID.fullmatch(m):
            raise ValueError("invalid matrix agent/model")
        if type(r) is not int or r < 1 or (a, m, r) in result:
            raise ValueError("invalid or duplicate matrix replicate")
        result.append((a, m, r))
    return result


def plan(dataset: Path, agents: list[str] | None = None, models: list[str] | None = None,
         matrix_config: Path | None = None, trial_config: Path | None = None,
         trials: list[tuple[str, str, int]] | None = None) -> tuple[Path, dict]:
    configured_matrix = validate_matrix([{"agent": a, "model": m, "replicate": r} for a, m, r in trials]) \
        if trials is not None else load_matrix(matrix_config)
    selected_agents = set(agents) if agents is not None else set(AGENTS)
    if not selected_agents or selected_agents - set(AGENTS):
        raise ValueError("pilot agents must be codex, claude and/or react")
    known_models = {model for _, model, _ in configured_matrix}
    selected_models = set(models) if models is not None else known_models
    if not selected_models or selected_models - known_models:
        raise ValueError("pilot models must come from the configured matrix")
    matrix = [{"agent": a, "model": m, "replicate": r}
              for a, m, r in configured_matrix if a in selected_agents and m in selected_models]
    if not matrix:
        raise ValueError("agent/model filters select no trials")
    dataset = dataset.resolve()
    metadata = validate_trial_data("urlquery", dataset)
    root, shared = repo_root(), primary_root()
    expected = shared / "data/urlquery" / metadata["dataset_version"]
    if dataset != expected:
        raise ValueError("pilot input must be the primary checkout's frozen URLQuery snapshot")
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    experiment = "pilot-" + stamp + "-" + uuid.uuid4().hex[:8]
    directory = shared / "runs/urlquery" / experiment
    config_source = trial_config or root / "configs" / f"{default_config('urlquery')}.toml"
    config = config_source.read_text()
    if trial_config is not None and tomllib.loads(config).get("benchmark_id") != "urlquery":
        raise ValueError("pilot config must be for the URLQuery benchmark")
    # Dataset version can change without changing prompt/model/time conditions.
    config = re.sub(r'^data_variant = .*$', f'data_variant = "urlquery/{dataset.name}"', config, flags=re.M)
    config = re.sub(r'^dataset_sha256 = .*\n?', '', config, flags=re.M)
    config += f'\ndataset_sha256 = "{metadata["dataset_sha256"]}"\n'
    claude_version = tomllib.loads(config).get("claude_cli_version")
    if not isinstance(claude_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", claude_version):
        raise ValueError("claude_cli_version must be an exact numeric version")
    codex_version = tomllib.loads(config).get("codex_cli_version")
    if not isinstance(codex_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", codex_version):
        raise ValueError("codex_cli_version must be an exact numeric version")
    cfg = tomllib.loads(config)
    if dataset.resolve() == urlquery_dataset_dir().resolve():
        # The benchmark's own snapshot: hold the config to the manifest's pins.
        validate_config(cfg, "urlquery")
    budget_min, timeout_min = cfg.get("budget_min", 10), cfg.get("timeout_min", 15)
    if type(budget_min) is not int or type(timeout_min) is not int or not 0 < budget_min < timeout_min:
        raise ValueError("config needs integer budget_min < timeout_min")
    directory.mkdir(parents=True, exist_ok=False)
    config_path = directory / "pilot-config.toml"
    config_path.write_text(config)
    payload = {"experiment_id": experiment, **metadata, "dataset_path": str(dataset),
               "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
               "config": str(config_path), "config_sha256": file_sha256(config_path),
               "matrix": matrix,
               "image": f"mbab-urlquery-sandbox-codex-{codex_version}-claude-{claude_version}",
               "image_build_args": {"CLAUDE_VERSION": claude_version, "CODEX_VERSION": "rust-v" + codex_version},
               "budget_minutes": budget_min, "outer_guard_seconds": timeout_min * 60,
               "effort": cfg.get("effort", "medium"),
               "status": "planned", "grading": "none"}
    if matrix_config is not None:
        payload["matrix_source"] = str(matrix_config.resolve())
        payload["matrix_source_sha256"] = file_sha256(matrix_config)
    if trial_config is not None:
        payload["trial_config_source"] = str(trial_config.resolve())
        payload["trial_config_source_sha256"] = file_sha256(trial_config)
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    return directory, payload


def _prepare(directory: Path, payload: dict) -> dict:
    """Build the pinned image and check input isolation; return the runner env."""
    root = repo_root()
    env = {k: v for k, v in os.environ.items() if k not in OVERRIDES}
    env.update(CONFIG=payload["config"], IMAGE=payload["image"])
    build_args = [arg for key, value in sorted(payload["image_build_args"].items())
                  for arg in ("--build-arg", f"{key}={value}")]
    # Build once outside the per-trial guard. The runner rebuild is then cached.
    subprocess.run(["docker", "build", "-q", "-t", env["IMAGE"], *build_args, "-f", "sandbox/docker/Dockerfile", "."], cwd=root, check=True)
    subprocess.run([str(root / ".venv/bin/python"), "scripts/check_urlquery_isolation.py", payload["dataset_path"],
                    "--image", env["IMAGE"], "--output", str(directory / "input-isolation.json")], cwd=root, check=True)
    return env


def _run_trial(directory: Path, payload: dict, env: dict, trial: dict) -> tuple[dict, bool]:
    """Run one trial; return its result and whether its lane should stop."""
    root = repo_root()
    agent, model, replicate = trial["agent"], trial["model"], trial["replicate"]
    stem = f"{agent}-{model.replace('/', '_')}-r{replicate}"
    log_path = directory / f"{stem}.log"
    started = time.time()
    timed_out = False
    with log_path.open("w") as log:
        process = subprocess.Popen(["bash", str(root / "sandbox/docker/run_trial.sh"), agent, model, str(replicate)],
                                   cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            rc = process.wait(timeout=payload["outer_guard_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                rc = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                rc = process.wait()
    lines = log_path.read_text(errors="replace").splitlines()
    paths = [line.removeprefix("run: ") for line in lines if line.startswith("run: ")]
    run = Path(paths[0]).resolve() if paths else None
    run_meta = {}
    if run and (run / "meta.json").is_file():
        run_meta = json.loads((run / "meta.json").read_text())
    if timed_out and run:
        # Only clean this launch's explicit UUID-named resources. Never
        # remove a network/container merely because it has our prefix.
        run_id = str(run_meta.get("run_id", ""))
        if run.parent != directory.parent or not re.fullmatch(r"[a-f0-9]{32}", run_id) or run_id[:12] not in run.name:
            raise ValueError("cannot safely identify timed-out trial resources")
        subprocess.run(["docker", "rm", "-f", f"mbab-agent-{run_id}", f"mbab-proxy-{run_id}"], capture_output=True)
        subprocess.run(["docker", "network", "rm", f"mbab-inner-{run_id}"], capture_output=True)
        secrets = run / ".secrets"
        if secrets.is_dir() and not secrets.is_symlink():
            shutil.rmtree(secrets)
    result = {"agent": agent, "requested_model": model, "replicate": replicate,
              "runner_returncode": rc, "outer_timeout": timed_out,
              "elapsed_seconds": round(time.time() - started, 2),
              "run_dir": str(run) if run else None, "launch_log": str(log_path),
              "termination": run_meta.get("termination"), "report_exists": run_meta.get("report_exists", False)}
    if run_meta and run_meta.get("benchmark_id") not in (None, "urlquery"):
        raise ValueError("runner returned wrong benchmark")
    if run_meta.get("dataset_sha256") and run_meta["dataset_sha256"] != payload["dataset_sha256"]:
        raise ValueError("runner returned wrong dataset")
    # The CLI hooks are a first line of enforcement, not proof that the run
    # satisfied the policy. Fail closed on a purported normal completion.
    validation_errors = []
    if run_meta.get("termination") == "normal" and not run_meta.get("model_refusal"):
        if run_meta.get("minimum_runtime_reached") is False:
            validation_errors.append("minimum_runtime_not_reached")
        elif run_meta.get("minimum_runtime_seconds", 0) > 0 and run_meta.get("minimum_runtime_reached") is not True:
            validation_errors.append("minimum_runtime_unverified")
    if run_meta.get("usage", {}).get("is_error") is True and not run_meta.get("model_refusal"):
        validation_errors.append("provider_error")
    result["minimum_runtime_reached"] = run_meta.get("minimum_runtime_reached")
    result["validation_errors"] = validation_errors
    (directory / f"{stem}.result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    # An authentication/capacity failure should not start another run on
    # that subscription. A refusal is an experimental result, not a retry.
    stop = bool(validation_errors) or timed_out or run_meta.get("termination") == "capacity_exhausted" or (
        rc not in (0, 124, 137) and not run_meta.get("model_refusal"))
    return result, stop


def _finish(directory: Path, payload: dict, results: list[dict]) -> None:
    (directory / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    payload["status"] = "finished" if len(results) == len(payload["matrix"]) else "stopped_with_unlaunched_trials"
    if payload["status"] == "finished" and any(
        row.get("validation_errors") or row.get("outer_timeout")
        or row.get("termination") in {"error", "capacity_exhausted"}
        for row in results
    ):
        payload["status"] = "finished_with_errors"
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")


def _collect_reports() -> None:
    subprocess.run([str(repo_root() / ".venv/bin/python"), "scripts/collect_reports.py", "--benchmark", "urlquery",
                    "--include-partial", "--include-rejected"], cwd=repo_root(), check=True)


def launch(directory: Path, payload: dict, parallel_all: bool = False) -> list[dict]:
    payload["parallel_all"] = parallel_all
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    env = _prepare(directory, payload)

    def lane(trials):
        results = []
        for trial in trials:
            result, stop = _run_trial(directory, payload, env, trial)
            results.append(result)
            if stop:
                break
        return results

    if parallel_all:
        lanes = [[trial] for trial in payload["matrix"]]
    else:
        agents = list(dict.fromkeys(trial["agent"] for trial in payload["matrix"]))
        lanes = [[trial for trial in payload["matrix"] if trial["agent"] == agent] for agent in agents]
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        results = [row for lane_results in pool.map(lane, lanes) for row in lane_results]
    _finish(directory, payload, results)
    _collect_reports()
    return results


def load_batch(path: Path) -> tuple[int, list[dict]]:
    """Read a batch file: max_parallel plus [[arms]] of config, replicates, models."""
    batch = tomllib.loads(path.read_text())
    max_parallel = batch.get("max_parallel")
    arms = batch.get("arms")
    if type(max_parallel) is not int or max_parallel < 1 or not isinstance(arms, list) or not arms:
        raise ValueError("batch needs max_parallel >= 1 and nonempty [[arms]]")
    parsed = []
    for arm in arms:
        if not isinstance(arm, dict) or set(arm) != {"config", "replicates", "models"}:
            raise ValueError("batch arm requires config, replicates, models only")
        reps, models = arm["replicates"], arm["models"]
        if type(reps) is not int or reps < 1 or not isinstance(models, list) or not models:
            raise ValueError("batch arm needs replicates >= 1 and nonempty models")
        pairs = [tuple(m.split(":", 1)) if isinstance(m, str) and ":" in m else (None, m) for m in models]
        # Replicate-major order, so one model's copies do not all start together.
        trials = validate_matrix([{"agent": a, "model": m, "replicate": r}
                                  for r in range(1, reps + 1) for a, m in pairs])
        config = (repo_root() / arm["config"]).resolve()
        if not config.is_file():
            raise ValueError(f"batch config not found: {arm['config']}")
        parsed.append({"config": config, "trials": trials})
    return max_parallel, parsed


def plan_batch(dataset: Path, path: Path) -> tuple[int, list[tuple[Path, dict]]]:
    max_parallel, arms = load_batch(path)
    plans = [plan(dataset, trial_config=arm["config"], trials=arm["trials"]) for arm in arms]
    for directory, payload in plans:
        payload["batch_source"] = str(path.resolve())
        payload["batch_source_sha256"] = file_sha256(path)
        (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    return max_parallel, plans


def launch_batch(plans: list[tuple[Path, dict]], max_parallel: int) -> list[dict]:
    """Run every arm's trials from one queue with at most `max_parallel` in flight.

    Longer-budget arms start first; the rest interleave across arms. A stop
    condition blocks further launches for that subscription (or that ReAct
    model) across all arms, as a lane stop does in `launch`.
    """
    envs = {}
    for directory, payload in plans:
        payload["batch_max_parallel"] = max_parallel
        (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
        envs[directory] = _prepare(directory, payload)
    ordered = sorted(plans, key=lambda item: -item[1]["budget_minutes"])
    queues = [[(directory, payload, trial) for trial in payload["matrix"]] for directory, payload in ordered]
    long_budget = ordered[0][1]["budget_minutes"]
    queue = [job for q in queues if q[0][1]["budget_minutes"] == long_budget for job in q]
    rest = [q for q in queues if q[0][1]["budget_minutes"] != long_budget]
    while any(rest):
        for q in rest:
            if q:
                queue.append(q.pop(0))
    blocked: set[str] = set()
    lock = threading.Lock()
    results: dict[Path, list[dict]] = {directory: [] for directory, _ in plans}

    def key(trial):
        return trial["model"] if trial["agent"] == "react" else trial["agent"]

    def worker(job):
        directory, payload, trial = job
        with lock:
            if key(trial) in blocked:
                return
        result, stop = _run_trial(directory, payload, envs[directory], trial)
        with lock:
            results[directory].append(result)
            if stop:
                blocked.add(key(trial))

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        list(pool.map(worker, queue))
    for directory, payload in plans:
        _finish(directory, payload, results[directory])
    _collect_reports()
    return [row for rows in results.values() for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=None,
                        help="frozen snapshot directory (default: the manifest's pinned snapshot)")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--agent", choices=AGENTS, action="append",
                        help="Run only this lane; repeat to include several (default: all in the matrix)")
    parser.add_argument("--matrix-config", type=Path, help="Explicit TOML [[trials]] matrix; default keeps the original four-run matrix")
    parser.add_argument("--config", type=Path, help="URLQuery trial config; default the manifest's default config")
    parser.add_argument("--parallel-all", action="store_true", help="Run every selected trial concurrently")
    parser.add_argument("--batch", type=Path, help="Batch TOML: several config arms run from one queue")
    parser.add_argument("--model", action="append",
                        help="Select model(s) from the planned matrix without rerunning other models")
    args = parser.parse_args()
    args.dataset = args.dataset or urlquery_dataset_dir()
    if args.batch:
        if args.agent or args.model or args.matrix_config or args.config or args.parallel_all:
            parser.error("--batch takes its configs and models from the batch file")
        max_parallel, plans = plan_batch(args.dataset, args.batch)
        print(json.dumps({"plans": [str(d / "plan.json") for d, _ in plans], "max_parallel": max_parallel,
                          "trials": sum(len(p["matrix"]) for _, p in plans), "launch": args.launch}), flush=True)
        if args.launch:
            launch_batch(plans, max_parallel)
            return int(any(p["status"] != "finished" for _, p in plans))
        return 0
    directory, payload = plan(args.dataset, agents=args.agent, models=args.model,
                              matrix_config=args.matrix_config, trial_config=args.config)
    print(json.dumps({"plan": str(directory / "plan.json"), "launch": args.launch}), flush=True)
    if args.launch:
        launch(directory, payload, parallel_all=args.parallel_all)
        return int(payload["status"] != "finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
