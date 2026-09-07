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
