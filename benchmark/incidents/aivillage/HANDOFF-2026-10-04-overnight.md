# Handoff: overnight AI Village batch (4 October 2026)

Oscar asked for an overnight batch with the new prompt, at 40 minutes, every model with and without subagents. Launch it, babysit it, check it, and log it. Do not change the prompt or configs without asking; he reviews results in the morning.

Read first: [README.md](README.md) (setup and file map) and [runs.md](runs.md) (earlier trials). Work in the worktree `~/Dev/MessageBoardAuditBench/.worktrees/claude-aivillage-pilot` (branch `claude/aivillage-pilot`); `data/` and `runs/` there are symlinks to the primary checkout. Never pull or switch branches in the primary checkout.

## What to launch

Prompt `aivillage-v8` (v3.13). Two configs, identical except subagent access:

- `configs/aivillage-v8-40.toml`: no subagents
- `configs/aivillage-v8-40-subagents.toml`: Claude's Task/Agent tools and Codex's multi-agent feature allowed

Both: full logs without reasoning traces, exactly 20 findings ranked by importance, 40 minutes, medium effort, report 5,000 to 6,000 words, tool output capped at about 50,000 characters for both harnesses (Claude 50,000 characters, Codex 12,500 tokens), and a breadth note added to the early-stop reminder.

| Harness | Model id | Samples per condition | Runs |
|---|---|---|---|
| claude | `claude-sonnet-5-5` | 2 | 4 |
| claude | `claude-opus-5` | 2 | 4 |
| claude | `claude-opus-5-5` | 2 | 4 |
| claude | `claude-sonnet-5` | 2 | 4 |
| codex | `gpt-6-luna` | 2 | 4 |
| codex | `gpt-6-sol` | 2 | 4 |
| codex | `gpt-6-astra` | 2 | 4 |

28 runs. At about 45 minutes each with 5 in parallel, roughly 4.5 hours. Oscar named Astra and Opus 5 explicitly and said Claude models can get multiple samples; Opus 5.5 and Sonnet 5 are additions within that. `claude-opus-5-5` and `gpt-6-astra` have not run in this eval yet, so smoke-test them first (below). Skip Fable 5.1: it refused this kind of task in the German wiki eval.

Run replicate 1 of everything before replicate 2, and alternate the two conditions, so that a mid-night failure leaves a balanced set.

## How

```bash
cd ~/Dev/MessageBoardAuditBench/.worktrees/claude-aivillage-pilot
S=/tmp/aivillage-overnight; mkdir -p $S

# 1. Build the image once. Simultaneous builds race on the tag and kill trials.
sg docker -c "docker build -q -t mbab-pinned-sandbox-codex-0.160.0-claude-2.1.283 \
  --build-arg CODEX_VERSION=rust-v0.160.0 --build-arg CLAUDE_VERSION=2.1.283 \
  -f sandbox/docker/Dockerfile ."

# 2. Smoke-test the two new model ids for 5 minutes on the one-week slice
#    (BUDGET_MIN and DATA_DIR overrides; the configs are otherwise unchanged).
for spec in "claude claude-opus-5-5" "codex gpt-6-astra"; do set -- $spec
  ALLOW_NETWORKED_SUBSCRIPTION=1 BUDGET_MIN=5 DATA_DIR=$PWD/data/aivillage/slice-v2-noreasoning \
  CONFIG=configs/aivillage-v8-40.toml sg docker -c "sandbox/docker/run_trial.sh $1 $2 9" > $S/smoke-$2.log 2>&1 &
  sleep 20; done; wait
#    Check each smoke run folder: transcript.jsonl grows, report.md exists, meta.json exit_code 0.
#    If a model id is refused, drop that model and say so in the morning summary.

# 3. Two queues so Claude never exceeds 3 at once (its quota is shared with Oscar's Mac) and the total stays at 5.
for r in 1 2; do for m in claude-sonnet-5-5 claude-opus-5 claude-opus-5-5 claude-sonnet-5; do for c in aivillage-v8-40 aivillage-v8-40-subagents; do
  echo "$c claude $m $r"; done; done; done > $S/claude.txt
for r in 1 2; do for m in gpt-6-luna gpt-6-sol gpt-6-astra; do for c in aivillage-v8-40 aivillage-v8-40-subagents; do
  echo "$c codex $m $r"; done; done; done > $S/codex.txt
run() { xargs -P "$1" -L 1 sh -c 'sleep $(( $(od -An -N1 -tu1 /dev/urandom) % 20 )); ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/$0.toml \
  sg docker -c "sandbox/docker/run_trial.sh $1 $2 $3" > '"$S"'/$0-$2-r$3.log 2>&1; echo "$0 $2 r$3 exit=$?"'; }
(run 3 < $S/claude.txt > $S/claude.done) &
(run 2 < $S/codex.txt > $S/codex.done) &
```

Run the launcher in the background (a tmux session, or the harness's background mode) and watch with `docker ps`, `uptime` and `df -h ~`. Stop launching if free disk falls below about 10 GB. The VM is shared: stop only processes and containers you started.

## While it runs

- A Codex run that fails with "Selected model is at capacity": rerun it with the next replicate number.
- A Claude run that fails with a usage or spend limit: test with `CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < runs/.claude-oauth-token)" claude -p ok --model claude-haiku-4-5 --output-format json`, stop launching Claude runs, and report it rather than retrying.
- Do not run `claude login` or copy credential files.

## When it finishes

1. For every run folder (`runs/*_aivillage-v8-40*`): exit code, minutes used, tool calls, and whether `report.md` exists. Then check citations:
   `python3 scripts/check_aivillage_citations.py data/aivillage/full-v2-noreasoning runs/<run>/report.md`
2. Count findings per report (should be 20), and for subagent runs, whether subagents were actually used: Claude transcripts contain `Task`/`Agent` tool calls; Codex rollouts contain `spawn_agent`.
3. Append a section to [runs.md](runs.md) in the same format as the earlier ones.
4. Build a reports page with `viewers/build_aivillage_reports.py` and publish it as a private claude.ai artifact, as with the earlier batches.
5. Write a short note in `notes/` comparing with and without subagents (tool calls, findings, citations, how many goal periods each run queried, and Substack matches using `data/raw/aivillage-sources/substack/`). One or two samples per cell, so treat differences as anecdotal.
6. Commit on `claude/aivillage-pilot`; do not push or merge.

## Open points to raise with Oscar in the morning

- **Report length.** He asked to "double the report lengths". This was set to 5,000 to 6,000 words, double the original 2,500 to 3,000. An intermediate draft had 4,000 to 5,000, so if he meant double that, the configs need 8,000 to 10,000.
- **Prompt v3.13 is not yet in the Google Doc.** Publish `prompt-v3-proposal.md` as a new tab under Prompt (`marginal publish ... --tab-title "v3.13 prompt proposal — 04-10"`), then move it under the Prompt parent tab (tab id `t.8jd2kagea02d`) and give it 10 pt space after paragraphs. Earlier sessions did this with marginal's Python API (`/home/oscar_gilg18/.local/share/uv/tools/marginal/bin/python`, `from marginal import gdocs`; `gdocs.batch_update` with `updateDocumentTabProperties` setting `parentTabId` and `index`, then `updateParagraphStyle` with `spaceBelow`). Ask first if unsure.
- **Subagents get no prompt change.** The prompt is identical in both conditions; only tool access differs. If Codex never spawns subagents, that may be why.
