"""Rubric grading: one implementation, two entry points.

`core` holds everything that decides what a grade *is* — the mode table, the prompt, the
parsing, the arithmetic, the output path. It talks to no provider and imports no client, so
both the legacy script (benchmark/rubrics/grade_with_rubrics.py) and the Inspect scorer can
import it and cannot drift apart. That shared definition is what makes the parity checks in
tests/test_grading_*.py mean anything: they compare two callers of the same functions, not
two reimplementations that happen to agree today.
"""

from messageboard_audit_bench.grading.core import (
    MODES,
    ModeSpec,
    aggregate,
    build_prompt,
    judge_name,
    load_sheets,
    out_dir,
    parse_items,
    sanitise,
)

__all__ = [
    "MODES",
    "ModeSpec",
    "aggregate",
    "build_prompt",
    "judge_name",
    "load_sheets",
    "out_dir",
    "parse_items",
    "sanitise",
]
