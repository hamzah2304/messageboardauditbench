"""Inspect task: blind investigation of a urlquery corpus, graded against an answer key."""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from report_eval_harness import prompts
from report_eval_harness.agents import (
    AgentKind,
    Effort,
    Truncation,
    claude_code_investigate,
    investigate,
)
from report_eval_harness.corpus import Corpus
from report_eval_harness.sandbox import compose_file
from report_eval_harness.scorer import claim_judge

SUBAGENT_NOTE = (
    "- You can delegate focused sub-questions to the `analyst` tool, a colleague with "
    "its own shell on the same logs. Give it one precise question at a time and check "
    "what it returns against the records.\n"
)
FINISH_NOTE = {
    "react": "When it is complete, call submit() with a one-sentence summary.",
    "claude_code": "When it is complete, end with a one-sentence summary.",
}


@task
def investigation(
    corpus: str = "puchoiswater",
    agent: AgentKind = "react",
    prompt: str = "blind.txt",
    subagents: bool | None = None,
    time_limit_minutes: int = 10,
    report_min_words: int = 2500,
    report_max_words: int = 3000,
    subagent_message_limit: int = 60,
    truncation: Truncation = "auto",
    effort: Effort | None = None,
) -> Task:
    if subagents is None:
        subagents = agent == "react"
    if subagents and agent == "claude_code":
        raise ValueError("claude_code runs without subagents; drop -T subagents=true")
    spec = Corpus(corpus)
    n_records = len(spec.records())
    if n_records == 0:
        raise FileNotFoundError(
            f"No records in {spec.data_dir}. Run: uv run report-eval-harness fetch {corpus}"
        )

    text = prompts.render(
        prompts.load(prompt),
        prompts.values(
            n_records=n_records,
            budget_min=time_limit_minutes,
            report_min_words=report_min_words,
            report_max_words=report_max_words,
            subagent_note=SUBAGENT_NOTE if subagents else "",
            finish_note=FINISH_NOTE[agent],
        ),
    )
    lengths = {"report_min_words": report_min_words, "report_max_words": report_max_words}
    sample = Sample(
        id=corpus,
        input=text,
        metadata={"corpus": corpus, "n_records": n_records, "claims": spec.claims()},
    )
    return Task(
        dataset=[sample],
        solver=claude_code_investigate(effort=effort, **lengths)
        if agent == "claude_code"
        else investigate(
            **lengths,
            subagents=subagents,
            subagent_message_limit=subagent_message_limit,
            truncation=truncation,
        ),
        scorer=claim_judge(),
        sandbox=("docker", str(compose_file(spec, claude=agent == "claude_code"))),
        time_limit=time_limit_minutes * 60,
        metadata={
            "corpus": corpus,
            "agent": agent,
            "prompt": prompt,
            "subagents": subagents,
            **lengths,
        },
    )
