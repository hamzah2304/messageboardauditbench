# Sandbox

Runs an agent (Claude Code, Codex, or a minimal ReAct scaffold over OpenRouter)
against the stripped dump with no web access except its own API endpoint, and
no view of anything but the data.

Everything lives in `sandbox/docker/`. The earlier permissions-based sandbox
(Linux user + iptables) that produced the first baselines was removed on
2026-09-05; `docs/HANDOFF.md` §4 records why.

There are two orchestrators. The default Inspect task uses the same image and
data in a network-disabled Inspect Docker sandbox; Claude Code and Codex obtain
their model connection from Inspect SWE, so Inspect owns the calls and logs
events live. The scripts documented below are the opt-in subscription backend:
they use the repository proxy and logged-in CLI credentials, then import the
recorded event stream into Inspect. See `messageboard_audit_bench/README.md` for
the native commands.

## How isolation works (Docker)

One image (`sandbox/docker/Dockerfile`: python:3.12-slim + jq/ripgrep/sqlite3 +
the `claude` and `codex` binaries, non-root user `agent`), used for three roles:

- **proxy** container: on the normal bridge network *and* on `mbab-inner`, runs
  `sandbox/proxy.py`, an HTTP CONNECT proxy that only forwards to vendor API
  hosts. Every CONNECT is logged (allow/deny) to `<run>/proxy.log`.
- **agent** container: on `mbab-inner` only. That network is created with
  `--internal`, so it has no gateway: nothing outside is routable, even by IP.
  `--dns 0.0.0.0` so outside names don't resolve either. The CLI reaches its
  API only because `HTTPS_PROXY=http://<proxy>:3128`. Filesystem: `/work` holds
  `data/*.jsonl` (read-only) and `prompt.txt`, nothing else; the repo is never
  mounted. Its `~/.claude` and `~/.codex` are throwaway per-run copies of the
  credentials (deleted at exit). No `meta.json` inside; that stays on the host.
- **canary** container: same image, network and mounts, run before every trial.
  Asserts outside DNS fails, direct egress fails (name and IP), the proxy refuses
  `collusion.wiki`, the proxy passes the vendor APIs, and `/work` contains
  exactly the data files and prompt. Saved as `<run>/canary.log`; the trial
  aborts (exit 3) if any check fails.

## Setup

- Docker (on macOS: `colima start`, or Docker Desktop). The image builds itself
  on first run (`docker build -t mbab-sandbox -f sandbox/docker/Dockerfile .`).
- Data: `scripts/build_data.sh` (fetches, strips, builds `data/verbatim`, verifies
  checksums). Every transformation is documented in `docs/data-processing.md`. `DATA_DIR=data/verbatim` selects the verbatim variant; the run name
  then ends in `_verbatim` and `meta.json` records `data_variant`.
- Codex: `~/.codex/auth.json` from a normal `codex login` is copied in.
- ReAct (any OpenRouter model, e.g. Kimi K3): put an OpenRouter key in
  `runs/.openrouter_key` (chmod 600) or export `OPENROUTER_API_KEY`. The
  scaffold is `sandbox/react_agent.py`: a plain tool-calling loop with two tools,
  `bash` and `write_file`, no pip dependencies, transcript in Claude Code's
  stream-json dialect so the parser and `inspect view` work unchanged. Effort is
  passed as OpenRouter's `reasoning.effort`; `BUDGET_MIN` (default 20) stops the
  loop issuing new model calls after that many minutes. Prompt caching markers
  are sent on every request and per-turn cache hits and cost are recorded.
  Time information reaches the model through the prompt and the shared
  `time_left` command.
- Claude: prefer a long-lived token from `claude setup-token`, stored as the
  sole contents of `runs/.claude-oauth-token` (gitignored), or export it as
  `CLAUDE_CODE_OAUTH_TOKEN`. This avoids concurrent refresh races between
  containers. `sandbox/docker/claude_login.sh` and copied credentials remain
  fallbacks for a single trial.

## Run

Every trial is a system (agent + model + replicate) under a config. Replicate
numbers identify nondeterministic runs; they do not seed model sampling. Configs live in
`configs/<name>.toml` and hold the benchmark-relevant conditions: which prompt
(`sandbox/prompts/<name>.txt`), the time budget the prompt states, the hard
kill timeout, the data variant, the reasoning effort, and the Claude Code tools
withheld from the agent. Shipped configs: `blind-20`, `blind-40`, `context-20`,
`context-40` (the `context` prompt prepends a summary of the OpenAI/Hugging Face
incident and says to treat this one as separate), plus `default` = `blind-20`.

In the subscription runner, Claude Code and Codex get the remaining budget
after every tool call via lifecycle hooks (`sandbox/time_left.sh`, wired
through throwaway config directories), and the ReAct scaffold appends it to
each tool result. Native Inspect execution gives all three harnesses the same
feedback and enforces the deadline independently with an Inspect scoped time
limit.

```
CONFIG=blind-20   sandbox/docker/run_trial.sh claude claude-opus-5 1
CONFIG=context-40 sandbox/docker/run_trial.sh codex  gpt-5.6-sol   1
CONFIG=blind-20   sandbox/docker/run_trial.sh react  moonshotai/kimi-k3 1
```

Run names include the config name and end in a unique run ID. `meta.json` records the config, its hash,
the prompt name, the budget, the data variant, the effort, and the hash of the
rendered prompt the agent saw. Env vars `PROMPT`, `BUDGET_MIN`, `TIMEOUT`,
`DATA_DIR`, `EFFORT` override single values for one-off experiments; prefer a
new config file for anything you will compare against.

Batch of many trials, concurrently:

```
cat > matrix.txt <<'M'
# agent  model                   config      replicate
claude   claude-opus-5           blind-20    1
claude   claude-opus-5           context-20  1
codex    gpt-5.6-sol             blind-40    1
react    moonshotai/kimi-k3      blind-20    1
react    google/gemini-3.8-flash context-40  1
M
sandbox/docker/run_batch.sh matrix.txt     # detached; progress in runs/batch_<stamp>.log
```

Lanes run concurrently. The claude and codex lanes run one trial at a time
(one subscription each; `LANE_PARALLEL=1` lifts that); the react lane runs
everything at once. Every trial has its own network and proxy.

Collect the reports for evaluation, one folder per normalized condition, data
variant, effort, and rendered prompt. Legacy time-bearing config names are
normalized to their prompt condition:

```
scripts/collect_reports.py     # -> reports/<condition>_<variant>_<effort>_p<prompt8>/<agent>_<model>_r<replicate>_<stamp>.md
                               #    + CONDITIONS.json per folder, reports/prompts/<prompt8>.txt, reports/index.jsonl
```

Each run writes `runs/<timestamp>_<agent>_<model>_r<replicate>_<config>_<run-id>/`: `canary.log`,
`proxy.log`, `transcript.jsonl` (the CLI's JSON event stream), `stderr.log`,
`meta.json` (exit code, wall time, CLI version, prompt hash), `report.md` (and
`final_message.md` for Codex) copied up from `work/`. `work/` is exactly what the
agent saw. Exit code 124 means the timeout fired.

What each run logs about the model calls (`<run>/usage.json`, written by
`messageboard_audit_bench/usage.py`; the key figures are copied into `meta.json` under
`usage`, and Inspect reads the same numbers through `transcripts.py`):

- tokens: total input, uncached input, output, cache read, cache write, cache-read
  fraction, and **reasoning** (Claude Code's
  `output_tokens_details.thinking_tokens`; Codex's `reasoning_output_tokens`;
  OpenRouter's `completion_tokens_details.reasoning_tokens`), plus the peak
  context size seen by any single call;
- cost in USD where the vendor reports it (Claude Code, OpenRouter), API calls,
  retries and errors, how the run ended (`terminal_reason`, `is_error`), and for
  Claude the last rate-limit window;
- `usage_source` says where the totals came from: the CLI's final event, a sum
  of per-call usage (run killed before it finished), or the Codex rollout.

New summaries carry `usage_schema: 2`: `input_tokens` is total input context,
`input_tokens_uncached` is its uncached subset, and `total_tokens` is total input
plus output. Older archived summaries have no schema marker and retain the
original harness-native meaning of `input_tokens`; do not aggregate those rows
with schema-2 rows without normalizing them first.

Reasoning text is logged where the vendor exposes it. Claude Code emits
`thinking` blocks (usually empty or a short summary for Claude 5 models) and
running `system/thinking_tokens` estimates. Codex is configured with
`model_reasoning_summary = "detailed"` and `show_raw_agent_reasoning = true`,
and runs *without* `--ephemeral` so its session rollout, which holds a
`token_count` per API call and every reasoning item (summaries, or encrypted
blobs), is copied to `<run>/codex_sessions/`. The ReAct scaffold stores
OpenRouter's `reasoning`/`reasoning_details` verbatim on each assistant event
(and passes them back so the model keeps its chain of thought across tool
calls), along with the serving provider, finish reason and latency per call.

Live tail: `python3 sandbox/watch.py runs/<run>`.

Prompts are in `sandbox/prompts/`: `blind` (no hint about who the editors were),
`context` (with the Hugging Face incident summary), `legacy` (the earlier
baselines' prompt). Each holds a `{{BUDGET_MIN}}` placeholder.
