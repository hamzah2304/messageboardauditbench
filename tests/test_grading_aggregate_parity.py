"""Every committed grade file must still come out of `core.aggregate` unchanged.

719 files, four judges, four rubrics — every number in every figure traces back to them.
The port lifted the arithmetic rather than rewriting it, and this replays the recorded
per-claim scores through the lifted version to prove the lift was faithful. It costs no
API calls, so it runs in CI on every push.

The check covers `recall` and `contradiction` too, which are out of scope for the Inspect
scorer: `aggregate` is shared across all five modes, so a change made for v2 that broke the
round-3 numbers would be caught here rather than in a figure three weeks later.

Two differences are expected and are asserted as such rather than waved through:

- `rubric` is absent from 239 older files, written before the grader recorded which rubric
  produced them. The rebuilt dict may add it, and nothing else.
- `by_mode` on the nine `bl_*` seed baselines splits over `recall_calibrated`, a
  grading_mode that no longer exists — every claim was converted to `recall_accuracy`.
  Those splits are not reproducible from today's claim set and must not be, so the field is
  checked only where the modes it names still exist.
"""

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


def is_pre_conversion(path: Path) -> bool:
    """The seed baselines were graded before every claim became recall_accuracy.

    Their by_mode splits the claims the way the rubric did then, so they cannot be rebuilt
    from today's claim set and should not be. Nothing else in the corpus predates the
    conversion — test_only_the_seed_baselines_predate_the_mode_conversion holds that line.
    """
    return path.name.startswith("graded_bl_")


def test_only_the_seed_baselines_predate_the_mode_conversion() -> None:
    """The by_mode exemption must not quietly grow to cover a real regression."""
    unreproducible = []
    for path in grade_files():
        recorded = json.loads(path.read_text())
        if not recorded.get("scores") or "by_mode" not in recorded:
            continue
        rebuilt = core.aggregate(
            recorded["report"], recorded.get("title", ""), recorded.get("grader", ""),
            recorded.get("rubric", "recall"), recorded["scores"], recorded.get("per_rubric", {}),
            variant=recorded.get("rubric_variant"),
        )
        if rebuilt.get("by_mode") != recorded["by_mode"]:
            unreproducible.append(path.name)
    assert all(is_pre_conversion(Path(n)) for n in unreproducible), unreproducible
    assert len(unreproducible) == 9, (
        f"expected the 9 seed baselines to be the only irreproducible by_mode, "
        f"got {len(unreproducible)}: {unreproducible}"
    )


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

    if "by_mode" in recorded and not is_pre_conversion(path):
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
