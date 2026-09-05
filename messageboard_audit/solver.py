"""Solvers that run a coding-agent CLI in the sandbox, or replay a finished run.

`cli_agent(...)` launches sandbox/docker/run_trial.sh, then folds the CLI's transcript
and the report it wrote into Inspect state, so `inspect view` renders the whole
session and the scorers see the report as the completion.

`replay(...)` does the same for runs already on disk under runs/, so you can
bring past baseline runs into Inspect without re-running the models.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.solver import Generate, Solver, TaskState, solver

from messageboard_audit.transcripts import Parsed, parse

REPO = Path(__file__).resolve().parent.parent


def _fold(state: TaskState, run_dir: Path, agent: str) -> TaskState:
    parsed: Parsed = parse(agent, run_dir / "transcript.jsonl")
    state.messages = state.messages + parsed.messages

    report_path = run_dir / "report.md"
    report = report_path.read_text(errors="replace") if report_path.exists() else ""
    if not report and agent == "codex" and (run_dir / "final_message.md").exists():
        report = (run_dir / "final_message.md").read_text(errors="replace")

    usage = ModelUsage(
        input_tokens=parsed.input_tokens,
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
        output_tokens=parsed.output_tokens,
        cache_read_tokens=parsed.cache_read_tokens,
        wall_seconds=meta.get("wall_seconds"),
        exit_code=meta.get("exit_code"),
        cli_version=meta.get("cli_version"),
        model=meta.get("model"),
        **{f"cli_{k}": v for k, v in parsed.extra.items() if isinstance(v, (str, int, float))},
    )
    state.completed = True
    return state


@solver
def cli_agent(agent: str, model: str, effort: str = "high", timeout: str = "25m") -> Solver:
    """Launch a fresh sandbox trial, then fold its transcript into state."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        seed = state.epoch
        cmd = [str(REPO / "sandbox" / "docker" / "run_trial.sh"), agent, model, str(seed)]
        env = {"EFFORT": effort, "TIMEOUT": timeout}
        proc = subprocess.run(
            cmd, cwd=REPO, env={**_os_environ(), **env},
            capture_output=True, text=True,
        )
        # run_trial.sh prints the run dir on its first "run: <path>" line
        run_dir = None
        for line in proc.stdout.splitlines():
            if line.startswith("run: "):
                run_dir = Path(line[5:].strip())
        if run_dir is None:
            state.metadata["launch_error"] = proc.stderr[-2000:]
            state.output = ModelOutput.from_content(model=agent, content="(trial did not launch)")
            state.completed = True
            return state
        return _fold(state, run_dir, agent)

    return solve


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
