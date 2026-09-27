"""Plan/launch a small, explicitly unscored subscription pilot on one pinned input.

Uses the existing Docker runner. One lane per subscription; no model calls until
--launch. Plans are exclusive-create artifacts and are never silently resumed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import time
import tomllib
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from messageboard_audit_bench.benchmarks import validate_trial_data
from messageboard_audit_bench.dataset_manifest import file_sha256
from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.urlquery_data import primary_root

MATRIX = [("codex", "gpt-6-astra", 1), ("codex", "gpt-6-sol", 1),
          ("claude", "claude-opus-5-5", 1), ("claude", "claude-opus-5-5", 2)]
OVERRIDES = ("PROMPT", "BUDGET_MIN", "TIMEOUT", "DATA_DIR", "DATA_DIR_OVERRIDE", "EFFORT",
             "MIN_RUNTIME_FRACTION", "MBAB_MIN_RUNTIME_FRACTION", "RESUME_FROM")


def load_matrix(path: Path | None) -> list[tuple[str, str, int]]:
    if path is None:
        return MATRIX
    trials = tomllib.loads(path.read_text()).get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("matrix config requires nonempty [[trials]]")
    result = []
    for row in trials:
        if not isinstance(row, dict) or set(row) != {"agent", "model", "replicate"}:
            raise ValueError("matrix trial requires agent, model, replicate only")
        a, m, r = row["agent"], row["model"], row["replicate"]
        if a not in ("codex", "claude") or not isinstance(m, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", m):
            raise ValueError("invalid matrix agent/model")
        if type(r) is not int or r < 1 or (a, m, r) in result:
            raise ValueError("invalid or duplicate matrix replicate")
        result.append((a, m, r))
    return result


def plan(dataset: Path, agents: list[str] | None = None, models: list[str] | None = None,
         matrix_config: Path | None = None, trial_config: Path | None = None) -> tuple[Path, dict]:
    configured_matrix = load_matrix(matrix_config)
    selected_agents = set(agents) if agents is not None else {"codex", "claude"}
    if not selected_agents or selected_agents - {"codex", "claude"}:
        raise ValueError("pilot agents must be codex and/or claude")
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
    config_source = trial_config or root / "configs/urlquery-10.toml"
    config = config_source.read_text()
    if trial_config is not None and tomllib.loads(config).get("benchmark_id") != "urlquery":
        raise ValueError("pilot config must be for the URLQuery benchmark")
    # Dataset version can change without changing prompt/model/time conditions.
    config = re.sub(r'^data_variant = .*$', f'data_variant = "urlquery/{dataset.name}"', config, flags=re.M)
    config += f'\ndataset_sha256 = "{metadata["dataset_sha256"]}"\n'
    claude_version = tomllib.loads(config).get("claude_cli_version")
    if not isinstance(claude_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", claude_version):
        raise ValueError("claude_cli_version must be an exact numeric version")
    codex_version = tomllib.loads(config).get("codex_cli_version")
    if not isinstance(codex_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", codex_version):
        raise ValueError("codex_cli_version must be an exact numeric version")
    directory.mkdir(parents=True, exist_ok=False)
    config_path = directory / "pilot-config.toml"
    config_path.write_text(config)
    payload = {"experiment_id": experiment, **metadata, "dataset_path": str(dataset),
               "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
               "config": str(config_path), "config_sha256": file_sha256(config_path),
               "matrix": matrix,
               "image": f"mbab-urlquery-sandbox-codex-{codex_version}-claude-{claude_version}",
               "image_build_args": {"CLAUDE_VERSION": claude_version, "CODEX_VERSION": "rust-v" + codex_version},
               "budget_minutes": 10, "outer_guard_seconds": 900, "effort": "medium",
               "status": "planned", "grading": "none"}
    if matrix_config is not None:
        payload["matrix_source"] = str(matrix_config.resolve())
        payload["matrix_source_sha256"] = file_sha256(matrix_config)
    if trial_config is not None:
        payload["trial_config_source"] = str(trial_config.resolve())
        payload["trial_config_source_sha256"] = file_sha256(trial_config)
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    return directory, payload


def launch(directory: Path, payload: dict, parallel_all: bool = False) -> list[dict]:
    root = repo_root()
    payload["parallel_all"] = parallel_all
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    env = {k: v for k, v in os.environ.items() if k not in OVERRIDES}
    env.update(CONFIG=payload["config"], IMAGE=payload["image"])
    build_args = [arg for key, value in sorted(payload["image_build_args"].items())
                  for arg in ("--build-arg", f"{key}={value}")]
    # Build once outside the per-trial guard. The runner rebuild is then cached.
    subprocess.run(["docker", "build", "-q", "-t", env["IMAGE"], *build_args, "-f", "sandbox/docker/Dockerfile", "."], cwd=root, check=True)
    subprocess.run([str(root / ".venv/bin/python"), "scripts/check_urlquery_isolation.py", payload["dataset_path"],
                    "--image", env["IMAGE"], "--output", str(directory / "input-isolation.json")], cwd=root, check=True)

    def lane(trials):
        results = []
        for trial in trials:
            agent, model, replicate = trial["agent"], trial["model"], trial["replicate"]
            log_path = directory / f"{agent}-{model}-r{replicate}.log"
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
            results.append(result)
            (directory / f"{agent}-{model}-r{replicate}.result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)
            # An authentication/capacity failure should not start another run on
            # that subscription. A refusal is an experimental result, not a retry.
            if timed_out or run_meta.get("termination") == "capacity_exhausted" or (rc not in (0, 124, 137) and not run_meta.get("model_refusal")):
                break
        return results

    if parallel_all:
        lanes = [[trial] for trial in payload["matrix"]]
    else:
        agents = list(dict.fromkeys(trial["agent"] for trial in payload["matrix"]))
        lanes = [[trial for trial in payload["matrix"] if trial["agent"] == agent] for agent in agents]
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        results = [row for lane_results in pool.map(lane, lanes) for row in lane_results]
    (directory / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    payload["status"] = "finished" if len(results) == len(payload["matrix"]) else "stopped_with_unlaunched_trials"
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    subprocess.run([str(root / ".venv/bin/python"), "scripts/collect_reports.py", "--benchmark", "urlquery",
                    "--include-partial", "--include-rejected"], cwd=root, check=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--agent", choices=("codex", "claude"), action="append",
                        help="Run only this subscription lane; repeat to include both (default: both)")
    parser.add_argument("--matrix-config", type=Path, help="Explicit TOML [[trials]] matrix; default keeps the original four-run matrix")
    parser.add_argument("--config", type=Path, help="URLQuery trial config; default configs/urlquery-10.toml")
    parser.add_argument("--parallel-all", action="store_true", help="Run every selected trial concurrently")
    parser.add_argument("--model", action="append",
                        help="Select model(s) from the planned matrix without rerunning other models")
    args = parser.parse_args()
    directory, payload = plan(args.dataset, agents=args.agent, models=args.model,
                              matrix_config=args.matrix_config, trial_config=args.config)
    print(json.dumps({"plan": str(directory / "plan.json"), "launch": args.launch}), flush=True)
    if args.launch:
        launch(directory, payload, parallel_all=args.parallel_all)


if __name__ == "__main__":
    main()
