# Lightweight sandbox for baseline trials

Runs a coding agent (Claude Code or Codex) against the stripped dump with no
web access except the agent's own vendor API. No Docker.

How isolation works:

- The agent runs as an unprivileged Linux user `agentbox` in a fresh run directory.
- An iptables rule rejects every packet from that user except to loopback.
- On loopback sits `proxy.py`, an HTTP CONNECT proxy that only forwards to
  `api.anthropic.com`, `chatgpt.com`, `api.openai.com`, `auth.openai.com`.
  Denied hosts are logged to `runs/proxy.log`, so you can see what the agent tried.
- Both CLIs read `HTTPS_PROXY`. If the agent unsets it and curls directly, the
  iptables rule still blocks it.

What is not isolated: the agent can read anything on this VM that is
world-readable, and it holds the subscription token it runs with. Good enough
for a baseline; use Docker for anything adversarial.

## One-time setup (needs sudo, run it yourself)

```
./sandbox/setup_sandbox.sh
```

Creates `agentbox`, copies the `claude` and `codex` binaries to `/opt/agentbox/bin`,
copies `~/.claude/.credentials.json` and `~/.codex/auth.json` into agentbox's
home (mode 600), and installs the iptables chain. Idempotent; re-run after a CLI
upgrade or re-login.

## Each session

```
./sandbox/start_proxy.sh                        # once per boot
./sandbox/run_trial.sh claude claude-opus-5 1   # seed 1
./sandbox/run_trial.sh codex  gpt-5.6-sol   1
```

Knobs: `EFFORT=medium` (default), `TIMEOUT=25m` (the prompt tells the agent it has about 20 minutes), `DATA_DIR=data/raw_stripped`.

Each run writes `runs/<timestamp>_<agent>_<model>_s<seed>/` containing the data
copy, `prompt.txt`, `transcript.jsonl` (the CLI's JSON event stream),
`stderr.log`, `meta.json` (exit code, wall time, CLI version, prompt hash), and
whatever the agent wrote, ideally `report.md`. Codex also leaves its final
message in `final_message.md`.

The prompt is `sandbox/prompt.txt`. It is deliberately blind: it does not say
the editors were AI agents.

## Checking the lock from inside

```
sudo -u agentbox curl -s -m 5 https://collusion.wiki/   # should fail: connection refused
sudo -u agentbox env HTTPS_PROXY=http://127.0.0.1:3128 curl -s -o /dev/null -w '%{http_code}' https://api.anthropic.com/
```
