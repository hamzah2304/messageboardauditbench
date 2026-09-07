"""Minimum-runtime policy shared by the subscription harnesses.

This module deliberately uses only the standard library.  A copy is placed in
the Docker image and is called directly by Claude Code/Codex Stop hooks and by
the small subscription ReAct loop.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_MIN_RUNTIME_FRACTION = 0.75
_STATE_FILE = Path("/work/.mbab-runtime-policy.json")
_REFUSAL = re.compile(
    r"\b(?:i (?:can(?:not|'t)|won't)|unable to|cannot assist|can't assist|"
    r"must refuse|policy prevents)\b",
    re.IGNORECASE,
)


def fraction(value: str | float | None) -> float:
    """Validate the configurable portion of the budget that must elapse."""
    if value is None:
        return DEFAULT_MIN_RUNTIME_FRACTION
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "min_runtime_fraction must be a finite number in [0, 1)"
        ) from exc
    if not math.isfinite(result) or not 0 <= result < 1:
        raise ValueError("min_runtime_fraction must be a finite number in [0, 1)")
    return result


def minimum_runtime_seconds(budget_seconds: int | float, share: float) -> int:
    """Return the cross-backend threshold, always rounded up to a full second."""
    return math.ceil(float(budget_seconds) * fraction(share))


def _percent(share: float) -> str:
    return f"{share * 100:g}%"


def instruction(min_runtime_fraction: float, budget_minutes: float) -> str:
    """The policy disclosure appended to subscription prompts."""
    if min_runtime_fraction == 0:
        return (
            "\n\nMinimum working period: disabled for this run. You may finish "
            "when you are satisfied with the investigation.\n"
        )
    minimum = budget_minutes * min_runtime_fraction
    return (
        "\n\nThe evaluation intentionally will not accept a normal completion until "
        f"at least {_percent(min_runtime_fraction)} of the {budget_minutes:g}-minute time "
        f"budget has elapsed (about {minimum:g} minutes). If you try to finish earlier, "
        "you will be returned to the investigation. Use that time for meaningful "
        "verification, evidence gathering, and improving report.md; do not idle or sleep. "
        "Keep report.md in place: edit it, never delete, move, or "
        "truncate it. If report.md is missing at the deadline the "
        "trial scores zero.\n"
    )


def _terminal(event: dict[str, Any]) -> bool:
    """Do not retain a session that has explicitly errored or refused.

    Hook payloads differ across CLI versions, so this intentionally looks only
    at terminal/status fields and the final assistant message, not arbitrary
    prompt or transcript text.
    """
    for key in ("is_error", "error", "status", "stop_reason", "reason", "type"):
        value = event.get(key)
        if value is True:
            return True
        if isinstance(value, str) and any(
            token in value.lower() for token in ("error", "refusal", "reject", "fail")
        ):
            return True
    message = event.get("last_assistant_message") or event.get("assistant_message")
    if isinstance(message, str) and _REFUSAL.search(message):
        return True
    return False


def _record(state_file: Path, *, now: float) -> int:
    """Persist a small, inspectable count in the run's /work mount."""
    try:
        previous = json.loads(state_file.read_text())
    except (OSError, ValueError, TypeError):
        previous = {}
    count = int(previous.get("early_finish_blocks", 0)) + 1
    try:
        state_file.write_text(
            json.dumps(
                {"early_finish_blocks": count, "last_block_epoch": round(now, 3)}
            )
            + "\n"
        )
    except OSError:
        # The policy must not crash an agent if a nonstandard harness does not
        # expose /work. Enforcement still works; only the audit marker is lost.
        pass
    return count


def early_stop_reason(
    event: dict[str, Any],
    *,
    earliest_finish_epoch: float | None = None,
    now: float | None = None,
    min_runtime_fraction: float | None = None,
    state_file: Path = _STATE_FILE,
) -> str:
    """Return a Stop-hook block reason only for an ordinary premature finish."""
    if _terminal(event):
        return ""
    if earliest_finish_epoch is None:
        raw = os.environ.get("MBAB_EARLIEST_FINISH_EPOCH")
        if not raw:
            return ""
        try:
            earliest_finish_epoch = float(raw)
        except ValueError:
            return ""
    now = time.time() if now is None else now
    if now >= earliest_finish_epoch:
        return ""
    try:
        share = fraction(
            min_runtime_fraction
            if min_runtime_fraction is not None
            else os.environ.get("MBAB_MIN_RUNTIME_FRACTION")
        )
    except ValueError:
        share = DEFAULT_MIN_RUNTIME_FRACTION
    count = _record(state_file, now=now)
    remaining = max(1, int((earliest_finish_epoch - now + 59) // 60))
    return (
        f"The evaluation intentionally does not accept a normal completion before "
        f"{_percent(share)} of its time budget has elapsed (about {remaining} more minute"
        f"{'s' if remaining != 1 else ''} to that threshold). Continue the investigation "
        "with meaningful verification, evidence gathering, or improvements to report.md. "
        "Do not idle or sleep. Keep report.md in place: edit it, never "
        "delete, move, or truncate it. If report.md is missing at the "
        "deadline the trial scores zero. This is early-completion reminder "
        f"#{count}."
    )


def stop_reason(event: dict[str, Any], *, report: Path) -> str:
    """Combine the pre-existing one-shot overlength correction and runtime policy."""
    # Imported lazily so `python -S /sandbox/runtime_policy.py` remains
    # standalone when report_length.py is next to this file in the image.
    from report_length import env_limits
    from report_length import stop_reason as report_length_stop_reason

    # A terminal refusal/error is never held for either policy.
    if _terminal(event):
        return ""
    length_reason = report_length_stop_reason(report, *env_limits())
    runtime_reason = early_stop_reason(event)
    return " ".join(part for part in (length_reason, runtime_reason) if part)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook", choices=["Stop"])
    parser.add_argument("--report", type=Path, default=Path("/work/report.md"))
    parser.add_argument("--instruction", action="store_true")
    parser.add_argument("--minimum-runtime-seconds", action="store_true")
    parser.add_argument("--fraction")
    parser.add_argument("--budget-minutes", type=float)
    parser.add_argument("--validate-fraction")
    args = parser.parse_args()
    if args.validate_fraction is not None:
        try:
            print(f"{fraction(args.validate_fraction):g}")
        except ValueError as exc:
            parser.error(str(exc))
        return
    if args.instruction:
        print(
            instruction(
                fraction(args.fraction),
                args.budget_minutes if args.budget_minutes is not None else 20,
            ),
            end="",
        )
        return
    if args.minimum_runtime_seconds:
        print(
            minimum_runtime_seconds(
                (args.budget_minutes if args.budget_minutes is not None else 20) * 60,
                fraction(args.fraction),
            )
        )
        return
    if args.hook:
        try:
            event = json.load(sys.stdin)
        except json.JSONDecodeError:
            event = {"error": "invalid hook payload"}
        reason = stop_reason(
            event if isinstance(event, dict) else {"error": "bad hook payload"},
            report=args.report,
        )
        print(json.dumps({"decision": "block", "reason": reason} if reason else {}))


if __name__ == "__main__":
    main()
