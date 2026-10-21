"""The rubric judge, as an Inspect scorer.

One sheet at a time, the same bytes the standalone grader sends, through Inspect's model
layer instead of a hand-rolled thread pool — so the judge's calls land in the eval log,
count against the run's token accounting, and obey `--max-connections` like everything
else.

The whole aggregate dict goes into `Score.metadata`, not just the number. That is what lets
`export.py` reproduce `benchmarks/german-wiki/graded/.../graded_<key>.json` byte for byte, which in turn
is why no figure, viewer or analysis script has to change.

Failure is per sheet, never fatal: one unparseable response should not throw away the other
seven sheets' claims. But a report where *every* sheet failed is not a report that scored
zero — an auth or billing error hits all of them at once — so that case returns
`Score.unscored` and the exporter writes nothing. The standalone grader learned this the
expensive way, after a lapsed Anthropic balance wrote 112 files recording a total of 0.
"""

from __future__ import annotations

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

from slopvestigator_bench.grading import core
from slopvestigator_bench.grading import judge as judging

# Tried in order, dropping down when a provider rejects the level outright. Mirrors the
# standalone grader's ladder.
EFFORTS = ("xhigh", "high", "medium")


def _config(model: Model, effort: str) -> GenerateConfig:
    """Effort goes in a different field per provider, and only Anthropic takes `effort`."""
    if judging.is_anthropic(model):
        return GenerateConfig(effort=effort, max_tokens=32000)
    return GenerateConfig(reasoning_effort=effort, max_tokens=16000)


def _messages(system: str, prefix: str, suffix: str) -> list[Any]:
    """Sheet first, report second, always.

    Inspect's ContentText carries no cache_control, so the explicit breakpoint the
    standalone grader sets is not reproducible here. Anthropic's automatic caching covers
    it instead: it caches the longest matching prefix, and the prefix — sheet plus answer
    key, ~90 kB — is identical for every report graded on this sheet. Reversing these two
    blocks would silently cost that.
    """
    return [
        ChatMessageSystem(content=system),
        ChatMessageUser(content=[ContentText(text=prefix), ContentText(text=suffix)]),
    ]


async def grade_sheet(
    model: Model,
    mode: str,
    rubric_id: str,
    report_md: str,
    templates: dict[str, str],
    variant: str | None = None,
    efforts: tuple[str, ...] = EFFORTS,
) -> tuple[dict[str, dict], str]:
    """One sheet. Returns (claims, effort actually used); raises only if nothing parses."""
    spec = core.MODES[mode]
    system, prefix, suffix = core.build_prompt(mode, rubric_id, report_md, templates, variant)
    last: Exception | None = None
    for effort in efforts:
        try:
            out = await judging.generate(model, _messages(system, prefix, suffix), _config(model, effort))
        except Exception as exc:  # noqa: BLE001 — an effort the provider rejects, or a real error
            last = exc
            if "effort" in str(exc).lower():
                continue
            raise
        data = core.extract_json(out.completion)
        if data is None:
            # one retry, telling it to drop the wrapper
            out = await judging.generate(
                model, _messages(system, prefix, suffix + core.JSON_ONLY), _config(model, effort)
            )
            data = core.extract_json(out.completion)
        if data is None:
            raise ValueError(
                f"unparseable JSON from {model} on {mode}/{rubric_id}: {out.completion[:200]!r}"
            )
        return core.parse_items(data, spec.lo, spec.hi), effort
    raise RuntimeError(f"all efforts failed for {mode}/{rubric_id}: {last!r}")


@scorer(metrics=[mean(), stderr()])
def sheet_scorer(
    rubric: str = "v2", judge: str | Model | None = None, variant: str | None = None,
    effort: str | None = None,
) -> Scorer:
    """Grade the report against every sheet of `rubric`.

    Args:
      rubric: a key of `core.MODES`, including the wiki's "v2"/"tldrh" and
        Mythos 5's "m5"/"m5tldrh" and RubyHack's "rh"/"rhtldrh" pairs.
      judge: the grading model. Resolved at scoring time through the `grader` model role,
        so `--model-role grader=openai/gpt-5.6-sol` works as it does for the other scorers.
      variant: a rubric variant (`core.VARIANTS`); the task derives it from the data
        variant, so a verbatim_anthropic run is judged against the swapped answer key.
      effort: one reasoning effort for every sheet (``high`` in the standard condition).
        Unset, each sheet tries xhigh, then high, then medium, as the published grades did.

    A report with any failed sheet is unscored: the surviving sheets' grades stay in the
    metadata, but no score is computed from part of the rubric.
    """
    if rubric not in core.MODES:
        raise ValueError(f"unknown rubric {rubric!r}; expected one of {sorted(core.MODES)}")
    core.load_sheets(rubric, variant)  # Validate assets before launching an agent.

    async def score(state: TaskState, target: Target) -> Score:
        selected_variant = variant or core.variant_for_data(state.metadata.get("data_variant"))
        sets, templates = core.load_sheets(rubric, selected_variant)
        model = get_model(judge, role="grader")
        report_md = state.output.completion if state.output else ""
        key = str(state.sample_id)
        title = str(state.metadata.get("title", key))

        per_claim: dict[str, dict] = {}
        per_rubric: dict[str, dict] = {}
        failures: dict[str, str] = {}
        for spec in sets:
            rubric_id = spec["rubric_id"]
            try:
                items, used = await grade_sheet(
                    model, rubric, rubric_id, report_md, templates, selected_variant,
                    (effort,) if effort else EFFORTS,
                )
            except Exception as exc:  # noqa: BLE001 — recorded, not raised: other sheets stand
                failures[rubric_id] = f"{type(exc).__name__}: {exc}"[:300]
                continue
            # Claim sheets return one item per claim; a holistic sheet (unnumbered: tldr, tldrh,
            # origin) returns one item named after the sheet.
            holistic = not core.MODES[rubric].numbered and set(items) == {rubric_id}
            if set(items) != set(spec["claim_ids"]) and not holistic:
                # A parseable sheet that skips or invents claims would score part of the rubric.
                failures[rubric_id] = f"returned {len(set(items) & set(spec['claim_ids']))} of {spec['n_claims']} claims"
                continue
            per_claim.update(items)
            per_rubric[rubric_id] = {
                "score": round(sum(i["score"] for i in items.values()), 2),
                "max": len(items),
                "effort": used,
            }

        # recorded bare, the way every existing grade file records it
        out = core.aggregate(
            key, title, core.judge_name(str(model)), rubric, per_claim, per_rubric, sets, selected_variant
        )
        if failures:
            return Score.unscored(
                reason=f"{len(failures)} of {len(sets)} sheets failed",
                answer="ungraded",
                explanation="; ".join(f"{k}: {v}" for k, v in failures.items())[:600],
                metadata={"grader": str(model), "rubric": rubric, "failures": failures,
                          **({"grade": out} if out["max"] else {})},
            )

        value = out["contradiction"] if rubric == "contradiction" else out["accuracy"]
        return Score(
            value=value,
            answer=f"{out['total']}/{out['max']}",
            explanation=(
                f"{len(per_rubric)}/{len(sets)} sheets graded by {model}"
                + (f"; failed: {', '.join(failures)}" if failures else "")
            ),
            metadata={"grade": out, "failures": failures, "variant": selected_variant},
        )

    return score
