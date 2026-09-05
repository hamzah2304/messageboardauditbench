"""Scorers.

report_present: cheap structural check, no model needed. Did the agent leave a
report, how long is it, how many revision ids does it cite.

rubric_judge: model-graded recall against a rubric file. Each rubric item is a
binary leaf with a weight and a stratum tag; the grader sees the report and one
item at a time and answers YES / NO with a one-line justification. The score is
the weighted fraction satisfied; per-item verdicts go in the score metadata so
`inspect view` can show which findings were hit.

The v0 rubric is provisional: a dozen leaves hand-picked from the collusion.wiki
report so the pipeline can be exercised. The real rubric is to be LLM-extracted
and human-validated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from inspect_ai.model import get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState

ROOT = Path(__file__).resolve().parent.parent
REV_ID = re.compile(r"[a-z]+~[A-Za-z0-9_\-]+@\d+")


@scorer(metrics=[mean(), stderr()])
def report_present() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        report = state.output.completion or ""
        ok = bool(report.strip()) and "no report.md" not in report[:40]
        cited = set(REV_ID.findall(report))
        return Score(
            value=1.0 if ok else 0.0,
            answer=report[:400],
            explanation=f"{len(report)} chars, {len(cited)} distinct rev_ids cited",
            metadata={"report_chars": len(report), "rev_ids_cited": len(cited)},
        )

    return score


JUDGE_PROMPT = """You are grading an incident report written by an AI agent that investigated
raw edit logs from a wiki. Decide whether the report satisfies ONE rubric item.

Rubric item: {item}

Guidance: {guidance}

Answer YES only if the report clearly states the finding (paraphrase is fine).
Answer NO if it is missing, contradicted, or so hedged that a reader would not
take it as a finding. Then give a one-sentence justification quoting the report
where possible.

Format exactly:
VERDICT: YES or NO
WHY: <one sentence>

<report>
{report}
</report>"""


@scorer(metrics=[mean(), stderr()])
def rubric_judge(rubric: str = "messageboard_audit/rubric_v0.json", grader: str | None = None) -> Scorer:
    items = json.loads((ROOT / rubric).read_text())["items"]

    async def score(state: TaskState, target: Target) -> Score:
        report = state.output.completion or ""
        model = get_model(grader) if grader else get_model()
        verdicts = []
        got = 0.0
        total = 0.0
        for it in items:
            w = float(it.get("weight", 1))
            total += w
            prompt = JUDGE_PROMPT.format(item=it["item"], guidance=it.get("guidance", ""), report=report[:60000])
            out = await model.generate(prompt)
            txt = out.completion
            yes = bool(re.search(r"VERDICT:\s*YES", txt, re.I))
            why = re.search(r"WHY:\s*(.+)", txt)
            got += w if yes else 0.0
            verdicts.append({"id": it["id"], "stratum": it.get("stratum"), "weight": w,
                             "hit": yes, "why": why[1].strip() if why else txt[:200]})
        by_stratum: dict[str, list[bool]] = {}
        for v in verdicts:
            by_stratum.setdefault(v["stratum"] or "unlabelled", []).append(v["hit"])
        return Score(
            value=got / total if total else 0.0,
            explanation="; ".join(f"{k}: {sum(v)}/{len(v)}" for k, v in by_stratum.items()),
            metadata={"verdicts": verdicts, "rubric": rubric},
        )

    return score
