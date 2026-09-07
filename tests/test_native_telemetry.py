import json
import subprocess
import sys
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import (
    ContentReasoning,
    ContentText,
    ModelOutput,
    ModelUsage,
    get_model,
)
from inspect_ai.solver import generate

from messageboard_audit_bench.native_telemetry import event_coverage, hook_coverage


def test_event_coverage_requires_raw_calls_and_complete_tool_evidence() -> None:
    events = [
        {
            "event": "model",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "completed": "2026-01-01T00:00:02+00:00",
            "span_id": "agent",
            "call": {"request": {}, "response": {}},
            "error": None,
            "retries": [],
            "output": {
                "choices": [{"message": {"content": [{"type": "reasoning"}]}}],
                "usage": {"reasoning_tokens": 3},
            },
        },
        {
            "event": "tool",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "completed": "2026-01-01T00:00:03+00:00",
            "span_id": "agent",
            "id": "call-1",
            "arguments": {"command": "rg x"},
            "result": "",
            "error": None,
        },
    ]
    result = event_coverage(events)
    assert result["raw_model_api_complete"] is True
    assert result["inspect_tool_inputs_complete"] is True
    assert result["inspect_tool_results_complete"] is True
    assert result["reasoning_text_model_events"] == 1
    assert result["reasoning_token_model_events"] == 1
    assert result["max_observed_model_event_overlap"] == 1


def test_event_coverage_marks_disabled_raw_api_logging_and_missing_fields() -> None:
    result = event_coverage(
        [
            {
                "event": "model",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "completed": "2026-01-01T00:00:01+00:00",
                "error": None,
                "retries": [],
            },
            {"event": "tool", "id": "call-1", "span_id": "agent", "arguments": None},
        ]
    )
    assert result["raw_model_api_complete"] is False
    assert result["inspect_tool_timestamps_complete"] is False
    assert result["inspect_tool_inputs_complete"] is False
    assert result["inspect_tool_results_complete"] is False


def test_hook_telemetry_captures_actual_lifecycle_payload_and_clock(
    tmp_path: Path,
) -> None:
    script = Path(__file__).parents[1] / "sandbox" / "tool_telemetry.py"
    path = tmp_path / "events.jsonl"
    payload = {
        "tool_name": "Bash",
        "tool_use_id": "tool-1",
        "tool_input": {"command": "rg needle"},
    }
    for event in ("PreToolUse", "PostToolUse"):
        subprocess.run(
            [sys.executable, str(script), "--event", event, "--path", str(path)],
            input=json.dumps(payload),
            text=True,
            check=True,
        )
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    coverage = hook_coverage(rows)
    assert rows[0]["payload"] == payload
    assert coverage["tool_hook_lifecycle_complete"] is True
    assert coverage["tool_hook_lifecycle_pairs_observed"] == 1
    assert coverage["tool_hook_correlated_pair_count"] == 1


def test_inspect_raw_model_event_preserves_provider_reasoning_and_usage(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(tmp_path / "trace.log"))
    output = ModelOutput.from_content(
        "mockllm/model",
        [ContentReasoning(reasoning="provider reasoning"), ContentText(text="answer")],
    )
    output.usage = ModelUsage(input_tokens=5, output_tokens=4, reasoning_tokens=3)
    model = get_model("mockllm/model", custom_outputs=lambda *_args: output)
    [log] = eval(
        Task(dataset=[Sample(input="test")], solver=generate()),
        model=model,
        display="none",
        log_dir=str(tmp_path),
        log_realtime=False,
        log_model_api=True,
    )
    sample = read_eval_log(log.location).samples[0]
    coverage = event_coverage(sample.events)
    assert coverage["raw_model_api_complete"] is True
    assert coverage["reasoning_text_model_events"] == 1
    assert coverage["reasoning_token_model_events"] == 1


def test_hook_coverage_measures_overlap_and_flags_unobserved_and_unfinished_calls():
    def row(event, call_id, clock):
        return dict(
            event=event,
            tool_call_id=call_id,
            monotonic_ns=clock,
            timestamp_utc="2026-01-01T00:00:00Z",
            source="cli_hook",
            payload={},
        )

    rows = [
        row("PreToolUse", "a", 1),
        row("PreToolUse", "b", 2),
        row("PostToolUse", "a", 3),
        row("PostToolUseFailure", "b", 4),
        row("PreToolUse", "unfinished", 5),
    ]
    coverage = hook_coverage(rows, ["a", "b", "unfinished", "not-recorded"])
    assert coverage["tool_hook_max_observed_overlap"] == 2
    assert coverage["tool_hook_missing_end_ids"] == ["unfinished"]
    assert coverage["tool_hook_unobserved_requested_ids"] == ["not-recorded"]
    assert coverage["tool_hook_lifecycle_complete"] is False
