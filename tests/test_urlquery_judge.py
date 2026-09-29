"""The URLQuery judge's prompt assembly and answer handling, without calling the API."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks" / "urlquery" / "judge"))
grade = pytest.importorskip("grade")
render_sheet = pytest.importorskip("render_sheet")
grade_openrouter = pytest.importorskip("grade_openrouter")
combine_f13_grades = pytest.importorskip("combine_f13_grades")


def test_blocks_reassemble_the_prompt_and_cache_the_first_two():
    prompt = render_sheet.render("F4", "ARTICLE TEXT", "REPORT TEXT")
    blocks = grade.split_blocks(prompt)
    assert "".join(b["text"] for b in blocks) == prompt
    assert [("cache_control" in b) for b in blocks] == [True, True, False]
    assert "ARTICLE TEXT" in blocks[0]["text"] and "REPORT TEXT" in blocks[1]["text"]
    assert "### Finding F4" in blocks[2]["text"]


def test_validate_snaps_sub_scores_and_flags_missing_ids():
    data = {"score": 0.73, "contradicted": False, "quote": "q", "reason": "r",
            "sub_findings": [{"id": "F4.1", "score": 0.6}, {"id": "F4.2", "score": 1}]}
    out, notes = grade.validate(data, "F4", ["F4.1", "F4.2", "F4.3"])
    assert out["score"] == 0.7
    assert [s["score"] for s in out["sub_findings"]] == [0.5, 1.0, None]
    assert out["sub_mean"] == 0.75
    assert any("snapped" in n for n in notes) and any("!= expected" in n for n in notes)


def test_extract_json_strips_fences_and_prose():
    assert grade.extract_json('```json\n{"score": 1}\n```') == {"score": 1}
    assert grade.extract_json('Here it is: {"score": 0.5} done') == {"score": 0.5}
    assert grade.extract_json("no json") is None


def test_synthesis_finding_gets_half_weight_in_final_mean():
    weighted, unweighted = grade_openrouter.score_means({"F3": 0.0, "F4": 1.0}, ["F3", "F4"])
    assert weighted == 0.667
    assert unweighted == 0.5
    assert grade_openrouter.score_means({"F3": 0.0}, ["F3", "F4"]) == (None, None)


def test_f13_prompt_excludes_model_report_quotes():
    prompt = render_sheet.render("F13", "ARTICLE", "REPORT")
    assert "#### Sub-finding F13.4" in prompt
    assert "a model report suggested this finding, but that report is not evidence" in prompt
    assert "**In the article:**" not in prompt


def test_combining_f13_preserves_existing_judgments():
    report = "Report with no scan links"
    shared = {key: "same" for key in ("run", "agent", "model", "replicate", "condition",
                                          "judge", "effort", "prompt_sha256", "article_sha256")}
    shared["report_sha256"] = grade.sha(report)
    old = {f"F{i}": {"status": "ok", "score": i / 20} for i in range(1, 13)}
    new = {"status": "ok", "score": 0.8}
    base = {**shared, "findings": old, "findings_sha256": "old", "score_mean": 0.1}
    added = {**shared, "findings": {"F13": new}, "findings_sha256": "new"}
    result = combine_f13_grades.combine(base, added, source_hash="source",
                                        combined_hash="combined", report=report)
    assert all(result["findings"][fid] == value for fid, value in old.items())
    assert result["findings"]["F13"] == new
    assert result["n_scored"] == result["n_findings"] == 13
    assert result["rubric_provenance"]["F1-F12_findings_sha256"] == "old"
    assert result["rubric_provenance"]["F13_findings_sha256"] == "new"
    assert result["score_mean"] == grade_openrouter.score_means(
        {fid: value["score"] for fid, value in result["findings"].items()},
        [f"F{i}" for i in range(1, 14)],
    )[0]
