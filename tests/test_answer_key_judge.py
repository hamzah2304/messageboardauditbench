"""The finding judge every benchmark shares: one prompt, filled per benchmark, one call per headline."""

import pytest

from slopvestigator_bench.grading import answer_key_judge as akj
from slopvestigator_bench.grading import findings as fj


@pytest.mark.parametrize("name", sorted(akj.SPECS))
def test_every_headline_renders_a_complete_prompt(name):
    findings = akj.graded_findings(akj.load_key(name))
    source = "THE SOURCE" if akj.SPECS[name].source else None
    for finding in findings:
        prompt = akj.render(name, finding, "THE REPORT {{NOT_A_SLOT}}", source, akj.report_variables(name, None))
        assert "{{" not in prompt.replace("{{NOT_A_SLOT}}", ""), finding["id"]
        rules, report, block = fj.split_prompt(prompt)
        assert "THE REPORT" in report and block.startswith("## The finding to score")
        assert ("THE SOURCE" in rules) == bool(source)
        assert f"### Finding {finding['id']}" in block
        assert all(f"#### Sub-finding {s['id']}" in block for s in finding["subfindings"])


def test_every_judge_sees_a_finding_in_the_same_form():
    """The prompts differ; the finding block is one renderer's, so the same fields show the same way."""
    for name in akj.SPECS:
        finding = akj.graded_findings(akj.load_key(name))[0]
        block = akj.render_finding(name, finding)
        assert block.startswith(f"### Finding {finding['id']}") and f"**Finding:** {finding['claim']}" in block
        assert (f"**Notes:** {finding['judge_notes']}" in block) == bool(finding["judge_notes"])
        assert (f"**Detail:** {finding['detail']}" in block) == bool(finding.get("detail"))
        for sub in finding["subfindings"]:
            assert f"#### Sub-finding {sub['id']}\n\n**Sub-finding:** {sub['claim']}" in block
        assert akj.render_finding(name, finding, "R") in akj.render(name, finding, "R", "S", akj.report_variables(name, None))


def test_report_scores():
    heads = ["A", "B", "C"]
    body = {"findings": {h: {"status": "ok", "score": s} for h, s in zip(heads, (1.0, 0.5, 0.0), strict=True)}}
    akj.summarize("german-wiki", body, heads, {"C": 0.5}, "")
    assert body["score"] == body["score_mean"] == 0.6 and body["score_mean_unweighted"] == 0.5
    body["findings"]["C"]["status"] = "refused"
    akj.summarize("german-wiki", body, heads, {}, "")
    assert body["score"] is None and body["unscored"] == ["C"]


def test_minor_headlines_count_half():
    assert akj.headline_weights(akj.graded_findings(akj.load_key("transluce"))) == fj.headline_weights() == {"F3": 0.5}
    assert akj.headline_weights(akj.graded_findings(akj.load_key("german-wiki"))) == {}


async def test_an_answer_for_another_finding_or_missing_sub_findings_is_not_a_grade():
    import json

    from inspect_ai.model import ModelOutput, get_model

    from slopvestigator_bench.grading.finding_scorer import grade_finding

    def judge(answer):
        return get_model("mockllm/model", custom_outputs=lambda *_a, **_k: ModelOutput.from_content("mockllm/model", json.dumps(answer)))

    full = {"finding_id": "M001", "score": 1, "contradicted": False, "quote": "", "reason": "r",
            "sub_findings": [{"id": s, "score": 1} for s in ("M001.1", "M001.2")]}
    assert (await grade_finding(judge(full), "high", "M001", ["M001.1", "M001.2"], "## The model's report\n## The finding to score\n"))["status"] == "ok"
    for bad in ({**full, "finding_id": "M999"}, {**full, "sub_findings": []}):
        result = await grade_finding(judge(bad), "high", "M001", ["M001.1", "M001.2"], "## The model's report\n## The finding to score\n")
        assert result["status"] == "invalid" and result["error"]


def test_the_export_says_how_many_answer_key_grades_it_leaves_out():
    from types import SimpleNamespace

    from slopvestigator_bench.grading import export

    score = SimpleNamespace(value=0.5, metadata={"grade": {"rubric": "answer-key", "score": 0.5}})
    log = SimpleNamespace(samples=[SimpleNamespace(scores={"german_wiki_key_scorer": score}, metadata={}, epoch=1)])
    assert export.grades_in(log) == [] and export.answer_key_grades_in(log) == 1


def test_duplicate_extra_or_non_numeric_entries_are_not_a_grade():
    expected = ["S1", "S2"]
    good = {"finding_id": "F", "score": 0.5, "sub_findings": [{"id": "S1", "score": 1}, {"id": "S2", "score": 0}]}
    cases = [
        {**good, "sub_findings": good["sub_findings"] + [{"id": "S1", "score": 0}]},  # duplicate
        {**good, "sub_findings": good["sub_findings"] + [{"id": "S3", "score": 1}]},  # extra
        {**good, "score": "NaN"},
        {**good, "sub_findings": [{"id": "S1", "score": float("inf")}, {"id": "S2", "score": 0}]},
    ]
    result, _ = fj.validate(good, "F", expected)
    assert fj.incomplete(good, result, "F") is None and fj.usable({"status": "ok", **result})
    for bad in cases:
        try:
            result, _ = fj.validate(bad, "F", expected)
        except (TypeError, ValueError):
            continue
        assert fj.incomplete(bad, result, "F"), bad
    assert not fj.usable({"status": "ok", "sub_findings": [{"id": "S1", "score": None}]})


def test_a_finding_with_an_unscored_sub_finding_does_not_count():
    body = {"findings": {"A": {"status": "ok", "score": 1.0, "sub_findings": [{"id": "A.1", "score": None}]}}}
    akj.summarize("german-wiki", body, ["A"], {}, "")
    assert body["score"] is None and body["unscored"] == ["A"]
