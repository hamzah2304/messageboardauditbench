from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
from inspect_ai.tool import ToolCall, ToolCallError

from messageboard_audit_bench.run_audit import (
    _claude_raw_observations,
    _codex_raw_observations,
    _hook_evidence,
    _proxy_evidence,
    audit_native,
    audit_run,
    tool_evidence,
    write_audit,
)


def test_tool_evidence_distinguishes_attempts_from_recorded_results() -> None:
    messages = [
        ChatMessageAssistant(
            content="",
            tool_calls=[
                ToolCall(
                    id="network",
                    function="bash",
                    arguments={"command": "curl https://example.test"},
                ),
                ToolCall(
                    id="files", function="bash", arguments={"command": "rg token data"}
                ),
                ToolCall(
                    id="missing", function="bash", arguments={"command": "cat absent"}
                ),
                ToolCall(
                    id="read",
                    function="Read",
                    arguments={"file_path": "/work/data/events.jsonl"},
                ),
            ],
        ),
        ChatMessageTool(
            content="failed",
            tool_call_id="network",
            function="bash",
            error=ToolCallError(type="error", message="network unreachable"),
        ),
        ChatMessageTool(content="rows", tool_call_id="files", function="bash"),
        ChatMessageTool(content="data", tool_call_id="read", function="Read"),
    ]
    result = tool_evidence(messages)
    assert result["network_command_attempts"][0]["result_success"] is False
    assert result["file_access_command_attempts"][0]["result_success"] is True
    assert result["tool_results_missing"] == ["missing"]
    assert result["tool_failures_observed"][0]["tool_call_id"] == "network"
    assert result["file_access_confirmed"] == [
        {"tool_call_id": "read", "tool": "Read", "path": "/work/data/events.jsonl"}
    ]
    assert result["network_access_confirmed"] == []


def test_audit_run_marks_missing_artifacts_as_unknown_coverage(tmp_path) -> None:
    result = audit_run(tmp_path)
    coverage = result["logging_coverage"]
    assert coverage["raw_transcript_available"] is False
    assert "transcript.jsonl" in coverage["missing_artifacts"]
    assert "unknown coverage" in coverage["coverage_note"]
    assert result["audit_error"] == "transcript.jsonl or meta.agent is unavailable"


def test_write_audit_creates_json_and_concise_markdown(tmp_path) -> None:
    output = tmp_path / "out"
    write_audit(tmp_path, output)
    assert (output / "audit.json").is_file()
    text = (output / "audit.md").read_text()
    assert "# Run audit" in text
    assert "unknown coverage" in text


def test_claude_raw_thinking_and_assistant_model_are_retained(tmp_path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":""}}}',
                '{"type":"assistant","message":{"model":"claude-sonnet-5","content":[{"type":"thinking","thinking":"","signature":"encrypted"}]}}',
            ]
        )
        + "\n"
    )
    observed = _claude_raw_observations(transcript)
    assert observed["served_observations"] == [
        {"model": "claude-sonnet-5", "source": "assistant.message.model"}
    ]
    assert observed["raw_reasoning_available"] is True
    assert (
        "stream_event.content_block_delta[type=thinking_delta]"
        in observed["raw_reasoning_sources"]
    )


def test_codex_declared_model_is_not_marked_served_and_hook_ids_are_not_compared(
    tmp_path,
) -> None:
    rollout = tmp_path / "codex_sessions" / "a" / "rollout-a.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text('{"type":"turn_context","payload":{"model":"gpt-5.6-terra"}}\n')
    observed = _codex_raw_observations(tmp_path)
    assert observed["served_observations"] == []
    assert observed["declared_observations"] == [
        {"model": "gpt-5.6-terra", "source": "codex_rollout.turn_context.model"}
    ]
    hooks = [
        {
            "source": "cli_hook",
            "event": "PreToolUse",
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "monotonic_ns": 1,
            "tool_call_id": "exec-1",
            "tool_name": "Bash",
            "payload": {},
        },
        {
            "source": "cli_hook",
            "event": "PostToolUse",
            "timestamp_utc": "2026-01-01T00:00:01+00:00",
            "monotonic_ns": 2,
            "tool_call_id": "exec-1",
            "tool_name": "Bash",
            "payload": {},
        },
    ]
    coverage = _hook_evidence("codex", hooks, ["item-1"])
    assert coverage["tool_hook_lifecycle_complete"] is True
    assert (
        coverage["tool_hook_requested_id_mapping_status"]
        == "unavailable_incomparable_id_spaces"
    )
    assert "tool_hook_unobserved_requested_ids" not in coverage


def test_proxy_records_are_not_attributed_to_agent(tmp_path) -> None:
    path = tmp_path / "proxy.log"
    path.write_text("deny CONNECT collusion.wiki:443\nallow CONNECT api.example:443\n")
    evidence = _proxy_evidence(path)
    assert evidence["allowed_tunnel_records"] == 1
    assert evidence["denied_tunnel_records"] == 1
    assert (
        evidence["attempt_attribution"] == "unknown_mixed_harness_preflight_and_agent"
    )


def test_audit_native_preserves_unknown_served_model_and_malformed_hooks() -> None:
    messages = [
        ChatMessageAssistant(
            content="",
            tool_calls=[
                ToolCall(id="call-1", function="bash", arguments={"command": "ls"})
            ],
        ),
        ChatMessageTool(content="ok", tool_call_id="call-1", function="bash"),
    ]
    hooks = [
        {
            "source": "cli_hook",
            "event": "PreToolUse",
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "monotonic_ns": 1,
            "tool_call_id": "call-1",
            "tool_name": "Bash",
            "payload": {},
        },
        {
            "source": "cli_hook",
            "event": "PostToolUse",
            "timestamp_utc": "2026-01-01T00:00:01+00:00",
            "monotonic_ns": 2,
            "tool_call_id": "call-1",
            "tool_name": "Bash",
            "payload": {},
        },
    ]
    result = audit_native(
        messages,
        [],
        {
            "model": "requested-only",
            "tool_lifecycle_events": hooks,
            "tool_lifecycle_malformed_records": 1,
        },
    )
    assert result["audit_schema"] == 2
    assert len(result["audit_code_sha256"]) == 64
    assert result["served_model"]["served"] is None
    assert result["logging_coverage"]["malformed_tool_telemetry_records"] == 1
    assert result["logging_coverage"]["full_coverage"] is False
    assert result["hook_coverage"]["tool_hook_lifecycle_complete"] is True


def test_audit_run_marks_malformed_tool_telemetry_as_incomplete(tmp_path) -> None:
    (tmp_path / "meta.json").write_text('{"agent":"claude","model":"test"}')
    (tmp_path / "transcript.jsonl").write_text(
        '{"type":"system","subtype":"init","model":"test"}\n'
        '{"type":"assistant","message":{"model":"test","content":[]}}\n'
    )
    (tmp_path / "tool-events.jsonl").write_text("not-json\n")
    result = audit_run(tmp_path)
    assert result["logging_coverage"]["malformed_tool_telemetry_records"] == 1
    assert result["logging_coverage"]["tool_telemetry_full_coverage"] is False
    assert result["logging_coverage"]["runner_events_available"] is False
