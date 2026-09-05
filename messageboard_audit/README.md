# MessageBoardAuditBench (Inspect)

An Inspect eval that scores whether a coding agent can investigate the
collusion.wiki edit logs and write a sound incident report. Agents run in the
Docker sandbox (`../sandbox/docker/`, see `../sandbox/README.md`), no web access. Every run becomes an Inspect
`.eval` log you browse with `inspect view`.

## Layout

| file | role |
|---|---|
| `task.py` | two tasks: `messageboard_audit` (run fresh trials) and `messageboard_audit_replay` (import runs already on disk) |
| `solver.py` | `cli_agent` launches `sandbox/docker/run_trial.sh`; `replay` imports a finished run. Both fold the CLI transcript + report into Inspect state |
| `transcripts.py` | converts the Claude Code, Codex and ReAct event streams into Inspect messages + tool calls, so the viewer renders them natively |
| `scorer.py` | `rubric_scorer` (model judge over `rubric.yaml`, per-leaf verdicts in metadata) and `process_metrics` (turns, tokens, wall time, no judge) |
| `rubric.yaml` | starter rubric: positive leaves + penalty leaves, each tagged derivable yes/partly/no. LLM-seeded, needs human validation |

## Setup (once)

```
uv sync                            # installs inspect-ai and this package
../scripts/build_data.sh           # data variants
../sandbox/docker/claude_login.sh  # once, for Claude Code trials
```

The judge needs an API key even though the agents run on subscription:

```
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, and set -T judge=openai/...
```

## Run fresh trials

```
uv run inspect eval messageboard_audit/task.py@messageboard_audit \
  -T agent=claude -T model=claude-opus-5 -T config=blind-20 --epochs 3
uv run inspect eval messageboard_audit/task.py@messageboard_audit \
  -T agent=codex  -T model=gpt-5.6-sol   -T config=context-40 --epochs 3
```

`--epochs N` runs N seeds (the seed is passed to the CLI as the trial seed).
Conditions (prompt, budget, timeout, data variant, effort) come from `configs/<config>.toml`. `-T judge=anthropic/claude-sonnet-5` picks the judge.

## Import runs already on disk

```
uv run inspect eval messageboard_audit/task.py@messageboard_audit_replay
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
