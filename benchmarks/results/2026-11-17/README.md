# Performance and cost across three evals

The [headline figure](../../../docs/figures/results/performance-vs-cost.png) compares
11 models at 10 and 30 minutes. Each point gives German wiki, Transluce and AI Village
equal weight. The [30-minute breakdown](../../../docs/figures/results/eval-breakdown.png)
shows the five selected reports per model and eval as small dots, with their mean as
a diamond. SVG and PDF exports accompany both figures.

## Reports and selection

Each model, eval and time budget contributes the first five eligible reports in
replicate order. The original five attempts are retained, and supplementary runs
fill cells that had fewer than five eligible reports. Selection does not depend on
judge scores. The exact selected run names are in [selection.json](selection.json);
[runs.jsonl](runs.jsonl) records every attempt, eligibility, exclusion reasons,
selection, score and cost.

Eligibility follows the existing run checks, including requested-model fidelity,
report presence and length, refusals and minimum runtime. Performance therefore
measures eligible reports, not success across every attempted run. Excluded attempts
remain visible in the data and count toward cost. This distinction matters for
models with more failed attempts.

## Scores

Average the five selected report scores within each eval, then average the three
eval means equally and multiply by 100. This is a summary of three distinct rubrics,
not accuracy. German wiki averages 12 headline scores; Transluce averages 13, with
F3 at half weight; AI Village averages the best 20 of 96 finding scores.

All reports use the reviewed answer keys, GPT-6.1 Sol at high effort, and the same
Codex CLI judge transport. Models use different investigation scaffolds. Small
sample differences are descriptive, not evidence of a model or scaffold effect.
The [grading method](../../../docs/answer-keys.md) links the answer keys and exact
prompt implementation.

## USD

Within each eval, average the cost of every attempted run, including excluded
attempts. Then average the three eval means equally. This preserves equal eval
weight even when some conditions needed more attempts. It is cost per attempted
run, not total cost divided by the number of successful reports. Grading cost is
excluded.

ReAct uses recorded OpenRouter spend. Claude Code uses its reported API-equivalent
list cost, with a token estimate when that field is absent. Codex uses a token
estimate. Uncached input and cache writes use the pinned input rate; cached input
uses 10% of that rate; output uses the pinned output rate. Rates and per-run cost
inputs are recorded in [provenance.json](provenance.json) and `runs.jsonl`. These
rates are frozen for this evaluation.

## Verify and reproduce

The public export includes numeric grades for
[German wiki](../../german-wiki/results/2026-11-17-grades.jsonl), [Transluce](../../transluce/results/2026-11-17-grades.jsonl) and
[AI Village](../../aivillage/results/2026-11-17-grades.jsonl). They retain every finding and subfinding score,
contradiction flags and provenance hashes. Raw reports and judge quotations can
contain credentials reproduced from the source logs, so those remain in the local
archive. Their hashes identify the originals; the public numeric export supports
checking score arithmetic, but not independently reassessing the judge's reading
of each report.

From a fresh checkout:

```bash
uv sync --frozen
uv run python scripts/verify_eval_results.py
uv run scripts/plot_eval_results.py
```

The verifier checks the rubric and prompt hashes, every report score, selection
rule, all 66 condition cells, and the 22 model–budget averages in
[summary.json](summary.json). The archived Transluce article is identified by its hash; checking its bytes requires
the local archive. Plotting uses isolated, pinned dependencies. To
re-export from the original local archive:

```bash
uv run python scripts/export_eval_results.py --archive /path/to/archive
uv run scripts/plot_eval_results.py
uv run python scripts/verify_eval_results.py
```

The exporter rejects unfinished runs, missing or incomplete grades, stale grading
inputs and missing original attempts. It publishes only allowlisted numeric fields
and provenance. The [initial snapshot](../2026-11-16/README.md) preserves the results
before the supplementary runs.
