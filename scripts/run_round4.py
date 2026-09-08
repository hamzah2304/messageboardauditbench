#!/usr/bin/env -S uv run python
"""Review, validate, or explicitly execute the declared round-4 matrix."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inspect_ai.log import read_eval_log

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "experiments" / "round4.toml"
RUNNER = ROOT / "scripts" / "run_inspect_matrix.sh"


@dataclass(frozen=True)
class Job:
    system_id: str
    agent: str
    backend: str
    model: str
    budget_minutes: int
    epochs: int
    max_connections: int


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = tomllib.loads(path.read_text())
    required = {
        "name",
        "config",
        "time_limits_minutes",
        "epochs",
        "min_runtime_fraction",
        "logs_dir",
        "systems",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError(f"manifest missing fields: {', '.join(missing)}")
    if data["config"] not in ("blind", "blind-anthropic"):
        raise ValueError("manifests run the blind config or its provider-swap twin blind-anthropic")
    if not 0 <= data["min_runtime_fraction"] < 1:
        raise ValueError("min_runtime_fraction must be in [0, 1)")
    if len({row["id"] for row in data["systems"]}) != len(data["systems"]):
        raise ValueError("system ids must be unique")
    return data


def expand_jobs(manifest: dict[str, Any]) -> list[Job]:
    jobs: list[Job] = []
    default_budgets = manifest["time_limits_minutes"]
    default_epochs = manifest["epochs"]
    for row in manifest["systems"]:
        agent = row["agent"]
        backend = row["backend"]
        if agent in {"claude", "codex"} and backend != "subscription":
            raise ValueError(f"{row['id']}: {agent} must use the subscription backend")
        if agent == "react" and backend != "inspect":
            raise ValueError(f"{row['id']}: ReAct must use the native Inspect backend")
        if agent not in {"claude", "codex", "react"}:
            raise ValueError(f"{row['id']}: unsupported agent {agent!r}")
        max_connections = row["max_connections"]
        if "muse" in row["model"].lower() and max_connections != 2:
            raise ValueError(f"{row['id']}: Muse requires max_connections = 2")
        budgets = row.get("time_limits_minutes", default_budgets)
        epochs = row.get("epochs", default_epochs)
        if any(type(value) is not int or value <= 0 for value in budgets):
            raise ValueError(f"{row['id']}: budgets must be positive integers")
        if type(epochs) is not int or epochs <= 0:
            raise ValueError(f"{row['id']}: epochs must be a positive integer")
        for budget in budgets:
            jobs.append(
                Job(
                    system_id=row["id"],
                    agent=agent,
                    backend=backend,
                    model=row["model"],
                    budget_minutes=budget,
                    epochs=epochs,
                    max_connections=max_connections,
                )
            )
    return jobs


def command(
    manifest: dict[str, Any],
    job: Job,
    max_samples: int | None = None,
    max_sandboxes: int | None = None,
    epochs: int | None = None,
) -> list[str]:
    logs = Path(manifest["logs_dir"]) / job.system_id / f"{job.budget_minutes}m"
    cmd = [
        str(RUNNER),
        "--backend",
        job.backend,
        "--agent",
        job.agent,
        "--config",
        manifest["config"],
        "--time-limit-minutes",
        str(job.budget_minutes),
        "--min-runtime-fraction",
        str(manifest["min_runtime_fraction"]),
        "--epochs",
        str(epochs if epochs is not None else job.epochs),
        "--max-samples",
        str(max_samples if max_samples is not None else manifest["max_samples"]),
        "--max-sandboxes",
        str(max_sandboxes if max_sandboxes is not None else manifest["max_sandboxes"]),
        "--max-connections",
        str(job.max_connections),
        "--max-retries",
        str(manifest["max_retries"]),
        "--request-timeout",
        str(manifest["request_timeout_seconds"]),
        "--attempt-timeout",
        str(manifest["attempt_timeout_seconds"]),
        "--retry-on-error",
        str(manifest["retry_on_error"]),
        "--logs",
        str(logs),
    ]
    if job.backend == "inspect":
        cmd.extend(["--model", job.model])
    else:
        cmd.extend(["--subscription-model", job.model])
    if not manifest["score_during_generation"]:
        cmd.extend(["--", "--no-score"])
    return cmd


def select_jobs(
    jobs: list[Job],
    lane: str,
    system: str | None,
    time_limit_minutes: int | list[int] | None = None,
) -> list[Job]:
    selected = [job for job in jobs if lane == "all" or job.agent == lane]
    if system is not None:
        selected = [job for job in selected if job.system_id == system]
    if time_limit_minutes is not None:
        requested = (
            {time_limit_minutes}
            if isinstance(time_limit_minutes, int)
            else set(time_limit_minutes)
        )
        selected = [job for job in selected if job.budget_minutes in requested]
    if not selected:
        raise ValueError("no jobs match the requested lane/system")
    return selected


def ordered_longest_first(jobs: list[Job]) -> list[Job]:
    """Schedule long cells first to reduce the batch's overall makespan."""
    return sorted(jobs, key=lambda job: job.budget_minutes, reverse=True)


def log_dir(manifest: dict[str, Any], job: Job) -> Path:
    return ROOT / manifest["logs_dir"] / job.system_id / f"{job.budget_minutes}m"


def run_job(
    manifest: dict[str, Any],
    job: Job,
    max_samples: int | None,
    max_sandboxes: int | None,
    epochs: int | None,
    resume_existing: bool = False,
) -> int:
    destination = log_dir(manifest, job)
    existing = (
        sorted(destination.glob("*.eval"), key=lambda path: path.stat().st_mtime)
        if destination.is_dir()
        else []
    )
    if resume_existing and existing:
        current = existing[-1]
        while True:
            try:
                status = read_eval_log(current, header_only=True).status
            except (EOFError, OSError, ValueError):
                status = "started"
            if status != "started":
                print(
                    f"ATTACHED: {job.system_id} {job.budget_minutes}m "
                    f"finished with status {status}"
                )
                return 0 if status == "success" else 1
            print(f"ATTACHED: waiting for {job.system_id} {job.budget_minutes}m")
            time.sleep(30)

    before = set(destination.glob("*.eval")) if destination.is_dir() else set()
    result = subprocess.run(
        command(manifest, job, max_samples, max_sandboxes, epochs),
        cwd=ROOT,
        env=execution_env(),
    )
    if result.returncode:
        return result.returncode

    created = sorted(set(destination.glob("*.eval")) - before)
    if len(created) != 1:
        print(
            f"ERROR: expected one new Inspect log for {job.system_id} "
            f"{job.budget_minutes}m, found {len(created)}",
            file=sys.stderr,
        )
        return 1
    status = read_eval_log(created[0], header_only=True).status
    if status != "success":
        print(
            f"ERROR: {job.system_id} {job.budget_minutes}m log status is {status}",
            file=sys.stderr,
        )
        return 1
    return 0


def readiness(jobs: list[Job]) -> list[str]:
    problems: list[str] = []
    if shutil.which("docker") is None:
        problems.append("docker is not installed")
    if not all(
        (ROOT / "data" / "verbatim" / name).is_file()
        for name in (
            "events.jsonl",
            "labels.jsonl",
            "pages.jsonl",
            "revisions.jsonl",
        )
    ):
        problems.append("data/verbatim is incomplete")
    if any(job.agent == "claude" for job in jobs):
        token = ROOT / "runs" / ".claude-oauth-token"
        copied_login = ROOT / "runs" / ".claude-home" / ".credentials.json"
        host_login = Path.home() / ".claude" / ".credentials.json"
        if (
            not token.is_file()
            and not copied_login.is_file()
            and not host_login.is_file()
        ):
            problems.append("Claude subscription credentials are missing")
    if any(job.agent == "codex" for job in jobs):
        if not (Path.home() / ".codex" / "auth.json").is_file():
            problems.append("Codex subscription credentials are missing")
    openrouter_key_file = ROOT / "runs" / ".openrouter_key"
    saved_openrouter_key = (
        openrouter_key_file.read_text().strip() if openrouter_key_file.is_file() else ""
    )
    if (
        any(job.agent == "react" for job in jobs)
        and not os.environ.get("OPENROUTER_API_KEY")
        and not saved_openrouter_key
    ):
        problems.append("OPENROUTER_API_KEY is missing")
    return problems


def execution_env() -> dict[str, str]:
    """Load the gitignored OpenRouter key for native Inspect without printing it."""
    env = dict(os.environ)
    key_file = ROOT / "runs" / ".openrouter_key"
    if not env.get("OPENROUTER_API_KEY") and key_file.is_file():
        key = key_file.read_text().strip()
        if key:
            env["OPENROUTER_API_KEY"] = key
    return env


def summary(jobs: list[Job]) -> str:
    samples = sum(job.epochs for job in jobs)
    nominal_minutes = sum(job.epochs * job.budget_minutes for job in jobs)
    return (
        f"{len(jobs)} jobs, {samples} samples, "
        f"{nominal_minutes / 60:g} nominal agent-hours"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Round-4 plan. Prints commands unless --execute is explicit."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--lane", choices=["all", "claude", "codex", "react"], default="all"
    )
    parser.add_argument("--system", help="run/print one manifest system id")
    parser.add_argument(
        "--time-limit-minutes",
        type=int,
        action="append",
        help="select a declared time limit; repeat to select more than one",
    )
    parser.add_argument("--check", action="store_true", help="check launch readiness")
    parser.add_argument(
        "--execute", action="store_true", help="actually run selected jobs"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        help="override Inspect sample concurrency for selected jobs",
    )
    parser.add_argument(
        "--max-sandboxes",
        type=int,
        help="override Inspect sandbox concurrency for selected jobs",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        help="override replicate count for each selected job",
    )
    parser.add_argument(
        "--parallel-jobs",
        type=int,
        default=1,
        help="model cells to run concurrently (default: 1)",
    )
    parser.add_argument(
        "--resume-existing",
        action="store_true",
        help="attach to the newest existing log for each cell instead of duplicating it",
    )
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
        jobs = select_jobs(
            expand_jobs(manifest),
            args.lane,
            args.system,
            args.time_limit_minutes,
        )
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))

    for name, value in (
        ("max_samples", args.max_samples),
        ("max_sandboxes", args.max_sandboxes),
        ("epochs", args.epochs),
        ("parallel_jobs", args.parallel_jobs),
    ):
        if value is not None and value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")

    jobs = ordered_longest_first(jobs)
    print(f"{manifest['name']}: {summary(jobs)}")
    for job in jobs:
        print(
            shlex.join(
                command(
                    manifest,
                    job,
                    args.max_samples,
                    args.max_sandboxes,
                    args.epochs,
                )
            )
        )

    if args.check or args.execute:
        problems = readiness(jobs)
        if problems:
            for problem in problems:
                print(f"NOT READY: {problem}", file=sys.stderr)
            return 1
        print("READY: credentials, Docker executable, and verbatim data are present")

    if not args.execute:
        print("DRY RUN: nothing launched (pass --execute explicitly)")
        return 0

    failures: list[tuple[Job, int]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.parallel_jobs
    ) as executor:
        futures = {}
        for index, job in enumerate(jobs, start=1):
            print(f"[{index}/{len(jobs)}] queued {job.system_id} {job.budget_minutes}m")
            future = executor.submit(
                run_job,
                manifest,
                job,
                args.max_samples,
                args.max_sandboxes,
                args.epochs,
                args.resume_existing,
            )
            futures[future] = job
        for future in concurrent.futures.as_completed(futures):
            job = futures[future]
            result = future.result()
            if result:
                failures.append((job, result))
                print(
                    f"FAILED: {job.system_id} {job.budget_minutes}m rc={result}",
                    file=sys.stderr,
                )
            else:
                print(f"DONE: {job.system_id} {job.budget_minutes}m")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
