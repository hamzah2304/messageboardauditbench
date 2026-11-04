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


def test_the_benchmarks_share_everything_but_their_modules():
    """Blanking each benchmark's module text leaves the same sheet for all three."""
    blanked = set()
    for name in akj.SPECS:
        text = akj.sheet(name)
        for kind in ("framing", "parts", "rules"):
            if module := akj._module(kind, name):
                text = text.replace(module, f"<{kind}>")
        blanked.add(text.replace("\n<rules>\n", ""))
    assert len(blanked) == 1


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
