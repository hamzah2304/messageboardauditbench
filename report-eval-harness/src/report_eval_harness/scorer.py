"""LLM judge: scores the report against each claim in the corpus answer key.

Mirrors MBAB's finding grading in miniature: each claim gets 0-1 in 0.1 steps
against anchored descriptions, then ``strict = mean(max(2s - 1, 0))`` so that
half-credit gestures count as zero. The judge is the ``grader`` model role.
"""

from __future__ import annotations

import json
import re

from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState
from inspect_ai.util import sandbox

from report_eval_harness.feedback import REPORT_PATH, report_counts

DEFAULT_JUDGE = "anthropic/claude-fable-5-1"

JUDGE_TEMPLATE = """\
You are grading an incident-investigation report against an answer key written by
the human investigators. For each claim below, decide how well the report
establishes it.

Scale (use 0.1 steps):
- 1.0: the report states the claim, or a near-paraphrase, as its own conclusion.
- 0.7: the report reaches the conclusion with minor gaps or imprecision.
- 0.5: a charitable reading finds the claim, or the report shows the evidence without
  drawing the conclusion.
- 0.2: only a vague gesture in the right direction.
- 0.0: absent, or contradicted.

Rules:
1. Inference vs evidence: the report must draw the conclusion. Showing the evidence
   without the conclusion caps the claim at 0.5.
2. Search the whole report, not just the TL;DR.
3. Follow each claim's grading note. For recall_calibrated claims, confident
   assertion of what the evidence cannot show scores 0.
4. Grade only what is in the report. Do not reward length or style.

<answer_key>
{claims}
</answer_key>

<report>
{report}
</report>

Reply with a single JSON object and nothing else, mapping each claim id to
{{"score": <0.0-1.0>, "reason": "<one sentence>"}}.
"""


def strict(score: float) -> float:
    return max(2 * score - 1, 0.0)


def parse_grades(text: str, claim_ids: list[str]) -> dict[str, dict]:
    """Extract per-claim grades from the judge's reply; missing claims get None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(match.group(0)) if match else {}
    grades = {}
    for cid in claim_ids:
        entry = data.get(cid)
        if isinstance(entry, dict) and isinstance(entry.get("score"), (int, float)):
            grades[cid] = {
                "score": min(max(float(entry["score"]), 0.0), 1.0),
                "reason": str(entry.get("reason", "")),
            }
        else:
            grades[cid] = None
    return grades


async def read_report(state: TaskState) -> str:
    try:
        return await sandbox().read_file(REPORT_PATH)
    except FileNotFoundError:
        return ""


@scorer(metrics={"strict": [mean(), stderr()], "raw": [mean(), stderr()]})
def claim_judge():
    async def score(state: TaskState, target: Target) -> Score:
        report = await read_report(state)
        claims = state.metadata["claims"]
        if not report.strip():
            return Score(
                value={"strict": 0.0, "raw": 0.0},
                explanation=f"No report at {REPORT_PATH}.",
                metadata={"report_words": 0, "tldr_words": None, "grades": {}},
            )

        rendered = "\n".join(
            json.dumps({k: c[k] for k in ("id", "claim", "grading_mode", "note")}) for c in claims
        )
        judge = get_model(role="grader", default=DEFAULT_JUDGE)
        output = await judge.generate(
            JUDGE_TEMPLATE.format(claims=rendered, report=report),
            config=GenerateConfig(temperature=0.0),
        )
        ids = [c["id"] for c in claims]
        try:
            grades = parse_grades(output.completion, ids)
        except json.JSONDecodeError:
            grades = dict.fromkeys(ids)
        if all(g is None for g in grades.values()):
            # Unscored, not zero (MBAB's rule): error the sample so it can be re-scored.
            raise RuntimeError(f"Judge reply unparseable: {output.completion[:500]}")

        # Unparsed claims count as 0 so a flaky judge cannot inflate the score.
        scores = [g["score"] if g else 0.0 for g in grades.values()]
        counts = report_counts(report)
        return Score(
            value={
                "strict": sum(map(strict, scores)) / len(scores),
                "raw": sum(scores) / len(scores),
            },
            answer=report,
            explanation="\n".join(
                f"{cid}: {g['score']:.1f} {g['reason']}" if g else f"{cid}: unparsed"
                for cid, g in grades.items()
            ),
            metadata={
                "report_words": counts.words,  # the prompt's count: inline links excluded
                "tldr_words": counts.tldr_words,
                "grades": grades,
            },
        )

    return score
