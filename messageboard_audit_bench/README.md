# MessageBoardAuditBench (Inspect)

An installable Inspect eval that scores whether a coding agent can investigate
the collusion.wiki edit logs and write a sound incident report. Agents run in a
network-isolated Docker sandbox. Every trial becomes an Inspect `.eval` log
that can be explored with `inspect view`.

## Layout

| file | role |
|---|---|
| `task.py` | two tasks: `messageboard_audit_bench` (run fresh trials) and `messageboard_audit_bench_replay` (import runs already on disk) |
| `solver.py` | `cli_agent` launches `sandbox/docker/run_trial.sh`; `replay` imports a finished run. Both fold the CLI transcript + report into Inspect state |
| `transcripts.py` | converts the Claude Code, Codex and ReAct event streams into Inspect messages + tool calls, so the viewer renders them natively |
| `scorer.py` | `rubric_scorer` (model judge over `rubric.yaml`, per-leaf verdicts in metadata) and `process_metrics` (turns, tokens, wall time, no judge) |
| `rubric.yaml` | starter rubric: positive leaves + penalty leaves, each tagged derivable yes/partly/no. LLM-seeded, needs human validation |

## Setup

Run these commands from the repository root:

```
uv sync                           # installs Inspect and registers the plugin
scripts/build_data.sh             # downloads and verifies the data variants
sandbox/docker/claude_login.sh    # once, for Claude Code trials
```

The eval deliberately depends on the repository's Docker sandbox, configs, and
locally built dataset. If the Python package was installed non-editably, run
Inspect from the checkout root or set `MESSAGEBOARD_AUDIT_BENCH_ROOT` to it.

The judge needs an API key even though the agents run on subscription:

```
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, and set -T judge=openai/...
```

## Run fresh trials

```
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=claude -T model=claude-opus-5 -T condition=blind \
  -T time_limit_minutes=30 \
  --epochs 3 --max-samples 1
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=codex -T model=gpt-5.6-sol -T condition=context \
  -T time_limit_minutes=40 \
  --epochs 3 --max-samples 1
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T model=openai/gpt-5.6-sol -T condition=blind \
  -T time_limit_minutes=20 \
  --epochs 3
```

`--epochs N` runs N independent replicates. Replicate numbers identify runs;
they do not seed model sampling. Use `--max-samples 1` to serialize epochs when
running a subscription-backed CLI.
The task supports all three existing harnesses: `claude` invokes Claude Code,
`codex` invokes Codex CLI, and `react` invokes the model-neutral OpenRouter tool
loop. The default is Claude Code, not ReAct. These are system-level conditions,
so comparisons across harnesses are not bare-model comparisons.

### Inspect integration boundary

The task, custom solver, scorers, package registration, `.eval` output, and log
viewer integration are native Inspect components. The current Claude Code and
Codex execution path is not the `inspect-swe` agent bridge: the custom solver
launches the repository's hardened Docker runner and folds each CLI transcript
into Inspect after the process finishes. Consequently, use `-T model=...`, not
Inspect's top-level `--model`; Inspect's native per-generation limits and live
model-event stream do not control these external CLI calls. The repository's
own deadline, timeout, usage accounting, and isolation controls do apply.

For a fully Inspect-managed coding-agent run, this solver should be migrated to
the `inspect_swe.claude_code()` and `inspect_swe.codex_cli()` agents. Those
agents proxy model calls through Inspect, making Inspect model selection,
limits, checkpointing, and live logs apply normally.

`-T condition=blind|context` chooses the prompt and its fixed data/effort
profile; condition names never encode time. `-T time_limit_minutes=N` controls
the stated budget and sets the hard sandbox timeout to `N` plus the condition's
five-minute timeout grace. If omitted, the time limit defaults to 20 minutes
for every condition.
`-T judge=anthropic/claude-sonnet-5` picks the judge;
an Inspect `grader` model role takes precedence when one is supplied.

## Import runs already on disk

```
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_replay
```

Folds every `runs/*_s*` directory (skipping `failed_*`) into one eval, scores
each. Use this to bring past baseline runs into the viewer without spending
model time.

## Inspect the logs (the recommended way)

```
uv run inspect view          # opens the browser log viewer
```

You get, per run: the full message timeline (agent text, each bash command and
its output, the reasoning where available), the report as the sample output, the
rubric score with per-leaf hit/miss in the score metadata, and the process
metrics (turns, tokens, wall time). Select two runs to compare side by side.

The process metrics distinguish total input, uncached input, cache reads, and
the cache-read fraction. Claude Code and Codex CLI retain their native caching
behavior. The ReAct loop keeps an append-only conversation with stable tools
and instructions, uses OpenRouter's cache controls, and sends one stable
`session_id` throughout the trial so routing stays on the same provider. A
nonzero `cache_read_tokens` value confirms that a provider cache was hit.

Programmatic access:

```
uv run python -c "from inspect_ai.log import list_eval_logs, read_eval_log; \
  lg=read_eval_log(list_eval_logs('logs')[-1].name); print(lg.results)"
```

## Notes / next steps

- The judge is only as good as `rubric.yaml`; expand and human-validate it, then
  add the claim-precision and citation-support scorers described in
  `../docs/design-notes.md`.
- Comparing Claude-in-Claude-Code against GPT-in-Codex is a *system* comparison,
  not a bare-model one. `-T agent=react -T model=<openrouter id>` runs the bare
  tool loop in `sandbox/react_agent.py` for model-only numbers.

Development checks run with `uv run ruff check .` and `uv run pytest -q`.
