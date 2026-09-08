"""The Inspect rubric scorer, driven by canned judge replies.

No API calls: `mockllm/model` with `custom_outputs` returns whatever the test hands it,
which is the pattern `tests/test_solver.py` already uses for the legacy scorer.

What matters here is the failure behaviour as much as the arithmetic. A report where every
sheet failed is not a report that scored zero — an auth or billing error takes all of them
down at once — and recording it as zero is both a wrong number and, because the resume path
skips anything already written, a permanently wrong one. So the scorer must come back
unscored and the exporter must write nothing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from inspect_ai.model import (
    ChatMessageUser,
    ModelName,
    ModelOutput,
    ModelUsage,
    get_model,
)
from inspect_ai.scorer import Target
from inspect_ai.solver import TaskState

from messageboard_audit_bench.grading import core, export
from messageboard_audit_bench.grading.scorer import sheet_scorer

REPORT = "## TL;DR\nAgents from OpenAI colluded on a wiki.\n\n## Findings\nDetail.\n"


def state(report: str = REPORT, sample_id: str = "r4b10_test_rep1") -> TaskState:
    st = TaskState(
        model=ModelName("mockllm/model"),
        sample_id=sample_id,
        epoch=1,
        input=report,
        messages=[ChatMessageUser(content=report)],
        metadata={"title": "a staged report"},
        target=Target(""),
    )
    st.output = ModelOutput.from_content(model="staged-report", content=report)
    return st


def judge(replies: list[str]):
    """A mock judge that returns `replies` in order, then repeats the last one."""
    seen = iter(replies)
    last: list[str] = [replies[-1]]

    def nxt(*_args, **_kwargs) -> ModelOutput:
        try:
            last[0] = next(seen)
        except StopIteration:
            pass
        return ModelOutput(model="mockllm/model", completion=last[0], usage=ModelUsage())

    return get_model("mockllm/model", custom_outputs=nxt)


def sheet_reply(mode: str, index: int, score: float) -> str:
    """A well-formed reply giving every claim on sheet `index` the same score."""
    sets, _ = core.load_sheets(mode)
    spec = sets[index]
    items = [{"id": c["id"], "score": score, "quote": "", "reason": "x"} for c in spec["claims"]]
    return json.dumps({"rubric_id": spec["rubric_id"], "items": items})


async def test_scores_every_sheet_and_reports_the_mean() -> None:
    sets, _ = core.load_sheets("v2")
    replies = [sheet_reply("v2", i, 1.0) for i in range(len(sets))]
    score = await sheet_scorer(rubric="v2", judge=judge(replies))(state(), Target(""))

    grade = score.metadata["grade"]
    assert grade["max"] == 38, "all 38 points should have been graded"
    assert score.value == 1.0
    assert grade["accuracy"] == 1.0
    assert len(grade["per_rubric"]) == len(sets)
    assert not score.metadata["failures"]


async def test_scores_are_clamped_and_rounded() -> None:
    sets, _ = core.load_sheets("v2")
    # 1.44 rounds to 1.4 then clamps to 1.0; -3 clamps to 0.0
    replies = [sheet_reply("v2", 0, 1.44)] + [sheet_reply("v2", i, -3) for i in range(1, len(sets))]
    score = await sheet_scorer(rubric="v2", judge=judge(replies))(state(), Target(""))

    values = {i["score"] for i in score.metadata["grade"]["scores"].values()}
    assert values <= {0.0, 1.0}
    assert 1.0 in values and 0.0 in values


async def test_prose_wrapped_json_is_recovered() -> None:
    body = sheet_reply("tldrh", 0, 0.7)
    wrapped = f"Here is my assessment.\n```json\n{body}\n```\nHope that helps."
    score = await sheet_scorer(rubric="tldrh", judge=judge([wrapped]))(state(), Target(""))

    assert score.value == 0.7
    assert not score.metadata["failures"]


async def test_unparseable_reply_is_retried_then_recorded_as_a_sheet_failure() -> None:
    score = await sheet_scorer(rubric="tldrh", judge=judge(["not json at all"]))(
        state(), Target("")
    )

    # tldrh is a single sheet, so its failure is a total failure. Score.unscored carries
    # NaN, which is how Inspect keeps it in the log but out of the metrics.
    assert math.isnan(score.value), "an ungraded report must not be scored"
    assert "TLDRH" in score.metadata["failures"]


async def test_one_bad_sheet_does_not_discard_the_others() -> None:
    sets, _ = core.load_sheets("v2")
    replies = ["still not json", "also not json"]  # V1 fails: one try plus the retry
    replies += [sheet_reply("v2", i, 0.9) for i in range(1, len(sets))]
    score = await sheet_scorer(rubric="v2", judge=judge(replies))(state(), Target(""))

    grade = score.metadata["grade"]
    assert list(score.metadata["failures"]) == ["V1"]
    assert 0 < grade["max"] < 38, "the surviving sheets should still be graded"
    assert grade["accuracy"] == 0.9


async def test_a_total_failure_is_unscored_and_exports_nothing(tmp_path: Path) -> None:
    score = await sheet_scorer(rubric="v2", judge=judge(["nope"]))(state(), Target(""))

    assert math.isnan(score.value)
    assert score.answer == "ungraded"
    assert len(score.metadata["failures"]) == 8

    class _Sample:
        scores = {"sheet_scorer": score}

    class _Log:
        samples = [_Sample()]

    assert export.export(_Log(), out_dir=tmp_path) == []
    assert list(tmp_path.iterdir()) == []


async def test_exported_grade_matches_what_the_standalone_grader_would_write(
    tmp_path: Path,
) -> None:
    """The exporter is the compatibility seam; its output has to be the old file shape."""
    sets, _ = core.load_sheets("v2")
    replies = [sheet_reply("v2", i, 0.5) for i in range(len(sets))]
    score = await sheet_scorer(rubric="v2", judge=judge(replies))(state(), Target(""))

    class _Sample:
        scores = {"sheet_scorer": score}

    class _Log:
        samples = [_Sample()]

    written = export.export(_Log(), out_dir=tmp_path)
    assert [p.name for p in written] == ["graded_r4b10_test_rep1.json"]
    on_disk = json.loads(written[0].read_text())
    assert set(on_disk) >= {
        "report", "title", "grader", "rubric", "total", "max", "per_rubric", "scores",
        "accuracy", "by_mode",
    }
    # and it round-trips through the same aggregation the corpus is checked with
    rebuilt = core.aggregate(
        on_disk["report"], on_disk["title"], on_disk["grader"], on_disk["rubric"],
        on_disk["scores"], on_disk["per_rubric"],
    )
    assert rebuilt == on_disk


def test_unknown_rubric_fails_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown rubric"):
        sheet_scorer(rubric="not-a-rubric")
