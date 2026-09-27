"""What the harness tells the agent after each tool call, and how it counts report words.

The investigation prompt promises the agent two things:
- the time remaining, after every tool call;
- the report and TL;DR word counts, whenever report.md changes.

``with_feedback`` wraps a tool so its result (or error) ends with that note. It runs on the
host, so it works the same for the ReAct lead and for Claude Code's bridged tools.

Word counts follow the prompt's definition: whitespace-separated units in the raw Markdown
after removing complete inline links ``[label](URL)``. The TL;DR count covers the body of
the TL;DR section, not its heading or bold ``TL;DR:`` lead-in.
"""

from __future__ import annotations

import functools
import hashlib
import re
from dataclasses import dataclass

from inspect_ai.tool import ContentText, Tool, ToolDef, ToolError, ToolResult
from inspect_ai.util import sample_limits, sandbox

REPORT_PATH = "/work/report.md"
TLDR_MAX_WORDS = 200

# [label](url), allowing one level of brackets inside the label, e.g. [[1]](url).
INLINE_LINK = re.compile(r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]\([^()\s]*\)")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^ {0,3}(```|~~~)")
TLDR = re.compile(r"\bTL\s*;?\s*DR\b", re.IGNORECASE)
TLDR_LEAD_IN = re.compile(r"^\s*[*_]*\s*TL\s*;?\s*DR\s*[*_]*\s*[:.\-–—]?\s*[*_]*\s*", re.IGNORECASE)


def count_words(text: str) -> int:
    return len(INLINE_LINK.sub("", text).split())


def _fenced(lines: list[str]) -> list[bool]:
    """Which lines are fences or inside a fenced code block (so '#' there is no heading)."""
    flags, inside = [], False
    for line in lines:
        if FENCE.match(line):
            flags.append(True)
            inside = not inside
        else:
            flags.append(inside)
    return flags


def tldr_section(text: str) -> str | None:
    """The TL;DR's body: under a heading naming it, or after a ``TL;DR:`` lead-in line.

    It runs to the next heading of any level: reports often put "# TL;DR" above "## ..."
    sections, so a same-level rule would count the whole report.
    """
    lines = text.splitlines()
    fenced = _fenced(lines)
    for i, line in enumerate(lines):
        if fenced[i]:
            continue
        heading = HEADING.match(line)
        lead_in = None if heading else TLDR_LEAD_IN.match(line)
        if heading and TLDR.search(heading.group(2)):
            body = []
        elif lead_in:
            body = [line[lead_in.end() :]]
        else:
            continue
        for j in range(i + 1, len(lines)):
            if not fenced[j] and HEADING.match(lines[j]):
                break
            body.append(lines[j])
        return "\n".join(body)
    return None


@dataclass(frozen=True)
class ReportCounts:
    words: int
    tldr_words: int | None  # None: no TL;DR section found


def report_counts(text: str) -> ReportCounts:
    tldr = tldr_section(text)
    return ReportCounts(count_words(text), None if tldr is None else count_words(tldr))


def _clock(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    return f"{seconds // 60}m{seconds % 60:02d}s"


class Feedback:
    """Per-sample state for the note: the report digest the agent was last told about."""

    def __init__(self, min_words: int = 0, max_words: int = 0):
        self.min_words = min_words
        self.max_words = max_words
        self._digest: str | None = None

    async def note(self) -> str:
        parts = [self._time()]
        try:
            report: str | None = await sandbox().read_file(REPORT_PATH)
        except FileNotFoundError:
            report = None
        digest = None if report is None else hashlib.sha256(report.encode()).hexdigest()
        if digest != self._digest:
            self._digest = digest
            parts.append(self._report(report))
        return "[harness] " + " ".join(p for p in parts if p)

    def _time(self) -> str:
        try:
            limit = sample_limits().time
        except RuntimeError:  # no running sample (unit tests)
            return ""
        if limit.limit is None:
            return ""
        return f"Time remaining: {_clock(limit.remaining or 0)} of {_clock(limit.limit)}."

    def _report(self, report: str | None) -> str:
        if report is None:
            return "report.md no longer exists."
        counts = report_counts(report)
        text = f"report.md changed: {counts.words:,} words"
        if self.max_words:
            text += f" (target {self.min_words:,}-{self.max_words:,}"
            if counts.words > self.max_words:
                text += f"; {counts.words - self.max_words:,} over"
            text += ")"
        if counts.tldr_words is None:
            return text + "; no TL;DR section found."
        text += f"; TL;DR {counts.tldr_words} words (max {TLDR_MAX_WORDS}"
        if counts.tldr_words > TLDR_MAX_WORDS:
            text += f"; {counts.tldr_words - TLDR_MAX_WORDS} over"
        return text + ")."


def with_feedback(tool: Tool, feedback: Feedback) -> Tool:
    """``tool``, with the harness note appended to every result and error message."""
    tdef = ToolDef(tool)

    # wraps() keeps the inner signature and type hints, which Inspect uses to parse arguments.
    @functools.wraps(tdef.tool)
    async def execute(*args, **kwargs) -> ToolResult:
        try:
            result = await tdef.tool(*args, **kwargs)
        except ToolError as ex:
            raise ToolError(f"{ex.message}\n\n{await feedback.note()}") from ex
        note = await feedback.note()
        if isinstance(result, str | int | float | bool):
            return f"{result}\n\n{note}"
        if isinstance(result, list):
            return [*result, ContentText(text=note)]
        return [result, ContentText(text=note)]

    return ToolDef(
        execute,
        name=tdef.name,
        description=tdef.description,
        parameters=tdef.parameters,
        parallel=tdef.parallel,
        viewer=tdef.viewer,
        model_input=tdef.model_input,
        max_output=tdef.max_output,
        options=tdef.options,
    ).as_tool()
