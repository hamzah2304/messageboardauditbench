# Getting started

Run the benchmark from a checkout with Python 3.11+, [uv](https://docs.astral.sh/uv/),
and Docker running.

## Install and verify the data

```bash
git clone https://github.com/hamzah2304/messageboardauditbench
cd messageboardauditbench
uv sync --frozen
scripts/build_data.sh
scripts/build_data.sh --verify
scripts/doctor.sh
```

The build downloads the public archive and checks the generated datasets against
committed checksums. A mismatch must be resolved before comparing new scores with
published results. Do not rebuild the shared data while trials are reading it.

If the upstream host is unreachable or has moved, the build does not depend on it.
Any copy of `full-wiki-logs.zip` works, because the pinned SHA256 in
`scripts/fetch_data.sh` is what establishes that a copy is the benchmark's dataset:

```bash
MBAB_DUMP_ARCHIVE=/path/to/full-wiki-logs.zip scripts/build_data.sh   # a local copy
MBAB_DUMP_URL=https://example.org/full-wiki-logs.zip scripts/build_data.sh  # a mirror
```

Both are verified against the same digest, and a copy that does not match is
rejected. `scripts/fetch_data.sh` prints these instructions on a failed download.

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
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=blind -T time_limit_minutes=30 \
  --model openai/gpt-5.6-sol \
  --model-role grader=openai/gpt-5.6-sol \
  --epochs 3 --max-samples 1
uv run inspect view
```

Use `agent=claude` or `agent=codex` for the Inspect SWE CLI scaffolds, with a
compatible `--model` and its provider key. For a short setup check, use
`-T time_limit_minutes=1 -T min_runtime_fraction=0 --epochs 1`; it still makes
paid agent and grader calls and is not a benchmark result.

Each sample runs the existing `v2` finding sheets and `tldrh` summary sheet by
default, followed by process and length diagnostics. The two rubric scores and
per-finding grades appear in the `.eval` log. The judge defaults to
`openai/gpt-5.6-sol`; `--model-role grader=...` overrides it. Reproducing a
published comparison requires its recorded judge, prompts and data version.
The sheet mean differs from the figures' strict score: they transform each
finding credit `s` to `max(2s - 1, 0)` before averaging.

To select one rubric use `-T rubric=v2` or `-T rubric=tldrh`; comma-separated
modes run together. `-T rubric=legacy` selects the older starter rubric only.
To defer all scoring, use Inspect's `--no-score`, then `inspect score LOG.eval`.

## Ablations

The provider-attribution ablation uses the same task and time parameter:

```bash
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=blind -T time_limit_minutes=30 \
  -T data_variant=verbatim_anthropic \
  --model openai/gpt-5.6-sol --model-role grader=openai/gpt-5.6-sol
```

The grader automatically uses the Anthropic-swapped sheets and answer key.
This is a new run under the current prompt; historical `blind-*-anthropic`
configs used an earlier prompt and remain available to the direct runner.

For a ReAct continuation, use the parent `.eval` log:

```bash
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_continue \
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
uv run inspect eval messageboard_audit_bench/grade_reports \
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
runs with `messageboard_audit_bench/messageboard_audit_bench_replay`; this spends
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
