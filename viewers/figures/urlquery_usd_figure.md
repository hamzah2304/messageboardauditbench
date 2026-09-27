# URLQuery v6: performance versus USD per run

Open [the USD figure](urlquery_usd_figure.html) or [the capability figure](urlquery_capability_figure.html). Both are built from the final
`urlquery-agents-v6-10` and `urlquery-agents-v6-30` runs (12 models, two
replicates per budget). Each model-budget mark shows mean score against mean
USD cost over valid runs, on a log USD axis. Individual runs are not drawn.
The runtime cutoff is strictly more than 5 minutes for 10-minute runs and
strictly more than 15 minutes for 30-minute runs. The data file records excluded
runs and reasons. One Sonnet 5 report had only 194 words against a requested
2,400-word minimum, so 47 of 48 graded reports enter the plotted results.
Drag model names in the figure to adjust their placement; positions are saved
in this browser. **Reset labels** restores the default layout.
Both plots focus the score axis on 0.15–0.55; the underlying scores remain on
the 0–1 scale. The USD plot spans $0.03–$20 per run.

The capability plot uses the repository's Epoch Capabilities Index snapshot
retrieved 2026-09-07. Eight of the twelve models have a value. Gemini 3.8 Flash
and Muse Spark 1.3 use the previous generation's value as a marked proxy;
GPT-6 Sol, GPT-6 Luna, Opus 4.6, and DeepSeek V4 Flash lack a value and are
omitted from that plot. Their report scores remain in the table.

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
