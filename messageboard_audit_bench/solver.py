"""Solvers that run a coding-agent CLI in the sandbox, or replay a finished run.

`subscription_agent(...)` launches sandbox/docker/run_trial.sh, then folds the
CLI's transcript and the report it wrote into Inspect state, so `inspect view`
renders the whole session and the scorers see the report as the completion.

`replay(...)` does the same for runs already on disk under runs/, so you can
bring past baseline runs into Inspect without re-running the models.
"""

from __future__ import annotations

import json
import shutil
import asyncio
import subprocess
from pathlib import Path

from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.solver import Generate, Solver, TaskState, solver

from messageboard_audit_bench.report_length import acceptance_limits, limits, measure
from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.transcripts import Parsed, parse

REFUSAL_RERUN_LIMIT = 2
TIMEOUT_GRACE_MINUTES = 5


def _output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _run_dir_from_output(output: str) -> Path | None:
    found = None
    for line in output.splitlines():
        if line.startswith("run: "):
            found = Path(line[5:].strip())
    return found


def _cleanup_interrupted_run(run_dir: Path) -> None:
    """Remove runner resources and credentials after a killed shell."""
    try:
        meta = json.loads((run_dir / "meta.json").read_text())
        run_id = str(meta["run_id"])
    except (OSError, KeyError, json.JSONDecodeError):
        run_id = ""
    if run_id:
        for command in (
            ["docker", "rm", "-f", f"mbab-agent-{run_id}", f"mbab-proxy-{run_id}"],
            ["docker", "network", "rm", f"mbab-inner-{run_id}"],
        ):
            try:
                subprocess.call(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    for name in ("report.md", "final_message.md"):
        source = run_dir / "work" / name
        destination = run_dir / name
        if source.exists() and not destination.exists():
            shutil.copyfile(source, destination)
    secrets = run_dir / ".secrets"
    if secrets.is_dir():
        shutil.rmtree(secrets)


def _fold(state: TaskState, run_dir: Path, agent: str) -> TaskState:
    parsed: Parsed = parse(agent, run_dir / "transcript.jsonl")
    state.messages = state.messages + parsed.messages

    report_path = run_dir / "report.md"
    report = report_path.read_text(errors="replace") if report_path.exists() else ""
    report_source = report_path if report else None
    fallback_path = run_dir / "final_message.md"
    if not report and agent == "codex" and fallback_path.exists():
        report = fallback_path.read_text(errors="replace")
        report_source = fallback_path if report else None

    usage = ModelUsage(
        # Inspect defines input_tokens as the uncached/full-rate subset; its
        # cache fields are disjoint. Benchmark metadata below also retains the
        # cache-inclusive total for straightforward cache-rate analysis.
        input_tokens=parsed.input_tokens_uncached,
        output_tokens=parsed.output_tokens,
        total_tokens=parsed.input_tokens + parsed.output_tokens,
        input_tokens_cache_read=parsed.cache_read_tokens or None,
        input_tokens_cache_write=parsed.cache_write_tokens or None,
        reasoning_tokens=parsed.reasoning_tokens or None,
        total_cost=parsed.cost_usd,
    )
    state.output = ModelOutput.from_content(
        model=agent, content=report or "(no report written)"
    )
    state.output.usage = usage

    meta = {}
    if (run_dir / "meta.json").exists():
        meta = json.loads((run_dir / "meta.json").read_text())
    state.metadata.update(
        agent=agent,
        run_dir=str(run_dir),
        report_written=bool(report),
        report_chars=len(report),
        report_source=str(report_source) if report_source else None,
        turns=parsed.turns,
        tool_calls=parsed.tool_calls,
        input_tokens=parsed.input_tokens,
        input_tokens_uncached=parsed.input_tokens_uncached,
        output_tokens=parsed.output_tokens,
        cache_read_tokens=parsed.cache_read_tokens,
        cache_write_tokens=parsed.cache_write_tokens,
        cache_read_fraction=parsed.extra.get("cache_read_fraction"),
        usage_schema=parsed.extra.get("usage_schema"),
        reasoning_tokens=parsed.reasoning_tokens,
        cost_usd=parsed.cost_usd,
        wall_seconds=meta.get("wall_seconds"),
        config=meta.get("config", meta.get("condition", meta.get("prompt"))),
        prompt=meta.get("prompt"),
        budget_min=meta.get("budget_min"),
        min_runtime_fraction=meta.get("min_runtime_fraction"),
        minimum_runtime_seconds=meta.get("minimum_runtime_seconds"),
        minimum_runtime_reached=meta.get("minimum_runtime_reached"),
        early_stop_attempts=meta.get("early_stop_attempts", 0),
        data_variant=meta.get("data_variant"),
        effort=meta.get("effort"),
        exit_code=meta.get("exit_code"),
        replicate=meta.get("replicate", meta.get("seed")),
        run_id=meta.get("run_id"),
        cli_version=meta.get("cli_version"),
        model=meta.get("model"),
        model_served=meta.get("model_served", meta.get("model")),
        model_fallback=meta.get("model_fallback"),
        terminal_refusal=bool(meta.get("model_refusal")),
        transcript_diagnostics=parsed.extra.get("transcript_diagnostics"),
        **{
            f"cli_{k}": v
            for k, v in parsed.extra.items()
            if isinstance(v, (str, int, float))
        },
    )
    state.metadata.update(
        measure(
            report,
            *limits(meta),
            exists=report_source is not None,
            acceptance=acceptance_limits(meta),
        )
    )
    state.completed = True
    return state


@solver
def subscription_agent(
    agent: str,
    model: str,
    config: str = "blind",
    time_limit_minutes: int | None = None,
    timeout_minutes: int | None = None,
    prompt: str | None = None,
    data_variant: str | None = None,
    effort: str | None = None,
    min_runtime_fraction: float = 0.75,
) -> Solver:
    """Launch a fresh sandbox trial, then fold its transcript into state."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        repo = repo_root()
        replicate = state.epoch
        cmd = [
            str(repo / "sandbox" / "docker" / "run_trial.sh"),
            agent,
            model,
            str(replicate),
        ]
        env = {"CONFIG": config}
        if prompt is not None:
            env["PROMPT"] = prompt
        if data_variant is not None:
            env["DATA_DIR"] = str(repo / "data" / data_variant)
        if effort is not None:
            env["EFFORT"] = effort
        if time_limit_minutes is not None:
            env["BUDGET_MIN"] = str(time_limit_minutes)
        if timeout_minutes is not None:
            env["TIMEOUT"] = f"{timeout_minutes}m"
        # The runner derives its absolute earliest-finish timestamp from its
        # actual container start, alongside its deadline. Computing one here
        # would incorrectly charge image build/canary time to the agent.
        env["MBAB_MIN_RUNTIME_FRACTION"] = str(min_runtime_fraction)
        run_dirs: list[Path] = []
        proc = None
        run_dir = None
        for refusal_attempt in range(REFUSAL_RERUN_LIMIT + 1):
            # Await the runner instead of blocking the event loop: a blocking subprocess.run here made
            # every sample of an eval run one at a time whatever --max-samples said.
            try:
                proc = await _run_async(
                    cmd,
                    cwd=repo,
                    env={**_os_environ(), **env},
                    timeout=(timeout_minutes + TIMEOUT_GRACE_MINUTES) * 60
                    if timeout_minutes is not None
                    else None,
                )
            except subprocess.TimeoutExpired as ex:
                stdout = _output_text(ex.stdout)
                stderr = _output_text(ex.stderr)
                interrupted = _run_dir_from_output(stdout)
                if interrupted is not None:
                    _cleanup_interrupted_run(interrupted)
                proc = subprocess.CompletedProcess(
                    args=cmd,
                    returncode=124,
                    stdout=stdout,
                    stderr=(stderr + "\nhost cleanup guard reached").strip(),
                )
            # run_trial.sh prints the run dir on its first "run: <path>" line.
            run_dir = _run_dir_from_output(proc.stdout)
            if run_dir is not None:
                run_dirs.append(run_dir)
            if proc.returncode != 5 or refusal_attempt >= REFUSAL_RERUN_LIMIT:
                break
        assert proc is not None
        if run_dir is None:
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout)[-2000:]
                raise RuntimeError(
                    f"trial failed before producing a run directory with exit "
                    f"code {proc.returncode}: {detail}"
                )
            state.metadata["launch_error"] = proc.stderr[-2000:]
            state.output = ModelOutput.from_content(
                model=agent, content="(trial did not launch)"
            )
            state.completed = True
            return state
        state = _fold(state, run_dir, agent)
        state.metadata.update(
            runner_returncode=proc.returncode,
            trial_failed=proc.returncode != 0,
            refusal_rerun_limit=REFUSAL_RERUN_LIMIT,
            refusal_reruns=max(0, len(run_dirs) - 1),
            prior_run_dirs=[str(path) for path in run_dirs[:-1]],
        )
        return state

    return solve


# Compatibility for code that imported the first packaged version directly.
cli_agent = subscription_agent


@solver
def replay() -> Solver:
    """Fold an existing run directory (from sample metadata `run_dir`)."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        run_dir = Path(state.metadata["run_dir"])
        agent = state.metadata.get("agent") or (
            "codex" if "codex" in run_dir.name else "claude"
        )
        return _fold(state, run_dir, agent)

    return solve


async def _run_async(
    cmd: list[str], *, cwd: Path, env: dict, timeout: float | None
) -> subprocess.CompletedProcess:
    """subprocess.run(capture_output=True, text=True) on a worker thread, so the event loop keeps
    serving the other samples. TimeoutExpired propagates unchanged."""
    return await asyncio.to_thread(
        subprocess.run, cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
    )


def _os_environ() -> dict:
    import os

    return dict(os.environ)
