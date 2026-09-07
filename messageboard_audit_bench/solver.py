"""Solvers that run a coding-agent CLI in the sandbox, or replay a finished run.

`subscription_agent(...)` launches sandbox/docker/run_trial.sh, then folds the
CLI's transcript and the report it wrote into Inspect state, so `inspect view`
renders the whole session and the scorers see the report as the completion.

`replay(...)` does the same for runs already on disk under runs/, so you can
bring past baseline runs into Inspect without re-running the models.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageTool,
    ModelOutput,
    ModelUsage,
)
from inspect_ai.solver import Generate, Solver, TaskState, solver

from messageboard_audit_bench.audit import trajectory_metrics
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
    resources = meta.get("resource_names", {}) if run_id else {}
    if run_id:
        # Only remove resources named for this run; metadata is trusted runner
        # output but the extra restriction prevents a broad cleanup by mistake.
        if resources:
            names = {
                key: value
                for key, value in resources.items()
                if isinstance(value, str)
                and value.startswith("mbab-")
                and value.endswith(run_id)
            }
            commands = [
                ["docker", "rm", "-f", names[key]]
                for key in ("model", "tools", "proxy")
                if key in names
            ]
            commands += (
                [["docker", "network", "rm", names["network"]]]
                if "network" in names
                else []
            )
            commands += [
                ["docker", "volume", "rm", names[key]]
                for key in ("ipc", "telemetry")
                if key in names
            ]
        else:
            commands = [
                ["docker", "rm", "-f", f"mbab-agent-{run_id}", f"mbab-proxy-{run_id}"],
                ["docker", "network", "rm", f"mbab-inner-{run_id}"],
            ]
        for command in commands:
            try:
                subprocess.call(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    trusted_auth = run_dir / ".trusted-auth"
    if trusted_auth.is_dir():
        shutil.rmtree(trusted_auth)
    secrets = run_dir / ".secrets"
    if secrets.is_dir():
        shutil.rmtree(secrets)


async def _run_process(
    command: list[str], *, cwd: Path, env: dict, timeout: float | None
):
    """Drain output throughout a run and terminate the runner on cancellation.

    The runner gets SIGTERM first so it can collect trusted artifacts and remove
    its containers. A process-group kill and metadata-based cleanup are the
    fallback if it cannot finish. No agent-controlled host paths are followed.
    """
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        start_new_session=True,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout: list[bytes] = []
    stderr: list[bytes] = []

    async def drain(stream, chunks):
        while chunk := await stream.read(65536):
            chunks.append(chunk)

    readers = [
        asyncio.create_task(drain(process.stdout, stdout)),
        asyncio.create_task(drain(process.stderr, stderr)),
    ]
    waiter = asyncio.create_task(process.wait())
    try:
        await asyncio.wait_for(asyncio.shield(waiter), timeout)
    except (TimeoutError, asyncio.CancelledError) as error:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(asyncio.shield(waiter), 15)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await waiter
        await asyncio.gather(*readers)
        output = b"".join(stdout).decode(errors="replace")
        directory = _run_dir_from_output(output)
        if directory is not None:
            await asyncio.to_thread(_cleanup_interrupted_run, directory)
        if isinstance(error, asyncio.CancelledError):
            raise
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=output,
            stderr=b"".join(stderr).decode(errors="replace"),
        ) from error
    await asyncio.gather(*readers)
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        b"".join(stdout).decode(errors="replace"),
        b"".join(stderr).decode(errors="replace"),
    )


def _raw_artifacts(run_dir: Path) -> dict[str, str]:
    """Keep unnormalized future CLI evidence in the portable Inspect log."""
    names = (
        "transcript.jsonl",
        "stderr.log",
        "tools.jsonl",
        "model_container.log",
        "tool_supervisor.log",
        "proxy.log",
        "launch_error.log",
        "retries.jsonl", "tool-events.jsonl", "audit.json", "provenance.json",
    )
    return {
        name: (run_dir / name).read_text(errors="replace")
        for name in names
        if (run_dir / name).is_file()
    }


def _attempt_usage(parsed: Parsed) -> dict:
    """Keep each retry's usage separate from the final-attempt score fields."""
    return {
        "input_tokens": parsed.input_tokens,
        "input_tokens_uncached": parsed.input_tokens_uncached,
        "output_tokens": parsed.output_tokens,
        "cache_read_tokens": parsed.cache_read_tokens,
        "cache_write_tokens": parsed.cache_write_tokens,
        "reasoning_tokens": parsed.reasoning_tokens,
        "cost_usd": parsed.cost_usd,
        "duration_ms": parsed.duration_ms,
    }


def _namespaced_attempt_messages(messages, prefix: str):
    """Avoid tool-ID collisions when earlier refusal attempts enter one viewer."""
    copied = copy.deepcopy(messages)
    call_ids: dict[str, str] = {}
    for message in copied:
        if isinstance(message, ChatMessageAssistant):
            if message.id:
                message.id = prefix + message.id
            for call in message.tool_calls or []:
                renamed = prefix + call.id
                call_ids[call.id] = renamed
                call.id = renamed
    for message in copied:
        if isinstance(message, ChatMessageTool) and message.tool_call_id:
            message.tool_call_id = call_ids.get(
                message.tool_call_id, prefix + message.tool_call_id
            )
    return copied


def _import_prior_attempts(
    state: TaskState, run_dirs: list[Path], agent: str
) -> list[dict]:
    """Append prior retry trajectories without letting them provide the report."""
    attempts = []
    for index, directory in enumerate(run_dirs, start=1):
        transcript = directory / "transcript.jsonl"
        entry = {
            "attempt": index,
            "run_dir": str(directory),
            "raw_artifacts": _raw_artifacts(directory),
        }
        if not transcript.exists():
            attempts.append(
                {**entry, "trajectory_imported": False, "reason": "missing transcript"}
            )
            continue
        try:
            parsed = parse(agent, transcript)
        except Exception as error:
            attempts.append(
                {
                    **entry,
                    "trajectory_imported": False,
                    "reason": f"{type(error).__name__}: {error}"[:500],
                }
            )
            continue
        state.messages += _namespaced_attempt_messages(
            parsed.messages, f"retry-{index}:"
        )
        attempts.append(
            {
                **entry,
                "trajectory_imported": True,
                "usage": _attempt_usage(parsed),
                "transcript_diagnostics": parsed.extra.get("transcript_diagnostics"),
            }
        )
    return attempts


def _fold(state: TaskState, run_dir: Path, agent: str) -> TaskState:
    parsed: Parsed = parse(agent, run_dir / "transcript.jsonl")
    state.messages = state.messages + parsed.messages

    report_path = run_dir / "report.md"
    report = report_path.read_text(errors="replace") if report_path.exists() else ""
    report_source = report_path if report else None

    usage = ModelUsage(
        # Inspect defines input_tokens as the uncached/full-rate subset; its
        # cache fields are disjoint. Benchmark metadata below also retains the
        # cache-inclusive total for straightforward cache-rate analysis.
        input_tokens=parsed.input_tokens_uncached,
        output_tokens=parsed.output_tokens,
        total_tokens=parsed.input_tokens + parsed.output_tokens,
        input_tokens_cache_read=parsed.cache_read_tokens or None,
        input_tokens_cache_write=parsed.cache_write_tokens or None,
        reasoning_tokens=parsed.reasoning_tokens,
        total_cost=parsed.cost_usd,
    )
    state.output = ModelOutput.from_content(
        model=agent, content=report or "(no report written)"
    )
    state.output.usage = usage

    meta = {}
    if (run_dir / "meta.json").exists():
        meta = json.loads((run_dir / "meta.json").read_text())
    state.metadata["subscription_raw_artifacts"] = _raw_artifacts(run_dir)
    for key in ("isolation", "scaffold", "logging", "resource_names"):
        if key in meta:
            state.metadata[key] = meta[key]
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
    state.metadata.update(trajectory_metrics(parsed.messages))
    state.metadata["trial_failed"] = meta.get("exit_code") not in (None, 0)
    state.completed = True
    return state


@solver
def subscription_agent(
    agent: str,
    model: str,
    config: str = "blind",
    allow_networked_subscription: bool = True,
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
        cmd = [str(repo / "sandbox" / "docker" / "run_trial.sh"), agent, model, str(replicate)]
        if not allow_networked_subscription:
            raise ValueError("subscription uses the restricted proxy with shell-accessible credentials; choose backend=inspect for offline tools")
        env = {"CONFIG": config, "ALLOW_NETWORKED_SUBSCRIPTION": "1"}
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
        run_dirs: list[Path] = []
        proc = None
        run_dir = None
        for refusal_attempt in range(REFUSAL_RERUN_LIMIT + 1):
            try:
                proc = await _run_process(
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
        prior_attempts = _import_prior_attempts(state, run_dirs[:-1], agent)
        state = _fold(state, run_dir, agent)
        state.metadata.update(
            runner_returncode=proc.returncode,
            trial_failed=proc.returncode != 0,
            refusal_rerun_limit=REFUSAL_RERUN_LIMIT,
            refusal_reruns=max(0, len(run_dirs) - 1),
            prior_run_dirs=[str(path) for path in run_dirs[:-1]],
            prior_attempts=prior_attempts,
            usage_scope="final_attempt",
            trajectory_scope="all_imported_attempts",
            trajectory_attempt_count=len(run_dirs),
        )
        # The final report and usage remain the final attempt's. Tool metrics,
        # however, now describe every trajectory shown in Inspect's viewer.
        state.metadata.update(trajectory_metrics(state.messages))
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


def _os_environ() -> dict:
    import os

    return dict(os.environ)
