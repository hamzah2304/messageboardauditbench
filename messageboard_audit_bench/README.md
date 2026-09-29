# Inspect tasks: German wiki report and Transluce report

An installable Inspect package with two evals on one harness. Agents run in a
network-isolated Docker sandbox, and every trial becomes an Inspect `.eval` log that
can be explored with `inspect view`.

| task | what it does |
|---|---|
| `german_wiki_report` | fresh trial: investigate the collusion.wiki edit logs and write an incident report, graded with the `v2` + `tldrh` claim sheets |
| `german_wiki_report_grade` | grade staged reports with a claim-sheet rubric |
| `german_wiki_report_replay` | import finished runs from `runs/` into Inspect, with scoring |
| `german_wiki_report_continue` | continue finished ReAct samples with a follow-up request |
| `transluce_report` | fresh trial: investigate the frozen urlquery.net snapshot, graded by the per-finding judge |
| `transluce_report_grade` | grade finished Transluce report runs with the per-finding judge |

Both fresh-trial tasks take `-T version=<MAJOR.MINOR>` and refuse to run if the checkout
is a different version. To run another version, use
`uv run python scripts/run_eval.py <german-wiki-report|transluce-report> --version X -- ...`,
which runs it from its git tag ([version history](../docs/benchmark-versions.md)). The
pre-rename names `messageboard_audit_bench`, `messageboard_audit_bench_replay`,
`messageboard_audit_bench_continue`, `grade_reports`, `urlquery_audit_bench` and
`urlquery_grade_reports` remain as aliases.

`benchmarks.py` records what each benchmark owns: its name, version, configs, data
location and rubric. The Transluce report's details are in
[`benchmarks/urlquery/README.md`](../benchmarks/urlquery/README.md); its options are
listed [below](#transluce-report-options).

## Layout

| file | role |
|---|---|
| `benchmarks.py` | the benchmark registry: names, versions and the version guard, run/report roots, the URLQuery manifest and dataset pin |
| `configs.py` | loads and validates a benchmark's named trial configs |
| `task.py` | fresh, replay and ReAct continuation tasks; `transluce_report` shares the fresh-task builder |
| `grading/` | German wiki claim sheets (`core.py`, `scorer.py`) and the Transluce finding judge (`findings.py`, `finding_scorer.py`); `task.py` holds `german_wiki_report_grade` and `transluce_report_grade` |
| `urlquery_*.py` | URLQuery data acquisition, corpus build and the batch launcher |
| `native.py` | runs Claude Code and Codex through Inspect SWE, or Inspect's built-in ReAct agent, then collects `report.md` |
| `solver.py` | `subscription_agent` launches `sandbox/docker/run_trial.sh`; `replay` imports a finished run |
| `transcripts.py` | loss-aware conversion of subscription and historical CLI events into Inspect messages + tool calls |
| `scorer.py` | report-quality, process, and report-length scorers |
| `rubric.yaml` | starter rubric: positive leaves + penalty leaves, each tagged derivable yes/partly/no. LLM-seeded, needs human validation |

## Setup

Run these commands from the repository root:

```
uv sync                           # installs Inspect and registers the plugin
scripts/build_data.sh             # downloads and verifies the data variants
claude setup-token                # preferred subscription Claude credential
# save its token in runs/.claude-oauth-token, or export CLAUDE_CODE_OAUTH_TOKEN
```

The eval deliberately depends on the repository's Docker sandbox, configs, and
locally built dataset. If the Python package was installed non-editably, run
Inspect from the checkout root or set `MESSAGEBOARD_AUDIT_BENCH_ROOT` to it.

Native execution needs the model provider key selected with `--model`. The
judge also needs a provider key:

```
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, and set -T judge=openai/...
```

## Run native Inspect SWE trials

```
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=claude -T config=blind -T time_limit_minutes=30 \
  -T min_runtime_fraction=0.75 \
  --model anthropic/claude-opus-4-1 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=codex -T config=context -T time_limit_minutes=40 \
  --model openai/gpt-5 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T agent=react -T config=blind \
  -T time_limit_minutes=20 \
  --model openai/gpt-5 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3
```

`--epochs N` is Inspect's standard option for N independent replicates.
Replicate numbers identify runs; they do not seed model sampling. Use
`--max-samples 1` to serialize epochs when running a subscription-backed CLI.
The task supports three harnesses: `claude` invokes Inspect SWE's Claude Code
agent, `codex` invokes Inspect SWE's Codex CLI agent, and `react` invokes
Inspect's model-neutral ReAct agent. The default is Claude Code. These are
different agent scaffolds, so comparisons across harnesses are not bare-model
comparisons.

### Inspect integration boundary

The default `backend=inspect` path is native end to end: Inspect owns model
selection, provider calls, prompt caching, the Docker sandbox, scoped time
limits, token accounting, and live log events. Claude Code and Codex are their
normal CLI interfaces and tools inside the sandbox; Inspect SWE supplies their
model bridge, so Inspect's generation config—not a subscription CLI setting—
governs model calls. Providers may reject or map unsupported reasoning-effort
levels; the requested level is recorded in task and sample metadata. The
wrapper only retrieves the report after the agent finishes (or the scoped time
limit fires). Provider refusals receive two same-model retries. Terminal
refusals are recorded from Inspect's normalized stop reason. Claude Code's
built-in safeguard model switching is not disabled.

`-T config=blind|context|mythos5|rubyhack` chooses the prompt and its fixed data/effort
profile; config names never encode time. `-T time_limit_minutes=N` controls
the stated budget and the scoped Inspect agent limit. An outer task guard gives
native cleanup five additional minutes; it does not give the agent more time.
The shared `time_left` sandbox command reports the same deadline. If omitted,
the time limit defaults to 20 minutes for every config.
`-T min_runtime_fraction=F` controls the shared minimum-runtime policy,
independently of config and budget. It defaults to `0.75`: normal completion
before 75% of the budget resumes the same session. The prompt states the exact
fraction and earliest finish time, and asks the agent to use resumed time to
verify evidence and improve `report.md`, not idle. Set `F=0` only for an
ablation. Refusals, failures, and hard limits are not resumed. Subscription
agents are told exactly N minutes; their container gets five additional minutes
to stop and finish writing, and the host guard allows another five minutes for
recovery and transcript folding.
The `blind` config currently renders the provenance-recorded `blind-v2`
template; `context` retains its own template.
Native Claude Code and Codex install lifecycle hooks without replacing Inspect
SWE's API bridge configuration. They inject the remaining time after every tool
call and report-length feedback only when the file is over the strict maximum.
Inspect ReAct appends the same feedback directly to its tool results. The
`post_tool_hook_fired` and `stop_hook_fired` metadata fields make this auditable
in Inspect logs.
`-T judge=openai/gpt-5.6-sol` picks the default judge;
an Inspect `grader` model role takes precedence when one is supplied.

## Run with a subscription CLI

```
uv run inspect eval messageboard_audit_bench/german_wiki_report \
  -T backend=subscription -T agent=claude \
  -T subscription_model=claude-opus-5 \
  -T config=blind -T time_limit_minutes=30 \
  -T judge=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
```

The subscription backend preserves the normal built-in tools, existing login,
and restricted proxy runner. Credentials and permitted vendor endpoints remain
accessible to agent commands; this trade-off is accepted for these evaluations.
Its model calls necessarily occur outside Inspect, so it cannot have live
Inspect SWE model events. Afterward, a loss-aware importer maps CLI text,
reasoning, tool calls/results, errors, and usage into Inspect's
message schema. Conversion diagnostics appear in sample metadata. Claude Code's
built-in safeguard switch remains enabled and any served fallback is recorded;
terminal refusals are still eligible for the task's bounded reruns. Codex is
relaunched at most twice when it exits on a capacity error before completing a
turn. Run
`PYTHONPATH=. python scripts/check_transcript_conversion.py runs` to verify all
completed local trajectories have valid, one-to-one tool call/result IDs.

## Import runs already on disk

```
uv run inspect eval messageboard_audit_bench/german_wiki_report_replay
```

Folds matching `runs/` directories that contain transcripts (including
interrupted runs, but skipping `failed_*`) into one eval and scores each. Use
this to bring past trajectories into the viewer without spending model time.

## Inspect the logs (the recommended way)

```
uv run inspect view          # opens the browser log viewer
```

You get, per run: the full message timeline (agent text, each bash command and
its output, the reasoning where available), the report as the sample output, the
rubric score with per-leaf hit/miss in the score metadata, and the process
metrics (turns, tokens, wall time). Select two runs to compare side by side.

Native runs explicitly set Inspect's `cache_prompt=True`; provider caching and
separate cache-read/cache-write usage appear in the standard Inspect log.
Subscription and replay runs use the CLI's reported counters. A nonzero cache
read value confirms a hit. The conversion step neither replays model calls nor
spends tokens.

Programmatic access:

```
uv run python -c "from inspect_ai.log import list_eval_logs, read_eval_log; \
  lg=read_eval_log(list_eval_logs('logs')[-1].name); print(lg.results)"
```

To export native reports for the repository's report/grade tooling, use the
public Inspect Log API wrapper rather than reading `.eval` files directly:

```
uv run python scripts/export_inspect_reports.py --logs logs --out reports/native
```

This defaults to native `backend=inspect` samples. `--backend all` also exports
subscription imports. Reports are grouped by agent scaffold, while backend
labels remain available in index rows.

## Report length

The round-3 conditions ask for 2,500–3,000 words and call 3,000 a strict upper
limit. The separate `report_length` scorer accepts any nonempty report through
3,200 words, so short reports pass and a small overrun is tolerated without
revealing that tolerance to the agent. Missing, empty, and longer reports fail
that score without changing the report-quality score.

If a native agent stops with an over-3,000-word report and at least a minute
remains, the wrapper resumes the same Claude Code, Codex CLI, or ReAct session
once with a request to shorten it. Subscription hooks likewise request shortening only for
overlong reports and allow the next stop. Post-tool feedback supplies the word
count after every saved report edit, including short and within-range drafts. Normal early finishes resume until the configured minimum runtime; the
length check itself does not force expansion of a short report. `report_length` in the
sandbox reports the current whitespace-based count on demand.

## Transluce report options

`transluce_report` shares the fresh-trial options of `german_wiki_report` (`agent`,
`backend`, `subscription_model`, `time_limit_minutes`, `min_runtime_fraction`,
`version`), and adds its own:

| option | default | meaning |
|---|---|---|
| `config` | `urlquery-agents-v6-30` | a config listed in `benchmarks/urlquery/benchmark.json` (`urlquery-agents-v6-30`, `urlquery-agents-v6-10`) |
| `judge` | `anthropic/claude-opus-5-5` | any `anthropic/<model>` or `openrouter/<model>`; `openrouter/openai/gpt-6-astra` is the final-run judge. A `grader` model role takes precedence |
| `judge_effort` | `xhigh` (Anthropic), `high` (others) | the judge's reasoning effort |
| `article_context` | `omitted` (Anthropic), `full` (others) | whether the judge reads Transluce's article or only the reviewed findings and their quotes |

There is no `data_variant` or `rubric` option: the snapshot and the rubric are pinned by
the manifest. `transluce_report_grade` takes `runs` (a glob under `runs/urlquery/`),
`batch` (a batch-launcher plan directory) or `launch` (a `launch.json`), plus the same
judge options.

```
uv run inspect eval messageboard_audit_bench/transluce_report \
  -T agent=claude --model anthropic/claude-opus-5-5          # Inspect-native, no network
uv run inspect eval messageboard_audit_bench/transluce_report_grade \
  -T launch=runs/urlquery/final-20260927-agents-v6/launch.json -T judge=openrouter/openai/gpt-6-astra
```

## Draft incidents

`scripts/build_data.sh` also builds the Mythos 5 transcript and the RubyHack package
corpus. These are drafts for future evals, not configs of `german_wiki_report`: the task
rejects `config=mythos5` and `config=rubyhack`. `scripts/incident_pipeline.py check`
validates them offline through `task.incident_task`. Pilot one through the subscription
runner (`CONFIG=mythos5 sandbox/docker/run_trial.sh react <model> 1`); see
[`docs/adding-an-incident.md`](../docs/adding-an-incident.md).

## Notes / next steps

- `german_wiki_report` defaults to `v2,tldrh`; the drafts' sheets are `m5,m5tldrh`
  (Mythos 5) and `rh,rhtldrh` (RubyHack).
  `rubric.yaml` is available only through `-T rubric=legacy`.
  See [setup and ablation commands](../docs/getting-started.md).
- Comparing Claude-in-Claude-Code against GPT-in-Codex is a *system* comparison,
  not a bare-model one. `-T agent=react --model=<inspect model>` runs Inspect's
  standard ReAct agent for a more model-centred comparison.

Development checks run with `uv run ruff check .` and `uv run pytest -q`.
