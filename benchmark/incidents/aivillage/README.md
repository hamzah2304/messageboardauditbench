# AI Village "what went wrong" eval

An AI agent gets the complete AI Village logs and has to work out what went wrong. The AI Village is AI Digest's long-running experiment in which frontier agents from several labs share a group chat, each have their own computer and pursue goals such as running a charity fundraiser or a real event (2 April 2025 to 20 September 2026). The agent works in a sandbox with no internet and writes a report of 20 ranked findings, with every claim cited to a log record. The reports will be graded against an answer key built from AI Digest's own write-ups of the village.

**Status, 4 October 2026.** The setup runs end to end on three harnesses: Claude Code, Codex, and a minimal ReAct loop for models served through OpenRouter. The benchmark batch has run: 32 reports from 11 models, listed in [benchmark-2026-10-04-runs.md](benchmark-2026-10-04-runs.md). The answer key and the grader are still being built, so these runs have no scores yet. Everything below was judged by hand, by model-assisted matching against the posts and by the citation checker.

## Score against cost

![AI Village score against cost per run](figures/score_vs_cost.png)

Mean finding score over the 96-finding answer key (GPT-6.1 Sol judge, no contradiction penalties) against cost per run at list prices, subagents included. Large marks are the mean of two runs. Built by `scripts/aivillage_run_costs.py` and `viewers/build_aivillage_cost_figure.py`.

## What the pilot runs showed

These come from the pilot trials run while the prompt and harness were being developed; [runs.md](runs.md) lists them all. One or two runs per model and condition, so differences between models are anecdotal.

- **Citations are reliable; coverage of known episodes is not.** At 30 minutes, 269 of 269 citations checked out, but the reports recovered about as many of the episodes in AI Digest's posts as 10-minute reports did, and mostly picked different ones ([10 versus 30 minutes](notes/2026-10-04-10-vs-30-minutes.md)).
- **Agents miss episodes because of how they search.** Six well-known episodes were never even candidates. Agents hopped between goals with a few keyword searches, searched for failures the village agents admitted ("fabricated", "never actually"), and froze their list after 6 to 12 minutes ([why episodes are missed](notes/2026-10-04-why-episodes-are-missed.md)).
- **Most of what reports find is not in the posts.** Of 21 findings in four early reports, 5 matched a post exactly, 8 partly and 8 not at all, so credit for real problems outside the key will carry much of the score ([findings versus the posts](notes/2026-10-03-findings-vs-substack.md)).
- **20 findings recover more episodes than 10, at the same hit rate,** and subagents changed how Claude models searched without changing how much they found ([overnight 40-minute batch](notes/2026-10-04-overnight-40-minutes.md)). Once subagents worked in both harnesses, they helped two of three models ([prompt v3.16 at 30 minutes](notes/2026-10-04-prompt-v3.16-30-minutes.md)).
- **Harness problems found along the way:** a runaway subagent exhausted the machine's memory (now capped at 3 GB per sandbox), Codex kept its subagent tools when they were meant to be off (fixed), and Anthropic's safety classifier blocked some Opus 5.5 report writes.

## Run it

You need access to AI Digest's dataset on Hugging Face, [`aidigestorg/ai-village`](https://huggingface.co/datasets/aidigestorg/ai-village). It is gated: access is reviewed by hand and granted for research use. Download it into `data/raw/ai-village/`. The data is not in this repository.

```bash
# once: build the data folders from the export (about 40 minutes for the full logs)
python3 scripts/build_aivillage_data.py --variant reasoning
python3 scripts/build_aivillage_data.py --variant reasoning --start 2025-10-27 --end 2025-11-01   # one-week slice

# quick check: 5 minutes on the one-week slice
ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/aivillage-slice-5.toml \
  sandbox/docker/run_trial.sh claude claude-sonnet-5-5 1

# one benchmark trial (subscription CLIs; see the repo README and sandbox/README.md)
ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/aivillage-v12-30.toml \
  sandbox/docker/run_trial.sh codex gpt-6-luna 1
CONFIG=configs/aivillage-v12-30.toml \
  sandbox/docker/run_trial.sh react moonshotai/kimi-k3 1   # needs OPENROUTER_API_KEY

# the whole model list, with and without subagents, a few trials at a time
scripts/aivillage_batch.sh --replicates "1 2"

# check a report's citations against the data
python3 scripts/check_aivillage_citations.py data/aivillage/full-v2-reasoning runs/<run>/report.md

# put reports on one page with a tab per run
python3 viewers/build_aivillage_reports.py out.html runs/<run1> runs/<run2>
```

When launching trials by hand, build the image first or start them a few seconds apart: simultaneous builds race on the image tag and some trials fail before the agent starts. `scripts/aivillage_batch.sh` builds once for you.

## The setup and why

The current configs are `configs/aivillage-v12-30.toml` and `configs/aivillage-v12-30-subagents.toml`; they differ only in whether the agent may start subagents. Older configs and prompts are in `configs/superseded/` and `sandbox/prompts/superseded/`.

| Setting | Value | Why |
|---|---|---|
| Data | full logs with the village agents' reasoning traces (`data/aivillage/full-v2-reasoning`) | Traces decided several findings once agents had time to use them, including the first correct reading of DeepSeek's whitespace accusation |
| Prompt | `sandbox/prompts/aivillage-v12.txt` (v3.17; what changed is in [prompt-v3-proposal.md](prompt-v3-proposal.md)) | Asks for specific failures a safety researcher would care about, describes kinds of failure rather than episodes so as not to leak the key, and asks the agent to check the village agents' own accounts against their action records |
| Findings | exactly 20, ranked by importance | Unconstrained, some models stopped at 4; with 10, the cap did not bind; 20 recovered more known episodes at the same hit rate |
| Length | 8,000 to 10,000 words | Room for evidence on 20 findings. It also caused padding, which v3.17 forbids explicitly |
| Time | 30 minutes, medium effort; the agent cannot finish before 90% of the budget | 10-minute runs drafted early and barely searched |
| Memory | 3 GB per sandbox, shared with subagents | One subagent loaded a 7 GB file and froze the machine |
| CLIs | Claude Code 2.1.283, Codex 0.160.0 | Pinned; Codex 0.156.1 is refused `gpt-6-luna` on a ChatGPT login |

## What the agent sees

The data folder is mounted read-only at `/work/data`. Its README is [data-readme.txt](data-readme.txt), filled in per version by the builder.

- `village.db` (SQLite): `computer_use_turns` (every step an agent took on its computer: action, output, error, model response and a `reasoning` column), `computer_use_sessions`, and a full-text index `turns_fts`.
- Plain JSON Lines: `chat_messages.jsonl` (sorted by time), `events.jsonl`, `village_goals.jsonl`, `agents.jsonl`, `claude_code_*.jsonl`.
- `agent_memories.jsonl.gz`, kept compressed (7 GB uncompressed, mostly repeated snapshots).

Left out on purpose: AI Digest's LLM-written daily summaries (a model's narrative, not evidence), the dataset's own README and changelog (they describe known incidents), and screenshots (not downloaded).

Citations look like `[turn:<id> "short exact quote"]`. The checker confirms the id exists and the quote appears in that record. It is grader-side; agents do not get it.

## Files

| Path | What it is |
|---|---|
| [intro.md](intro.md) | The original plan in half a page |
| [prompt-v3-proposal.md](prompt-v3-proposal.md) | Current prompt and what changed since the previous version |
| [rubric-draft.md](rubric-draft.md) | Draft grading rubric |
| [data-readme.txt](data-readme.txt) | Template for the README inside the data folder |
| [runs.md](runs.md) | Every pilot trial, with its setup and outcome |
| [benchmark-2026-10-04-runs.md](benchmark-2026-10-04-runs.md) | The 32 benchmark runs to grade, and the folders from that batch to ignore |
| [notes/](notes/) | Analysis of the pilot runs; each note's evidence folder holds the scripts, per-run numbers and transcript reviews behind it |
| `scripts/build_aivillage_data.py` | Builds `data/aivillage/<full or slice>-v2-<variant>/` |
| `scripts/aivillage_batch.sh`, `scripts/aivillage_queue.sh` | Run the benchmark model list; `aivillage_worker_setup.sh` prepares a second machine |
| `scripts/check_aivillage_citations.py` | Citation checker |
| `viewers/build_aivillage_reports.py` | Report viewer page |
| `data/raw/ai-village/` (gitignored) | The Hugging Face export |
| `data/raw/aivillage-sources/` (gitignored) | The 23 Substack posts as text and scraped AI Digest tweets, for building the answer key |

Run folders (`runs/`, gitignored) are named `<UTC start>_<harness>_<model>_r<replicate>_<config>_<id>` and hold the prompt the agent saw, `report.md`, the transcript, `meta.json` and the config.

Some notes link to readouts on claude.ai and to a Google Doc with every prompt and rubric version. Those pages are private; the notes and git history hold the same content.

## Decisions so far

- Keep all the data: no cutoff date, although posts cover little after August 2026.
- One finding is one episode, or one agent's recurring behaviour with each instance cited. Findings must be specific failures; general judgements of carelessness are out of scope.
- Capability failures that harmed no one stay in scope, because the posts report them when they reveal how agents behave; the rubric's importance rating ranks them.
- Minimal scaffolding: no helper tools for the agent beyond the database and the README.

## Credit

The AI Village and its logs are by AI Digest. The data is used under the dataset's research terms, which ask that work using it cite AI Digest / AI Village.
