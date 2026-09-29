# URLQuery v6: rescored findings versus USD per run

Open [the rescored USD figure](urlquery_usd_rescored_figure.html). It shows the
final v6 runs under the 13-finding fairness v3 score. The earlier
[12-finding USD figure](urlquery_usd_figure.html) remains available separately.

The score is the judge's weighted `score_mean` (F3 has weight 0.5, every other
finding weight 1). The data file records the judge and rubric hashes, the
13-finding provenance, each run's score and cost, and the excluded report.
All 48 final reports were graded; 47 enter the figure. The remaining Sonnet 5
report was only 194 words against the requested 2,400-word minimum. Eligible
runs must also exceed 5 minutes for the 10-minute budget or 15 minutes for
the 30-minute budget.

The plot shows model-budget mean scores against mean USD costs, with hollow
10-minute and filled 30-minute marks. Individual runs are not drawn. Drag
model labels to arrange them; **Reset labels** restores their positions.

Rebuild from the grade batch in the findings worktree:

```sh
python3 viewers/build_urlquery_usd_figure.py --rescored \
  --grades-dir ../codex-urlquery-derivability/reports/urlquery/graded/judge_gpt_6_astra_high_fairness_v3
```

The builder verifies the complete 48-run grade batch, consistent rubric and
prompt hashes, all 13 successful finding judgments and their weighted means,
and each report hash. The individual grade files stay untracked because they
quote reports. USD accounting follows the [original figure notes](urlquery_usd_figure.md).
