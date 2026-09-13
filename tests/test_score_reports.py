"""The published headline score, computed for an arbitrary set of grades."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from score_reports import combine  # noqa: E402


def _write(folder: Path, key: str, rubric: str, scores, judge="claude-fable-5-1"):
    folder.mkdir(parents=True, exist_ok=True)
    body = {"report": key, "grader": judge, "rubric": rubric}
    if rubric in {"tldrh", "m5tldrh", "rhtldrh"}:
        body["accuracy"] = scores
    else:
        body["scores"] = {f"N{i:02d}": {"score": s} for i, s in enumerate(scores)}
    (folder / f"graded_{key}.json").write_text(json.dumps(body))


def test_headline_is_seventy_thirty_over_the_strict_transform(tmp_path) -> None:
    # 1.0 -> 1.0 and 0.75 -> 0.5 under max(2s - 1, 0); 0.5 and 0.25 -> 0.0.
    _write(tmp_path / "v2", "run1", "v2", [1.0, 0.75, 0.5, 0.25])
    _write(tmp_path / "tldrh", "run1", "tldrh", 0.6)
    row = combine(tmp_path / "v2", tmp_path / "tldrh")["reports"][0]
    assert row["coverage_strict"] == 0.375  # (1.0 + 0.5 + 0 + 0) / 4
    assert row["coverage_raw"] == 0.625
    assert row["headline"] == round(0.7 * 0.375 + 0.3 * 0.6, 4)


def test_formula_accepts_mythos_finding_and_summary_directories(tmp_path) -> None:
    _write(tmp_path / "m5", "run1", "m5", [1.0, 0.75, 0.5])
    _write(tmp_path / "m5tldrh", "run1", "m5tldrh", 0.8)

    row = combine(tmp_path / "m5", tmp_path / "m5tldrh")["reports"][0]

    assert row["coverage_strict"] == 0.5
    assert row["headline"] == 0.59


def test_formula_accepts_rubyhack_finding_and_summary_directories(tmp_path) -> None:
    _write(tmp_path / "rh", "run1", "rh", [1.0, 0.75, 0.5])
    _write(tmp_path / "rhtldrh", "run1", "rhtldrh", 0.8)

    row = combine(tmp_path / "rh", tmp_path / "rhtldrh")["reports"][0]

    assert row["coverage_strict"] == 0.5
    assert row["headline"] == 0.59


def test_the_three_finding_numbers_stay_distinct(tmp_path) -> None:
    """Raw mean, strict mean and the above-half fraction are all different."""
    _write(tmp_path / "v2", "run1", "v2", [0.9, 0.6, 0.4, 0.0])
    _write(tmp_path / "tldrh", "run1", "tldrh", 0.5)
    row = combine(tmp_path / "v2", tmp_path / "tldrh")["reports"][0]
    assert row["coverage_raw"] == 0.475
    assert row["coverage_strict"] == 0.25  # (0.8 + 0.2 + 0 + 0) / 4
    assert row["fraction_above_half"] == 0.5  # 0.9 and 0.6 clear half credit
    assert len({row["coverage_raw"], row["coverage_strict"], row["fraction_above_half"]}) == 3


def test_a_report_graded_on_only_one_sheet_is_excluded_and_named(tmp_path) -> None:
    _write(tmp_path / "v2", "paired", "v2", [1.0])
    _write(tmp_path / "tldrh", "paired", "tldrh", 0.5)
    _write(tmp_path / "v2", "lonely", "v2", [1.0])
    result = combine(tmp_path / "v2", tmp_path / "tldrh")
    assert [r["report"] for r in result["reports"]] == ["paired"]
    assert any("lonely" in w and "tldrh" in w for w in result["warnings"])


def test_grades_from_two_judges_are_flagged_rather_than_silently_averaged(tmp_path) -> None:
    _write(tmp_path / "v2", "a", "v2", [1.0], judge="claude-fable-5-1")
    _write(tmp_path / "tldrh", "a", "tldrh", 0.5, judge="claude-fable-5-1")
    _write(tmp_path / "v2", "b", "v2", [1.0], judge="gpt-5.6-sol")
    _write(tmp_path / "tldrh", "b", "tldrh", 0.5, judge="gpt-5.6-sol")
    result = combine(tmp_path / "v2", tmp_path / "tldrh")
    assert len(result["reports"]) == 2
    assert any("more than one judge" in w for w in result["warnings"])


def test_reports_differing_only_by_prompt_id_stay_separate(tmp_path) -> None:
    """Two runs of one cell under different prompts are different reports."""
    for key, scores in (("r4b10_react_k_rep2", [1.0]), ("r4b10_react_k_rep2_p66b7fb24", [0.0])):
        _write(tmp_path / "v2", key, "v2", scores)
        _write(tmp_path / "tldrh", key, "tldrh", 0.5)
    result = combine(tmp_path / "v2", tmp_path / "tldrh")
    assert len(result["reports"]) == 2
    assert {r["coverage_strict"] for r in result["reports"]} == {1.0, 0.0}


def test_an_empty_pairing_reports_no_mean_rather_than_dividing_by_zero(tmp_path) -> None:
    (tmp_path / "v2").mkdir()
    (tmp_path / "tldrh").mkdir()
    result = combine(tmp_path / "v2", tmp_path / "tldrh")
    assert result["reports"] == []
    assert result["mean_headline"] is None
