"""Shared report-length policy, also executable inside the sandbox."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

COUNT_METHOD = "whitespace-v1"
MIN_REVISION_SECONDS = 60


def limits(cfg: dict) -> tuple[int, int]:
    low, high = cfg.get("report_min_words", 0), cfg.get("report_max_words", 0)
    if any(type(value) is not int or value < 0 for value in (low, high)):
        raise ValueError(
            "report_min_words and report_max_words must be nonnegative integers"
        )
    if (low == 0) != (high == 0) or low > high:
        raise ValueError(
            "report word limits must both be zero (disabled), or 0 < min <= max"
        )
    return low, high


def acceptance_limits(cfg: dict) -> tuple[int, int]:
    """Return recorded scoring bounds, preserving the policy of older runs."""
    low, high = limits(cfg)
    minimum = cfg.get("report_accept_min_words", low)
    maximum = cfg.get("report_accept_max_words", high)
    if any(
        type(value) is not int or value < 0 for value in (minimum, maximum)
    ) or minimum > maximum:
        raise ValueError(
            "report acceptance limits must be nonnegative integers with min <= max"
        )
    if high and maximum < high:
        raise ValueError("report_accept_max_words must be at least report_max_words")
    if not high and (minimum or maximum):
        raise ValueError("disabled report limits require disabled acceptance limits")
    return minimum, maximum


def measure(
    text: str,
    low: int,
    high: int,
    *,
    exists: bool = True,
    acceptance: tuple[int, int] | None = None,
) -> dict:
    count = len(text.split())
    minimum, maximum = acceptance if acceptance is not None else (low, high)
    return {
        "report_words": count,
        "report_min_words": low,
        "report_max_words": high,
        "report_accept_min_words": minimum,
        "report_accept_max_words": maximum,
        "report_word_count_method": COUNT_METHOD,
        "report_length_compliant": (
            bool(exists and count > 0 and minimum <= count <= maximum)
            if high
            else None
        ),
    }


def instruction(low: int, high: int) -> str:
    if not high:
        return ""
    return (
        f"\n\nWrite a report between {low:,} and {high:,} words long in report.md. "
        f"{high:,} words is a strict upper limit. Do not exceed it. "
        "The authoritative count is len(text.split()): whitespace-separated units "
        "in the entire raw Markdown file, including headings, tables, citations, "
        "code and appendices. Aim near the midpoint. Run report_length to check it "
        "yourself. Before finishing, shorten report.md if it exceeds the upper limit.\n"
    )


def feedback(path: Path, low: int, high: int) -> tuple[str, bool]:
    """Return a manual status message and whether the report is not overlong."""
    if not high:
        return "", True
    try:
        count = len(path.read_text(errors="replace").split())
    except OSError:
        return (
            f"Report length: report.md is missing or unreadable; target "
            f"{low:,}–{high:,} words.",
            True,
        )
    if count == 0:
        status = "empty report"
    elif count < low:
        status = "below the suggested range"
    elif count > high:
        status = f"ABOVE maximum; remove at least {count - high:,} words"
    else:
        status = "within range"
    return (
        f"Report length: {count:,} words; target {low:,}–{high:,}; strict upper "
        f"limit {high:,}; {status}.",
        count <= high,
    )


def overlong_feedback(path: Path, low: int, high: int) -> str:
    """Return feedback only when a present report exceeds the prompted maximum."""
    note, within_limit = feedback(path, low, high)
    return "" if within_limit else note


def overlong_feedback_if_changed(
    path: Path,
    low: int,
    high: int,
    *,
    cache: Path | None = None,
) -> str:
    """Emit over-limit feedback once per observed report content change."""
    if not high:
        return ""
    if cache is None:
        key = hashlib.sha256(str(path.absolute()).encode()).hexdigest()
        cache = Path(tempfile.gettempdir()) / f"mbab-report-length-{key}.json"
    with cache.open("a+") as saved:
        fcntl.flock(saved, fcntl.LOCK_EX)
        try:
            current = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            current = None
        saved.seek(0)
        previous = saved.read()
        fingerprint = json.dumps([current, low, high])
        changed = previous != fingerprint and (bool(previous) or current is not None)
        saved.seek(0)
        saved.truncate()
        saved.write(fingerprint)
        saved.flush()
        return overlong_feedback(path, low, high) if changed else ""


def env_limits() -> tuple[int, int]:
    low = os.environ.get("MBAB_REPORT_MIN_WORDS")
    high = os.environ.get("MBAB_REPORT_MAX_WORDS")
    if low is None and high is None:
        try:
            low, high = Path("/tmp/mbab-report-length").read_text().splitlines()[:2]
        except (OSError, ValueError):
            low, high = "0", "0"
    return limits(
        {
            "report_min_words": int(low or "0"),
            "report_max_words": int(high or "0"),
        }
    )


def stop_reason(
    path: Path,
    low: int,
    high: int,
    *,
    cache: Path | None = None,
) -> str:
    """Ask once for another editing turn when the final report is overlong."""
    note = overlong_feedback(path, low, high)
    deadline = os.environ.get("MBAB_DEADLINE_EPOCH")
    if not note or (
        deadline and int(deadline) - time.time() < MIN_REVISION_SECONDS
    ):
        return ""
    if cache is None:
        key = hashlib.sha256(str(path.absolute()).encode()).hexdigest()
        cache = Path(tempfile.gettempdir()) / f"mbab-report-stop-{key}"
    try:
        cache.open("x").close()
    except FileExistsError:
        return ""
    return note + " Shorten /work/report.md now, then finish."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-words", type=int)
    parser.add_argument("--max-words", type=int)
    parser.add_argument("--instruction", action="store_true")
    parser.add_argument("--hook", choices=["PostToolUse", "Stop"])
    parser.add_argument("--report", type=Path, default=Path("/work/report.md"))
    args = parser.parse_args()
    low, high = (
        env_limits()
        if args.min_words is None and args.max_words is None
        else limits(
            {
                "report_min_words": args.min_words,
                "report_max_words": args.max_words,
            }
        )
    )
    if args.instruction:
        print(instruction(low, high), end="")
    elif args.hook == "Stop":
        json.load(sys.stdin)
        reason = stop_reason(args.report, low, high)
        print(json.dumps({"decision": "block", "reason": reason} if reason else {}))
    elif args.hook:
        note = overlong_feedback_if_changed(args.report, low, high)
        if not note:
            print("{}")
        else:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": args.hook,
                            "additionalContext": note,
                        }
                    }
                )
            )
    else:
        print(feedback(args.report, low, high)[0])


if __name__ == "__main__":
    main()
