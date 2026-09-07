import json
from pathlib import Path

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool

from messageboard_audit_bench.transcripts import parse_claude, parse_codex


def _write_jsonl(path: Path, events: list[dict]) -> Path:
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return path


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
        ],
    )

    parsed = parse_claude(transcript)

    assert len(parsed.messages) == 2
    assert isinstance(parsed.messages[0], ChatMessageAssistant)
    assert parsed.messages[0].tool_calls is not None
    assert parsed.messages[0].tool_calls[0].function == "Bash"
    assert isinstance(parsed.messages[1], ChatMessageTool)
    assert parsed.turns == 1
    assert parsed.tool_calls == 1
