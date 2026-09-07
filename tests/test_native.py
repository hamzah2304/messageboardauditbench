from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from inspect_ai import Task, eval
from inspect_ai.agent import AgentState
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageTool,
    ModelOutput,
    ModelUsage,
    get_model,
)
from inspect_ai.tool import ToolCall
from inspect_ai.util import LimitExceededError

import messageboard_audit_bench.native as native
from messageboard_audit_bench.scorer import process_metrics
from tests.test_solver import _state


@pytest.mark.asyncio
async def test_native_solver_keeps_trajectory_and_prefers_report(monkeypatch) -> None:
    selected = object()
    captured = {}
    agent_state = AgentState(
        messages=[
            *_state().messages,
            ChatMessageAssistant(
                content="checking",
                tool_calls=[
                    ToolCall(id="call-1", function="bash", arguments={"cmd": "ls"})
                ],
            ),
            ChatMessageTool(content="data", tool_call_id="call-1", function="bash"),
            ChatMessageAssistant(content="done"),
        ]
    )

    def fake_agent(*_args, **kwargs):
        captured["agent_kwargs"] = kwargs
        return selected

    async def fake_prepare(
        deadline_epoch, budget_minutes, report_min_words, report_max_words
    ):
        captured.update(
            deadline_epoch=deadline_epoch,
            budget_minutes=budget_minutes,
            report_min_words=report_min_words,
            report_max_words=report_max_words,
        )

    monkeypatch.setattr(native, "inspect_agent", fake_agent)
    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(
        native,
        "sample_model_usage",
        lambda: {
            "provider/model": ModelUsage(
                input_tokens=10,
                input_tokens_cache_read=80,
                input_tokens_cache_write=10,
                output_tokens=7,
                reasoning_tokens=3,
                total_tokens=107,
            )
        },
    )

    async def fake_run(agent, messages, limits):
        captured.update(agent=agent, messages=messages, limits=limits)
        return agent_state, None

    async def fake_report():
        return "# Audit report\n\nEvidence.", None

    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent("codex", 90, min_runtime_fraction=0)(
        _state(), None
    )

    assert captured["agent"].__wrapped__ is selected
    assert captured["budget_minutes"] == 2
    assert captured["report_min_words"] == 0
    assert captured["report_max_words"] == 0
    assert captured["agent_kwargs"]["env"]["MBAB_BUDGET_MIN"] == "2"
    assert (
        int(captured["agent_kwargs"]["env"]["MBAB_DEADLINE_EPOCH"])
        == captured["deadline_epoch"]
    )
    assert captured["messages"][0].content == "Investigate"
    assert state.messages == agent_state.messages
    assert state.output.completion.startswith("# Audit report")
    assert state.metadata["backend"] == "inspect"
    assert state.metadata["report_written"] is True
    assert state.metadata["turns"] == 2
    assert state.metadata["tool_calls"] == 1
    assert state.metadata["input_tokens"] == 100
    assert state.metadata["input_tokens_uncached"] == 10
    assert state.metadata["cache_read_tokens"] == 80
    assert state.metadata["cache_read_fraction"] == 0.8
    assert state.metadata["output_tokens"] == 7
    assert state.metadata["reasoning_tokens"] == 3
    assert state.metadata["total_tokens"] == 107
    assert state.metadata["run_audit"]["served_model"]["served"] is None
    assert state.metadata["run_audit"]["tool_evidence"]["tool_calls_observed"] == 1


@pytest.mark.asyncio
async def test_native_solver_records_scoped_timeout_and_partial_report(
    monkeypatch,
) -> None:
    agent_state = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="partial")]
    )
    limit = LimitExceededError(type="time", value=60, limit=60)

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())

    async def fake_prepare(*_args):
        return None

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)

    async def fake_run(*_args, **_kwargs):
        return agent_state, limit

    async def fake_report():
        return "partial report", None

    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent("claude", 60)(_state(), None)

    assert state.output.completion == "partial report"
    assert state.metadata["limit_exceeded"] == "time"
    assert state.metadata["limit_value"] == 60


def test_native_solver_writes_a_standard_eval_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(tmp_path / "trace.log"))
    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())

    async def fake_prepare(*_args):
        return None

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)

    async def fake_run(_agent, messages, limits):
        return AgentState(
            messages=[*messages, ChatMessageAssistant(content="finished")]
        ), None

    async def fake_report():
        return "# Native report", None

    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)
    model = get_model(
        "mockllm/model",
        custom_outputs=lambda *_args: ModelOutput(
            model="mockllm/model", completion="unused", usage=ModelUsage()
        ),
    )
    task = Task(
        dataset=[Sample(input="Investigate", id="native-smoke")],
        solver=native.inspect_native_agent("codex", 60, min_runtime_fraction=0),
        scorer=process_metrics(),
    )

    [log] = eval(
        task,
        model=model,
        display="none",
        log_realtime=False,
        log_dir=str(tmp_path / "logs"),
    )

    assert log.status == "success"
    assert log.samples is not None
    sample = log.samples[0]
    assert sample.output.completion == "# Native report"
    assert sample.metadata["backend"] == "inspect"
    assert sample.scores["process_metrics"].value == 1.0


@pytest.mark.asyncio
async def test_native_solver_never_grades_chat_when_report_is_missing(
    monkeypatch,
) -> None:
    agent_state = AgentState(
        messages=[
            *_state().messages,
            ChatMessageAssistant(content="excellent findings"),
        ]
    )
    agent_state.output = ModelOutput.from_content(
        model="mockllm/model", content="excellent findings"
    )

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())

    async def fake_prepare(*_args):
        return None

    async def fake_run(*_args, **_kwargs):
        return agent_state, None

    async def fake_report():
        return "", "FileNotFoundError: /work/report.md"

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent("claude", 60, min_runtime_fraction=0)(
        _state(), None
    )

    assert state.output.completion == "(no report written)"
    assert state.metadata["report_written"] is False
    assert state.metadata["report_read_error"].startswith("FileNotFoundError")


@pytest.mark.asyncio
async def test_native_solver_marks_terminal_refusal_after_bounded_retries(
    monkeypatch,
) -> None:
    agent_state = AgentState(
        messages=[
            *_state().messages,
            ChatMessageAssistant(content="I cannot help with that."),
        ]
    )
    agent_state.output = ModelOutput.from_content(
        model="anthropic/test-model",
        content="I cannot help with that.",
        stop_reason="content_filter",
    )

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())

    async def fake_prepare(*_args):
        return None

    async def fake_run(*_args, **_kwargs):
        return agent_state, None

    async def fake_report():
        return "", "FileNotFoundError: /work/report.md"

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent("claude", 60)(_state(), None)

    assert state.output.completion == "(no report written)"
    assert state.metadata["terminal_refusal"] is True
    assert state.metadata["refusal_stop_reason"] == "content_filter"
    assert state.metadata["refusal_retry_limit"] == 2
    assert state.metadata["refusal_policy"] == "same_model_only"


@pytest.mark.asyncio
async def test_native_solver_resumes_same_agent_until_minimum_runtime(
    monkeypatch,
) -> None:
    selected = object()
    first = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="initial done")]
    )
    first.output = ModelOutput.from_content(
        model="mockllm/model", content="initial done"
    )
    continued = AgentState(
        messages=[*first.messages, ChatMessageAssistant(content="now done")]
    )
    continued.output = ModelOutput.from_content(
        model="mockllm/model", content="now done"
    )
    calls = []
    # started, first completion/continuation construction, then completion
    # after the continuation has used enough of the 100-second budget.
    clock = iter([0.0, 10.0, 10.0, 80.0, 80.0, 80.0])

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: selected)
    monkeypatch.setattr(
        native,
        "time",
        SimpleNamespace(time=lambda: 1_000.0, monotonic=lambda: next(clock, 80.0)),
    )

    async def fake_prepare(*_args):
        return None

    async def fake_run(agent, messages, limits):
        calls.append((agent, messages, limits))
        return (first, None) if len(calls) == 1 else (continued, None)

    async def fake_report():
        return "report", None

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent("codex", 100)(_state(), None)

    assert len(calls) == 2
    assert calls[0][0] is calls[1][0]
    assert calls[0][0].__wrapped__ is selected
    assert isinstance(calls[1][1][-1], native.ChatMessageUser)
    continuation = calls[1][1][-1].content
    assert "worked for about 10 seconds" in continuation
    assert "earliest acceptable finish is 75 seconds" in continuation
    assert "about 90 seconds remaining" in continuation
    assert "Do not idle" in continuation
    assert state.metadata["early_stop_attempts"] == 1
    assert state.metadata["minimum_runtime_seconds"] == 75
    assert state.metadata["minimum_runtime_reached"] is True


@pytest.mark.asyncio
async def test_native_solver_fails_instead_of_accepting_rapid_early_stops(
    monkeypatch,
) -> None:
    agent_state = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="done")]
    )
    agent_state.output = ModelOutput.from_content(model="mockllm/model", content="done")
    calls = 0

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        native,
        "time",
        SimpleNamespace(time=lambda: 1_000.0, monotonic=lambda: 0.0),
    )

    async def fake_prepare(*_args):
        return None

    async def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return agent_state, None

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)

    with pytest.raises(RuntimeError, match="minimum-runtime policy violation"):
        await native.inspect_native_agent("react", 100)(_state(), None)

    assert calls == native.MAX_EARLY_STOP_CONTINUATIONS + 1


@pytest.mark.parametrize("fraction", [-0.1, 1, 1.1])
def test_native_solver_rejects_invalid_minimum_runtime_fraction(
    fraction: float,
) -> None:
    with pytest.raises(ValueError, match="min_runtime_fraction"):
        native.inspect_native_agent("claude", 60, min_runtime_fraction=fraction)


@pytest.mark.asyncio
async def test_native_solver_pings_one_overlong_report_and_resumes_same_agent(
    monkeypatch,
) -> None:
    selected = object()
    first = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="done")]
    )
    first.output = ModelOutput.from_content(model="mockllm/model", content="done")
    corrected = AgentState(
        messages=[*first.messages, ChatMessageAssistant(content="shortened")]
    )
    corrected.output = ModelOutput.from_content(
        model="mockllm/model", content="shortened"
    )
    reports = iter([("one two three four", None), ("one two", None)])
    calls = []

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: selected)

    async def fake_prepare(*_args):
        return None

    async def fake_run(agent, messages, limits):
        calls.append((agent, messages, limits))
        return (first, None) if len(calls) == 1 else (corrected, None)

    async def fake_report():
        return next(reports, ("one two", None))

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent(
        "codex",
        120,
        report_min_words=2,
        report_max_words=3,
        min_runtime_fraction=0,
    )(_state(), None)

    assert len(calls) == 2
    assert calls[0][0] is calls[1][0]
    assert calls[0][0].__wrapped__ is selected
    assert isinstance(calls[1][1][-1], native.ChatMessageUser)
    assert "above the strict 3-word limit" in calls[1][1][-1].content
    assert state.output.completion == "one two"
    assert state.metadata["report_length_ping_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("report", ["", "one", "one two three"])
async def test_native_solver_does_not_continue_missing_short_or_valid_reports(
    monkeypatch, report: str
) -> None:
    agent_state = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="done")]
    )
    agent_state.output = ModelOutput.from_content(model="mockllm/model", content="done")
    calls = 0

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())

    async def fake_prepare(*_args):
        return None

    async def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return agent_state, None

    async def fake_report():
        return report, None if report else "FileNotFoundError: /work/report.md"

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent(
        "claude",
        60,
        report_min_words=2,
        report_max_words=3,
        min_runtime_fraction=0,
    )(_state(), None)

    assert calls == 1
    assert state.metadata["report_length_ping_count"] == 0


@pytest.mark.asyncio
async def test_native_solver_does_not_ping_after_time_limit(monkeypatch) -> None:
    agent_state = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="partial")]
    )
    agent_state.output = ModelOutput.from_content(
        model="mockllm/model", content="partial"
    )
    limit = LimitExceededError(type="time", value=60, limit=60)
    calls = 0

    monkeypatch.setattr(native, "inspect_agent", lambda *_args, **_kwargs: object())

    async def fake_prepare(*_args):
        return None

    async def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return agent_state, limit

    async def fake_report():
        return "one two three four", None

    monkeypatch.setattr(native, "_prepare_budget", fake_prepare)
    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent(
        "react",
        60,
        report_min_words=2,
        report_max_words=3,
        min_runtime_fraction=0,
    )(_state(), None)

    assert calls == 1
    assert state.metadata["report_length_ping_count"] == 0


@pytest.mark.parametrize("agent_name", ["claude", "codex", "react"])
def test_native_agents_use_the_shared_bounded_refusal_policy(
    monkeypatch, agent_name: str
) -> None:
    captured = {}

    def fake_adapter(*_args, **kwargs):
        captured.update(kwargs)
        return object()

    if agent_name == "claude":
        monkeypatch.setattr(native, "claude_code", fake_adapter)
    elif agent_name == "codex":
        monkeypatch.setattr(native, "codex_cli", fake_adapter)
    else:
        monkeypatch.setattr(native, "react", fake_adapter)

    native.inspect_agent(
        agent_name,
        claude_disallowed_tools=["WebSearch"],
        env={"MBAB_BUDGET_MIN": "1"},
    )

    assert captured["retry_refusals"] == native.REFUSAL_RETRY_LIMIT == 2
    if agent_name == "claude":
        assert captured["env"]["CLAUDE_CONFIG_DIR"] == native.CLAUDE_CONFIG_DIR
    elif agent_name == "codex":
        assert captured["config_overrides"] == {"features.hooks": "true"}
    else:
        assert len(captured["tools"]) == 2


@pytest.mark.asyncio
async def test_native_preflight_installs_claude_and_codex_hooks(monkeypatch) -> None:
    writes = {}

    class FakeSandbox:
        async def exec(self, _cmd):
            return SimpleNamespace(success=True, stdout='{"ok": true}')

        async def write_file(self, path, content):
            writes[path] = content

    monkeypatch.setattr(native, "sandbox", lambda: FakeSandbox())

    await native._prepare_budget(1234, 20, 2500, 3000)

    claude = json.loads(writes[f"{native.CLAUDE_CONFIG_DIR}/settings.json"])
    codex = json.loads(writes[f"{native.CODEX_HOME}/hooks.json"])
    assert claude["apiKeyHelper"] == "echo $ANTHROPIC_AUTH_TOKEN"
    assert "switchModelsOnFlag" not in claude
    assert {
        k: v for k, v in claude["hooks"].items() if k != "PostToolUseFailure"
    } == codex["hooks"]
    assert "PostToolUseFailure" in claude["hooks"]
    commands = [
        hook["command"]
        for group in codex["hooks"].values()
        for entry in group
        for hook in entry["hooks"]
    ]
    assert any("/sandbox/time_left.sh" in command for command in commands)
    assert any("--hook PostToolUse" in command for command in commands)
    assert any("runtime_policy.py --hook Stop" in command for command in commands)


@pytest.mark.parametrize("agent_name", ["claude", "codex", "react"])
def test_real_inspect_agent_adapters_construct(agent_name: str) -> None:
    selected = native.inspect_agent(
        agent_name,
        claude_disallowed_tools=["WebSearch"],
        env={"MBAB_BUDGET_MIN": "1"},
    )

    assert callable(selected)


def test_inspect_agent_rejects_unknown_adapter() -> None:
    with pytest.raises(ValueError, match="unsupported native agent"):
        native.inspect_agent(
            "unknown",
            claude_disallowed_tools=[],
        )
