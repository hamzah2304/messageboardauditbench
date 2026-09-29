# Getting started

Run the benchmarks from a checkout with Python 3.11+, [uv](https://docs.astral.sh/uv/),
and Docker running. This guide follows the German wiki report (`german_wiki_report`). The
Transluce report (`transluce_report`) uses the same install, credentials and Docker setup;
its data and runs are covered [at the end](#the-transluce-report).

## Install and verify the data

```bash
git clone https://github.com/hamzah2304/messageboardauditbench
cd messageboardauditbench
uv sync --frozen
scripts/build_data.sh
scripts/build_data.sh --verify
scripts/doctor.sh
uv run python scripts/incident_pipeline.py check --docker
```

The build downloads the public wiki archive and dispatches every registered
incident builder, then checks the generated datasets against committed checksums.
The Mythos builder removes
the release's editorial metadata row before it reaches an agent. A mismatch must
be resolved before comparing new scores with published results. Do not rebuild
the shared data while trials are reading it.

If the upstream host is unreachable or has moved, the build does not depend on it.
Any copy of `full-wiki-logs.zip` works, because the pinned SHA256 in
`scripts/fetch_data.sh` is what establishes that a copy is the benchmark's dataset:

```bash
MBAB_DUMP_ARCHIVE=/path/to/full-wiki-logs.zip scripts/build_data.sh   # a local copy
MBAB_DUMP_URL=https://example.org/full-wiki-logs.zip scripts/build_data.sh  # a mirror
```

Both are verified against the same digest, and a copy that does not match is
rejected. `scripts/fetch_data.sh` prints these instructions on a failed download.
The Mythos transcript has the same source-independent escape hatch:

```bash
MBAB_MYTHOS5_TRANSCRIPT=/path/to/transcript.jsonl scripts/build_data.sh
```

The local file must match the source digest pinned in
`scripts/build_mythos5_data.py`.

RubyHack is rebuilt from the 23 preserved Diffend pages cited by the
investigation. Each page is canonicalized only by removing its changing CSRF
token, then checked against a pinned digest. For an offline build, place those
pages under their builder-generated filenames and set:

```bash
MBAB_RUBYHACK_SOURCE_DIR=/path/to/diffend-pages scripts/build_data.sh
```

The builder extracts package diff lines and redacts embedded RubyGems API keys;
it never writes the source HTML into the repository.

The Python package needs the checkout's configs, sandbox and grading assets.
A wheel installed by itself is insufficient: run from the checkout root or set
`MESSAGEBOARD_AUDIT_BENCH_ROOT` to that checkout.

## Credentials and Docker access

Copy `.env.example` to `.env` and fill in the credentials for your chosen agent
and grader. Load that file explicitly when running Inspect:

```bash
uv run --env-file .env inspect eval ...
```

Run this command from a terminal or agent execution environment that can reach
Docker (`docker info`). An agent's restricted execution environment may lack
Docker access, and a Docker-enabled process may not inherit the same environment
variables. Loading `.env` in that process makes the credentials available there;
it does not grant Docker access. The matrix launcher loads `.env` when present.
A Claude subscription token authenticates subscription runs; it does not replace
an API key for native Inspect models or grading.

## Run and grade through Inspect

Set the API keys for the agent and grader providers. Native Inspect execution
uses API keys, without a host Claude Code or Codex login. For example, with
`OPENAI_API_KEY` set:

```bash
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=react -T config=blind -T time_limit_minutes=30 \
  --model openai/gpt-5.6-sol \
  --model-role grader=openai/gpt-5.6-sol \
  --epochs 3 --max-samples 1
uv run inspect view
```

The log records the benchmark version (`10.0`). To pin it, add `-T version=10.0`; the
task refuses to run if the checkout is a different version. To run an earlier version,
use the launcher, which runs it from its git tag:

```bash
uv run python scripts/run_eval.py german-wiki-report --list
uv run python scripts/run_eval.py german-wiki-report --version 9.0 -- \
  -T agent=react -T config=blind --model openai/gpt-5.6-sol
```

See [benchmark versions](benchmark-versions.md) for what each version changed.

Use `agent=claude` or `agent=codex` for the Inspect SWE CLI scaffolds, with a
compatible `--model` and its provider key. For a short setup check, use
`-T time_limit_minutes=1 -T min_runtime_fraction=0 --epochs 1`; it still makes
paid agent and grader calls and is not a benchmark result.

Each sample runs the `v2` finding sheets and `tldrh` summary sheet by default, followed
by process and length diagnostics. (The Mythos 5 and RubyHack incidents are drafts for
future evals, not configs of this task; see
[adding an incident](adding-an-incident.md).) The two rubric scores and
per-finding grades appear in the `.eval` log. The judge defaults to
`openai/gpt-5.6-sol`; `--model-role grader=...` overrides it. Reproducing a
published comparison requires its recorded judge, prompts and data version.
The sheet mean differs from the figures' strict score: they transform each
finding credit `s` to `max(2s - 1, 0)` before averaging.

To see the registered maturity, defaults, rubrics, and results status for every
incident, or exact commands for one of them:

```bash
uv run python scripts/incident_pipeline.py list
uv run python scripts/incident_pipeline.py guide rubyhack
```

To select one rubric use `-T rubric=v2` or `-T rubric=tldrh`; comma-separated
modes run together. `-T rubric=legacy` selects the older starter rubric only.
To defer all scoring, use Inspect's `--no-score`, then `inspect score LOG.eval`.

The Mythos 5 integration is a runnable transfer-study draft:

```bash
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=react -T config=mythos5 -T time_limit_minutes=30 \
  --model openai/gpt-5.6-sol --model-role grader=openai/gpt-5.6-sol
```

Do not present its score as comparable with the published wiki cells until the
documented contamination and judge-independence questions have been resolved.

The RubyHack package-forensics incident runs the same way. Its selected corpus
is much smaller, so start with the 10-minute condition and an independent judge:

```bash
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=react -T config=rubyhack -T time_limit_minutes=10 \
  --model openai/gpt-5.6-sol \
  --model-role grader=anthropic/claude-fable-5-1
```

The selected package diffs do not independently establish OpenAI attribution or
campaign-wide totals. The RubyHack rubrics reward reports that preserve those
limits.

## Ablations

The provider-attribution ablation uses the same task and time parameter:

```bash
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=react -T config=blind -T time_limit_minutes=30 \
  -T data_variant=verbatim_anthropic \
  --model openai/gpt-5.6-sol --model-role grader=openai/gpt-5.6-sol
```

The grader automatically uses the Anthropic-swapped sheets and answer key.
This is a new run under the current prompt; historical `blind-*-anthropic`
configs used an earlier prompt and remain available to the direct runner.

For a ReAct continuation, use the parent `.eval` log:

```bash
uv run inspect eval messageboard_audit_bench/german_wiki_report_continue \
  -T parent_log=logs/PARENT.eval -T parent_epochs=1,2,3 \
  -T config=followup-5k-min5 \
  --model-role grader=openai/gpt-5.6-sol --max-samples 1
```

This restores the conversation and report, inherits the parent's data variant
and model, and grants ten more minutes with a five-minute minimum working
period. Other scratch files are not restored. `followup-5k` uses the same longer
report request without the minimum. Both run the benchmark graders inline.
One parent sample per epoch is required; continuing a continuation is not
supported by this interface.

Historical Codex followups use native subscription session resume through
`scripts/run_followup.sh`; Claude Code continuation is not implemented. See
[the release audit](release-readiness.md) for the remaining corpus work.

## Export or grade existing reports

```bash
uv run python scripts/export_inspect_reports.py --logs logs --out reports/native
uv run python scripts/export_grades.py logs/EVAL_LOG.eval

# A grading-only eval: no agent execution or Docker.
uv run inspect eval messageboard_audit_bench/german_wiki_report_grade \
  -T dir=round4_blind120 -T rubric=v2 \
  --model-role grader=openai/gpt-5.6-sol
```

`grade_reports` accepts a folder under `benchmark/graded_inputs/` or an absolute
path. Its `_index.jsonl` supplies each report's data variant. For an unindexed
Anthropic report folder, pass `-T variant=anthropic`. Run it again with
`-T rubric=tldrh` for summary grades. Missing or failed sheets are recorded in
score metadata; inspect these before publishing aggregates.

Subscription trial setup, credentials and the direct Docker runner are described
in [`sandbox/README.md`](../sandbox/README.md). Import existing subscription
runs with `messageboard_audit_bench/german_wiki_report_replay`; this spends
judge tokens but does not rerun the agents.

## Historical experiment launcher

`scripts/run_round4.py` reproduces the publication matrix, rather than a single
smoke test. Selecting only `--time-limit-minutes 10` selects 13 systems and 39
samples. The historical manifest defers grading (`score_during_generation = false`);
the normal `inspect eval` task above runs both graders by default.

To inspect a one-sample subset without launching it:

```bash
uv run scripts/run_round4.py --system react-gpt-5-6-sol --time-limit-minutes 10 --epochs 1
```

The launcher prints its grading policy and commands; `--execute` is required to
launch them. Use the normal Inspect command for a small graded setup test.

Figure rendering finds Chrome/Chromium on `PATH` or in standard installation
locations. Set `CHROME_BIN` to an executable path to override discovery.

## The Transluce report

The Transluce report reads a frozen urlquery.net snapshot that lives only in the primary
checkout's gitignored `data/urlquery/2026-09-26-v1/`. It is built from public
urlquery.net JSON (`messageboard_audit_bench.urlquery_data` and `urlquery_prepare`, driven
by `configs/urlquery-data.toml`). The task checks it against the pinned hash before an
agent starts.

```bash
# one trial, graded by the default judge (Opus 5.5, article omitted)
uv run inspect eval messageboard_audit_bench/transluce_report \
  -T agent=claude --model anthropic/claude-opus-5-5
# a model matrix through the batch launcher, then grade the finished runs
uv run python -m messageboard_audit_bench.urlquery_pilot --batch configs/urlquery-final-batch.toml --launch
uv run python benchmarks/urlquery/judge/grade.py --batch runs/urlquery/<plan-dir> --plan   # resume-aware call count
```

[`benchmarks/urlquery/README.md`](../benchmarks/urlquery/README.md) covers the configs,
the judge choice and the grade files. URLQuery reports can quote recorded secrets, so
keep them out of tracked folders; the exporters refuse them.
