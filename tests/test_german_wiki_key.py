"""The German wiki answer-key grader: its prompt, its scorer, and where it is the default."""
import json
import re

from inspect_ai.model import ChatMessageUser, ModelOutput, get_model
from inspect_ai.scorer import Target
from inspect_ai.solver import TaskState

from slopvestigator_bench import incidents
from slopvestigator_bench.grading import answer_key_judge as akj
from slopvestigator_bench.grading import findings as fj
from slopvestigator_bench.grading import german_wiki_key as gk
from slopvestigator_bench.grading.task import german_wiki_report_grade


def _text(messages) -> str:
    out = []
    for m in messages:
        content = m.content
        out += [content] if isinstance(content, str) else [getattr(c, "text", "") for c in content]
    return "".join(out)


def key_reply(prompt: str, score: float = 1.0) -> str:
    """A well-formed answer for whichever headline the prompt asks about."""
    head = re.search(r"Finding sheet — (W\d+)", prompt)[1]
    finding = {f["id"]: f for f in akj.graded_findings(akj.load_key("german-wiki"))}[head]
    subs = [{"id": s["id"], "score": score, "contradicted": False, "quote": "", "reason": "x"}
            for s in finding["subfindings"]]
    return json.dumps({"finding_id": head, "sub_findings": subs, "contradicted": False,
                       "score": score, "quote": "", "reason": "x"})


def key_judge(score: float = 1.0, other: str | None = None):
    """A mock judge that answers answer-key prompts per headline and anything else with `other`."""
    def reply(messages, *_args, **_kwargs) -> ModelOutput:
        prompt = _text(messages)
        text = key_reply(prompt, score) if "# Finding sheet — W" in prompt else other
        return ModelOutput.from_content("mockllm/model", text)
    return get_model("mockllm/model", custom_outputs=reply)


def state(report="A report.", variant="verbatim") -> TaskState:
    return TaskState(model="mockllm/model", sample_id="s", epoch=1, input="x",
                     messages=[ChatMessageUser(content="x")],
                     output=ModelOutput.from_content("mockllm/model", report),
                     metadata={"data_variant": variant})


def test_every_headline_renders_a_complete_prompt():
    findings = akj.graded_findings(akj.load_key("german-wiki"))
    human = akj.source_text("german-wiki")
    for finding in findings:
        prompt = akj.render("german-wiki", finding, "THE REPORT", human)
        assert "{{" not in prompt.replace(human, ""), finding["id"]
        assert "<human_report>\n" + human in prompt
        assert "".join(fj.split_prompt(prompt)) == prompt
        assert "THE REPORT" in fj.split_prompt(prompt)[1]
        for sub in finding["subfindings"]:
            assert f"Sub-finding {sub['id']}" in prompt
            block = prompt.split(f"Sub-finding {sub['id']}", 1)[1].split("#### ", 1)[0]
            assert ("Low-weight detail" in block) == (sub["significance"] == "minor")
            assert f"**In the human report:** “{sub['fields']['report_quote']}”" in block


async def test_full_marks_score_one_with_every_headline_graded():
    score = await gk.german_wiki_key_scorer(judge=key_judge(), effort="high")(state(), Target(""))
    grade = score.metadata["grade"]
    assert score.value == 1.0
    assert grade["n_scored"] == grade["n_findings"] == len(akj.load_key("german-wiki")["findings"]) == 12
    assert grade["rubric"] == "answer-key" and grade["findings_sha256"] and grade["source_sha256"]
    assert all(r["status"] == "ok" and not r["validation"] for r in grade["findings"].values())


async def test_half_marks_and_an_anthropic_report_is_left_unscored():
    score = await gk.german_wiki_key_scorer(judge=key_judge(0.5), effort="high")(state(), Target(""))
    assert score.value == 0.5
    score = await gk.german_wiki_key_scorer(judge=key_judge(), effort="high")(
        state(variant="verbatim_anthropic"), Target(""))
    assert score.answer == "ungraded" and not score.metadata


def test_live_default_uses_the_key_where_it_covers_the_data():
    assert incidents.default_rubrics("verbatim") == "answer-key,tldrh"
    assert incidents.default_rubrics("raw_stripped") == "answer-key,tldrh"
    assert incidents.default_rubrics("verbatim_anthropic") == "v2,tldrh"


def test_grade_task_defaults_to_the_key():
    task = german_wiki_report_grade(judge="mockllm/model")
    assert task.metadata["rubric"] == "answer-key"

