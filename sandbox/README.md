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
  checksums). `DATA_DIR=data/verbatim` selects the verbatim variant; the run name
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

```
sandbox/docker/run_trial.sh claude claude-opus-5 1
sandbox/docker/run_trial.sh codex  gpt-5.6-sol   1
sandbox/docker/run_trial.sh react  moonshotai/kimi-k3 1
```

Knobs: `EFFORT=high`, `TIMEOUT=25m` (the prompt says ~20 minutes),
`DATA_DIR=data/raw_stripped`, `IMAGE=mbab-sandbox`.

Batch, one trial at a time per vendor (each CLI runs against one
subscription; the two chains and any `react` runs can run concurrently since
every trial gets its own network):

```
for m in claude-haiku-4-5 claude-sonnet-5 claude-opus-5 claude-fable-5-1; do sandbox/docker/run_trial.sh claude $m 1; done
for m in gpt-5.6-luna gpt-5.6-terra gpt-5.6-sol; do sandbox/docker/run_trial.sh codex $m 1; done
for m in google/gemini-3.8-flash moonshotai/kimi-k3; do sandbox/docker/run_trial.sh react $m 1; done
```

`sandbox/llm_scan.py` and `prompt_scan_addendum.txt` (the fan-out reading
tool, `SCAN=1` on the old launcher) are not wired into the Docker launcher.

Each run writes `runs/<timestamp>_<agent>_<model>_s<seed>/`: `canary.log`,
`proxy.log`, `transcript.jsonl` (the CLI's JSON event stream), `stderr.log`,
`meta.json` (exit code, wall time, CLI version, prompt hash), `report.md` (and
`final_message.md` for Codex) copied up from `work/`. `work/` is exactly what the
agent saw. Exit code 124 means the timeout fired.

Live tail: `python3 sandbox/watch.py runs/<run>`.

The prompt is `sandbox/prompt.txt`. It is deliberately blind: it does not say
the editors were AI agents, nor that anything definitely happened.
