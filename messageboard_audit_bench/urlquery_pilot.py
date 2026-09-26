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


def plan(dataset: Path) -> tuple[Path, dict]:
    dataset = dataset.resolve()
    metadata = validate_trial_data("urlquery", dataset)
    root, shared = repo_root(), primary_root()
    expected = shared / "data/urlquery" / metadata["dataset_version"]
    if dataset != expected:
        raise ValueError("pilot input must be the primary checkout's frozen URLQuery snapshot")
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    experiment = "pilot-" + stamp + "-" + uuid.uuid4().hex[:8]
    directory = shared / "runs/urlquery" / experiment
    directory.mkdir(parents=True, exist_ok=False)
    config = (root / "configs/urlquery-10.toml").read_text()
    # Dataset version can change without changing prompt/model/time conditions.
    config = re.sub(r'^data_variant = .*$', f'data_variant = "urlquery/{dataset.name}"', config, flags=re.M)
    config += f'\ndataset_sha256 = "{metadata["dataset_sha256"]}"\n'
    config_path = directory / "pilot-config.toml"
    config_path.write_text(config)
    payload = {"experiment_id": experiment, **metadata, "dataset_path": str(dataset),
               "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
               "config": str(config_path), "config_sha256": file_sha256(config_path),
               "matrix": [{"agent": a, "model": m, "replicate": r} for a, m, r in MATRIX],
               "budget_minutes": 10, "outer_guard_seconds": 900, "effort": "medium",
               "status": "planned", "grading": "none"}
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    return directory, payload


def launch(directory: Path, payload: dict) -> list[dict]:
    root = repo_root()
    env = {k: v for k, v in os.environ.items() if k not in OVERRIDES}
    env.update(CONFIG=payload["config"], IMAGE="mbab-urlquery-sandbox")
    # Build once outside the per-trial guard. The runner rebuild is then cached.
    subprocess.run(["docker", "build", "-q", "-t", env["IMAGE"], "-f", "sandbox/docker/Dockerfile", "."], cwd=root, check=True)
    subprocess.run([str(root / ".venv/bin/python"), "scripts/check_urlquery_isolation.py", payload["dataset_path"],
                    "--image", env["IMAGE"], "--output", str(directory / "input-isolation.json")], cwd=root, check=True)

    def lane(agent):
        results = []
        for selected, model, replicate in MATRIX:
            if selected != agent:
                continue
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

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [row for lane_results in pool.map(lane, ("codex", "claude")) for row in lane_results]
    (directory / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    payload["status"] = "finished" if len(results) == len(MATRIX) else "stopped_with_unlaunched_trials"
    (directory / "plan.json").write_text(json.dumps(payload, indent=2) + "\n")
    subprocess.run([str(root / ".venv/bin/python"), "scripts/collect_reports.py", "--benchmark", "urlquery",
                    "--include-partial", "--include-rejected"], cwd=root, check=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    directory, payload = plan(args.dataset)
    print(json.dumps({"plan": str(directory / "plan.json"), "launch": args.launch}), flush=True)
    if args.launch:
        launch(directory, payload)


if __name__ == "__main__":
    main()
