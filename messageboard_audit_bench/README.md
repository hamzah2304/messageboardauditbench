# MessageBoardAuditBench (Inspect)

An installable Inspect eval that scores whether a coding agent can investigate
the collusion.wiki edit logs and write a sound incident report. Agents run in a
network-isolated Docker sandbox. Every trial becomes an Inspect `.eval` log
that can be explored with `inspect view`.

## Layout

| file | role |
|---|---|
| `task.py` | two tasks: `messageboard_audit_bench` (run fresh trials) and `messageboard_audit_bench_replay` (import runs already on disk) |
| `native.py` | runs Claude Code and Codex through Inspect SWE, or Inspect's built-in ReAct agent, then collects `report.md` |
| `solver.py` | `subscription_agent` launches `sandbox/docker/run_trial.sh`; `replay` imports a finished run |
| `transcripts.py` | loss-aware conversion of subscription and historical CLI events into Inspect messages + tool calls |
| `scorer.py` | `rubric_scorer` (model judge over `rubric.yaml`, per-leaf verdicts in metadata) and `process_metrics` (turns, tokens, wall time, no judge) |
| `rubric.yaml` | starter rubric: positive leaves + penalty leaves, each tagged derivable yes/partly/no. LLM-seeded, needs human validation |

## Setup

Run these commands from the repository root:

```
uv sync                           # installs Inspect and registers the plugin
scripts/build_data.sh             # downloads and verifies the data variants
sandbox/docker/claude_login.sh    # only for subscription Claude trials
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
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=claude -T condition=blind -T time_limit_minutes=30 \
  --model anthropic/claude-opus-4-1 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=codex -T condition=context -T time_limit_minutes=40 \
  --model openai/gpt-5 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T condition=blind \
  -T time_limit_minutes=20 \
  --model openai/gpt-5 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3
```

`--epochs N` runs N independent replicates. Replicate numbers identify runs;
they do not seed model sampling. Use `--max-samples 1` to serialize epochs when
running a subscription-backed CLI.
The task supports three harnesses: `claude` invokes Inspect SWE's Claude Code
agent, `codex` invokes Inspect SWE's Codex CLI agent, and `react` invokes
Inspect's model-neutral ReAct agent. The default is Claude Code. These are
system-level conditions, so comparisons across harnesses are not bare-model
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
limit fires).

`-T condition=blind|context` chooses the prompt and its fixed data/effort
profile; condition names never encode time. `-T time_limit_minutes=N` controls
the stated budget and the scoped Inspect agent limit. An outer task guard gives
native cleanup five additional minutes; it does not give the agent more time.
The shared `time_left` sandbox command reports the same deadline. If omitted,
the time limit defaults to 20 minutes for every condition.
`-T judge=anthropic/claude-sonnet-5` picks the judge;
an Inspect `grader` model role takes precedence when one is supplied.

## Run with a subscription CLI

```
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T backend=subscription -T agent=claude \
  -T subscription_model=claude-opus-5 \
  -T condition=blind -T time_limit_minutes=30 \
  -T judge=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
```

The subscription backend uses the existing login and hardened proxy runner.
Its model calls necessarily occur outside Inspect, so it cannot have live
Inspect SWE model events. Afterward, a loss-aware importer maps CLI text,
reasoning, tool calls/results, errors, fallbacks, and usage into Inspect's
message schema. Conversion diagnostics appear in sample metadata. Run
`PYTHONPATH=. python scripts/check_transcript_conversion.py runs` to verify all
completed local trajectories have valid, one-to-one tool call/result IDs.

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

## Notes / next steps

- The judge is only as good as `rubric.yaml`; expand and human-validate it, then
  add the claim-precision and citation-support scorers described in
  `../docs/design-notes.md`.
- Comparing Claude-in-Claude-Code against GPT-in-Codex is a *system* comparison,
  not a bare-model one. `-T agent=react --model=<inspect model>` runs Inspect's
  standard ReAct agent for a more model-centred comparison.

Development checks run with `uv run ruff check .` and `uv run pytest -q`.
