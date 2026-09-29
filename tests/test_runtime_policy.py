import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from messageboard_audit_bench.runtime_policy import (
    early_stop_reason,
    fraction,
    instruction,
    minimum_runtime_seconds,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "messageboard_audit_bench" / "runtime_policy.py"


def test_ordinary_early_finish_is_blocked_and_recorded(tmp_path: Path) -> None:
    state = tmp_path / "runtime-policy.json"

    reason = early_stop_reason(
        {}, earliest_finish_epoch=200.0, now=100.0, state_file=state
    )

    assert "does not accept a normal completion" in reason
    assert "Do not idle or sleep" in reason
    assert json.loads(state.read_text())["early_finish_blocks"] == 1
    assert "#2" in early_stop_reason(
        {}, earliest_finish_epoch=200.0, now=110.0, state_file=state
    )


@pytest.mark.parametrize(
    "event",
    [
        {"is_error": True},
        {"stop_reason": "refusal"},
        {"last_assistant_message": "I can't help with that request."},
        {"last_assistant_message": "I'm sorry, I cannot assist with your task."},
        {"last_assistant_message": "I must refuse this request."},
        {"stop_reason": "content_filter"},
    ],
)
def test_terminal_refusal_or_error_is_not_retained(
    tmp_path: Path, event: dict[str, object]
) -> None:
    assert (
        early_stop_reason(
            event,
            earliest_finish_epoch=200.0,
            now=100.0,
            state_file=tmp_path / "state",
        )
        == ""
    )
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("message", [
    "Unable to reach data APIs from a browser due to CORS, the agent wrapped fetches.",
    "I won't add unverified interpretation of those at the buzzer; the report is final.",
    "Incident 1: agents unable to read cross-origin responses built beacon pages.",
    "The agent's workaround for being unable to return a large file through URLQuery.",
    "I cannot verify the operator's identity. The report is complete.",
    'The agent said "I cannot assist with this request."',
])
def test_investigation_summary_cannot_bypass_runtime_policy(tmp_path, message):
    assert early_stop_reason(
        {"last_assistant_message": message}, earliest_finish_epoch=200, now=100,
        state_file=tmp_path / "state",
    )


@pytest.mark.parametrize("event", [
    {"reason": "The report documents failed requests and error responses."},
    {"status": "no_error"},
    {"reason": True},
])
def test_only_explicit_terminal_statuses_bypass_runtime_policy(tmp_path, event):
    assert early_stop_reason(event, earliest_finish_epoch=200, now=100, state_file=tmp_path / "state")


def test_threshold_passes_and_fraction_is_validated(tmp_path: Path) -> None:
    assert (
        early_stop_reason(
            {}, earliest_finish_epoch=100.0, now=100.0, state_file=tmp_path / "state"
        )
        == ""
    )
    assert fraction("0.75") == 0.75
    for invalid in ("1", "1.01", "nan", "inf"):
        with pytest.raises(ValueError):
            fraction(invalid)
    assert "75%" in instruction(0.75, 20)
    assert minimum_runtime_seconds(10, 0.333) == 4
    assert "disabled" in instruction(0, 20)


def test_hook_cli_is_stdlib_standalone_and_blocks_early(tmp_path: Path) -> None:
    env = os.environ | {
        "MBAB_EARLIEST_FINISH_EPOCH": "9999999999",
        "MBAB_MIN_RUNTIME_FRACTION": "0.75",
        "MBAB_REPORT_MIN_WORDS": "0",
        "MBAB_REPORT_MAX_WORDS": "0",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            "--hook",
            "Stop",
            "--report",
            str(tmp_path / "report.md"),
        ],
        input="{}",
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "75%" in output["reason"]


def test_cli_uses_ceiling_for_cross_backend_threshold() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            "--minimum-runtime-seconds",
            "--fraction",
            "0.333",
            "--budget-minutes",
            str(10 / 60),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "4"
