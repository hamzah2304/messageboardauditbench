# Sandbox

Runs an agent (Claude Code, Codex, or a minimal ReAct scaffold over OpenRouter)
against the stripped dump with no web access except its own API endpoint, and
no view of anything but the data.

Everything lives in `sandbox/docker/`. The earlier permissions-based sandbox
(Linux user + iptables) that produced the first baselines was removed on
2026-09-05; `docs/HANDOFF.md` §4 records why.

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
  Time information reaches the model the same way as for the CLIs: only through
  the prompt (it can run `date`).
- Claude: `sandbox/docker/claude_login.sh` once. It runs `claude login` inside the
  image (prints a URL, paste the code back) and keeps the resulting
  `.credentials.json` in `runs/.claude-home/` (gitignored), copied into each
  trial. Needed because macOS keeps the host login in the Keychain, which a
  Linux container cannot read. On Linux hosts `~/.claude/.credentials.json` is
  used as a fallback, as is `CLAUDE_CODE_OAUTH_TOKEN` if set.

## Run

Every trial is a system (agent + model + seed) under a config. Configs live in
`configs/<name>.toml` and hold the benchmark-relevant conditions: which prompt
(`sandbox/prompts/<name>.txt`), the time budget the prompt states, the hard
kill timeout, the data variant, the reasoning effort, and the Claude Code tools
withheld from the agent. Shipped configs: `blind-20`, `blind-40`, `context-20`,
`context-40` (the `context` prompt prepends a summary of the OpenAI/Hugging Face
incident and says to treat this one as separate), plus `default` = `blind-20`.

```
CONFIG=blind-20   sandbox/docker/run_trial.sh claude claude-opus-5 1
CONFIG=context-40 sandbox/docker/run_trial.sh codex  gpt-5.6-sol   1
CONFIG=blind-20   sandbox/docker/run_trial.sh react  moonshotai/kimi-k3 1
```

Run names end in the config name. `meta.json` records the config, its hash,
the prompt name, the budget, the data variant, the effort, and the hash of the
rendered prompt the agent saw. Env vars `PROMPT`, `BUDGET_MIN`, `TIMEOUT`,
`DATA_DIR`, `EFFORT` override single values for one-off experiments; prefer a
new config file for anything you will compare against.

Batch of many trials, concurrently:

```
cat > matrix.txt <<'M'
# agent  model                   config      seed
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

Collect the reports for evaluation, one folder per config and prompt version:

```
scripts/collect_reports.py     # -> reports/<config>_p<prompt8>/<agent>_<model>_s<seed>_<stamp>.md
                               #    + CONDITIONS.json per folder, reports/prompts/<prompt8>.txt, reports/index.jsonl
```

Each run writes `runs/<timestamp>_<agent>_<model>_s<seed>/`: `canary.log`,
`proxy.log`, `transcript.jsonl` (the CLI's JSON event stream), `stderr.log`,
`meta.json` (exit code, wall time, CLI version, prompt hash), `report.md` (and
`final_message.md` for Codex) copied up from `work/`. `work/` is exactly what the
agent saw. Exit code 124 means the timeout fired.

Live tail: `python3 sandbox/watch.py runs/<run>`.

Prompts are in `sandbox/prompts/`: `blind` (no hint about who the editors were),
`context` (with the Hugging Face incident summary), `legacy` (the earlier
baselines' prompt). Each holds a `{{BUDGET_MIN}}` placeholder.
