import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from inspect_ai.scorer import Target

from messageboard_audit_bench.report_length import (
    acceptance_limits,
    feedback,
    instruction,
    limits,
    measure,
    overlong_feedback_if_changed,
    render_prompt,
    stop_reason,
)
from messageboard_audit_bench.scorer import report_length
from messageboard_audit_bench.solver import _fold
from messageboard_audit_bench.task import _prompt_for
from tests.test_solver import _run_dir, _state

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "messageboard_audit_bench" / "report_length.py"


@pytest.mark.parametrize(
    "count,accepted",
    [
        (0, False),
        (1, True),
        (2499, True),
        (2500, True),
        (3000, True),
        (3001, True),
        (3100, True),
        (3101, False),
    ],
)
def test_acceptance_is_separate_from_prompt_target(count: int, accepted: bool) -> None:
    result = measure(
        "word " * count,
        2500,
        3000,
        acceptance=(0, 3100),
    )
    assert result["report_length_compliant"] is accepted


@pytest.mark.parametrize(
    "low,high", [(0, 2), (2, 0), (3, 2), (-1, 2), (True, 2), (1.5, 2)]
)
def test_bad_target_config_is_rejected(low, high) -> None:
    with pytest.raises(ValueError):
        limits({"report_min_words": low, "report_max_words": high})


@pytest.mark.parametrize(
    "minimum,maximum", [(-1, 3100), (0, 2999), (0, True), (3400, 3100)]
)
def test_bad_acceptance_config_is_rejected(minimum, maximum) -> None:
    with pytest.raises(ValueError):
        acceptance_limits(
            {
                "report_min_words": 2500,
                "report_max_words": 3000,
                "report_accept_min_words": minimum,
                "report_accept_max_words": maximum,
            }
        )


def test_only_overlong_reports_trigger_hook_feedback(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    cache = tmp_path / "hook-state"

    assert overlong_feedback_if_changed(report, 2, 3, cache=cache) == ""
    report.write_text("one")
    assert overlong_feedback_if_changed(report, 2, 3, cache=cache) == ""
    report.write_text("one two three")
    assert overlong_feedback_if_changed(report, 2, 3, cache=cache) == ""
    report.write_text("one two three four")
    assert "remove at least 1" in overlong_feedback_if_changed(
        report, 2, 3, cache=cache
    )
    assert overlong_feedback_if_changed(report, 2, 3, cache=cache) == ""


def test_stop_ping_is_overlong_only_and_happens_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    cache = tmp_path / "stop-state"
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "9999999999")

    assert stop_reason(report, 2, 3, cache=cache) == ""
    report.write_text("one")
    assert stop_reason(report, 2, 3, cache=cache) == ""
    report.write_text("one two three four")
    assert "remove at least 1" in stop_reason(report, 2, 3, cache=cache)
    assert stop_reason(report, 2, 3, cache=cache) == ""


def test_stop_ping_does_not_start_a_rewrite_near_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text("one two three four")
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "1059")
    monkeypatch.setattr(
        "messageboard_audit_bench.report_length.time.time", lambda: 1000
    )

    assert stop_reason(report, 2, 3, cache=tmp_path / "stop-state") == ""


def test_hook_cli_is_standalone_and_silent_for_short_report(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("one")
    command = [
        sys.executable,
        "-S",
        str(SCRIPT),
        "--min-words",
        "2",
        "--max-words",
        "3",
        "--hook",
        "PostToolUse",
        "--report",
        str(report),
    ]
    result = subprocess.run(
        command,
        input="{}",
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {}


def test_prompt_contains_target_but_not_hidden_tolerance() -> None:
    prompt = _prompt_for("blind")
    assert instruction(0, 0) == ""
    assert "between 2,500 and 3,000 words" in prompt
    assert "3,000 words is a strict upper limit" in prompt
    assert "3,100" not in prompt


def test_embedded_prompt_renders_once_and_can_disable_length() -> None:
    template = (ROOT / "sandbox" / "prompts" / "blind-v2.txt").read_text()

    rendered = render_prompt(template, 37, 2500, 3000)
    disabled = render_prompt(template, 15, 0, 0)

    assert "Time budget: you have 37 minutes" in rendered
    assert "(2,500 to 3,000 words)" in rendered
    assert rendered.count("3,000 words is a strict upper limit") == 1
    assert "{{" not in rendered
    assert "strict upper limit" not in disabled
    assert "0 to 0" not in disabled


def test_prompt_renderer_cli_matches_library() -> None:
    template = ROOT / "sandbox" / "prompts" / "blind-v2.txt"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            "--template",
            str(template),
            "--budget-min",
            "37",
            "--min-words",
            "2500",
            "--max-words",
            "3000",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == render_prompt(template.read_text(), 37, 2500, 3000)


async def test_codex_fallback_report_is_measured(tmp_path: Path) -> None:
    run = _run_dir(tmp_path / "run")
    meta = json.loads((run / "meta.json").read_text())
    meta.update(
        report_min_words=2,
        report_max_words=8,
        report_accept_min_words=0,
        report_accept_max_words=8,
    )
    (run / "meta.json").write_text(json.dumps(meta))
    (run / "report.md").rename(run / "final_message.md")

    state = _fold(_state(), run, "codex")
    score = await report_length()(state, Target(""))

    assert state.metadata["report_words"] > 0
    assert state.metadata["report_source"].endswith("final_message.md")
    assert score.value == 1


def test_manual_feedback_still_describes_short_reports(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("one")
    note, within_max = feedback(report, 2, 3)
    assert "below the suggested range" in note
    assert within_max is True


async def test_legacy_run_without_length_policy_is_unscored() -> None:
    state = _state()
    state.output = None
    score = await report_length()(state, Target(""))

    assert math.isnan(score.value)
    assert score.answer == "disabled"
