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
# Re-pinned for rubric v1.1 (answer-key.json after QA and the overlap check, 2026-11-03).
PROMPT_PINS = {
    "F1": "6c70434a9795a1db6af7fdc13d64bb2e2c6f7154b4ed69955533c86bdb292bd4",
    "F2": "1f32385f6ec46849083b1340071b2cb34b03a2a47efdfcb5f4741f24cda838c4",
    "F3": "ec132b5825857a866a6b80f646a89bf9ca99e723575451280b5b7cc53e5f7dbb",
    "F4": "5f38d588d7b489ef56a67a0c2fb147d46636af04beec2cafa4b9b777a508d508",
    "F5": "3957f2611b9e4789fa1057ddedd69f1bd9956447fdd203c0a1f5d035a12bd514",
    "F6": "f419b62b03b82ee967599fd576058d6de1a88e7b586c719995bc4cdfc48191a5",
    "F7": "11e43a61ed557ae0e7d76727013d185bdfd0bc6a03da6ec976ff861923f8dc3a",
    "F8": "1d56ea8c515cfb1b16d57facf5fa45df19901228f14c905286a30b5abd637283",
    "F9": "f56c39a839cfa48cc9412f1f82d3df447920657965f2d63ad677f660208ff84b",
    "F10": "564caa6e213356ea6de0912319bb9e4e1271c0466dbfd6ba2c342ac100531d9d",
    "F11": "1b4ee087f07647e6534609ba7be03c1ca3e312a8e54f623eab713ff10b93ae10",
    "F12": "813ada74eb6b86bb82334422ba79a66f31e603a49ddc3dc8597f8c2e83b08d53",
    "F13": "b1c28c3ce58b8bede8c0b38420a6a99561de913e35ab29dd2571ce14ec0ba2c0",
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


def test_both_graders_default_to_the_standard_judge(monkeypatch, tmp_path):
    """openrouter/openai/gpt-6.1-sol at high effort works in the batch grader and the Inspect scorer."""
    from slopvestigator_bench import standard
    from slopvestigator_bench.grading import findings
    from slopvestigator_bench.grading.finding_scorer import finding_scorer

    judge, effort = standard.judge()
    assert (judge, effort) == ("openrouter/openai/gpt-6.1-sol", "high")
    # Batch grader: the default, the OpenRouter route, its call settings and where its grades go.
    args = grade.parser().parse_args([])
    assert args.judge == judge and grade.DEFAULT_EFFORT == effort
    assert grade.provider_of(judge) == ("openrouter", "openai/gpt-6.1-sol")
    assert grade.transport_of("openai") is findings.TRANSPORTS["openrouter"]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-key")
    client = grade.Judge(judge, effort)
    assert client.provider == "openrouter" and client.effort == "high" and "openrouter.ai" in str(client.client.base_url)
    assert findings.judge_dir("openai/gpt-6.1-sol", "high") == "judge_gpt_6_1_sol_high"  # where the OpenAI-direct grades went
    # The request: no fallback provider, OpenRouter's cost reported and recorded.
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        msg = type("Msg", (), {"content": "{}", "refusal": None})()
        usage = type("U", (), {"model_dump": lambda s: {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.002}})()
        return type("R", (), {"choices": [type("C", (), {"message": msg, "finish_reason": "stop"})()], "usage": usage})()

    monkeypatch.setattr(client.client.chat.completions, "create", create)
    _, usage, _, _ = client._openrouter("prompt")
    assert sent["extra_body"]["provider"] == {"allow_fallbacks": False, "require_parameters": True}
    assert client.cost(usage) == 0.002
    # The article is read in full for a non-Anthropic judge, as for the v1.0 Astra grades.
    assert findings.default_article_context(judge) == "full"
    # Inspect scorer: built without a judge, it takes the standard one.
    monkeypatch.setattr(findings, "article_text", lambda context: "ARTICLE")
    assert finding_scorer() is not None
    with pytest.raises(SystemExit):
        grade.provider_of("mistral/large")
