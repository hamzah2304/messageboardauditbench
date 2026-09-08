"""Eval log -> benchmark/graded/.../graded_<key>.json.

The compatibility seam. `scripts/report_performance.py`, the headline and combined
figures, the audit viewers and the judge-vs-human comparison all read that file layout;
none of them should have to learn what an eval log is. The scorer already put the whole
aggregate dict in each sample's score metadata, so this is a copy, not a recomputation —
which is deliberate, because a second computation here could disagree with the first.

Samples that came back unscored are skipped, mirroring the standalone grader's write
guard: a report whose every sheet failed must not be recorded as having scored zero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from messageboard_audit_bench.grading import core


def grades_in(log: Any) -> list[dict]:
    """The aggregate dicts recorded by sheet_scorer, one per scored sample."""
    out = []
    for sample in log.samples or []:
        for score in (sample.scores or {}).values():
            grade = (score.metadata or {}).get("grade")
            if grade and grade.get("max"):
                out.append(grade)
    return out


def export(log: Any, out_dir: Path | None = None, force: bool = False) -> list[Path]:
    """Write one graded_<key>.json per scored sample. Returns the paths written."""
    written = []
    for grade in grades_in(log):
        target = out_dir or core.out_dir(grade["grader"], grade["rubric"])
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"graded_{grade['report']}.json"
        if path.exists() and not force:
            continue
        path.write_text(json.dumps(grade, indent=1, ensure_ascii=False))
        written.append(path)
    return written
