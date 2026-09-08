# Ablation reproduction and archive

The provider-attribution and followup experiments use the same report and
sheet-grading pipeline as the main benchmark. The staged folders below contain
byte-identical copies of the indexed reports, with `_index.jsonl` retaining the
source paths, data variant and available parent identifiers.

| Experiment | Staged folder in `benchmark/graded_inputs/` | Reports |
|---|---|---:|
| Anthropic attribution, 10 minutes | `ablation_anthropic_b10` | 7 |
| Anthropic attribution, 30 minutes | `ablation_anthropic_b30` | 24 |
| Exploratory longer followup | `fu5k` | 8 |
| Five-minute minimum, 10-minute parents | `fu5k_min5_b10` | 26 |
| Five-minute minimum, 30-minute parents | `fu5k_min5_b30` | 27 |
| Five-minute minimum, 120-minute parents | `fu5k_min5_b120` | 26 |

These are archive counts from the initial cleanup, not completed comparison
cells. Subsequent provider-swap runs are exported separately under
`reports/provider_swap/`; see `experiments/provider_swap.toml` for the current
Inspect reproduction plan. Consult the tracked indexes and grades for current
completion counts. The current followup figure uses 78 matched finding-grade
pairs. The early followup sets are exploratory; partial runs and model fallbacks
retain their source labels. No new judge calls were made during release cleanup.
The local Anthropic data did not match the manifest during the initial audit;
reconcile the version used by each historical batch before interpreting a
provider-attribution comparison.

## Rebuild the staged inputs

Run from the repository root:

```bash
uv run python scripts/stage_graded_inputs.py reports \
  blind-10-anthropic=ablation_anthropic_b10:abl10a \
  blind-30-anthropic=ablation_anthropic_b30:abl30a
for harness in codex react; do
  uv run python scripts/stage_graded_inputs.py reports/followup-5k/$harness \
    followup-5k=fu5k:fu5k
  uv run python scripts/stage_graded_inputs.py reports/followup-5k-min5/$harness \
    'followup-5k-min5^10=fu5k_min5_b10:fu5kb10' \
    'followup-5k-min5^30=fu5k_min5_b30:fu5kb30' \
    'followup-5k-min5^120=fu5k_min5_b120:fu5kb120'
done
```

Followup prefixes distinguish the parent's budget, and replicate keys use the
parent epoch when available.
An Inspect continuation creates one sample per parent epoch, so its own
`replicate=1` does not uniquely identify the original replicate.

## Grade an archived cohort

Choose the same judge as the comparison's baseline; for example:

```bash
uv run inspect eval messageboard_audit_bench/grade_reports \
  -T dir=ablation_anthropic_b30 -T rubric=v2 \
  --model-role grader=anthropic/claude-fable-5-1
uv run python scripts/export_grades.py logs/GRADING_LOG.eval
```

Repeat with `rubric=tldrh` for summary quality, and the other folders as needed.
The staged Anthropic index selects the swapped sheets and answer key automatically.
Grades are written under a separate `variant_anthropic` directory, preserving
the originals. These commands make paid judge calls.

See [Getting started](../docs/getting-started.md#ablations) for new native
Inspect ablations. Historical launch plans remain in `provider_swap_*.txt` and
`scripts/run_followup.sh`. Those plans use the historical prompts and, for
Codex followups, subscription session files; they cannot be reproduced from
tracked reports alone.

The [followup figure](../viewers/figures/followup_5k.html) compares longer reports
after ten additional minutes, including a five-minute minimum working period.
It cannot isolate the effect of report length from the effect of extra time.
