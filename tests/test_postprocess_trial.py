import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "postprocess_trial.py"


def _run(tmp_path: Path, transcript: list[dict]) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "meta.json").write_text(
        json.dumps(
            {
                "agent": "claude",
                "model": "claude-test",
                "run_id": "abc",
                "report_min_words": 2,
                "report_max_words": 3,
                "report_accept_min_words": 0,
                "report_accept_max_words": 4,
            }
        )
    )
    (run / "transcript.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in transcript)
    )
    (run / "report.md").write_text("one two three")
    return run


def test_postprocess_is_standalone_and_preserves_normal_exit(tmp_path: Path) -> None:
    run = _run(tmp_path, [{"type": "result", "stop_reason": "end_turn"}])

    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), str(run), "0", "12"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    meta = json.loads((run / "meta.json").read_text())
    assert meta["exit_code"] == 0
    assert meta["wall_seconds"] == 12
    assert meta["report_words"] == 3


def test_postprocess_maps_structured_terminal_refusal_to_exit_five(
    tmp_path: Path,
) -> None:
    run = _run(
        tmp_path,
        [
            {"type": "system", "subtype": "model_refusal_no_fallback"},
            {"type": "result", "stop_reason": "refusal", "is_error": True},
        ],
    )

    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), str(run), "1", "4"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 5
    meta = json.loads((run / "meta.json").read_text())
    assert meta["exit_code"] == 5
    assert meta["model_refusal"] == {"events": 1, "terminal": True}


def test_postprocess_does_not_treat_recovered_refusal_as_terminal(
    tmp_path: Path,
) -> None:
    run = _run(
        tmp_path,
        [
            {"type": "system", "subtype": "model_refusal_no_fallback"},
            {"type": "assistant", "message": {"stop_reason": "refusal"}},
            {"type": "result", "subtype": "success", "stop_reason": "end_turn", "is_error": False},
        ],
    )
    meta = json.loads((run / "meta.json").read_text())
    meta["model_refusal"] = {"events": 1, "terminal": True}
    (run / "meta.json").write_text(json.dumps(meta))

    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), str(run), "0", "12"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    meta = json.loads((run / "meta.json").read_text())
    assert meta["exit_code"] == 0
    assert "model_refusal" not in meta


def test_postprocess_does_not_accept_a_conversational_fallback(tmp_path: Path) -> None:
    run = _run(tmp_path, [{"type": "result", "stop_reason": "end_turn"}])
    (run / "report.md").rename(run / "final_message.md")
    meta = json.loads((run / "meta.json").read_text())
    meta["agent"] = "codex"
    (run / "meta.json").write_text(json.dumps(meta))
    result = subprocess.run([sys.executable, "-S", str(SCRIPT), str(run), "0", "12"], capture_output=True, text=True)
    assert result.returncode == 0
    saved = json.loads((run / "meta.json").read_text())
    assert saved["report_source"] is None
    assert saved["report_words"] == 0
    assert saved["report_length_compliant"] is False


def _resampled(tmp_path: Path, transcript: list[dict], resampling: dict, rc: int, seconds: int) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    run = _run(tmp_path, transcript)
    meta = json.loads((run / "meta.json").read_text())
    meta.update(model="claude-opus-5", budget_min=1, refusal_resampling=resampling)
    (run / "meta.json").write_text(json.dumps(meta))
    subprocess.run([sys.executable, "-S", str(SCRIPT), str(run), str(rc), str(seconds)], capture_output=True, text=True)
    return json.loads((run / "meta.json").read_text())


FLAG = [{"type": "system", "subtype": "init", "session_id": "s1"},
        {"type": "assistant", "message": {"model": "claude-opus-5", "stop_reason": "tool_use"}},
        {"type": "system", "subtype": "model_refusal_no_fallback", "original_model": "claude-opus-5"},
        {"type": "assistant", "message": {"model": "<synthetic>", "stop_reason": "refusal"}},
        {"type": "result", "stop_reason": "refusal", "is_error": True}]


def test_a_resampled_flag_is_counted_but_does_not_end_the_run(tmp_path: Path) -> None:
    resumed = [{"type": "system", "subtype": "init", "session_id": "s1"},
               {"type": "assistant", "message": {"model": "claude-opus-5", "stop_reason": "tool_use"}}]  # killed at the deadline
    meta = _resampled(tmp_path, FLAG + resumed, {"flag_cap": 3, "flags": 1, "resumes": 1, "outcome": None}, 124, 70)
    assert "model_refusal" not in meta and "model_fallback" not in meta
    assert meta["termination"] == "active_time_limit" and meta["safety_flags"] == 1


def test_the_flag_cap_ends_the_run_as_refusal_cap(tmp_path: Path) -> None:
    meta = _resampled(tmp_path, FLAG * 3, {"flag_cap": 3, "flags": 3, "resumes": 2, "outcome": "cap_reached"}, 1, 20)
    assert meta["termination"] == "refusal_cap" and meta["safety_flags"] == 3
    assert "model_refusal" not in meta and "model_fallback" not in meta
    deadline = _resampled(tmp_path / "d", FLAG, {"flag_cap": 3, "flags": 1, "resumes": 0, "outcome": "deadline"}, 1, 60)
    assert deadline["termination"] == "active_time_limit" and deadline["stopped_at_active_limit"] is True


def test_another_claude_model_answering_is_a_fallback(tmp_path: Path) -> None:
    other = [{"type": "assistant", "message": {"model": "claude-opus-4-8", "stop_reason": "end_turn"}},
             {"type": "result", "subtype": "success", "stop_reason": "end_turn", "is_error": False}]
    meta = _resampled(tmp_path, FLAG[:2] + other, {"flag_cap": 3, "flags": 0, "resumes": 0, "outcome": None}, 0, 70)
    assert meta["model_served"] == "claude-opus-4-8" and meta["model_fallback"]["trigger"] == "response_model"
