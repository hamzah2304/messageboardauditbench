"""The URLQuery finding judge, as an Inspect scorer.

One call per headline finding, the same prompt bytes the batch grader
(benchmarks/urlquery/judge/grade.py) sends, through Inspect's model layer so the judge's
calls land in the eval log and obey ``--max-connections``. The judge is any Inspect model:
``anthropic/claude-opus-5-5`` (the default) or ``openrouter/openai/gpt-6-astra``, the
final-run judge. The full grade file, as the batch grader writes it, goes into
``Score.metadata["grade"]``.

A refusal, a truncated or unparseable answer, or an API error leaves that finding
unscored; it is never recorded as zero. A report with any unscored headline gets
``Score.unscored`` (its grade file keeps the findings that did score), because a mean
over a subset of findings is not comparable with a complete one.
"""

from __future__ import annotations

import asyncio
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

from messageboard_audit_bench.benchmarks import urlquery_manifest
from messageboard_audit_bench.grading import findings as fj
from messageboard_audit_bench.grading.core import judge_name


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
            out = await model.generate(_messages(prompt, fj.JSON_ONLY if attempt else ""),
                                       config=_config(model, effort))
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


@scorer(metrics=[mean(), stderr()])
def finding_scorer(
    judge: str | Model | None = None,
    effort: str | None = None,
    article_context: str | None = None,
) -> Scorer:
    """Grade a URLQuery report against every headline of the reviewed findings rubric.

    Args:
      judge: the grading model. Resolved at scoring time through the ``grader`` model
        role. Defaults to the manifest's judge (``anthropic/claude-opus-5-5``).
      effort: reasoning effort; ``xhigh`` for Anthropic judges, ``high`` otherwise.
      article_context: ``full`` gives the judge Transluce's article (the GPT-6 Astra final
        grades); ``omitted`` replaces it with a fixed note, which avoids the Opus judge's
        refusals on the article. Defaults per transport from the manifest: ``omitted``
        for Anthropic judges, ``full`` otherwise.
    """
    grading = urlquery_manifest()["grading"]
    judge = judge or grading["default_judge"]
    context = article_context or fj.default_article_context(str(judge))
    fj.article_text(context)  # Validate the article is available before launching an agent.
    findings = fj.load_findings()
    heads = fj.headlines(findings)
    subs = {h: fj.sub_ids(h, findings) for h in heads}

    async def score(state: TaskState, target: Target) -> Score:
        model = get_model(judge, role="grader")
        used_effort = effort or default_effort(str(model))
        report = state.output.completion if state.output else ""
        article = fj.article_text(context)
        body: dict = {
            **({"run": state.metadata["run"]} if state.metadata.get("run") else {}),
            # Recorded without the transport prefix, as the batch grader's files record it.
            **fj.stamp(judge_name(str(model)), used_effort, article),
            "article_context": context,
            "report_sha256": fj.sha(report),
            "findings": {},
        }

        async def one(h: str) -> None:
            body["findings"][h] = await grade_finding(model, used_effort, h, subs[h], fj.render(h, article, report))

        # The first call warms the shared prefix. For Anthropic, a report-level refusal
        # on it recurs on every finding; keep it as unscored rather than repeat it.
        await one(heads[0])
        skip = fj.TRANSPORTS[fj.transport(str(model))]["skip_after_first_refusal"]
        if not (skip and body["findings"][heads[0]]["status"] == "refused"):
            await asyncio.gather(*(one(h) for h in heads[1:]))
        fj.summarize(body, heads, report)
        value = body["score_mean"]
        if value is None:
            return Score.unscored(
                reason=f"{len(body['unscored'])} of {len(heads)} findings unscored",
                answer="ungraded",
                explanation=", ".join(f"{h}: {body['findings'].get(h, {}).get('status', 'skipped')}"
                                      for h in body["unscored"]),
                metadata={"grade": body},
            )
        return Score(
            value=value,
            answer=f"{value:.3f}",
            explanation=f"{len(heads)} findings graded by {model}; unweighted mean {body['score_mean_unweighted']}",
            metadata={"grade": body},
        )

    return score
