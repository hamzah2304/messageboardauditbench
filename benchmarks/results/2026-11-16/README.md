# Current-lineup evaluation snapshot

This snapshot contains all 330 planned trials: 11 models × 3 benchmarks × 2 time budgets × 5 replicates. Of these, 316 are eligible. Five produced no report and nine produced reports but failed other eligibility checks. Excluded trials remain in `runs.jsonl`; displayed means use only eligible reports.

The results use the reviewed answer-key rubric and GPT-6.1 Sol at high effort through the Codex subscription. The plot scores multiply the stored report score by 100. German wiki averages 12 headlines; Transluce takes a weighted mean over 13 headlines (F3 has half weight); AI Village averages the best 20 of 96. These are different scoring rules, so scores should be compared within each benchmark.

The current lineup includes each model in its configured scaffold. Historical open-weight Codex comparisons and superseded models are not included. Models and scaffolds are confounded; these figures cannot isolate scaffold effects. Run counts are too small to treat modest gaps as established differences.

## Three figure options

- [Individual runs and means at 30 minutes](../../../docs/figures/eval-options/refined/01-runs.png): recommended main figure because it shows variation between runs.
- [Both budgets as a heatmap](../../../docs/figures/eval-options/refined/02-heatmap.png): a compact overview with exact means and eligible counts.
- [10 versus 30 minutes](../../../docs/figures/eval-options/refined/03-time.png): descriptive differences between separate run groups, with endpoint sample sizes.

SVG and PDF exports accompany each PNG. The `draft/` directory preserves the initial designs before one independent review and refinement round. The HTML gallery presents the choices together; it does not replace the README's published results.

## Reproduce

From the repository root:

```sh
uv run scripts/plot_eval_options.py
```

The script uses isolated, pinned plotting dependencies, without changing the benchmark environment. It validates that all 330 unique trial slots are present, five per cell, and that every eligible report has a score. It reads only this frozen snapshot and regenerates `docs/figures/eval-options/refined/`.

`provenance.json` records the grading code revision and scoring rules. Each trial row includes the source run name, the grade-file SHA-256, eligibility and exclusion reasons. The source grade files and raw reports are not included here; their hashes permit comparison with the local grading archive, but this snapshot alone does not reproduce the judge calls. This is a figure-selection PR, not a complete publication of the grading pipeline or raw evidence.
