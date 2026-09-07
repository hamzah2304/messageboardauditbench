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
    ModelOutput,
    ModelUsage,
)
from inspect_ai.model._model import sample_model_usage
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import Tool, ToolDef, bash, text_editor
from inspect_ai.util import LimitExceededError, sandbox, time_limit
from inspect_swe import claude_code, codex_cli

from messageboard_audit_bench.report_length import acceptance_limits, limits, measure

REPORT_PATH = "/work/report.md"
# A refusal is retried through the same provider/model only. Keeping this
# finite makes the treatment reproducible and prevents a refused prompt from
# consuming the full trial budget in the bridge retry loop.
REFUSAL_RETRY_LIMIT = 2
MIN_REVISION_SECONDS = 60
CLAUDE_CONFIG_DIR = "/work/.mbab-claude"
CODEX_HOME = "/work/.codex"


def _hook_config() -> dict:
    return {
        "hooks": {
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "sh -c 'touch /tmp/mbab-post-tool-hook-fired; "
                                "exec /sandbox/time_left.sh'"
                            ),
                        },
                        {
                            "type": "command",
                            "command": (
                                "python3 /sandbox/report_length.py --hook PostToolUse"
                            ),
                        },
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "sh -c 'touch /tmp/mbab-stop-hook-fired; "
                                "exec python3 /sandbox/report_length.py --hook Stop'"
                            ),
                        }
                    ]
                }
            ],
        }
    }


def _with_react_feedback(base: Tool, env: dict[str, str]) -> Tool:
    """Append the same time/overlength context after native ReAct tools."""
    definition = ToolDef(base)

    @wraps(base)
    async def execute(*args, **kwargs):
        result = await base(*args, **kwargs)
        await sandbox().exec(["touch", "/tmp/mbab-post-tool-hook-fired"])
        deadline = int(env["MBAB_DEADLINE_EPOCH"])
        budget = env["MBAB_BUDGET_MIN"]
        left = max(0, deadline - int(time.time()))
        note = f"Time budget: about {(left + 30) // 60} of {budget} minutes left."
        report, _ = await _read_report()
        overlong = _overlong_revision(
            report, int(env.get("MBAB_REPORT_MAX_WORDS", "0"))
        )
        if overlong:
            note += " " + overlong
        return f"{result}\n\n[{note}]"

    return ToolDef(
        execute,
        name=definition.name,
        description=definition.description,
        parameters=definition.parameters,
        parallel=definition.parallel,
        viewer=definition.viewer,
        max_output=definition.max_output,
        options=definition.options,
    ).as_tool()


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
            disallowed_tools=list(claude_disallowed_tools),
            retry_refusals=REFUSAL_RETRY_LIMIT,
            env={**env, "CLAUDE_CONFIG_DIR": CLAUDE_CONFIG_DIR},
            version="sandbox",
        )
    if agent == "codex":
        return codex_cli(
            cwd="/work",
            env=env,
            version="sandbox",
            web_search="disabled",
            retry_refusals=REFUSAL_RETRY_LIMIT,
            config_overrides={"features.hooks": "true"},
        )
    if agent == "react":
        return react(
            name="messageboard_audit_react",
            tools=[
                _with_react_feedback(bash(), env),
                _with_react_feedback(text_editor(), env),
            ],
            retry_refusals=REFUSAL_RETRY_LIMIT,
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


async def _marker_exists(path: str) -> bool:
    try:
        return (await sandbox().exec(["test", "-e", path])).success
    except Exception:
        return False


async def _prepare_budget(
    deadline_epoch: int,
    budget_minutes: int,
    report_min_words: int,
    report_max_words: int,
) -> None:
    """Check mounted data and configure shared sandbox-side helpers."""
    check = await sandbox().exec(
        [
            "sh",
            "-c",
            "test -s /work/data/events.jsonl"
            " && test -s /work/data/labels.jsonl"
            " && test -s /work/data/pages.jsonl"
            " && test -s /work/data/revisions.jsonl"
            " && ! getent hosts collusion.wiki >/dev/null 2>&1"
            " && ! curl -sS --connect-timeout 1 --max-time 2 "
            "https://1.1.1.1/ >/dev/null 2>&1",
        ]
    )
    if not check.success:
        raise RuntimeError(
            "sandbox preflight failed: verify the benchmark dataset and disabled "
            "network"
        )
    await sandbox().write_file(
        "/tmp/mbab-time-budget",
        f"{deadline_epoch}\n{budget_minutes}\n",
    )
    await sandbox().write_file(
        "/tmp/mbab-report-length",
        f"{report_min_words}\n{report_max_words}\n",
    )
    configured = await sandbox().exec(["mkdir", "-p", CLAUDE_CONFIG_DIR, CODEX_HOME])
    if not configured.success:
        raise RuntimeError("could not create native agent configuration directories")
    hooks = _hook_config()
    await sandbox().write_file(
        f"{CLAUDE_CONFIG_DIR}/settings.json",
        json.dumps(
            {
                "apiKeyHelper": "echo $ANTHROPIC_AUTH_TOKEN",
                **hooks,
            }
        ),
    )
    await sandbox().write_file(
        f"{CODEX_HOME}/hooks.json",
        json.dumps(hooks),
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


def _terminal_refusal(agent_state: AgentState) -> bool:
    """Whether the bridge exposed a refusal after its bounded retries.

    Inspect normalizes provider refusals to ``content_filter``. The bridge
    deliberately keeps only the final response after retrying, so inspecting
    the final ``AgentState.output`` is the reliable way to distinguish a
    terminal refusal from an earlier, successfully retried one. Do not infer
    refusal from prose: provider wording is unstable and a report may discuss
    refusals as evidence.
    """
    return bool(
        agent_state.output and agent_state.output.stop_reason == "content_filter"
    )


def _overlong_revision(report: str, maximum: int) -> str | None:
    """Return the single native correction prompt, only above the hard target."""
    count = len(report.split())
    if not maximum or count <= maximum:
        return None
    return (
        f"report.md is {count:,} words, above the strict {maximum:,}-word limit. "
        f"Shorten it by at least {count - maximum:,} words now, preserving the "
        "strongest evidence and citations, then finish."
    )


def _record_native_metrics(
    state: TaskState,
    *,
    report: str,
    report_read_error: str | None,
    elapsed: float,
    limit_error: LimitExceededError | None,
    terminal_refusal: bool,
    agent_stop_reason: str | None,
    report_length_ping_count: int,
    post_tool_hook_fired: bool,
    stop_hook_fired: bool,
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
        terminal_refusal=terminal_refusal,
        agent_stop_reason=agent_stop_reason,
        refusal_stop_reason="content_filter" if terminal_refusal else None,
        refusal_retry_limit=REFUSAL_RETRY_LIMIT,
        refusal_policy="same_model_only",
        report_length_ping_count=report_length_ping_count,
        post_tool_hook_fired=post_tool_hook_fired,
        stop_hook_fired=stop_hook_fired,
    )
    state.metadata.update(
        measure(
            report,
            *limits(state.metadata),
            exists=bool(report),
            acceptance=acceptance_limits(state.metadata),
        )
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
        await _prepare_budget(
            deadline_epoch,
            budget_minutes,
            report_min_words,
            report_max_words,
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
        result = await run(
            selected,
            state.messages,
            limits=[time_limit(time_limit_seconds)],
        )
        agent_state, limit_error = result
        terminal_refusal = _terminal_refusal(agent_state)
        report, report_read_error = await _read_report()
        report_length_ping_count = 0

        # Do not make agents use more of their budget merely because they stop
        # early or write a short report. A single continuation is reserved for
        # correcting a report above the prompt's strict upper limit.
        revision = _overlong_revision(report, report_max_words)
        remaining = max(0, deadline_epoch - int(time.time()))
        if (
            revision
            and remaining >= MIN_REVISION_SECONDS
            and limit_error is None
            and not terminal_refusal
        ):
            report_length_ping_count = 1
            correction_messages = [
                *agent_state.messages,
                ChatMessageUser(content=revision),
            ]
            corrected_state, correction_limit = await run(
                selected,
                correction_messages,
                limits=[time_limit(remaining)],
            )
            agent_state = corrected_state
            limit_error = correction_limit
            terminal_refusal = _terminal_refusal(agent_state)
            report, report_read_error = await _read_report()

        agent_stop_reason = (
            agent_state.output.stop_reason if agent_state.output else None
        )
        post_tool_hook_fired = await _marker_exists("/tmp/mbab-post-tool-hook-fired")
        stop_hook_fired = await _marker_exists("/tmp/mbab-stop-hook-fired")
        _copy_agent_state(state, agent_state)
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
            terminal_refusal=terminal_refusal,
            agent_stop_reason=agent_stop_reason,
            report_length_ping_count=report_length_ping_count,
            post_tool_hook_fired=post_tool_hook_fired,
            stop_hook_fired=stop_hook_fired,
        )
        return state

    return solve
