from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
from inspect_ai.tool import ToolCall, ToolCallError

from messageboard_audit_bench.run_audit import audit_run, tool_evidence


def test_tool_evidence_distinguishes_attempts_from_recorded_results() -> None:
    messages = [
        ChatMessageAssistant(content="", tool_calls=[
            ToolCall(id="network", function="bash", arguments={"command": "curl https://example.test"}),
            ToolCall(id="files", function="bash", arguments={"command": "rg token data"}),
            ToolCall(id="missing", function="bash", arguments={"command": "cat absent"}),
        ]),
        ChatMessageTool(content="failed", tool_call_id="network", function="bash", error=ToolCallError(type="error", message="network unreachable")),
        ChatMessageTool(content="rows", tool_call_id="files", function="bash"),
    ]
    result = tool_evidence(messages)
    assert result["network_command_attempts"][0]["result_success"] is False
    assert result["file_access_command_attempts"][0]["result_success"] is True
    assert result["tool_results_missing"] == ["missing"]
    assert result["tool_failures_observed"][0]["tool_call_id"] == "network"


def test_audit_run_marks_missing_artifacts_as_unknown_coverage(tmp_path) -> None:
    result = audit_run(tmp_path)
    coverage = result["logging_coverage"]
    assert coverage["raw_transcript_available"] is False
    assert "transcript.jsonl" in coverage["missing_artifacts"]
    assert "unknown coverage" in coverage["coverage_note"]
    assert result["audit_error"] == "transcript.jsonl or meta.agent is unavailable"
