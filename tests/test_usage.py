import json
from pathlib import Path

from messageboard_audit_bench.usage import summarize


def _run_with_result(path: Path) -> Path:
    path.mkdir()
    result = {
        "type": "result",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 5,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 10,
        },
    }
    (path / "transcript.jsonl").write_text(json.dumps(result) + "\n")
    return path


def test_claude_usage_reports_disjoint_input_categories(tmp_path: Path) -> None:
    usage = summarize(_run_with_result(tmp_path / "claude"), "claude")

    assert usage["usage_schema"] == 2
    assert usage["input_tokens"] == 190
    assert usage["input_tokens_uncached"] == 100
    assert usage["total_tokens"] == 195
    assert usage["cache_read_fraction"] == 80 / 190


def test_react_usage_treats_cached_tokens_as_prompt_subset(tmp_path: Path) -> None:
    usage = summarize(_run_with_result(tmp_path / "react"), "react")

    assert usage["input_tokens"] == 100
    assert usage["input_tokens_uncached"] == 10
    assert usage["total_tokens"] == 105
    assert usage["cache_read_fraction"] == 0.8


def test_killed_stream_uses_per_message_usage_for_claude_and_react(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "killed"
    run_dir.mkdir()
    assistant = {
        "type": "assistant",
        "message": {
            "id": "msg-1",
            "content": [{"type": "text", "text": "still working"}],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 5,
                "cache_read_input_tokens": 80,
                "cache_creation_input_tokens": 10,
            },
        },
    }
    (run_dir / "transcript.jsonl").write_text(json.dumps(assistant) + "\n")

    claude = summarize(run_dir, "claude")
    react = summarize(run_dir, "react")

    assert claude["usage_source"] == "per_message_sum"
    assert claude["input_tokens"] == 190
    assert claude["input_tokens_uncached"] == 100
    assert react["usage_source"] == "per_message_sum"
    assert react["input_tokens"] == 100
    assert react["input_tokens_uncached"] == 10
    assert react["peak_context_tokens"] == 100


def test_codex_rollout_normalizes_cached_input(tmp_path: Path) -> None:
    run_dir = tmp_path / "codex"
    sessions = run_dir / "codex_sessions"
    sessions.mkdir(parents=True)
    event = {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": 200,
                    "cached_input_tokens": 160,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 7,
                },
                "last_token_usage": {"input_tokens": 120},
            },
        },
    }
    (sessions / "rollout-test.jsonl").write_text(json.dumps(event) + "\n")

    usage = summarize(run_dir, "codex")

    assert usage["usage_source"] == "codex_rollout"
    assert usage["input_tokens"] == 200
    assert usage["input_tokens_uncached"] == 40
    assert usage["cache_read_fraction"] == 0.8
    assert usage["total_tokens"] == 220
