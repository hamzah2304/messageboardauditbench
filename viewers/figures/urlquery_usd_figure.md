# URLQuery v6: performance versus USD per run

Open [the interactive figure](urlquery_usd_figure.html). It is built from the final
`urlquery-agents-v6-10` and `urlquery-agents-v6-30` runs (12 models, two
replicates per budget). Each model-budget mark shows mean score against mean
USD cost over valid runs, on a log USD axis. Individual runs are not drawn.
The data file records excluded runs and reasons: five ended before the required
75% runtime, and one Sonnet 5 report had only 194 words against a requested
2,400-word minimum. Thus 42 of 48 graded reports enter the plotted results.

Rebuild after data or presentation changes:

```sh
python3 viewers/build_urlquery_usd_figure.py
```

The [data file](urlquery_usd_figure.json) has one row per run. Its `performance`
values are the `score_mean` from the 48 complete GPT-6 Astra high-effort grades
in `reports/urlquery/graded/judge_gpt_6_astra_high/`. Those grades use the
reviewed findings file (`findings_sha256` recorded in the JSON), which differs
from the current `urlquery/main` `findings_v1.json`; interpret the points as
scores under that reviewed rubric. The grade files themselves stay untracked
because they quote reports. To re-import a matching batch:

```sh
python3 viewers/build_urlquery_usd_figure.py --grades-dir /path/to/judge_gpt_6_astra_high
```

The builder checks the judge, rubric and prompt hashes, all 12 findings, all
48 run IDs, and each report hash. A rebuild without `--grades-dir` preserves
the existing scores by run directory name.

For Codex subscription runs, USD is a token-equivalent estimate at the
[OpenAI Standard short-context API list price](https://developers.openai.com/api/docs/pricing)
checked 2026-09-27. Other models use the run's recorded `usage.json`
`cost_usd`. These are model-run costs; judge costs and subscription charges
are excluded. The short Sonnet 5 report also has partial usage and no recorded
USD cost; it is excluded from both axes.
