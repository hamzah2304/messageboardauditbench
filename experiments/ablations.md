# Ablation reproduction and archive

The provider-attribution and followup experiments use the same report and
sheet-grading pipeline as the main benchmark. The staged folders below contain
byte-identical copies of the indexed reports, with `_index.jsonl` retaining the
source paths, data variant and available parent identifiers.

| Experiment | Staged folder in `benchmark/graded_inputs/` | Reports |
|---|---|---:|
| Anthropic attribution, 10 minutes | `ablation_anthropic10` | 7 |
| Anthropic attribution, 30 minutes | `ablation_anthropic30` | 24 |
| Longer followup, Codex | `followup_5k_codex` | 4 |
| Longer followup, ReAct | `followup_5k_react` | 4 |
| Longer followup with 5-minute minimum, Codex | `followup_5k_min5_codex` | 36 |
| Longer followup with 5-minute minimum, ReAct | `followup_5k_min5_react` | 43 |

These are archive counts, not completed comparison cells. The early followup
sets are exploratory; partial runs and model fallbacks retain their source
labels. No grades were generated during release cleanup. The local Anthropic
data did not match the current manifest; reconcile the version used by each
historical batch before interpreting a provider-attribution comparison.

## Rebuild the staged inputs

Run from the repository root:

```bash
uv run python scripts/stage_graded_inputs.py reports \
  blind-10-anthropic=ablation_anthropic10:ant10 \
  blind-30-anthropic=ablation_anthropic30:ant30
uv run python scripts/stage_graded_inputs.py reports/followup-5k/codex \
  followup-5k=followup_5k_codex:fu5k
uv run python scripts/stage_graded_inputs.py reports/followup-5k/react \
  followup-5k=followup_5k_react:fu5k
uv run python scripts/stage_graded_inputs.py reports/followup-5k-min5/codex \
  followup-5k-min5=followup_5k_min5_codex:fu5km5
uv run python scripts/stage_graded_inputs.py reports/followup-5k-min5/react \
  followup-5k-min5=followup_5k_min5_react:fu5km5
```

Followup filenames distinguish the parent's budget and, for ReAct, parent epoch.
An Inspect continuation creates one sample per parent epoch, so its own
`replicate=1` does not uniquely identify the original replicate.

## Grade an archived cohort

Choose the same judge as the comparison's baseline; for example:

```bash
uv run inspect eval messageboard_audit_bench/grade_reports \
  -T dir=ablation_anthropic30 -T rubric=v2 \
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
