"""Reaggregate every grade retained in the publication snapshot without API calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from messageboard_audit_bench.grading import core
from messageboard_audit_bench.runtime import repo_root

GRADED = repo_root() / "benchmark" / "graded"
# fields aggregate() derives rather than passes through
DERIVED = ("total", "max", "accuracy", "contradiction", "n_contradicted", "worst")
# fields later versions of the grader added; a rebuilt dict may carry them, nothing else
ADDITIVE = {"rubric"}


def grade_files() -> list[Path]:
    return sorted(GRADED.rglob("graded_*.json"))


def test_there_are_grades_to_check() -> None:
    # a checkout with no grades would make every parametrised case vacuous
    assert len(grade_files()) > 500


@pytest.mark.parametrize("path", grade_files(), ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_recorded_grade_reaggregates_identically(path: Path) -> None:
    recorded = json.loads(path.read_text())
    if not recorded.get("scores"):
        pytest.skip("no per-claim scores recorded")
    mode = recorded.get("rubric", "recall")

    rebuilt = core.aggregate(
        key=recorded["report"],
        title=recorded.get("title", ""),
        judge=recorded.get("grader", ""),
        mode=mode,
        per_claim=recorded["scores"],
        per_rubric=recorded.get("per_rubric", {}),
        # a grade against a rubric variant records it; rebuilding must feed it back
        variant=recorded.get("rubric_variant"),
    )

    for field in DERIVED:
        if field in recorded:
            assert rebuilt.get(field) == recorded[field], (
                f"{path.name}: {field} was {recorded[field]!r}, now {rebuilt.get(field)!r}"
            )

    if "by_mode" in recorded:
        assert rebuilt.get("by_mode") == recorded["by_mode"], (
            f"{path.name}: by_mode was {recorded['by_mode']!r}, "
            f"now {rebuilt.get('by_mode')!r}"
        )

    # nothing is lost or altered; later grader versions may only have added fields
    for key, value in recorded.items():
        if key == "by_mode":
            continue
        assert key in rebuilt, f"{path.name}: {key} is no longer produced"
        assert rebuilt[key] == value, f"{path.name}: {key} changed"
    assert set(rebuilt) - set(recorded) <= ADDITIVE, (
        f"{path.name}: unexpected new fields {sorted(set(rebuilt) - set(recorded) - ADDITIVE)}"
    )
