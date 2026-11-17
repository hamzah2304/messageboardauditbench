# Initial evaluation snapshot

This snapshot preserves the original 330 attempts: 11 models × three evals × two
time budgets × five replicates. Of these, 316 reports were eligible; five attempts
produced no report and nine failed other eligibility checks. All attempts and their
costs remain in `runs.jsonl`.

The [current results](../2026-11-17/README.md) add supplementary runs to obtain five
eligible reports per condition. The exporter uses this original run list to check
that no initial attempt is lost. The current public numeric grades also cover these
original reports; hashes identify their raw local grade and usage files.

`summary.json` contains the original 22 model–budget averages. `provenance.json`
records the original model lineup, pinned prices and grading implementation.
These are historical inputs, not the source of the current README figures.
