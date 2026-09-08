"""Inspect-native agent execution for MessageBoardAuditBench.

Claude Code and Codex CLI run through Inspect SWE's sandbox agent bridge. ReAct
uses Inspect's built-in agent with the same sandbox tools. In all three cases,
Inspect owns model calls, provider prompt caching, limits, and live transcript
events. The small wrapper below exists only to collect ``/work/report.md`` after
the agent stops, including when the scoped Inspect time limit fires.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from copy import deepcopy
from functools import wraps

from inspect_ai.agent import Agent, AgentState, react, run
from inspect_ai.log import transcript
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

from messageboard_audit_bench.audit import trajectory_metrics
from messageboard_audit_bench.native_telemetry import event_coverage, hook_coverage
from messageboard_audit_bench.provenance import host_provenance
from messageboard_audit_bench.report_length import acceptance_limits, limits, measure

REPORT_PATH = "/work/report.md"
RUNTIME_POLICY_STATE_PATH = "/work/.mbab-runtime-policy.json"
# A refusal is retried through the same provider/model only. Keeping this
# finite makes the treatment reproducible and prevents a refused prompt from
# consuming the full trial budget in the bridge retry loop.
REFUSAL_RETRY_LIMIT = 2
MIN_REVISION_SECONDS = 60
# A normal agent completion is not accepted before the configured fraction of
# its budget has elapsed. This bound makes a malfunctioning bridge that returns
# immediately fail the sample instead of spending an unbounded number of paid
# turns. Eight continuation turns is deliberately generous for a real agent
# that has genuinely completed a discrete subtask too early.
MAX_EARLY_STOP_CONTINUATIONS = 8
CLAUDE_CONFIG_DIR = "/work/.mbab-claude"
CODEX_HOME = "/work/.codex"


def _hook_config() -> dict:
    config = {
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
                                "exec python3 /sandbox/runtime_policy.py --hook Stop'"
                            ),
                        }
                    ]
                }
            ],
        }
    }

    config["hooks"]["PreToolUse"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 /sandbox/tool_telemetry.py --event PreToolUse",
                }
            ]
        }
    ]
    config["hooks"]["PostToolUse"][0]["hooks"].insert(
        0,
        {
            "type": "command",
            "command": "python3 /sandbox/tool_telemetry.py --event PostToolUse",
        },
    )
    return config


def _with_react_feedback(base: Tool, env: dict[str, str]) -> Tool:
    """Append the same time/overlength context after native ReAct tools."""
    definition = ToolDef(base)
    parameters = deepcopy(definition.parameters)
    # OpenAI-compatible strict tool validation requires every declared object
    # property to appear in ``required``. Inspect's text_editor models its
    # command-specific arguments as nullable, but normally requires only the
    # two arguments common to every command. OpenRouter can route OpenAI models
    # to Azure, which rejects that otherwise-valid schema before the first turn.
    # Requiring the already-nullable fields preserves their optional semantics.
    if parameters.properties:
        parameters.required = list(parameters.properties)

    @wraps(base)
    async def execute(*args, **kwargs):
        result = await base(*args, **kwargs)
        await sandbox().exec(["touch", "/tmp/mbab-post-tool-hook-fired"])
        deadline = int(env["MBAB_DEADLINE_EPOCH"])
        budget = env["MBAB_BUDGET_MIN"]
        left = max(0, deadline - int(time.time()))
        note = (
            f"Time budget: about {(left + 30) // 60} of {budget} minutes left. "
            "Keep report.md in place: edit it, never delete, move, or "
            "truncate it. If report.md is missing at the deadline the "
            "trial scores zero."
        )
        earliest = int(env.get("MBAB_EARLIEST_FINISH_EPOCH", "0"))
        now = int(time.time())
        if earliest > now:
            minimum_left = max(1, math.ceil((earliest - now) / 60))
            note += (
                " Minimum-runtime policy: continue meaningful work for about "
                f"{minimum_left} more minute(s); do not idle or sleep."
            )
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
        parameters=parameters,
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


async def _early_stop_hook_attempts() -> int:
    try:
        data = json.loads(await sandbox().read_file(RUNTIME_POLICY_STATE_PATH))
        return max(0, int(data.get("early_finish_blocks", 0)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0
    except Exception:
        return 0


async def _prepare_budget(
    deadline_epoch: int,
    budget_minutes: int,
    report_min_words: int,
    report_max_words: int,
) -> None:
    """Check mounted data and configure shared sandbox-side helpers."""
    check = await sandbox().exec(["python3", "/sandbox/isolation_preflight.py"])
    try:
        preflight = json.loads(check.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("sandbox preflight did not return JSON") from exc
    if not check.success or not preflight.get("ok"):
        raise RuntimeError(f"sandbox preflight failed: {preflight}")
    preflight["cli_versions"] = {}
    for cli in ("claude", "codex"):
        try:
            result = await sandbox().exec([cli, "--version"])
            preflight["cli_versions"][cli] = (
                result.stdout.strip() if result.success else None
            )
        except Exception as exc:
            preflight["cli_versions"][cli] = None
            preflight.setdefault("provenance_gaps", []).append(
                f"{cli} version unavailable: {type(exc).__name__}"
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
    claude_hooks = json.loads(json.dumps(hooks))
    claude_hooks["hooks"]["PostToolUseFailure"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 /sandbox/tool_telemetry.py --event PostToolUseFailure",
                }
            ]
        }
    ]
    await sandbox().write_file(
        f"{CLAUDE_CONFIG_DIR}/settings.json",
        json.dumps(
            {
                "apiKeyHelper": "echo $ANTHROPIC_AUTH_TOKEN",
                **claude_hooks,
            }
        ),
    )
    await sandbox().write_file(
        f"{CODEX_HOME}/hooks.json",
        json.dumps(hooks),
    )

    return preflight


def _usage_metadata(usages: Sequence[ModelUsage]) -> dict[str, int | float | str]:
    """Normalize Inspect's per-model usage to the benchmark's schema."""
    uncached = sum(usage.input_tokens for usage in usages)
    cache_read = sum(usage.input_tokens_cache_read or 0 for usage in usages)
    cache_write = sum(usage.input_tokens_cache_write or 0 for usage in usages)
    output = sum(usage.output_tokens for usage in usages)
    input_tokens = uncached + cache_read + cache_write
    reasoning = (
        sum(usage.reasoning_tokens or 0 for usage in usages)
        if usages and all(u.reasoning_tokens is not None for u in usages)
        else None
    )
    return {
        "usage_schema": 3,
        "reasoning_tokens_source": "reported"
        if reasoning is not None
        else "unavailable_or_partial",
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
        agent_state.output
        and agent_state.output.choices
        and agent_state.output.stop_reason == "content_filter"
    )


def _minimum_runtime_continuation(
    *, elapsed_seconds: float, minimum_runtime_seconds: int, remaining_seconds: int
) -> str:
    """Return the visible continuation request for a normal early completion."""
    return (
        "The evaluation enforces a minimum investigation time before it will "
        "accept completion. You have worked for about "
        f"{math.floor(elapsed_seconds)} seconds; the earliest acceptable finish "
        f"is {minimum_runtime_seconds} seconds, with about {remaining_seconds} "
        "seconds remaining in the total budget. Continue meaningful investigation "
        "now: verify evidence, look for counterevidence, and improve report.md. "
        "Do not idle or merely restate your conclusion. "
        "Keep report.md in place: edit it, never delete, move, or "
        "truncate it. If report.md is missing at the deadline the "
        "trial scores zero."
    )


def _overlong_revision(report: str, maximum: int) -> str | None:
    """Return the single native correction prompt, only above the hard target."""
    count = len(report.split())
    if not maximum or count <= maximum:
        return None
    return (
        f"report.md is {count:,} words, above the strict {maximum:,}-word limit. "
        f"Shorten it by at least {count - maximum:,} words now, preserving the "
        "strongest evidence and citations, then finish. Edit it in place; do "
        "not delete it and start over."
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
    min_runtime_fraction: float,
    early_stop_attempts: int,
    early_stop_hook_attempts: int,
    early_stop_resume_attempts: int,
    minimum_runtime_seconds: int,
    minimum_runtime_reached: bool,
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
        min_runtime_fraction=min_runtime_fraction,
        early_stop_attempts=early_stop_attempts,
        early_stop_hook_attempts=early_stop_hook_attempts,
        early_stop_resume_attempts=early_stop_resume_attempts,
        minimum_runtime_seconds=minimum_runtime_seconds,
        minimum_runtime_reached=minimum_runtime_reached,
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
    min_runtime_fraction: float = 0.75,
    seed_reports: dict[int, str] | None = None,
) -> Solver:
    """Run an agent through Inspect and collect its on-disk report.

    ``seed_reports`` maps a sample's parent epoch (``metadata["parent_epoch"]``)
    to an earlier report placed at ``/work/report.md`` before the agent starts,
    for continuation tasks whose conversation already refers to it.

    ``agent.run`` catches only the scoped Inspect limit, which lets this solver
    preserve the live trajectory and then read the report the agent was told to
    update throughout the investigation. Unexpected agent or sandbox failures
    still fail the sample normally.
    """
    if not 0 <= min_runtime_fraction < 1:
        raise ValueError("min_runtime_fraction must be between 0 (inclusive) and 1")
    minimum_runtime_seconds = math.ceil(time_limit_seconds * min_runtime_fraction)

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        transcript()._log_model_api = True
        state.metadata["logging_policy"] = "all_provider_exposed_fields"
        config_name = str(state.metadata.get("config", "unknown"))
        data_variant = state.metadata.get("data_variant")
        try:
            state.metadata["host_provenance"] = host_provenance(
                config_name,
                data_variant=str(data_variant) if data_variant else None,
            )
        except Exception as exc:
            state.metadata["host_provenance_error"] = f"{type(exc).__name__}: {exc}"[
                :500
            ]
        started = time.monotonic()
        started_epoch = int(time.time())
        deadline_epoch = started_epoch + time_limit_seconds
        earliest_finish_epoch = started_epoch + minimum_runtime_seconds
        budget_minutes = max(1, round(time_limit_seconds / 60))
        state.metadata["sandbox_preflight"] = await _prepare_budget(
            deadline_epoch,
            budget_minutes,
            report_min_words,
            report_max_words,
        )
        seed_report = (
            seed_reports.get(int(state.metadata.get("parent_epoch", -1)))
            if seed_reports
            else None
        )
        if seed_reports and seed_report is None:
            raise RuntimeError("no seed report for this sample's parent epoch")
        if seed_report is not None:
            # Through exec, so the file belongs to the agent's uid and stays editable.
            seeded = await sandbox().exec(
                ["sh", "-c", f"cat > {REPORT_PATH}"], input=seed_report
            )
            if not seeded.success:
                raise RuntimeError(f"could not seed {REPORT_PATH}: {seeded.stderr}")
            state.metadata["seed_report_words"] = len(seed_report.split())
        selected = inspect_agent(
            agent,
            claude_disallowed_tools=claude_disallowed_tools,
            env={
                "MBAB_DEADLINE_EPOCH": str(deadline_epoch),
                "MBAB_EARLIEST_FINISH_EPOCH": str(earliest_finish_epoch),
                "MBAB_BUDGET_MIN": str(budget_minutes),
                "MBAB_MIN_RUNTIME_FRACTION": str(min_runtime_fraction),
                "MBAB_REPORT_MIN_WORDS": str(report_min_words),
                "MBAB_REPORT_MAX_WORDS": str(report_max_words),
            },
        )
        agent_state = AgentState(messages=state.messages)
        limit_error = None
        terminal_refusal = False
        early_stop_resume_attempts = 0
        report_length_ping_count = 0
        minimum_runtime_reached = False
        underlying = selected

        @wraps(underlying)
        async def tracked(current):
            nonlocal agent_state
            agent_state = current
            agent_state = await underlying(current)
            return agent_state

        selected = tracked
        try:
            result = await run(
                selected,
                state.messages,
                limits=[time_limit(time_limit_seconds)],
            )
            agent_state, limit_error = result
            terminal_refusal = _terminal_refusal(agent_state)
            early_stop_resume_attempts = 0

            # Reuse the same Inspect agent object and its complete conversation,
            # which keeps the agent session and its cached prompt prefix intact.
            # Refusals and scoped limits are terminal outcomes, not invitations to
            # keep spending the budget.
            while (
                limit_error is None
                and not terminal_refusal
                and time.monotonic() - started < minimum_runtime_seconds
            ):
                if early_stop_resume_attempts >= MAX_EARLY_STOP_CONTINUATIONS:
                    _copy_agent_state(state, agent_state)
                    raise RuntimeError(
                        "minimum-runtime policy violation: agent completed normally "
                        f"{MAX_EARLY_STOP_CONTINUATIONS} times before the required "
                        f"{minimum_runtime_seconds}-second investigation period"
                    )
                elapsed = time.monotonic() - started
                remaining = max(0, math.ceil(time_limit_seconds - elapsed))
                if remaining == 0:
                    break
                early_stop_resume_attempts += 1
                continuation_messages = [
                    *agent_state.messages,
                    ChatMessageUser(
                        content=_minimum_runtime_continuation(
                            elapsed_seconds=elapsed,
                            minimum_runtime_seconds=minimum_runtime_seconds,
                            remaining_seconds=remaining,
                        )
                    ),
                ]
                agent_state, limit_error = await run(
                    selected,
                    continuation_messages,
                    limits=[time_limit(remaining)],
                )
                terminal_refusal = _terminal_refusal(agent_state)

            elapsed = time.monotonic() - started
            minimum_runtime_reached = elapsed >= minimum_runtime_seconds
            report, report_read_error = await _read_report()
            report_length_ping_count = 0

            # Do not make agents use more of their budget merely because they stop
            # early or write a short report. A single continuation is reserved for
            # correcting a report above the prompt's strict upper limit.
            revision = _overlong_revision(report, report_max_words)
            remaining = max(0, math.ceil(time_limit_seconds - elapsed))
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

        except Exception as exc:
            state.metadata["agent_error"] = f"{type(exc).__name__}: {exc}"[:1000]
            raise
        finally:
            report, report_read_error = await _read_report()
            minimum_runtime_reached = (
                time.monotonic() - started >= minimum_runtime_seconds
            )
            if agent != "react":
                ids = [
                    call.id
                    for message in agent_state.messages
                    if isinstance(message, ChatMessageAssistant)
                    for call in message.tool_calls or []
                ]
                try:
                    raw = await sandbox().read_file("/tmp/mbab-tool-events.jsonl")
                    records = []
                    malformed = 0
                    for line in raw.splitlines():
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            malformed += 1
                            continue
                        if isinstance(record, dict):
                            records.append(record)
                        else:
                            malformed += 1
                    state.metadata["tool_lifecycle_events"] = records
                    state.metadata["tool_lifecycle_malformed_records"] = malformed
                    state.metadata.update(hook_coverage(records, ids))
                    state.metadata["tool_hook_full_coverage"] = not malformed
                except Exception as exc:
                    state.metadata["tool_telemetry_error"] = (
                        f"{type(exc).__name__}: {exc}"[:500]
                    )
                    state.metadata.update(hook_coverage([], ids))
            state.metadata.update(event_coverage(transcript().events))
            state.metadata.update(trajectory_metrics(agent_state.messages))
            agent_stop_reason = (
                agent_state.output.stop_reason
                if agent_state.output and agent_state.output.choices
                else None
            )
            early_stop_hook_attempts = await _early_stop_hook_attempts()
            early_stop_attempts = early_stop_hook_attempts + early_stop_resume_attempts
            post_tool_hook_fired = await _marker_exists(
                "/tmp/mbab-post-tool-hook-fired"
            )
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
                min_runtime_fraction=min_runtime_fraction,
                early_stop_attempts=early_stop_attempts,
                early_stop_hook_attempts=early_stop_hook_attempts,
                early_stop_resume_attempts=early_stop_resume_attempts,
                minimum_runtime_seconds=minimum_runtime_seconds,
                minimum_runtime_reached=minimum_runtime_reached,
                post_tool_hook_fired=post_tool_hook_fired,
                stop_hook_fired=stop_hook_fired,
            )
            # Lazy import prevents the audit helper from creating a native
            # runtime import cycle. It reads the finalized trajectory only.
            try:
                from messageboard_audit_bench.run_audit import audit_native

                state.metadata["run_audit"] = audit_native(
                    agent_state.messages, list(transcript().events), state.metadata
                )
            except Exception as exc:
                state.metadata["run_audit_error"] = f"{type(exc).__name__}: {exc}"[:500]
        return state

    return solve
