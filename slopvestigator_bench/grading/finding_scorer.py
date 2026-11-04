"""The answer-key finding judge, as Inspect scorers.

One call per headline finding (`grading.answer_key_judge`), the same prompt bytes the batch
grader (scripts/grade_answer_key.py) sends, through Inspect's model layer so the judge's
calls land in the eval log and obey ``--max-connections``. `answer_key_score` is shared by the
Transluce scorer here, the German wiki one (`grading.german_wiki_key`) and the AI Village one
(`grading.aivillage`). The judge is any Inspect model:
the standard judge (configs/standard.toml) by default, or ``openrouter/openai/gpt-6-astra``,
the v1.0 final-run judge. The full grade file, as the batch grader writes it, goes into
``Score.metadata["grade"]``.

A refusal, a truncated or unparseable answer, or an API error leaves that finding
unscored; it is never recorded as zero. A report with any unscored headline gets
``Score.unscored`` (its grade file keeps the findings that did score), because a mean
over a subset of findings is not comparable with a complete one.
"""

from __future__ import annotations

import time
from typing import Any

from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageUser,
    ContentText,
    GenerateConfig,
    Model,
    get_model,
)
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState

from slopvestigator_bench.grading import findings as fj
from slopvestigator_bench.grading import judge as judging
from slopvestigator_bench.grading.core import judge_name


def default_effort(judge: str) -> str:
    return fj.TRANSPORTS[fj.transport(judge)]["effort"]


def _config(model: Model, effort: str) -> GenerateConfig:
    """The batch grader's request, per transport (`findings.TRANSPORTS`).

    Anthropic: ``reasoning_effort`` makes Inspect send adaptive thinking with
    ``output_config.effort``, as the batch grader does, plus prompt caching.
    Other judges: reasoning effort and a JSON-object response format.
    """
    settings = fj.TRANSPORTS[fj.transport(str(model))]
    if fj.transport(str(model)) == "anthropic":
        return GenerateConfig(reasoning_effort=effort, max_tokens=settings["max_tokens"], cache_prompt=True)
    return GenerateConfig(reasoning_effort=effort, max_tokens=settings["max_tokens"],
                          extra_body={"response_format": {"type": "json_object"}})


def _refused(out) -> bool:
    """Anthropic refusals arrive as content_filter; OpenAI-style ones as refusal content."""
    if out.stop_reason == "content_filter":
        return True
    content = out.choices[0].message.content if out.choices else ""
    return isinstance(content, list) and any(getattr(part, "refusal", None) for part in content)


def _messages(prompt: str, suffix: str = "") -> list[Any]:
    rules, report, finding = fj.split_prompt(prompt)
    return [
        ChatMessageSystem(content=fj.SYSTEM),
        ChatMessageUser(content=[ContentText(text=rules), ContentText(text=report),
                                 ContentText(text=finding + suffix)]),
    ]


async def grade_finding(model: Model, effort: str, headline: str, subs: list[str], prompt: str) -> dict:
    """One headline. Returns a result dict with a status; never raises for a judge failure."""
    started = time.time()
    raws: list[str] = []
    usage: list[dict] = []
    attempts = fj.TRANSPORTS[fj.transport(str(model))]["attempts"]
    try:
        for attempt in range(attempts):
            out = await judging.generate(model, _messages(prompt, fj.JSON_ONLY if attempt else ""),
                                         _config(model, effort))
            raws.append(out.completion)
            usage.append(out.usage.model_dump() if out.usage else {})
            if _refused(out):
                return {"status": "refused", "refusal": out.completion[:500], "usage": usage, "raw": raws}
            if out.stop_reason == "max_tokens":
                return {"status": "truncated", "usage": usage, "raw": raws}
            data = fj.extract_json(out.completion)
            if data is None:
                continue
            try:
                result, notes = fj.validate(data, headline, subs)
            except (TypeError, ValueError) as exc:
                return {"status": "invalid", "error": repr(exc), "usage": usage, "raw": raws}
            return {"status": "ok", **result, "validation": notes, "usage": usage, "raw": raws,
                    "seconds": round(time.time() - started, 1)}
    except Exception as exc:  # noqa: BLE001 — recorded, not raised: other findings stand
        return {"status": "api_error", "error": f"{type(exc).__name__}: {exc}"[:500], "usage": usage, "raw": raws}
    return {"status": "unparseable", "usage": usage, "raw": raws}


def answer_key_score(name: str, judge: str | Model | None, effort: str | None,
                     article_context: str | None = None, unscored_if=None):
    """The scoring function every benchmark's scorer shares (`grading.answer_key_judge`).

    One call per headline of the benchmark's answer key; the full grade goes into
    ``Score.metadata["grade"]``. ``unscored_if(metadata)`` may return a reason to leave a report
    unscored without calling the judge.
    """
    from slopvestigator_bench.grading import answer_key_judge as akj

    if judge is None:
        from slopvestigator_bench import standard

        judge, effort = standard.judge()[0], effort or standard.judge()[1]
    spec = akj.SPECS[name]
    context = (article_context or fj.default_article_context(str(judge))) if spec.source == "article" else None
    source = akj.source_text(name, context)  # Fails here, before an agent runs, if the article is missing.
    key = akj.load_key(name)
    findings = akj.graded_findings(key)

    async def score(state: TaskState, target: Target) -> Score:
        if unscored_if and (reason := unscored_if(state.metadata)):
            return Score.unscored(reason=reason, answer="ungraded")
        model = get_model(judge, role="grader")
        used_effort = effort or default_effort(str(model))
        report = state.output.completion if state.output else ""
        body: dict = {
            **({"run": state.metadata["run"]} if state.metadata.get("run") else {}),
            # Recorded without the transport prefix, as the batch grader's files record it.
            **akj.stamp(name, judge_name(str(model)), used_effort, source, key),
            **({"article_context": context} if context else {}),
            "report_sha256": fj.sha(report),
            "findings": {},
        }
        variables = akj.report_variables(name, state.metadata.get("data_variant"))
        await akj.grade_report(name, model, used_effort, report, source, variables, findings, body)
        n = body["n_findings"]
        if body["score"] is None:
            return Score.unscored(
                reason=f"{len(body['unscored'])} of {n} findings unscored",
                answer="ungraded",
                explanation=", ".join(f"{h}: {body['findings'].get(h, {}).get('status', 'skipped')}"
                                      for h in body["unscored"]),
                metadata={"grade": body},
            )
        value = {"score": body["score"], "coverage": body["score_mean"]} if spec.top_k else body["score"]
        how = f"mean of the best {spec.top_k}, coverage {body['score_mean']}" if spec.top_k else f"unweighted mean {body['score_mean_unweighted']}"
        return Score(value=value, answer=f"{body['score']:.3f}",
                     explanation=f"{n} findings graded by {model}; {how}", metadata={"grade": body})

    return score


@scorer(metrics=[mean(), stderr()])
def finding_scorer(
    judge: str | Model | None = None,
    effort: str | None = None,
    article_context: str | None = None,
) -> Scorer:
    """Grade a URLQuery report against every headline of the Transluce answer key.

    Args:
      judge: the grading model. Resolved at scoring time through the ``grader`` model
        role. Defaults to the standard judge (configs/standard.toml), with its effort; the
        manifest's ``default_judge`` records the v1.0 judge.
      effort: reasoning effort; for another judge, ``xhigh`` for Anthropic, ``high`` otherwise.
      article_context: ``full`` gives the judge Transluce's article (the GPT-6 Astra final
        grades); ``omitted`` replaces it with a fixed note, which avoids the Opus judge's
        refusals on the article. Defaults per transport from the manifest: ``omitted``
        for Anthropic judges, ``full`` otherwise.
    """
    return answer_key_score("transluce", judge, effort, article_context)
