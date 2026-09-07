"""Inspect-native agent execution for MessageBoardAuditBench.

Claude Code and Codex CLI run through Inspect SWE's sandbox agent bridge. ReAct
uses Inspect's built-in agent with the same sandbox tools. In all three cases,
Inspect owns model calls, provider prompt caching, limits, and live transcript
events. The small wrapper below exists only to collect ``/work/report.md`` after
the agent stops, including when the scoped Inspect time limit fires.
"""
from __future__ import annotations

import time
from collections.abc import Sequence

from inspect_ai.agent import Agent, AgentState, react, run
from inspect_ai.model import ChatMessageAssistant, ModelOutput, ModelUsage
from inspect_ai.model._model import sample_model_usage
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import bash, text_editor
from inspect_ai.util import LimitExceededError, sandbox, time_limit
from inspect_swe import claude_code, codex_cli

REPORT_PATH = "/work/report.md"


def inspect_agent(
    agent: str,
    *,
    claude_disallowed_tools: Sequence[str],
    env: dict[str, str] | None = None,
) -> Agent:
    """Return the first-class Inspect agent selected by the task."""
    if agent == "claude":
        return claude_code(
            cwd="/work",
            disallowed_tools=list(claude_disallowed_tools),
            env=env,
            version="sandbox",
        )
    if agent == "codex":
        return codex_cli(
            cwd="/work",
            env=env,
            version="sandbox",
            web_search="disabled",
        )
    if agent == "react":
        return react(
            name="messageboard_audit_react",
            tools=[bash(), text_editor()],
        )
    raise ValueError(f"unsupported native agent: {agent!r}")


async def _read_report() -> tuple[str, str | None]:
    try:
        return await sandbox().read_file(REPORT_PATH), None
    except Exception as ex:
        # The trajectory and usage are already safely in Inspect. A malformed
        # report or a container that disappeared during collection should be
        # scored as no report, not discard an otherwise recoverable sample.
        return "", f"{type(ex).__name__}: {ex}"[:500]


async def _prepare_budget(deadline_epoch: int, budget_minutes: int) -> None:
    """Check mounted data and configure ``time_left`` for every harness."""
    check = await sandbox().exec(
        [
            "sh",
            "-c",
            "test -s /work/data/events.jsonl"
            " && test -s /work/data/labels.jsonl"
            " && test -s /work/data/pages.jsonl"
            " && test -s /work/data/revisions.jsonl",
        ]
    )
    if not check.success:
        raise RuntimeError(
            "benchmark dataset is missing or incomplete; run scripts/build_data.sh"
        )
    await sandbox().write_file(
        "/tmp/mbab-time-budget",
        f"{deadline_epoch}\n{budget_minutes}\n",
    )


def _usage_metadata(usages: Sequence[ModelUsage]) -> dict[str, int | float | str]:
    """Normalize Inspect's per-model usage to the benchmark's schema."""
    uncached = sum(usage.input_tokens for usage in usages)
    cache_read = sum(usage.input_tokens_cache_read or 0 for usage in usages)
    cache_write = sum(usage.input_tokens_cache_write or 0 for usage in usages)
    output = sum(usage.output_tokens for usage in usages)
    input_tokens = uncached + cache_read + cache_write
    reasoning = sum(usage.reasoning_tokens or 0 for usage in usages)
    return {
        "usage_schema": 2,
        "usage_source": "inspect",
        "input_tokens": input_tokens,
        "input_tokens_uncached": uncached,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "cache_read_fraction": cache_read / input_tokens if input_tokens else 0.0,
        "output_tokens": output,
        "reasoning_tokens": reasoning,
        "total_tokens": input_tokens + output,
    }


def _copy_agent_state(state: TaskState, agent_state: AgentState) -> None:
    state.messages = agent_state.messages
    if agent_state.output:
        state.output = agent_state.output


def _record_native_metrics(
    state: TaskState,
    *,
    report: str,
    report_read_error: str | None,
    elapsed: float,
    limit_error: LimitExceededError | None,
) -> None:
    assistants = [m for m in state.messages if isinstance(m, ChatMessageAssistant)]
    state.metadata.update(
        _usage_metadata(list(sample_model_usage().values())),
        backend="inspect",
        report_written=bool(report),
        report_read_error=report_read_error,
        report_chars=len(report),
        turns=len(assistants),
        tool_calls=sum(len(m.tool_calls or []) for m in assistants),
        cost_usd=state.cost_usage,
        wall_seconds=round(elapsed, 3),
        limit_exceeded=limit_error.type if limit_error else None,
        limit_value=limit_error.limit if limit_error else None,
    )


@solver
def inspect_native_agent(
    agent: str,
    time_limit_seconds: int,
    claude_disallowed_tools: Sequence[str] = (),
) -> Solver:
    """Run an agent through Inspect and collect its on-disk report.

    ``agent.run`` catches only the scoped Inspect limit, which lets this solver
    preserve the live trajectory and then read the report the agent was told to
    update throughout the investigation. Unexpected agent or sandbox failures
    still fail the sample normally.
    """
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        started = time.monotonic()
        deadline_epoch = int(time.time()) + time_limit_seconds
        budget_minutes = max(1, round(time_limit_seconds / 60))
        await _prepare_budget(deadline_epoch, budget_minutes)
        selected = inspect_agent(
            agent,
            claude_disallowed_tools=claude_disallowed_tools,
            env={
                "MBAB_DEADLINE_EPOCH": str(deadline_epoch),
                "MBAB_BUDGET_MIN": str(budget_minutes),
            },
        )
        result = await run(
            selected,
            state.messages,
            limits=[time_limit(time_limit_seconds)],
        )
        agent_state, limit_error = result
        _copy_agent_state(state, agent_state)

        report, report_read_error = await _read_report()
        model = state.output.model or str(state.model)
        # report.md is the benchmark answer contract. Never grade the agent's
        # last conversational message when the file is absent.
        state.output = ModelOutput.from_content(
            model=model,
            content=report or "(no report written)",
        )

        _record_native_metrics(
            state,
            report=report,
            report_read_error=report_read_error,
            elapsed=time.monotonic() - started,
            limit_error=limit_error,
        )
        return state

    return solve
