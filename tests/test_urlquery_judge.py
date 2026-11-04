"""The URLQuery judge's prompt assembly and answer handling, without calling the API."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks" / "transluce" / "judge"))
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
# the judge before it moved into slopvestigator_bench.grading.findings. A change here
# changes what the judge reads: bump the rubric, and regrade, rather than update the pins.
# Re-pinned for rubric v1.1 (answer-key.json after QA and the overlap check, 2026-11-03), then
# for the finding sheet every benchmark shares (benchmarks/judge/finding-sheet.md, 2026-11-04).
PROMPT_PINS = {
    "F1": "d6a9e3b8f37c274156533b67596061f2128a99490341a5fb9e60036c75ddc0c9",
    "F2": "5cf584fb0b24b64b2e7f845269fee20ccf9385e214b990f9055251d2b9b9c953",
    "F3": "6f6d2624f70812ada20954d98805345a9090a441a943923c50b4ca874c74a95c",
    "F4": "a53bc66e03fb606fb1490dce08d0221cd1603549cf810e12d90ff5dbf21c52b0",
    "F5": "333053ba352555835e1a02ebe4d9ea1eb009fb5f51d72422e36bdc5635762a6f",
    "F6": "2d7b422aa7d2a20f2ef76ff19ef3841375eac6b72e9b640be20d4110304c2cac",
    "F7": "c3a6e5c4858a8eac9c40666823345526fb795ff1c6bf9ba26a06b984652f069d",
    "F8": "c986b4084d3ba69e63193d2cc464990956c9a840382486c264f6dd2ff3563e9b",
    "F9": "3f847389d887a4080a2a5fa134e952f60696e226995a364ffaa76e76583f48a2",
    "F10": "3dcb35f70befd9a1687432a10c8bd96cc608a9ce74e9af5c8dd711eaaff773bd",
    "F11": "e79999f44967e830381e83b1338fd9b909c8efa3b7ae158e46ad79a65c9fba10",
    "F12": "8bde1b523c335138cad579f1d56efc1e23abcf3f1b4e7b5b3c36643600e2c61a",
    "F13": "e2569b94d953eb4d0f6654ab0fcacfa8073c2b436e793b088ca53146a6bcba1d",
}
PIN_REPORT = "A report linking https://urlquery.net/report/" + "0" * 8 + "-0000-0000-0000-" + "0" * 12 + " and more.\n"


def test_rendered_prompts_are_byte_identical_to_the_graded_ones():
    got = {h: grade.sha(render_sheet.render(h, "ARTICLE TEXT", PIN_REPORT))
           for h in [f["id"] for f in render_sheet.load_findings() if f["parent"] is None]}
    assert got == PROMPT_PINS
    assert grade.sha(render_sheet.TEMPLATE.read_bytes()) == "81f6c97108c2ad6e73d0750b46de4b8161c5efaa0272ada55c6fe1c60f783939"
    assert grade.sha(render_sheet.FINDINGS.read_bytes()) == "101dc26b21630e075b78aaf23045b611a9b1bd258b2c53cd12ea96f5064d0ac8"


def test_judge_names_select_transport_and_keep_existing_grade_directories():
    assert grade.provider_of("anthropic/claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert grade.provider_of("claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert grade.provider_of("openrouter/openai/gpt-6-astra") == ("openrouter", "openai/gpt-6-astra")
    from slopvestigator_bench.grading.findings import judge_dir
    assert judge_dir("claude-opus-5-5") == "judge_claude_opus_5_5"
    assert judge_dir("openai/gpt-6-astra", "high") == "judge_gpt_6_astra_high"
    assert grade_openrouter.OUT.name == "judge_gpt_6_astra_high"


def test_both_judge_paths_read_one_transport_table():
    from slopvestigator_bench.grading import finding_scorer, findings

    assert grade.TRANSPORTS is findings.TRANSPORTS
    for judge in ("anthropic/claude-opus-5-5", "claude-opus-5-5", "openrouter/openai/gpt-6-astra"):
        assert grade.provider_of(judge)[0] == findings.transport(judge)
        assert finding_scorer.default_effort(judge) == findings.TRANSPORTS[findings.transport(judge)]["effort"]
    config = finding_scorer._config(type("M", (), {"__str__": lambda s: "anthropic/claude-opus-5-5"})(), "xhigh")
    # reasoning_effort, not effort: Inspect then sends adaptive thinking like the batch grader.
    assert config.reasoning_effort == "xhigh" and config.effort is None and config.max_tokens == 32000


def test_both_graders_default_to_the_standard_judge_including_openai(monkeypatch, tmp_path):
    """openai/gpt-6.1-sol at high effort works in the batch grader and the Inspect scorer."""
    from slopvestigator_bench import standard
    from slopvestigator_bench.grading import findings
    from slopvestigator_bench.grading.finding_scorer import finding_scorer

    judge, effort = standard.judge()
    assert (judge, effort) == ("openai/gpt-6.1-sol", "high")
    # Batch grader: the default, the OpenAI route, its call settings and where its grades go.
    args = grade.parser().parse_args([])
    assert args.judge == judge and grade.DEFAULT_EFFORT == effort
    assert grade.provider_of(judge) == ("openai", "gpt-6.1-sol")
    assert grade.transport_of("openai") is findings.TRANSPORTS["openrouter"]
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-key")
    client = grade.Judge(judge, effort)
    assert client.provider == "openai" and client.effort == "high" and "openrouter" not in str(client.client.base_url)
    assert findings.judge_dir("gpt-6.1-sol", "high") == "judge_gpt_6_1_sol_high"
    # The article is read in full for a non-Anthropic judge, as for the v1.0 Astra grades.
    assert findings.default_article_context(judge) == "full"
    # Inspect scorer: built without a judge, it takes the standard one.
    monkeypatch.setattr(findings, "article_text", lambda context: "ARTICLE")
    assert finding_scorer() is not None
    with pytest.raises(SystemExit):
        grade.provider_of("mistral/large")
