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


# sha256 of each headline's rendered prompt for a fixed article and report, taken from
# the judge before it moved into messageboard_audit_bench.grading.findings. A change here
# changes what the judge reads: bump the rubric, and regrade, rather than update the pins.
PROMPT_PINS = {
    "F1": "7b01f15ddfa3046991e03cc454b145611c1b86a563b017c56f1c7d612eaf77e8",
    "F2": "b66104d0193cfe319942bea71ac073c14f3a779d734bf91e471d24d2af52b11c",
    "F3": "2087b530f4271d507b23769fac244b327e1f55d79988edfaaddb13d5a19a50c3",
    "F4": "f17b553d8daac8049000efffcde165a00546e144e69062763687bd4d49c16324",
    "F5": "f56662c78cc5c5ec49bc0fdd494bce483a5c8f93b39f103c7a8b6e2e7ccf3736",
    "F6": "c545ea8c83650bbc29386c4c04812eb68b876fa3a51a35076e8e74826246530f",
    "F7": "fbb3fa4c4c027accc7424848b8f42db838bacb539bf2b618cca9711d89feee27",
    "F8": "07790c6e0f184ecc6be1bd3e6389c2317bfece63de029a33fde443826d6fbd6e",
    "F9": "32293f52f0206ecbe66a5cb31036e0e01c1bfa8a8101f18018241543b48a7eb4",
    "F10": "d42c63d990ce68c88ca2f1c2ef521919a39c03787ce973c177f72640a9fb2c50",
    "F11": "bc06b50c7521e0554daf29e5d7434b0a59403a660de950d1fae7a83b2e268116",
    "F12": "d1da476e1ac3ffb47f037087bc2e0b9fc71efecc4e9e37118c6a8fe464efa751",
    "F13": "f05bf925e1789f0a4fa5635704c51988b84e161ed5822cb59ccb5edeff26fc89",
}
PIN_REPORT = "A report linking https://urlquery.net/report/" + "0" * 8 + "-0000-0000-0000-" + "0" * 12 + " and more.\n"


def test_rendered_prompts_are_byte_identical_to_the_graded_ones():
    got = {h: grade.sha(render_sheet.render(h, "ARTICLE TEXT", PIN_REPORT))
           for h in [f["id"] for f in render_sheet.load_findings() if f["parent"] is None]}
    assert got == PROMPT_PINS
    assert grade.sha(render_sheet.TEMPLATE.read_bytes()) == "7dff278e1f96f87f4c9784ac37fdc46164a9ac9fe5d93c28b92a17e6ea477778"
    assert grade.sha(render_sheet.FINDINGS.read_bytes()) == "101dc26b21630e075b78aaf23045b611a9b1bd258b2c53cd12ea96f5064d0ac8"


def test_judge_names_select_transport_and_keep_existing_grade_directories():
    assert grade.provider_of("anthropic/claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert grade.provider_of("claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert grade.provider_of("openrouter/openai/gpt-6-astra") == ("openrouter", "openai/gpt-6-astra")
    from messageboard_audit_bench.grading.findings import judge_dir
    assert judge_dir("claude-opus-5-5") == "judge_claude_opus_5_5"
    assert judge_dir("openai/gpt-6-astra", "high") == "judge_gpt_6_astra_high"
    assert grade_openrouter.OUT.name == "judge_gpt_6_astra_high"
