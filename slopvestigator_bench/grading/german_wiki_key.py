"""The German wiki finding judge: a report graded against benchmarks/german-wiki/answer-key.json.

The answer key's counterpart of the claim sheets (rubric "v2"): one judge call per headline
finding, with that finding's own sub-findings, judged against the human report as context.
The prompt is benchmarks/german-wiki/judge/finding_sheet_answer_key.md, the Transluce finding
sheet without its scan links. The call, the retries and the answer's validation are the Transluce
judge's (grading.finding_scorer.grade_finding, grading.findings.validate): the headline scores
0-1 in tenths, each sub-finding 0-1 in quarters, and the report score is the mean over headlines
(a minor headline would count half, as Transluce's F3 does; none is minor now).

Grading one finding at a time is what the key's overlap check assumed: a headline and its own
sub-findings are parts of one score, so W08 and its only sub-finding N28 are not counted twice.

The key names OpenAI, so it has no provider variant: reports written from verbatim_anthropic data
are left unscored (grade them with rubric "v2").
"""

from __future__ import annotations

import asyncio
import json

from inspect_ai.model import Model, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState

from slopvestigator_bench.grading import findings as fj
from slopvestigator_bench.grading.core import judge_name, variant_for_data
from slopvestigator_bench.runtime import repo_root

ROOT = "benchmarks/german-wiki"
KEY = f"{ROOT}/answer-key.json"
TEMPLATE = f"{ROOT}/judge/finding_sheet_answer_key.md"
HUMAN_REPORT = f"{ROOT}/human_report.txt"
MINOR_HEADLINE_WEIGHT = 0.5


def load_key() -> dict:
    from slopvestigator_bench import answer_key

    key = answer_key.load(repo_root() / KEY)
    if problems := answer_key.validate(key):
        raise ValueError(f"{KEY}: " + "; ".join(problems[:5]))
    return key


def headline_weights(key: dict) -> dict[str, float]:
    return {f["id"]: MINOR_HEADLINE_WEIGHT for f in key["findings"] if f["significance"] == "minor"}


def render_finding(finding: dict) -> str:
    lines = [f"### Finding {finding['id']}", "", f"**Finding:** {finding['claim']}", ""]
    if finding.get("detail"):
        lines += [f"**Detail:** {finding['detail']}", ""]
    if finding.get("judge_notes"):
        lines += [f"**Notes:** {finding['judge_notes']}", ""]
    for sub in finding["subfindings"]:
        lines += [f"#### Sub-finding {sub['id']}", "", f"**Sub-finding:** {sub['claim']}", ""]
        if sub["significance"] == "minor":
            lines += ["**Scoring role:** Low-weight detail. Score it for diagnostics, but its omission alone should not lower the parent finding score.", ""]
        if quote := sub.get("fields", {}).get("report_quote"):
            lines += [f"**In the human report:** “{quote}”", ""]
        if sub.get("judge_notes"):
            lines += [f"**Notes:** {sub['judge_notes']}", ""]
    return "\n".join(lines).rstrip()


def render(finding: dict, human_report: str, report: str) -> str:
    subs = [s["id"] for s in finding["subfindings"]]
    return (
        (repo_root() / TEMPLATE).read_text()
        .replace("{{HUMAN_REPORT}}", human_report)
        .replace("{{MODEL_REPORT}}", report)
        .replace("{{FINDING_BLOCK}}", render_finding(finding))
        .replace("{{SUB_IDS}}", "(" + ", ".join(subs) + ")" if subs else "(none: this finding has no sub-findings, so return an empty list)")
        .replace("{{HEADLINE_ID}}", finding["id"])
    )


def stamp(judge: str, effort: str, key: dict, human_report: str) -> dict:
    """What a grade depends on besides the report."""
    return {
        "judge": judge,
        "effort": effort,
        "rubric": "answer-key",
        "prompt_sha256": fj.sha((repo_root() / TEMPLATE).read_bytes()),
        "key_sha256": fj.sha(json.dumps(key, indent=1, ensure_ascii=False) + "\n"),
        "human_report_sha256": fj.sha(human_report),
    }


def summarize(body: dict, heads: list[str], weights: dict[str, float]) -> dict:
    scored = {h: body["findings"][h]["score"] for h in heads if body["findings"].get(h, {}).get("status") == "ok"}
    body["headline_weights"] = weights
    body["n_scored"] = len(scored)
    body["n_findings"] = len(heads)
    body["score_mean"], body["score_mean_unweighted"] = fj.score_means(scored, heads, weights)
    body["unscored"] = [h for h in heads if h not in scored]
    return body


@scorer(metrics=[mean(), stderr()])
def german_wiki_key_scorer(judge: str | Model | None = None, effort: str | None = None,
                           variant: str | None = None) -> Scorer:
    """Grade a German wiki report against every headline of the answer key.

    Args:
      judge: the grading model, resolved at scoring time through the ``grader`` model role.
        Defaults to the standard judge (configs/standard.toml), with its effort.
      effort: reasoning effort; for another judge, ``xhigh`` for Anthropic, ``high`` otherwise.
      variant: a rubric variant for every report; unset, each report's data variant decides.
        The key has none, so any variant leaves the report unscored.
    """
    from slopvestigator_bench.grading.finding_scorer import (
        default_effort,
        grade_finding,
    )

    if judge is None:
        from slopvestigator_bench import standard

        judge, effort = standard.judge()[0], effort or standard.judge()[1]
    key = load_key()
    human_report = (repo_root() / HUMAN_REPORT).read_text()
    findings = {f["id"]: f for f in key["findings"]}
    heads = list(findings)
    weights = headline_weights(key)

    async def score(state: TaskState, target: Target) -> Score:
        sample_variant = variant or variant_for_data(state.metadata.get("data_variant"))
        if sample_variant:
            return Score.unscored(reason=f"the answer key has no {sample_variant!r} variant; grade with rubric v2",
                                  answer="ungraded")
        model = get_model(judge, role="grader")
        used_effort = effort or default_effort(str(model))
        report = state.output.completion if state.output else ""
        body: dict = {
            **({"run": state.metadata["run"]} if state.metadata.get("run") else {}),
            **stamp(judge_name(str(model)), used_effort, key, human_report),
            "report_sha256": fj.sha(report),
            "findings": {},
        }

        async def one(h: str) -> None:
            subs = [s["id"] for s in findings[h]["subfindings"]]
            body["findings"][h] = await grade_finding(model, used_effort, h, subs, render(findings[h], human_report, report))

        # The first call warms the shared prefix; for Anthropic a report-level refusal on it
        # recurs on every finding, so it is kept as unscored rather than repeated.
        await one(heads[0])
        skip = fj.TRANSPORTS[fj.transport(str(model))]["skip_after_first_refusal"]
        if not (skip and body["findings"][heads[0]]["status"] == "refused"):
            await asyncio.gather(*(one(h) for h in heads[1:]))
        summarize(body, heads, weights)
        value = body["score_mean"]
        if value is None:
            return Score.unscored(
                reason=f"{len(body['unscored'])} of {len(heads)} findings unscored",
                answer="ungraded",
                explanation=", ".join(f"{h}: {body['findings'].get(h, {}).get('status', 'skipped')}" for h in body["unscored"]),
                metadata={"grade": body},
            )
        return Score(
            value=value,
            answer=f"{value:.3f}",
            explanation=f"{len(heads)} findings graded by {model}; unweighted mean {body['score_mean_unweighted']}",
            metadata={"grade": body},
        )

    return score
