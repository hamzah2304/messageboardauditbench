#!/usr/bin/env -S uv run python
"""Review, validate, or explicitly execute the declared round-4 matrix."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    if data["config"] != "blind":
        raise ValueError("round 4 is declared as a blind-only experiment")
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
        str(job.epochs),
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
    time_limit_minutes: int | None = None,
) -> list[Job]:
    selected = [job for job in jobs if lane == "all" or job.agent == lane]
    if system is not None:
        selected = [job for job in selected if job.system_id == system]
    if time_limit_minutes is not None:
        selected = [
            job for job in selected if job.budget_minutes == time_limit_minutes
        ]
    if not selected:
        raise ValueError("no jobs match the requested lane/system")
    return selected


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
        help="select only jobs with this declared time limit",
    )
    parser.add_argument("--check", action="store_true", help="check launch readiness")
    parser.add_argument(
        "--execute", action="store_true", help="actually run selected jobs sequentially"
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
    ):
        if value is not None and value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")

    print(f"{manifest['name']}: {summary(jobs)}")
    for job in jobs:
        print(
            shlex.join(
                command(manifest, job, args.max_samples, args.max_sandboxes)
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

    for index, job in enumerate(jobs, start=1):
        print(f"[{index}/{len(jobs)}] launching {job.system_id} {job.budget_minutes}m")
        result = subprocess.run(
            command(manifest, job, args.max_samples, args.max_sandboxes),
            cwd=ROOT,
            env=execution_env(),
        )
        if result.returncode:
            print(
                f"STOPPED: {job.system_id} {job.budget_minutes}m exited "
                f"{result.returncode}",
                file=sys.stderr,
            )
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
