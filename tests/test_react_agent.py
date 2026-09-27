import importlib.util
import json
import sys
from pathlib import Path

import pytest

from messageboard_audit_bench.usage import summarize_claude_stream

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def react(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "messageboard_audit_bench"))
    spec = importlib.util.spec_from_file_location("react_agent", ROOT / "sandbox/react_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Investigate and write report.md.")
    monkeypatch.setattr(sys, "argv", ["react_agent", "--model", "fixture/model", "--prompt-file", str(prompt),
                                     "--cwd", str(tmp_path), "--max-turns", "2"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-not-a-key")
    monkeypatch.setenv("MBAB_EARLIEST_FINISH_EPOCH", "9999999999")
    monkeypatch.setenv("MBAB_REPORT_MIN_WORDS", "0")
    monkeypatch.setenv("MBAB_REPORT_MAX_WORDS", "0")
    return module


def response(**choice_overrides):
    return {"id": "fixture-response", "provider": "fixture", "choices": [{
        "message": {"content": "Report complete."}, "finish_reason": "stop", **choice_overrides,
    }], "usage": {"prompt_tokens": 12, "completion_tokens": 3, "cost": 0.01}}


@pytest.mark.parametrize("payload", [
    response(finish_reason="error"),
    response(native_finish_reason="ERROR"),
    response(error={"code": 502}),
    {**response(), "error": {"code": 502}},
    {"choices": []},
    {"choices": [{"message": None}]},
])
def test_provider_failure_exits_nonzero_and_is_counted(react, tmp_path, monkeypatch, capsys, payload):
    monkeypatch.setattr(react, "chat", lambda *args: (payload, 0, 1))
    assert react.main() == 1
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(capsys.readouterr().out)
    events = [json.loads(line) for line in transcript.read_text().splitlines()]
    assert events[-1]["subtype"] == "error"
    assert events[-1]["is_error"] is True
    assert events[-1]["terminal_reason"] == "api_error"
    summary = summarize_claude_stream(transcript, input_includes_cache=True)
    assert summary["api_errors"] == 1
    assert summary["is_error"] is True
    if payload.get("usage"):
        assert summary["input_tokens"] == 12
        assert summary["cost_usd"] == 0.01


def test_error_completion_does_not_execute_partial_tool_calls(react, monkeypatch, capsys):
    payload = response(finish_reason="error", message={"tool_calls": [{
        "id": "call-1", "function": {"name": "bash", "arguments": '{"command":"touch sentinel"}'},
    }]})
    monkeypatch.setattr(react, "chat", lambda *args: (payload, 0, 1))
    monkeypatch.setattr(react, "run_tool", lambda *args: pytest.fail("executed failed provider output"))
    assert react.main() == 1


def test_ordinary_completion_is_returned_to_investigation(react, tmp_path, monkeypatch, capsys):
    payload = response(message={"content": "Agents unable to read cross-origin responses built beacon pages."})
    replies = iter([payload, response()])
    reminders = []

    def chat(base, key, body):
        reminders.extend(m["content"] for m in body["messages"] if m["role"] == "user")
        return next(replies), 0, 1

    monkeypatch.setattr(react, "chat", chat)
    # Advance across the policy threshold without sleeping or accessing /work.
    policy = sys.modules["runtime_policy"]
    original = policy.early_stop_reason
    times = iter([100, 200])
    monkeypatch.setattr(policy, "early_stop_reason", lambda event: original(
        event, earliest_finish_epoch=200, now=next(times), state_file=tmp_path / "state",
    ))
    assert react.main() == 0
    assert any("does not accept a normal completion" in str(m) for m in reminders)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["num_turns"] == 2
    assert events[-1]["is_error"] is False
