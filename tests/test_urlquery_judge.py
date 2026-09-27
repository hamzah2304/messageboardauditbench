"""The URLQuery judge's prompt assembly and answer handling, without calling the API."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks" / "urlquery" / "judge"))
grade = pytest.importorskip("grade")
render_sheet = pytest.importorskip("render_sheet")


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
