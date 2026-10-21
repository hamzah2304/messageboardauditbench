# Publication evidence index

This checkout is the blog's round-4 snapshot. Historical rounds and prototypes
remain accessible at the `inspect-logs-2026-09-08` Git tag; they are not inputs
to the current headline figures.

## Main results

- `benchmarks/german-wiki/reports/round4/index.jsonl` selects the exported reports and records model,
  harness, budget, epoch, fallback status, and source Inspect log.
- `benchmarks/german-wiki/graded_inputs/round4_blind{10,30,120}/` contains the exact staged
  reports and their provenance indexes.
- `benchmarks/german-wiki/graded/judge_claude_fable_5_1/v2/graded_r4*.json` contains the
  38-finding grades; the parallel `tldrh/` directory contains holistic TLDR grades.
- `benchmarks/german-wiki/figures/combined_score.json` records the 70/30 combination of
  transformed finding coverage and holistic TLDR assessment.
- `scripts/viewers/build_headline_figures.py` builds the headline page and cross-checks
  the combined scores. `scripts/viewers/render_headline_pngs.py` renders its figures;
  `scripts/viewers/figures/results_figures.md` links the current exported plots.

The underlying finding score is `mean(max(2s - 1, 0))`, not a binary fraction
of findings above 0.5. Raw Inspect sheet scores and the publication transform
must not be mixed. Fallback runs and incomplete cells need their recorded labels.

## Ablations

- `benchmarks/german-wiki/reports/provider_swap/` and `benchmarks/german-wiki/graded_inputs/pswap_b{10,30,120}/`
  contain the Inspect provider-swap round. The earlier `ablation_anthropic_b*`
  cohorts are retained as ablation evidence, separately identified by their prefixes.
- `benchmarks/german-wiki/reports/followup-5k-min5/` and `benchmarks/german-wiki/graded_inputs/fu5k_min5_b*/`
  contain the followups with a five-minute minimum; `fu5k/` is exploratory.
- Swapped grades live in each rubric's `variant_anthropic/` directory.
- `benchmarks/german-wiki/experiments/round4.toml` and `benchmarks/german-wiki/experiments/provider_swap.toml` are the launch
  manifests. `benchmarks/german-wiki/experiments/ablations.md` documents the staging and grading commands.
- `benchmarks/german-wiki/figures/followup_5k.{json,csv}` records matched followup comparisons.
  `scripts/viewers/build_followup5k_figure.py` builds the companion page.

The followup treatment adds time and requests a longer report. It does not
isolate the causal effect of report length.

## Ground truth and grader checks

- `benchmarks/german-wiki/human_report.txt` and `human_report_anthropic.txt` are the answer keys.
- `benchmarks/german-wiki/rubrics/v2_*` and `tldrh_*` are the current grading sheets; the
  `anthropic/` subdirectory contains the provider-swapped versions.
- `benchmarks/german-wiki/audit/`, `benchmarks/german-wiki/claims/`, `benchmarks/german-wiki/feasibility/`, and
  `benchmarks/german-wiki/rubric_review/` retain the human ratings and rubric-development
  evidence. These are not additional model-result rounds.
- Alternative round-4 judges and scoring sheets are retained for validation.
  Older sheets still supported by the grading code remain as compatibility assets;
  they do not define the headline metric.

## Logs and history

[Download Inspect logs](artifacts/inspect-logs.md) from the experiment release.
The manifest maps report names to source log basenames and sample epochs;
absolute paths embedded in historical indexes are provenance, not configuration.

The default checkout excludes rounds 1–3, seed baseline reports and grades, the
68-claim prototype, superseded augmentation code, old design handoffs, and stale
result drafts. Retrieve those from the pre-cleanup tag if studying development
history. No historical prompt, report, or grade was rewritten to match the new metric.
