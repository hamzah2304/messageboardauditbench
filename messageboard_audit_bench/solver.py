"""Solvers that run a coding-agent CLI in the sandbox, or replay a finished run.

`subscription_agent(...)` launches sandbox/docker/run_trial.sh, then folds the
CLI's transcript and the report it wrote into Inspect state, so `inspect view`
renders the whole session and the scorers see the report as the completion.

`replay(...)` does the same for runs already on disk under runs/, so you can
bring past baseline runs into Inspect without re-running the models.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.solver import Generate, Solver, TaskState, solver

from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.transcripts import Parsed, parse


def _fold(state: TaskState, run_dir: Path, agent: str) -> TaskState:
    parsed: Parsed = parse(agent, run_dir / "transcript.jsonl")
    state.messages = state.messages + parsed.messages

    report_path = run_dir / "report.md"
    report = report_path.read_text(errors="replace") if report_path.exists() else ""
    if not report and agent == "codex" and (run_dir / "final_message.md").exists():
        report = (run_dir / "final_message.md").read_text(errors="replace")

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
    state.output = ModelOutput.from_content(model=agent, content=report or "(no report written)")
    state.output.usage = usage

    meta = {}
    if (run_dir / "meta.json").exists():
        meta = json.loads((run_dir / "meta.json").read_text())
    state.metadata.update(
        agent=agent,
        run_dir=str(run_dir),
        report_written=bool(report),
        report_chars=len(report),
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
        config=meta.get("config"),
        condition=meta.get("condition", meta.get("prompt", meta.get("config"))),
        prompt=meta.get("prompt"),
        budget_min=meta.get("budget_min"),
        data_variant=meta.get("data_variant"),
        effort=meta.get("effort"),
        exit_code=meta.get("exit_code"),
        replicate=meta.get("replicate", meta.get("seed")),
        run_id=meta.get("run_id"),
        cli_version=meta.get("cli_version"),
        model=meta.get("model"),
        transcript_diagnostics=parsed.extra.get("transcript_diagnostics"),
        **{f"cli_{k}": v for k, v in parsed.extra.items() if isinstance(v, (str, int, float))},
    )
    state.completed = True
    return state


@solver
def subscription_agent(
    agent: str,
    model: str,
    condition: str = "blind",
    time_limit_minutes: int | None = None,
    timeout_minutes: int | None = None,
    prompt: str | None = None,
    data_variant: str | None = None,
    effort: str | None = None,
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
        env = {"CONFIG": condition}
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
        proc = subprocess.run(
            cmd, cwd=repo, env={**_os_environ(), **env},
            capture_output=True, text=True,
        )
        # run_trial.sh prints the run dir on its first "run: <path>" line
        run_dir = None
        for line in proc.stdout.splitlines():
            if line.startswith("run: "):
                run_dir = Path(line[5:].strip())
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout)[-2000:]
            raise RuntimeError(f"trial failed with exit code {proc.returncode}: {detail}")
        if run_dir is None:
            state.metadata["launch_error"] = proc.stderr[-2000:]
            state.output = ModelOutput.from_content(model=agent, content="(trial did not launch)")
            state.completed = True
            return state
        return _fold(state, run_dir, agent)

    return solve


# Compatibility for code that imported the first packaged version directly.
cli_agent = subscription_agent


@solver
def replay() -> Solver:
    """Fold an existing run directory (from sample metadata `run_dir`)."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        run_dir = Path(state.metadata["run_dir"])
        agent = state.metadata.get("agent") or ("codex" if "codex" in run_dir.name else "claude")
        return _fold(state, run_dir, agent)

    return solve


def _os_environ() -> dict:
    import os
    return dict(os.environ)
