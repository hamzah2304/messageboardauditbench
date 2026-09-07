from __future__ import annotations

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
                tool_calls=[ToolCall(id="call-1", function="bash", arguments={"cmd": "ls"})],
            ),
            ChatMessageTool(content="data", tool_call_id="call-1", function="bash"),
            ChatMessageAssistant(content="done"),
        ]
    )

    def fake_agent(*_args, **kwargs):
        captured["agent_kwargs"] = kwargs
        return selected

    async def fake_prepare(deadline_epoch, budget_minutes, *_args):
        captured.update(deadline_epoch=deadline_epoch, budget_minutes=budget_minutes)

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

    async def fake_run(agent, messages, limits, **_kwargs):
        captured.update(agent=agent, messages=messages, limits=limits)
        return agent_state, None

    async def fake_report():
        return "# Audit report\n\nEvidence.", None

    monkeypatch.setattr(native, "run", fake_run)
    monkeypatch.setattr(native, "_read_report", fake_report)

    state = await native.inspect_native_agent("codex", 90)(_state(), None)

    assert captured["agent"].__wrapped__ is selected
    assert captured["budget_minutes"] == 2
    assert captured["agent_kwargs"]["env"]["MBAB_BUDGET_MIN"] == "2"
    assert int(captured["agent_kwargs"]["env"]["MBAB_DEADLINE_EPOCH"]) == captured["deadline_epoch"]
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


@pytest.mark.asyncio
async def test_native_solver_records_scoped_timeout_and_partial_report(monkeypatch) -> None:
    agent_state = AgentState(messages=[*_state().messages, ChatMessageAssistant(content="partial")])
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

    async def fake_run(_agent, messages, limits, **_kwargs):
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
        solver=native.inspect_native_agent("codex", 60),
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
async def test_native_solver_never_grades_chat_when_report_is_missing(monkeypatch) -> None:
    agent_state = AgentState(
        messages=[*_state().messages, ChatMessageAssistant(content="excellent findings")]
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

    state = await native.inspect_native_agent("claude", 60)(_state(), None)

    assert state.output.completion == "(no report written)"
    assert state.metadata["report_written"] is False
    assert state.metadata["report_read_error"].startswith("FileNotFoundError")


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


@pytest.mark.asyncio
async def test_feedback_counts_only_changed_report(monkeypatch):
    from inspect_ai.model import GenerateConfig

    report = [""]

    async def read():
        return report[0], None

    monkeypatch.setattr(native, "_read_report", read)
    callback = native._feedback_filter({"MBAB_REPORT_MIN_WORDS": "2", "MBAB_REPORT_MAX_WORDS": "3", "MBAB_DEADLINE_EPOCH": "9999999999"})

    async def note():
        result = await callback(None, [], [], "auto", GenerateConfig())
        return result.input[-1].text

    assert "Report length" not in await note()
    report[0] = "one two three four"
    assert "Remove at least 1 words" in await note()
    assert "Report length" not in await note()
    report[0] = "one two"
    assert "Report length: 2 words" in await note()
    assert "seconds remaining" in await note()


@pytest.mark.asyncio
async def test_native_automatically_shortens_before_original_deadline(monkeypatch):
    reports = ["word " * 3101]
    calls = []

    async def prepare(*args):
        return {"ok": True}

    async def read():
        return reports[0], None

    async def fake_run(agent, messages, limits, **kwargs):
        calls.append(messages)
        if len(calls) == 2:
            reports[0] = "word " * 2999
        return AgentState(messages=[*messages, ChatMessageAssistant(content="done")]), None

    monkeypatch.setattr(native, "_prepare_budget", prepare)
    monkeypatch.setattr(native, "_read_report", read)
    monkeypatch.setattr(native, "inspect_agent", lambda *a, **kw: object())
    monkeypatch.setattr(native, "run", fake_run)
    state = _state()
    state.metadata.update(report_min_words=2500, report_max_words=3000, report_accept_min_words=0, report_accept_max_words=3100)
    result = await native.inspect_native_agent("codex", 60, report_min_words=2500, report_max_words=3000)(state, None)
    assert len(calls) == 2
    assert "3101 words" in calls[1][-1].text
    assert "original deadline" in calls[1][-1].text
    assert result.metadata["report_words"] == 2999
    assert result.metadata["report_length_compliant"] is True
    assert result.metadata["report_length_revision_count"] == 1


@pytest.mark.asyncio
async def test_native_retains_partial_report_and_messages_on_adapter_error(monkeypatch):
    async def prepare(*args):
        return {"ok": True}

    async def failing_agent(state):
        state.messages.append(ChatMessageAssistant(content="partial investigation"))
        raise RuntimeError("adapter failed")

    async def read():
        return "partial evidence", None

    monkeypatch.setattr(native, "_prepare_budget", prepare)
    monkeypatch.setattr(native, "_read_report", read)
    monkeypatch.setattr(native, "inspect_agent", lambda *a, **kw: failing_agent)
    state = _state()
    with pytest.raises(RuntimeError, match="adapter failed"):
        await native.inspect_native_agent("codex", 60)(state, None)
    assert state.messages[-1].text == "partial investigation"
    assert state.output.completion == "partial evidence"
    assert state.metadata["agent_error"] == "RuntimeError: adapter failed"


def test_reasoning_count_unknown_is_distinct_from_reported_zero():
    assert native._usage_metadata([ModelUsage(reasoning_tokens=0)])["reasoning_tokens"] == 0
    assert native._usage_metadata([ModelUsage()])["reasoning_tokens"] is None
    assert native._usage_metadata([ModelUsage(reasoning_tokens=10), ModelUsage()])["reasoning_tokens"] is None
