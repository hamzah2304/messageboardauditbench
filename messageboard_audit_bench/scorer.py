"""Scorers for the incident report.

`rubric_scorer` grades the report against rubric.yaml with a model judge: one
judgement per leaf (present / absent) plus the penalty leaves. Score is the
weighted fraction of positive leaves hit, minus penalties, clamped to [0,1].
The per-leaf verdicts are stored in the score metadata so `inspect view` shows
exactly what was credited.

`process_metrics` is a no-LLM scorer that surfaces turns, tokens and whether a
report was written, so those show up as columns without a judge call.
"""

from __future__ import annotations

from importlib.resources import files

import yaml
from inspect_ai.model import Model, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState

RUBRIC = files("messageboard_audit_bench").joinpath("rubric.yaml")

JUDGE_PROMPT = """You are grading an incident report written by an AI agent that investigated wiki edit logs.

You are checking ONE specific claim. Decide whether the report makes this claim, supported by its own reasoning or citations. Be strict: a vague hint does not count, but the report need not use the same words.

CLAIM TO CHECK:
{claim}

Answer with exactly one line: `YES` if the report clearly makes this claim, or `NO` if it does not, followed by a short reason.

REPORT:
{report}
"""


def _load_rubric() -> dict:
    return yaml.safe_load(RUBRIC.read_text())


async def _judge(model: Model, claim: str, report: str) -> tuple[bool, str]:
    if not report.strip():
        return False, "empty report"
    out = await model.generate(JUDGE_PROMPT.format(claim=claim, report=report[:60000]))
    text = out.completion.strip()
    hit = text.upper().startswith("YES")
    return hit, text[:200]


@scorer(metrics=[mean(), stderr()])
def rubric_scorer(judge: str | Model = "anthropic/claude-sonnet-5") -> Scorer:
    rubric = _load_rubric()

    async def score(state: TaskState, target: Target) -> Score:
        # Resolve the judge at scoring time. This keeps task discovery and
        # construction independent of credentials and provider configuration.
        model = get_model(judge, role="grader")
        report = state.output.completion if state.output else ""
        leaves, penalties = rubric["leaves"], rubric.get("penalties", [])
        pos_total = sum(leaf["weight"] for leaf in leaves)
        got, verdicts = 0.0, {}
        for leaf in leaves:
            hit, reason = await _judge(model, leaf["claim"], report)
            verdicts[leaf["id"]] = {
                "hit": hit,
                "weight": leaf["weight"],
                "derivable": leaf["derivable"],
                "reason": reason,
            }
            if hit:
                got += leaf["weight"]
        penalty = 0.0
        for pnode in penalties:
            hit, reason = await _judge(model, pnode["claim"], report)
            verdicts[pnode["id"]] = {
                "penalty": hit,
                "weight": pnode["weight"],
                "reason": reason,
            }
            if hit:
                penalty += pnode["weight"]
        raw = (got - penalty) / pos_total if pos_total else 0.0
        value = max(0.0, min(1.0, raw))
        hits = [k for k, v in verdicts.items() if v.get("hit")]
        return Score(
            value=value,
            answer=f"{got:.0f}/{pos_total} positive, -{penalty:.0f} penalty",
            explanation="hit: " + ", ".join(hits),
            metadata={"judge": str(model), "verdicts": verdicts},
        )

    return score


@scorer(metrics=[mean()])
def process_metrics() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        m = state.metadata
        return Score(
            value=1.0 if m.get("report_written") else 0.0,
            answer="report written" if m.get("report_written") else "no report",
            metadata={
                "usage_schema": m.get("usage_schema"),
                "turns": m.get("turns"),
                "tool_calls": m.get("tool_calls"),
                "input_tokens": m.get("input_tokens"),
                "input_tokens_uncached": m.get("input_tokens_uncached"),
                "cache_read_tokens": m.get("cache_read_tokens"),
                "cache_read_fraction": m.get("cache_read_fraction"),
                "output_tokens": m.get("output_tokens"),
                "wall_seconds": m.get("wall_seconds"),
                "report_chars": m.get("report_chars"),
                "report_words": m.get("report_words"),
                "report_length_ping_count": m.get("report_length_ping_count"),
                "min_runtime_fraction": m.get("min_runtime_fraction"),
                "minimum_runtime_seconds": m.get("minimum_runtime_seconds"),
                "minimum_runtime_reached": m.get("minimum_runtime_reached"),
                "early_stop_attempts": m.get("early_stop_attempts"),
                "early_stop_hook_attempts": m.get("early_stop_hook_attempts"),
                "early_stop_resume_attempts": m.get("early_stop_resume_attempts"),
                "post_tool_hook_fired": m.get("post_tool_hook_fired"),
                "stop_hook_fired": m.get("stop_hook_fired"),
                "terminal_refusal": m.get("terminal_refusal"),
                "agent_stop_reason": m.get("agent_stop_reason"),
                "backend": m.get("backend"),
                "scaffold": m.get("scaffold"),
            },
        )

    return score


@scorer(metrics=[mean()])
def report_length() -> Scorer:
    """Score the saved acceptance policy separately from report quality."""

    async def score(state: TaskState, target: Target) -> Score:
        from messageboard_audit_bench.report_length import (
            acceptance_limits,
            limits,
            measure,
        )

        low, high = limits(state.metadata)
        result = measure(
            state.output.completion if state.output else "",
            low,
            high,
            exists=bool(state.metadata.get("report_written")),
            acceptance=acceptance_limits(state.metadata),
        )
        if "report_length_compliant" in state.metadata:
            result.update(
                {key: state.metadata[key] for key in result if key in state.metadata}
            )
        valid = result["report_length_compliant"]
        if not high:
            answer = "disabled"
            explanation = "No length requirement recorded for this run."
        else:
            answer = "accepted" if valid else "outside acceptance limits or missing"
            explanation = (
                f"{result['report_words']} words; acceptance bounds "
                f"{result['report_accept_min_words']}–"
                f"{result['report_accept_max_words']} inclusive; report must be "
                "nonempty."
            )
        if valid is None:
            return Score.unscored(
                answer=answer,
                explanation=explanation,
                metadata=result,
            )
        return Score(
            value=0.0 if valid is False else 1.0,
            answer=answer,
            explanation=explanation,
            metadata=result,
        )

    return score
