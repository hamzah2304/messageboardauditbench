"""Shared report-length policy, also executable inside the sandbox."""

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

COUNT_METHOD = "whitespace-no-inline-links-v2"
MIN_REVISION_SECONDS = 60


def _closing_delimiter(text: str, start: int, opener: str, closer: str) -> int | None:
    """Find a balanced Markdown delimiter, allowing escaped punctuation."""
    depth = 0
    index = start
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def count_words(text: str) -> int:
    """Count whitespace units after removing complete inline Markdown links.

    Both the visible label and destination of ``[label](destination)`` are
    omitted. Backtick code spans and fenced code stay literal, as do images,
    reference links, bare URLs, and malformed inline links.
    """
    kept: list[str] = []
    index = 0
    code_ticks = 0
    while index < len(text):
        if text[index] == "`":
            end = index + 1
            while end < len(text) and text[end] == "`":
                end += 1
            ticks = end - index
            if code_ticks == 0:
                code_ticks = ticks
            elif code_ticks == ticks:
                code_ticks = 0
            kept.append(text[index:end])
            index = end
            continue
        if not code_ticks and text[index] == "[" and (index == 0 or text[index - 1] not in "!\\"):
            label_end = _closing_delimiter(text, index, "[", "]")
            if label_end is not None and text[label_end + 1 : label_end + 2] == "(":
                link_end = _closing_delimiter(text, label_end + 1, "(", ")")
                if link_end is not None:
                    kept.append(" ")
                    index = link_end + 1
                    continue
        kept.append(text[index])
        index += 1
    return len("".join(kept).split())


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
    if (
        any(type(value) is not int or value < 0 for value in (minimum, maximum))
        or minimum > maximum
    ):
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
    count = count_words(text)
    minimum, maximum = acceptance if acceptance is not None else (low, high)
    return {
        "report_words": count,
        "report_min_words": low,
        "report_max_words": high,
        "report_accept_min_words": minimum,
        "report_accept_max_words": maximum,
        "report_word_count_method": COUNT_METHOD,
        "report_length_compliant": (
            bool(exists and count > 0 and minimum <= count <= maximum) if high else None
        ),
    }


def instruction(low: int, high: int) -> str:
    if not high:
        return ""
    return (
        f"\n\nWrite a report between {low:,} and {high:,} words long in report.md. "
        f"{high:,} words is a strict upper limit. Do not exceed it. "
        "The authoritative count is whitespace-separated units in the raw "
        "Markdown file after excluding complete inline links of the form "
        "[label](URL). Headings, tables, code and appendices still count. "
        "Aim near the midpoint. The current report and "
        "TL;DR counts are reported whenever report.md changes. Before finishing, "
        "shorten report.md if it exceeds the upper limit.\n"
    )


def render_prompt(
    template: str, budget_min: int, low: int, high: int, findings_count: int = 0, subagents: bool = False
) -> str:
    """Render shared config values without duplicating embedded length prose.

    `{{#FINDINGS_COUNT}}...{{/FINDINGS_COUNT}}` is kept only when a fixed number of findings
    is configured, `{{^FINDINGS_COUNT}}...{{/FINDINGS_COUNT}}` only when it is not.
    `{{#SUBAGENTS}}...{{/SUBAGENTS}}` is kept only when the config allows subagents,
    `{{^SUBAGENTS}}...{{/SUBAGENTS}}` only when it does not.
    """
    embedded_length = "{{#REPORT_LENGTH}}" in template
    text = re.sub(
        r"\{\{#REPORT_LENGTH\}\}(.*?)\{\{/REPORT_LENGTH\}\}",
        lambda match: match.group(1) if high else "",
        template,
        flags=re.DOTALL,
    )
    text = re.sub(r"\{\{#FINDINGS_COUNT\}\}(.*?)\{\{/FINDINGS_COUNT\}\}",
                  lambda match: match.group(1) if findings_count else "", text, flags=re.DOTALL)
    text = re.sub(r"\{\{\^FINDINGS_COUNT\}\}(.*?)\{\{/FINDINGS_COUNT\}\}",
                  lambda match: "" if findings_count else match.group(1), text, flags=re.DOTALL)
    text = re.sub(r"\{\{#SUBAGENTS\}\}(.*?)\{\{/SUBAGENTS\}\}",
                  lambda match: match.group(1) if subagents else "", text, flags=re.DOTALL)
    text = re.sub(r"\{\{\^SUBAGENTS\}\}(.*?)\{\{/SUBAGENTS\}\}",
                  lambda match: "" if subagents else match.group(1), text, flags=re.DOTALL)
    for token, value in {
        "BUDGET_MIN": str(budget_min),
        "REPORT_MIN_WORDS": f"{low:,}",
        "REPORT_MAX_WORDS": f"{high:,}",
        "FINDINGS_COUNT": str(findings_count),
    }.items():
        text = text.replace("{{" + token + "}}", value)
    return text if embedded_length else text + instruction(low, high)


TLDR_HEADING = re.compile(r"^\s*(?:#+\s*)?(?:\*\*)?(?:\d+[.)]\s*)?tl;?dr\b", re.IGNORECASE)
NEXT_HEADING = re.compile(
    r"^\s*(?:#+\s|\*\*?\d+[.)]\s|\d+[.)]\s+[A-Z]|\*\*[^*\n]{1,80}\*\*:?\s*$)"
)


def tldr_words(text: str) -> int | None:
    """Count words after the first TL;DR heading and before the next heading."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if TLDR_HEADING.match(line)), None)
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if NEXT_HEADING.match(line):
            break
        body.append(line)
    heading_rest = TLDR_HEADING.sub("", lines[start], count=1)
    heading_rest = re.sub(r"^[\s:*\-\u2013\u2014.]+", "", heading_rest)
    return count_words(heading_rest + " " + " ".join(body))


def describe_count(text: str, low: int, high: int) -> str:
    """Describe the report and TL;DR counts using the scoring convention."""
    count = count_words(text)
    if count == 0:
        status = "empty report"
    elif count < low:
        status = "below the suggested range"
    elif count > high:
        status = f"ABOVE maximum; remove at least {count - high:,} words"
    else:
        status = "within range"
    tldr = tldr_words(text)
    tldr_note = "" if tldr is None else f" TL;DR: {tldr:,} words (limit 200)."
    return (
        f"Report length: {count:,} words; target {low:,}–{high:,}; strict upper "
        f"limit {high:,}; {status}.{tldr_note}"
    )


def feedback(path: Path, low: int, high: int) -> tuple[str, bool]:
    """Return a manual status message and whether the report is not overlong."""
    if not high:
        return "", True
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return (
            f"Report length: report.md is missing or unreadable; target "
            f"{low:,}–{high:,} words.",
            True,
        )
    return describe_count(text, low, high), count_words(text) <= high


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


def count_feedback_if_changed(
    path: Path, low: int, high: int, *, cache: Path | None = None
) -> str:
    """Return the count once per observed content change, including within range."""
    if not high:
        return ""
    if cache is None:
        key = hashlib.sha256(str(path.absolute()).encode()).hexdigest()
        cache = Path(tempfile.gettempdir()) / f"mbab-report-count-{key}.json"
    with cache.open("a+") as saved:
        fcntl.flock(saved, fcntl.LOCK_EX)
        try:
            current = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return ""
        saved.seek(0)
        fingerprint = json.dumps([current, low, high])
        if saved.read() == fingerprint:
            return ""
        saved.seek(0)
        saved.truncate()
        saved.write(fingerprint)
        saved.flush()
    return feedback(path, low, high)[0]


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
    if not note or (deadline and int(deadline) - time.time() < MIN_REVISION_SECONDS):
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
    parser.add_argument("--template", type=Path)
    parser.add_argument("--budget-min", type=int, default=20)
    parser.add_argument("--findings-count", type=int, default=0)
    parser.add_argument("--subagents", action="store_true")
    parser.add_argument("--hook", choices=["PostToolUse", "Stop"])
    parser.add_argument("--always", action="store_true")
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
    if args.template:
        print(
            render_prompt(args.template.read_text(), args.budget_min, low, high, args.findings_count, args.subagents),
            end="",
        )
    elif args.instruction:
        print(instruction(low, high), end="")
    elif args.hook == "Stop":
        json.load(sys.stdin)
        reason = stop_reason(args.report, low, high)
        print(json.dumps({"decision": "block", "reason": reason} if reason else {}))
    elif args.hook:
        note = (
            count_feedback_if_changed(args.report, low, high)
            if args.always
            else overlong_feedback_if_changed(args.report, low, high)
        )
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
