"""Inspect-native agent execution for MessageBoardAuditBench.

Claude Code and Codex CLI run through Inspect SWE's sandbox agent bridge. ReAct
uses Inspect's built-in agent with the same sandbox tools. In all three cases,
Inspect owns model calls, provider prompt caching, limits, and live transcript
events. The small wrapper below exists only to collect ``/work/report.md`` after
the agent stops, including when the scoped Inspect time limit fires.
"""
from __future__ import annotations

import json
import time
from collections.abc import Sequence
from functools import wraps

from inspect_ai.agent import Agent, AgentState, react, run
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageUser,
    Model,
    ModelOutput,
    ModelUsage,
)
from inspect_ai.model._model import GenerateInput, sample_model_usage
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import ToolDef, bash, text_editor
from inspect_ai.util import LimitExceededError, sandbox, time_limit
from inspect_swe import claude_code, codex_cli

from messageboard_audit_bench.audit import trajectory_metrics
from messageboard_audit_bench.report_length import acceptance_limits, limits, measure

REPORT_PATH = "/work/report.md"


def _feedback_filter(env):
    previous = None

    async def filter_request(model: Model, messages, tools, tool_choice, config):
        nonlocal previous
        # No provider-hosted browsing/remote tools through the localhost model bridge.
        prohibited = {"web_search", "web_search_preview", "WebSearch", "WebFetch"}
        if any(t.name in prohibited for t in tools):
            raise RuntimeError("network tools are not permitted in this benchmark")
        report, _ = await _read_report()
        low, high = int(env.get("MBAB_REPORT_MIN_WORDS", 0)), int(env.get("MBAB_REPORT_MAX_WORDS", 0))
        left = max(0, int(env.get("MBAB_DEADLINE_EPOCH", time.time())) - int(time.time()))
        note = f"Time budget: {left} seconds remaining."
        if report != previous and high and (report or previous):
            count = len(report.split())
            note += f" Report length: {count:,} words; target {low:,}–{high:,}; strict upper limit {high:,}."
            if count > high:
                note += f" Remove at least {count-high:,} words."
        previous = report
        return GenerateInput([*messages, ChatMessageUser(content=note)], tools, tool_choice, config)

    return filter_request


def _react_feedback(tool, env, report_state):
    definition = ToolDef(tool)

    @wraps(tool)
    async def execute(*args, **kwargs):
        result = await tool(*args, **kwargs)
        report, _ = await _read_report()
        left = max(0, int(env.get("MBAB_DEADLINE_EPOCH", time.time())) - int(time.time()))
        note = f"Time budget: {left} seconds remaining."
        high = int(env.get("MBAB_REPORT_MAX_WORDS", 0))
        if report != report_state[0] and high and (report or report_state[0]):
            count = len(report.split())
            note += f" Report length: {count:,} words; strict upper limit {high:,}."
            if count > high:
                note += f" Remove at least {count-high:,} words."
        report_state[0] = report
        return f"{result}\n\n[{note}]"

    return ToolDef(execute, name=definition.name, description=definition.description,
                   parameters=definition.parameters, parallel=definition.parallel).as_tool()


def inspect_agent(
    agent: str,
    *,
    claude_disallowed_tools: Sequence[str],
    env: dict[str, str] | None = None,
) -> Agent:
    """Return the first-class Inspect agent selected by the task."""
    env = env or {}
    if agent == "claude":
        return claude_code(
            cwd="/work",
            disallowed_tools=sorted(set(claude_disallowed_tools) | {"Agent", "Task", "WebSearch", "WebFetch", "SendMessage", "TeamCreate"}),
            filter=_feedback_filter(env),
            retry_refusals=2,
            retry_uncaught_errors=2,
            env=env,
            version="sandbox",
        )
    if agent == "codex":
        return codex_cli(
            cwd="/work",
            env=env,
            version="sandbox",
            web_search="disabled",
            filter=_feedback_filter(env),
            retry_refusals=2,
            goals=False,
            config_overrides={"features.multi_agent": "false", "model_reasoning_summary": '"detailed"'},
        )
    if agent == "react":
        report_state = [None]
        return react(
            name="messageboard_audit_react",
            tools=[_react_feedback(bash(), env, report_state), _react_feedback(text_editor(), env, report_state)],
            retry_refusals=2,
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


async def _prepare_budget(deadline_epoch: int, budget_minutes: int,
                          report_min_words: int = 0, report_max_words: int = 0) -> dict:
    """Verify isolation and full data readability before starting the agent."""
    check = await sandbox().exec(["python3", "/sandbox/isolation_preflight.py"])
    try:
        preflight = json.loads(check.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"sandbox preflight did not return JSON: {check.stderr[:500]}") from exc
    if not check.success or not preflight.get("ok"):
        raise RuntimeError(f"sandbox preflight failed: {preflight}")
    await sandbox().write_file("/tmp/mbab-time-budget", f"{deadline_epoch}\n{budget_minutes}\n")
    await sandbox().write_file("/tmp/mbab-report-length", f"{report_min_words}\n{report_max_words}\n")
    return preflight


def _usage_metadata(usages: Sequence[ModelUsage]) -> dict[str, int | float | str]:
    """Normalize Inspect's per-model usage to the benchmark's schema."""
    uncached = sum(usage.input_tokens for usage in usages)
    cache_read = sum(usage.input_tokens_cache_read or 0 for usage in usages)
    cache_write = sum(usage.input_tokens_cache_write or 0 for usage in usages)
    output = sum(usage.output_tokens for usage in usages)
    input_tokens = uncached + cache_read + cache_write
    reasoning = sum(usage.reasoning_tokens or 0 for usage in usages) if usages and all(u.reasoning_tokens is not None for u in usages) else None
    return {
        "usage_schema": 3,
        "reasoning_tokens_source": "reported" if reasoning is not None else "unavailable_or_partial",
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
    state.metadata.update(trajectory_metrics(state.messages))
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
    report_min_words: int = 0,
    report_max_words: int = 0,
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
        state.metadata["sandbox_preflight"] = await _prepare_budget(
            deadline_epoch, budget_minutes, report_min_words, report_max_words
        )
        selected = inspect_agent(
            agent,
            claude_disallowed_tools=claude_disallowed_tools,
            env={
                "MBAB_DEADLINE_EPOCH": str(deadline_epoch),
                "MBAB_BUDGET_MIN": str(budget_minutes),
                "MBAB_REPORT_MIN_WORDS": str(report_min_words),
                "MBAB_REPORT_MAX_WORDS": str(report_max_words),
            },
        )
        agent_state = AgentState(messages=state.messages)
        limit_error = None
        revision_count = 0

        @wraps(selected)
        async def tracked_agent(current):
            nonlocal agent_state
            # Keep the live state even when the adapter raises before run() returns.
            agent_state = current
            agent_state = await selected(current)
            return agent_state

        try:
            agent_state, limit_error = await run(
                tracked_agent, state.messages,
                limits=[time_limit(max(1, deadline_epoch - int(time.time())))],
                name=agent,
            )
            report, report_read_error = await _read_report()
            while report_max_words and len(report.split()) > report_max_words and not limit_error:
                remaining = deadline_epoch - int(time.time())
                if remaining <= 0 or revision_count >= 3 or (agent_state.output and agent_state.output.stop_reason == "content_filter"):
                    break
                count = len(report.split())
                agent_state, limit_error = await run(
                    tracked_agent,
                    [*agent_state.messages, ChatMessageUser(content=f"report.md is {count} words. Shorten it to at most {report_max_words} words before finishing; the original deadline still applies.")],
                    limits=[time_limit(remaining)], name=agent,
                )
                revision_count += 1
                report, report_read_error = await _read_report()
        except Exception as exc:
            state.metadata["agent_error"] = f"{type(exc).__name__}: {exc}"[:1000]
            raise
        finally:
            report, report_read_error = await _read_report()
            state.metadata["report_length_revision_count"] = revision_count
            _copy_agent_state(state, agent_state)
            model = state.output.model or str(state.model)
            state.output = ModelOutput.from_content(model=model, content=report or "(no report written)")
            _record_native_metrics(
                state, report=report, report_read_error=report_read_error,
                elapsed=time.monotonic() - started, limit_error=limit_error,
            )
            state.metadata.update(measure(report, *limits(state.metadata), exists=bool(report), acceptance=acceptance_limits(state.metadata)))
        return state

    return solve
