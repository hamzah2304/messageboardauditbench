import json
from collections import Counter
from pathlib import Path

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ChatMessageUser

from messageboard_audit_bench.transcripts import parse_claude, parse_codex


def _write_jsonl(path: Path, events: list[dict]) -> Path:
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return path


def _assert_tool_pairs(parsed) -> None:
    calls = Counter(
        call.id
        for message in parsed.messages
        if isinstance(message, ChatMessageAssistant)
        for call in (message.tool_calls or [])
    )
    results = Counter(
        message.tool_call_id
        for message in parsed.messages
        if isinstance(message, ChatMessageTool)
    )
    assert calls == results
    diagnostics = parsed.extra["transcript_diagnostics"]
    assert diagnostics["unmatched_tool_calls"] == []
    assert diagnostics["unmatched_tool_results"] == []


def test_parse_codex_tool_round_trip(tmp_path: Path) -> None:
    transcript = _write_jsonl(
        tmp_path / "codex.jsonl",
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "cmd_1",
                    "type": "command_execution",
                    "command": "rg OpenAI data",
                    "aggregated_output": "42 matches\n",
                    "exit_code": 0,
                },
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 2,
                },
            },
        ],
    )

    parsed = parse_codex(transcript)

    assert len(parsed.messages) == 2
    assert isinstance(parsed.messages[0], ChatMessageAssistant)
    assert isinstance(parsed.messages[1], ChatMessageTool)
    assert parsed.tool_calls == 1
    assert parsed.reasoning_tokens == 2
    _assert_tool_pairs(parsed)


def test_parse_claude_merges_blocks_and_tool_result(tmp_path: Path) -> None:
    transcript = _write_jsonl(
        tmp_path / "claude.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "Checking logs."}],
                    "usage": {"input_tokens": 8, "output_tokens": 2},
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "model": "claude-test",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "Bash",
                            "input": {"command": "wc -l data/revisions.jsonl"},
                        }
                    ],
                    "usage": {"input_tokens": 8, "output_tokens": 2},
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": "14591 data/revisions.jsonl",
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "hook context"}]
                },
            },
        ],
    )

    parsed = parse_claude(transcript)

    assert len(parsed.messages) == 3
    assert isinstance(parsed.messages[0], ChatMessageAssistant)
    assert parsed.messages[0].tool_calls is not None
    assert parsed.messages[0].tool_calls[0].function == "Bash"
    assert isinstance(parsed.messages[1], ChatMessageTool)
    assert isinstance(parsed.messages[2], ChatMessageUser)
    assert "hook context" in parsed.messages[2].text
    assert parsed.turns == 1
    assert parsed.tool_calls == 1
    _assert_tool_pairs(parsed)


def test_parse_claude_is_loss_aware_and_repairs_tool_pairs(tmp_path: Path) -> None:
    transcript = _write_jsonl(
        tmp_path / "claude-edge.jsonl",
        [
            {"type": "system", "subtype": "init", "model": "claude-test", "claude_code_version": "2.1"},
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [
                        {"type": "thinking", "thinking": "inspect"},
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "false"}},
                    ],
                },
            },
            # Claude's verbose stream sometimes repeats a complete content block.
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "false"}},
                    ],
                },
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "orphan", "content": [{"type": "text", "text": "failed"}], "is_error": True}]},
            },
            {"type": "fallback", "from": {"model": "old"}, "to": {"model": "new"}},
            {"type": "new_event", "payload": "kept"},
        ],
    )
    with transcript.open("a") as stream:
        stream.write("not json\n[]\n")

    parsed = parse_claude(transcript)
    diagnostics = parsed.extra["transcript_diagnostics"]

    assert diagnostics["malformed_json"] == 1
    assert diagnostics["non_object_events"] == 1
    assert diagnostics["duplicate_blocks"] == 1
    assert diagnostics["orphan_tool_results"] == 1
    assert diagnostics["incomplete_tool_calls"] == 1
    assert diagnostics["unknown_events"] == {"new_event": 1}
    assert parsed.extra["model_fallbacks"][0]["to"] == {"model": "new"}
    assert any("unmapped Claude event" in str(message.content) for message in parsed.messages)
    _assert_tool_pairs(parsed)


def test_parse_claude_preserves_intentionally_repeated_text(tmp_path: Path) -> None:
    transcript = _write_jsonl(
        tmp_path / "claude-repeated-text.jsonl",
        [
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [{"type": "text", "text": "still checking"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [{"type": "text", "text": "still checking"}],
                },
            },
        ],
    )

    parsed = parse_claude(transcript)

    assert len(parsed.messages[0].content) == 2
    assert parsed.extra["transcript_diagnostics"]["duplicate_blocks"] == 0


def test_parse_codex_merges_lifecycle_and_preserves_errors(tmp_path: Path) -> None:
    transcript = _write_jsonl(
        tmp_path / "codex-edge.jsonl",
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": "false", "status": "in_progress"}},
            {"type": "item.updated", "item": {"id": "c1", "type": "command_execution", "aggregated_output": "oops"}},
            {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "exit_code": 1, "status": "failed"}},
            {"type": "item.completed", "item": {"id": "e1", "type": "error", "message": "model failed"}},
            {"type": "item.completed", "item": {"id": "u1", "type": "future_item", "value": 42}},
            {"type": "turn.failed", "error": {"message": "turn failed"}},
        ],
    )

    parsed = parse_codex(transcript)
    diagnostics = parsed.extra["transcript_diagnostics"]

    assert parsed.extra["codex_thread_id"] == "thread-1"
    assert diagnostics["unknown_items"] == {"future_item": 1}
    assert any(
        isinstance(message, ChatMessageTool) and message.error is not None
        for message in parsed.messages
    )
    assert any("future_item" in str(message.content) for message in parsed.messages)
    assert any("turn failed" in str(message.content) for message in parsed.messages)
    _assert_tool_pairs(parsed)


def test_parse_codex_closes_incomplete_tools(tmp_path: Path) -> None:
    transcript = _write_jsonl(
        tmp_path / "codex-incomplete.jsonl",
        [
            {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": "sleep 99"}},
            {"type": "item.started", "item": {"id": "f1", "type": "file_change", "changes": [{"kind": "update", "path": "report.md"}]}},
        ],
    )

    parsed = parse_codex(transcript)

    assert parsed.extra["transcript_diagnostics"]["incomplete_tool_calls"] == 2
    assert all(
        message.error is not None and message.error.type == "cancelled"
        for message in parsed.messages
        if isinstance(message, ChatMessageTool)
    )
    _assert_tool_pairs(parsed)
