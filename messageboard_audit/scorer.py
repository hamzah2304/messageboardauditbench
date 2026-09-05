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

import json
from pathlib import Path

import yaml
from inspect_ai.model import Model, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState

RUBRIC = Path(__file__).resolve().parent / "rubric.yaml"

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
def rubric_scorer(judge: str = "anthropic/claude-sonnet-5") -> Scorer:
    rubric = _load_rubric()
    model = get_model(judge)

    async def score(state: TaskState, target: Target) -> Score:
        report = state.output.completion if state.output else ""
        leaves, penalties = rubric["leaves"], rubric.get("penalties", [])
        pos_total = sum(l["weight"] for l in leaves)
        got, verdicts = 0.0, {}
        for l in leaves:
            hit, reason = await _judge(model, l["claim"], report)
            verdicts[l["id"]] = {"hit": hit, "weight": l["weight"], "derivable": l["derivable"], "reason": reason}
            if hit:
                got += l["weight"]
        penalty = 0.0
        for pnode in penalties:
            hit, reason = await _judge(model, pnode["claim"], report)
            verdicts[pnode["id"]] = {"penalty": hit, "weight": pnode["weight"], "reason": reason}
            if hit:
                penalty += pnode["weight"]
        raw = (got - penalty) / pos_total if pos_total else 0.0
        value = max(0.0, min(1.0, raw))
        hits = [k for k, v in verdicts.items() if v.get("hit")]
        return Score(
            value=value,
            answer=f"{got:.0f}/{pos_total} positive, -{penalty:.0f} penalty",
            explanation="hit: " + ", ".join(hits),
            metadata={"verdicts": verdicts},
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
                "turns": m.get("turns"),
                "tool_calls": m.get("tool_calls"),
                # Claude Code serves most context from cache; report both so the
                # input figure is not misread as the whole context it processed.
                "input_tokens_uncached": m.get("input_tokens"),
                "cache_read_tokens": m.get("cache_read_tokens"),
                "output_tokens": m.get("output_tokens"),
                "wall_seconds": m.get("wall_seconds"),
                "report_chars": m.get("report_chars"),
            },
        )

    return score
