# URLQuery v6: performance versus USD per run

Open [the interactive figure](urlquery_usd_figure.html). It is built from the final
`urlquery-agents-v6-10` and `urlquery-agents-v6-30` runs (12 models, two
replicates per budget). The figure shows completed runs on a log USD axis;
performance stays `null` until the URLQuery grades are ready.

Rebuild as the remaining runs finish:

```sh
python3 viewers/build_urlquery_usd_figure.py
```

The editable [data file](urlquery_usd_figure.json) has one row per run. Set
`performance` to a 0–1 score for each graded run, then rebuild. The builder
preserves non-null scores by run directory name. A model-budget point appears
on the performance plot after **both** replicates have scores. Until then,
its available costs appear in the pending strip.

For Codex subscription runs, USD is a token-equivalent estimate at the
[OpenAI Standard short-context API list price](https://developers.openai.com/api/docs/pricing)
checked 2026-09-27. Other models use the run's recorded `usage.json`
`cost_usd`. These are model-run costs; judge costs and subscription charges
are excluded. The cost average for a budget uses whichever runs have finished
and updates as the batch completes.
