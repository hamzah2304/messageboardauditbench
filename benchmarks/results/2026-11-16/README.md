# Performance and cost across three evals

The headline figure shows performance averaged equally across German wiki, Transluce and AI Village against mean USD per run, with both 10- and 30-minute points. The single-panel breakdown shows the same mean as a large diamond and each eval mean as a small shape. It removes the previous per-eval panels and count columns.

- [Performance versus USD](../../../docs/figures/eval-options/performance-vs-cost.png)
- [Overall mean and eval breakdown](../../../docs/figures/eval-options/eval-breakdown.png)

SVG and PDF exports accompany both PNGs. The model colors match between the two figures. Earlier plot alternatives remain in `draft/` and `refined/` as design history, but are not the current results presentation.

## Averaging

First average eligible report scores within each eval, model and budget, then average the three eval means. Each eval contributes exactly one third even when report counts differ. The plotted score is this average multiplied by 100, not accuracy. German wiki averages 12 headlines; Transluce takes a weighted mean over 13 (F3 has half weight); AI Village averages the best 20 of 96. Their mean is a summary of this suite, not a claim that the rubrics measure identical difficulty.

The snapshot contains all 330 trials: 11 models × 3 evals × 2 budgets × 5 replicates. Score means use 316 eligible reports. Five trials produced no report and nine failed other eligibility checks. All remain in `runs.jsonl`, including their costs. The current lineup uses each model in its configured scaffold; historical open-weight Codex comparisons and superseded models are not included. Models and scaffolds are confounded. Small differences and descriptive changes with time are not significance tests.

## USD

Cost is the arithmetic mean over all 15 attempted trials per model and budget (five per eval). Failed or excluded attempts count toward cost. Judge cost does not. ReAct uses recorded OpenRouter cost. Claude Code uses the CLI's reported API-equivalent list cost; one report without that field uses the token fallback below. Codex always uses the token fallback. These are not subscription cash charges, and the frozen rates are not presented as current market prices.

The fallback reproduces the existing results cost convention: uncached input and cache-write tokens at the pinned input rate, cached input tokens at 10% of that rate, and output tokens at the pinned output rate, divided by one million. `provenance.json` records each model's rates from `configs/lineup.toml` at commit `7a8c937`. Each trial records its cost basis, token inputs and usage-file SHA-256; `summary.json` contains all 22 model–budget averages and their eval components.

## Reproduce

```sh
uv run scripts/plot_eval_results.py
```

The script uses isolated, pinned plotting dependencies without changing the benchmark environment. It reads this frozen snapshot and regenerates the two figures and the numeric summary. It checks that every model–budget–eval cell has five trials and all cells have scored reports.

Scores were graded with GPT-6.1 Sol at high effort through the Codex subscription. Every report row includes the source run name and grade-file SHA-256. The raw reports, usage files and grades are retained in the local archive, not included in this numeric snapshot. The hashes permit verification against that archive; this snapshot alone does not reproduce judge calls. Integrating the grading pipeline and raw evidence into the publication branch remains separate from this figure update.
