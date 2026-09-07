"""Shared report-length policy, also executed standalone inside the sandbox."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

COUNT_METHOD = "whitespace-v1"


def limits(cfg: dict) -> tuple[int, int]:
    low, high = cfg.get("report_min_words", 0), cfg.get("report_max_words", 0)
    if any(type(v) is not int or v < 0 for v in (low, high)):
        raise ValueError("report_min_words and report_max_words must be nonnegative integers")
    if (low == 0) != (high == 0) or low > high:
        raise ValueError("report word limits must both be zero (disabled), or 0 < min <= max")
    return low, high


def acceptance_limits(cfg: dict) -> tuple[int, int]:
    """Use saved acceptance bounds; older runs retain their original limits."""
    low, high = limits(cfg)
    minimum = cfg.get("report_accept_min_words", low)
    maximum = cfg.get("report_accept_max_words", high)
    if any(type(v) is not int or v < 0 for v in (minimum, maximum)) or minimum > maximum:
        raise ValueError("report acceptance limits must be nonnegative integers with min <= max")
    if high and maximum < high:
        raise ValueError("report_accept_max_words must be at least report_max_words")
    if not high and (minimum or maximum):
        raise ValueError("disabled report limits require disabled acceptance limits")
    return minimum, maximum


def measure(text: str, low: int, high: int, *, exists: bool = True,
            acceptance: tuple[int, int] | None = None) -> dict:
    count = len(text.split())
    minimum, maximum = acceptance if acceptance is not None else (low, high)
    return {
        "report_words": count,
        "report_min_words": low,
        "report_max_words": high,
        "report_accept_min_words": minimum,
        "report_accept_max_words": maximum,
        "report_word_count_method": COUNT_METHOD,
        "report_length_compliant": bool(exists and count > 0 and minimum <= count <= maximum) if high else None,
    }


def instruction(low: int, high: int) -> str:
    if not high:
        return ""
    return (
        f"\n\nWrite a report between {low:,} and {high:,} words long in report.md. "
        f"{high:,} words is a strict upper limit. Do not exceed it. "
        "The authoritative count is len(text.split()): whitespace-separated units in the entire "
        "raw Markdown file, including headings, tables, citations, code and appendices. "
        "Aim near the midpoint. You receive the current count when a tool call changes report.md; "
        "run python3 /sandbox/report_length.py to check it yourself. Before finishing, shorten report.md if it exceeds the upper limit. "
        "\n"
    )


def render_prompt(template: str, budget_min: int, low: int, high: int) -> str:
    """Render shared config values; templates may supply their own length prose."""
    embedded_length = "{{#REPORT_LENGTH}}" in template
    text = re.sub(
        r"\{\{#REPORT_LENGTH\}\}(.*?)\{\{/REPORT_LENGTH\}\}",
        lambda match: match.group(1) if high else "",
        template, flags=re.DOTALL,
    )
    for token, value in {
        "BUDGET_MIN": str(budget_min),
        "REPORT_MIN_WORDS": f"{low:,}",
        "REPORT_MAX_WORDS": f"{high:,}",
    }.items():
        text = text.replace("{{" + token + "}}", value)
    return text if embedded_length else text + instruction(low, high)


def feedback(path: Path, low: int, high: int) -> tuple[str, bool]:
    if not high:
        return "", True
    try:
        count = len(path.read_text(errors="replace").split())
    except OSError:
        return f"Report length: report.md is missing or unreadable; target {low:,}–{high:,} words. Write it before finishing.", False
    if count == 0:
        status = "empty report; write the report before finishing"
    elif count < low:
        status = "below the suggested range"
    elif count > high:
        status = f"ABOVE maximum; remove at least {count - high:,} words"
    else:
        status = "within range"
    return f"Report length: {count:,} words; target {low:,}–{high:,}; strict upper limit {high:,}; {status}.", 0 < count <= high


def feedback_if_changed(path: Path, low: int, high: int, *, cache: Path | None = None) -> str:
    """Emit once per observed content change, independent of the editing tool.

    The cache lives outside /work and is isolated per report path and container.
    Locking serializes simultaneous CLI hooks so they don't duplicate feedback.
    A missing report on first use is silent; deleting a draft produces feedback.
    """
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
        return feedback(path, low, high)[0] if changed else ""


def env_limits() -> tuple[int, int]:
    if "MBAB_REPORT_MAX_WORDS" not in os.environ and Path("/tmp/mbab-report-length").exists():
        low, high = map(int, Path("/tmp/mbab-report-length").read_text().split())
        return limits({"report_min_words": low, "report_max_words": high})
    return limits({
        "report_min_words": int(os.environ.get("MBAB_REPORT_MIN_WORDS", "0")),
        "report_max_words": int(os.environ.get("MBAB_REPORT_MAX_WORDS", "0")),
    })


def stop_reason(path: Path, low: int, high: int) -> str:
    note, valid = feedback(path, low, high)
    deadline = os.environ.get("MBAB_DEADLINE_EPOCH")
    if valid or (deadline and time.time() >= int(deadline)):
        return ""
    return note + " Revise /work/report.md now, then finish. The original time budget still applies."


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-words", type=int)
    ap.add_argument("--max-words", type=int)
    ap.add_argument("--instruction", action="store_true")
    ap.add_argument("--template", type=Path)
    ap.add_argument("--budget-min", type=int)
    ap.add_argument("--hook", choices=["PostToolUse", "Stop"])
    ap.add_argument("--report", type=Path, default=Path("/work/report.md"))
    args = ap.parse_args()
    low, high = env_limits() if args.min_words is None and args.max_words is None else limits({
        "report_min_words": args.min_words, "report_max_words": args.max_words,
    })
    if args.template:
        if args.budget_min is None:
            ap.error("--template requires --budget-min")
        print(render_prompt(args.template.read_text(), args.budget_min, low, high), end="")
    elif args.instruction:
        print(instruction(low, high), end="")
    elif args.hook == "Stop":
        # Consume the hook input, but always use the fixed report path. Repeated
        # attempts remain blocked until valid or the original deadline expires.
        json.load(sys.stdin)
        reason = stop_reason(args.report, low, high)
        print(json.dumps({"decision": "block", "reason": reason} if reason else {}))
    else:
        note = feedback_if_changed(args.report, low, high) if args.hook else feedback(args.report, low, high)[0]
        if args.hook and not note:
            print("{}")
        elif args.hook:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": args.hook, "additionalContext": note,
            }}))
        else:
            print(note)


if __name__ == "__main__":
    main()
