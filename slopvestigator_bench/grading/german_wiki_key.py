"""The German wiki finding judge: a report graded against benchmarks/german-wiki/answer-key.json.

The answer key's counterpart of the claim sheets (rubric "v2"), graded as every benchmark is
(`grading.answer_key_judge`): one judge call per headline finding with its own sub-findings, the
human report given as context, and the report score the mean over the 12 headlines.

Grading one finding at a time is what the key's overlap check assumed: a headline and its own
sub-findings are parts of one score, so W08 and its only sub-finding N28 are not counted twice.

The key names OpenAI, so it has no provider variant: reports written from verbatim_anthropic data
are left unscored (grade them with rubric "v2").
"""

from __future__ import annotations

from inspect_ai.model import Model
from inspect_ai.scorer import Scorer, mean, scorer, stderr

from slopvestigator_bench.grading.core import variant_for_data
from slopvestigator_bench.grading.finding_scorer import answer_key_score


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
    def unscored_if(metadata: dict) -> str | None:
        if found := variant or variant_for_data(metadata.get("data_variant")):
            return f"the answer key has no {found!r} variant; grade with rubric v2"
        return None

    return answer_key_score("german-wiki", judge, effort, unscored_if=unscored_if)
