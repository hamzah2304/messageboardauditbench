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

    assert usage["usage_schema"] == 3
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


def test_partial_per_message_reasoning_stays_unknown(tmp_path: Path) -> None:
    run_dir = tmp_path / "partial"
    run_dir.mkdir()
    events = [
        {"type": "assistant", "message": {"id": "one", "content": [], "usage": {
            "input_tokens": 10, "output_tokens": 2, "reasoning_tokens": 4,
        }}},
        {"type": "assistant", "message": {"id": "two", "content": [], "usage": {
            "input_tokens": 20, "output_tokens": 3,
        }}},
    ]
    (run_dir / "transcript.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    usage = summarize(run_dir, "claude")

    assert usage["reasoning_tokens"] is None
    assert usage["reasoning_tokens_source"] == "unavailable_or_partial"


def test_null_reasoning_is_unknown_not_reported_zero(tmp_path: Path) -> None:
    run_dir = tmp_path / "null-reasoning"
    run_dir.mkdir()
    event = {"type": "assistant", "message": {"id": "one", "content": [], "usage": {
        "input_tokens": 10, "output_tokens": 2, "reasoning_tokens": None,
    }}}
    (run_dir / "transcript.jsonl").write_text(json.dumps(event) + "\n")

    usage = summarize(run_dir, "claude")

    assert usage["reasoning_tokens"] is None
    assert usage["reasoning_tokens_source"] == "unavailable"


def test_codex_rollouts_sum_sessions_but_not_snapshots_or_copies(tmp_path: Path) -> None:
    run_dir = tmp_path / "codex-multiple"
    sessions = run_dir / "codex_sessions"
    sessions.mkdir(parents=True)

    def rollout(path: Path, session: str, totals: list[dict]) -> None:
        events = [{"type": "session_meta", "payload": {"session_id": session}}]
        for total in totals:
            events.append({"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": total, "last_token_usage": {"input_tokens": total["input_tokens"]},
            }}})
        path.write_text("".join(json.dumps(event) + "\n" for event in events))

    first = {"input_tokens": 10, "output_tokens": 1, "reasoning_output_tokens": 0}
    final = {"input_tokens": 30, "output_tokens": 3, "reasoning_output_tokens": 2}
    rollout(sessions / "rollout-copy-a.jsonl", "shared", [first, final])
    rollout(sessions / "rollout-copy-b.jsonl", "shared", [first, final])
    rollout(sessions / "rollout-other.jsonl", "other", [{"input_tokens": 7, "output_tokens": 1}])

    usage = summarize(run_dir, "codex")

    assert usage["sessions"] == 2
    assert usage["input_tokens"] == 37
    assert usage["output_tokens"] == 4
    assert usage["reasoning_tokens"] is None
    assert usage["reasoning_tokens_source"] == "unavailable_or_partial"
    assert usage["api_calls"] == 3


def test_codex_retry_attempts_are_recorded_without_guessing_their_usage(tmp_path: Path) -> None:
    run_dir = tmp_path / "codex-retry"
    run_dir.mkdir()
    (run_dir / "transcript.attempt1.jsonl").write_text('{"type":"error"}\n')
    (run_dir / "transcript.attempt2.jsonl").write_text('{"type":"error"}\n')
    (run_dir / "transcript.jsonl").write_text(json.dumps({
        "type": "turn.completed",
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }) + "\n")

    usage = summarize(run_dir, "codex")

    assert usage["retry_attempt_transcripts"] == 2
    assert usage["attempts_recorded"] == 3
    assert usage["input_tokens"] == 10


def test_codex_equal_sized_calls_are_distinct(tmp_path: Path) -> None:
    sessions = tmp_path / "codex_sessions"
    sessions.mkdir()
    events = [{"type": "session_meta", "payload": {"id": "one"}}]
    for total in (10, 20):
        events.append({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": total},
            "last_token_usage": {"input_tokens": 10},
        }}})
    (sessions / "rollout-one.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    assert summarize(tmp_path, "codex")["api_calls"] == 2
