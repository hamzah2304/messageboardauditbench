# AI Village trials

Every trial so far, oldest first. Run folders are under `runs/` in the primary checkout (gitignored) and are named `<UTC start>_<harness>_<model>_r<replicate>_<config>_<id>`; each holds the prompt the agent saw, `report.md`, `transcript.jsonl`, `meta.json` and the config. Configs named here are in `configs/superseded/` unless marked current.

"Usable" means the run finished and its report can be compared with others. Citation counts are from `scripts/check_aivillage_citations.py` (id exists and quote appears in the record); runs before the quoted-citation format have no count.

## 3 October: pilot (old interface, data as compressed JSON Lines, no fixed number of findings)

| Start (UTC) | Model | Config | Outcome |
|---|---|---|---|
| 20:33 | Sonnet 5.5 | `aivillage-wrong-10-reasoning` | Usable but unpinned: ran Claude Code 2.1.263 and copied credentials. Kept as an extra sample |
| 20:33, 20:37 | Luna | `aivillage-wrong-10-reasoning` | Failed: Codex 0.156.1 refused `gpt-6-luna`. No report |
| 20:52 | Sonnet 5.5, Luna | `aivillage-wrong-10-reasoning` with a 3-minute budget | Smoke tests. Reports exist but are not comparable |
| 20:56 | Sonnet 5.5, Luna | `aivillage-wrong-10-reasoning` | Usable |
| 20:56, 21:04 | Sonnet 5.5, Luna | `aivillage-wrong-10-noreasoning` | Usable |

Findings: agents made 14 to 22 tool calls, stopped early and read mostly chat. See the [pilot readout](https://claude.ai/artifact/2TnoDfsqdMjuV1K6eXUiJY).

## 3 October: one-week slice (SQLite interface, 5 minutes)

| Start (UTC) | Model | Config | Citations | Outcome |
|---|---|---|---|---|
| 22:05 | Sonnet 5.5 | `aivillage-v4-slice-5-reasoning` | 49/49 | Interface test |
| 22:05 | Luna | `aivillage-v4-slice-5-reasoning` | 30/31 | Interface test; one invented id |
| 22:05 | Sonnet 5.5 | `aivillage-v4-slice-5-noreasoning` | 37/37 | Interface test |

The step-by-step log review behind the interface clean-up used these three runs.

## 3 October: full logs, no reasoning, open number of findings (prompt file `aivillage-wrong-v5`)

| Start (UTC) | Model | Config | Citations | Outcome |
|---|---|---|---|---|
| 22:44 | Sonnet 5.5 | `aivillage-v4-full-10-noreasoning` | 33/33 | Usable |
| 22:44 | Sonnet 5 | same | 23/23 | Usable |
| 22:44 | Luna | same | 42/43 | Usable; one invented id |
| 22:44 | Sol | same | 59/60 | Usable; one quote copied with JSON escaping |

Analysed in [notes/2026-10-03-findings-vs-substack.md](notes/2026-10-03-findings-vs-substack.md).

## 3 October, 23:34: aborted

Four runs of `aivillage-v4-full-10-reasoning` (Sonnet 5.5, Sonnet 5, Luna, Sol), stopped by hand within a few minutes because Oscar wanted to read the Substack comparison first. The two Codex runs have partial transcripts and no report. Do not use.

## 4 October: reasoning and fixed-count ablation (prompt file `aivillage-wrong-v6`)

| Start (UTC) | Model | Config | Findings | Citations |
|---|---|---|---|---|
| 00:09 | Sonnet 5.5 | `aivillage-v6-full-10-noreasoning` | 8 | 55/55 |
| 00:09 | Sonnet 5.5 | `aivillage-v6-full-10-reasoning` | 8 | 52/52 |
| 00:10 | Sonnet 5.5 | `aivillage-v6-top10-full-10-reasoning` | 10 | 54/54 |
| 00:22 | Sonnet 5.5 | `aivillage-v6-top10-full-10-noreasoning` (replicate 2) | 10 | 54/54 |
| 00:10 | Luna | `aivillage-v6-top10-full-10-reasoning` | 10 | 25/25 |
| 00:10 | Luna | `aivillage-v6-top10-full-10-noreasoning` | 10 | 23/32 |
| 00:19 | Luna | `aivillage-v6-full-10-noreasoning` (replicate 2) | 4 | 26/28 |
| 00:21 | Luna | `aivillage-v6-full-10-reasoning` (replicate 2) | 4 | 24/24 |

Three first attempts failed while building the image, before any agent started, and left no run folder; the replicate-2 runs replaced them. Analysed in [notes/2026-10-04-reasoning-and-count-ablation.md](notes/2026-10-04-reasoning-and-count-ablation.md).

## 4 October: default setup at 10 and 30 minutes (configs `aivillage-10` and `aivillage-30`, current; prompt `aivillage-v7`)

All exactly 10 findings; full logs without reasoning; medium effort.

| Start (UTC) | Model | Budget | Tool calls | Citations | Computer-use steps cited |
|---|---|---|---|---|---|
| 00:51 | Sonnet 5.5 | 30 min | 169 | 70/70 | 13 |
| 00:51 | Opus 5 | 30 min | 146 | 72/72 | 17 |
| 00:51 | Luna | 30 min | 92 | 46/46 | 28 |
| 00:52 | Sol | 30 min | 126 | 81/81 | 33 |
| 00:52 | Sonnet 5.5 | 10 min | 36 | 47/47 | 3 |
| 01:01 | Opus 5 | 10 min | 32 | 47/47 | 9 |
| 01:11 | Luna | 10 min | 38 | 26/29 | 6 |
| 01:18 | Sol | 10 min | 43 | 55/55 | 16 |

All exited cleanly and used at least 90% of their budget. Analysed in [notes/2026-10-04-10-vs-30-minutes.md](notes/2026-10-04-10-vs-30-minutes.md).

## 4 October: overnight batch, 40 minutes, with and without subagents (configs `aivillage-v8-40`, `aivillage-v8-40-subagents`, `aivillage-v8-40-subagents-xhigh`; prompt `aivillage-v8`, v3.13)

Exactly 20 findings, 5,000 to 6,000 words, full logs without reasoning, medium effort except the two xhigh runs Oscar added. "Subagents" means Claude's Task/Agent tools or Codex's multi-agent feature were allowed; the prompt is identical. Started from `claude/aivillage-pilot` at 7961830; 3 Claude and 2 Codex runs at a time.

| Start (UTC) | Model | Subagents | Rep | Minutes | Tool calls | Subagent calls | Citations | Outcome |
|---|---|---|---|---|---|---|---|---|
| 06:56 | Sonnet 5.5 | no | 1 | 36.1 | 183 | | 85/85 | Usable |
| 08:57 | Sonnet 5.5 | no | 2 | 36.3 | 263 | | 119/119 | Usable; blocked from finishing early 99 times |
| 06:56 | Sonnet 5.5 | yes | 1 | 36.1 | 285 | 11 | 119/119 | Usable |
| 08:57 | Sonnet 5.5 | yes | 2 | 38.1 | 363 | 10 | 154/154 | Usable |
| 08:11 | Sonnet 5.5 | yes, xhigh | 1 | 45.6 | 1058 | 22 | 179/179 | Froze at 08:38 with the VM out of memory, killed at 45 min; report complete from 24 min |
| 06:56 | Opus 5 | no | 1 | 36.3 | 133 | | 115/115 | Usable |
| 08:57 | Opus 5 | no | 2 | 36.2 | 148 | | 122/122 | Usable |
| 07:33 | Opus 5 | yes | 1 | 36.0 | 127 | 0 | 96/96 | Usable; never used subagents |
| 09:34 | Opus 5 | yes | 2 | 36.2 | 104 | 0 | 131/131 | Usable; never used subagents |
| 07:33 | Opus 5.5 | no | 1 | 36.7 | 207 | | 116/116 | Usable; first report write stopped by the safety classifier ("cyber"), rewritten without the blocked detail |
| 09:34 | Opus 5.5 | no | 2 | 11.7 | 36 | | — | **No report**: classifier stopped the report write, then the model refused to write any report |
| 07:33 | Opus 5.5 | yes | 1 | 36.2 | 428 | 13 | 176/176 | Usable; one subagent stopped by the classifier |
| 09:36 | Opus 5.5 | yes | 2 | 36.2 | 408 | 12 | 152/152 | Usable |
| 08:10 | Sonnet 5 | no | 1 | 46.5 | 113 | | 32/79 | Froze at 08:38, killed at 45 min; report complete; 44 quotes sit outside the citation brackets |
| 09:47 | Sonnet 5 | no | 2 | 36.1 | 198 | | 74/75 | Usable |
| 08:10 | Sonnet 5 | yes | 1 | 45.7 | 242 | 6 | 66/66 | Froze at 08:38, killed at 45 min; report complete |
| 10:11 | Sonnet 5 | yes | 2 | 36.1 | 623 | 29 | 81/82 | Usable |
| 06:56 | Luna | no | 1 | 38.3 | 109 | | 60/60 | Usable |
| 08:59 | Luna | no | 2 | 37.2 | 97 | | 60/62 | Usable |
| 06:56 | Luna | yes | 1 | 36.3 | 82 | 0 | 55/56 | Usable |
| 09:02 | Luna | yes | 2 | 38.2 | 62 | 0 | 60/61 | Usable |
| 07:33 | Sol | no | 1 | 39.7 | 141 | | 109/110 | Usable |
| 16:21 | Sol | no | 3 | 39.4 | 154 | | 133/133 | Usable; replaces replicate 2 (09:37), whose network check failed before the agent started |
| 07:35 | Sol | yes | 1 | 39.6 | 142 | 0 | 111/111 | Usable |
| 09:37 | Sol | yes | 2 | 39.9 | 163 | 0 | 125/125 | Usable |
| 08:16 | Sol | yes, xhigh | 1 | 45.0 | 109 | 0 | 65/82 | Provider stall from 08:38, killed at 45 min; sections 13–20 written after the budget, 17 citations unfixed |
| 08:14 | Astra | no | 1 | 44.7 | 122 | | 110/110 | Usable; one 18-minute provider stall from 08:38 |
| 09:41 | Astra | no | 2 | 40.0 | 147 | | 110/110 | Usable |
| 10:18 | Astra | yes | 2 | 39.7 | 141 | 0 | 112/112 | Usable |
| 10:22 | Astra | yes | 3 | 39.6 | 157 | 0 | 113/113 | Usable; replaces replicate 1 (08:16), whose network check failed before the agent started |

Problems in this batch:

- **Out of memory at 08:27 to 08:57.** A third-level subagent in the Sonnet 5.5 xhigh run loaded all of `agent_memories.jsonl.gz` into a Python list and reached 10.8 GB of the VM's 15 GB. At 08:38 three Claude runs stopped making tool calls within 7 seconds of each other and were killed at 45 minutes, and the two Codex runs then active stalled for 12 to 18 minutes. Runs now take `memory_limit` (3 GB for these configs, stated in the prompt; commit cacc6ee); none of this batch ran with it.
- **Codex subagents were never a separate condition.** Codex 0.160.0 shows the model the `spawn_agent` tools in both configs (`multi_agent = false` does not remove them) together with its own instruction not to spawn sub-agents unless the user asks. No Codex run spawned one. The same switch is used to disable subagents in URLQuery runs, so those may be affected too.
- **Safety classifier.** Opus 5.5's report writes were stopped (category "cyber") in 2 of 4 runs, both at a finding that quoted how an agent pulled developers' email addresses out of GitHub commit `.patch` files. Two other Opus 5.5 runs published the same material unstopped.
- **Network check.** 2 of 32 launches failed the pre-run check that the vendor host is reachable (both Codex); nothing ran and both were rerun.

Analysed in [notes/2026-10-04-overnight-40-minutes.md](notes/2026-10-04-overnight-40-minutes.md).

## 4 October, evening: subagent switch and prompt v3.14 checks

Harness probes (prompt `subagent-probe`, one-week slice, 3 minutes; configs were temporary copies of `aivillage-v9-40*.toml`). The agent lists its tools and tries to start one subagent.

| Start (UTC) | Model | Subagents | Result |
|---|---|---|---|
| 17:44 | Sonnet 5.5 | off | No `Agent` tool; "NO SUBAGENT TOOL" |
| 17:44 | Sonnet 5.5 | on | `Agent` tool; subagent answered 51 |
| 17:44 | Sol | off | **Had `spawn_agent` and used it** (subagent answered 51); also listed Notion tools from the ChatGPT account |
| 17:44 | Sol | on | `spawn_agent` used |
| 17:47 | Sol | off, after the fix | No collaboration tools, no Notion tools; "NO SUBAGENT TOOL" |
| 17:48 | Sol | on, after the fix | `spawn_agent` used; no Notion tools |

The fix: Codex's model catalog turns the collaboration tools on for GPT-6 models (`multi_agent_version`), whatever the `multi_agent` feature flag says, so with subagents off the runner now gives Codex its own catalog with that field removed; apps, plugins and browser or computer use are off for every benchmark.

Prompt v3.14 smoke tests (`aivillage-v9-40-subagents`, one-week slice, `BUDGET_MIN=5`, replicate 9):

| Start (UTC) | Model | Subagent calls | Notes |
|---|---|---|---|
| 17:49 | Sonnet 5.5 | 0 | Blocked from finishing 16 times; did real work between attempts but still ended its turn after almost every tool call; 2,362 words |
| 17:49 | Sol | 3 | Each subagent wrote only under its own `/work/scratch/<name>/`; no sleep; 3,386 words |

Five minutes on the slice cannot reach 20 findings or 8,000 words, so these only check that the prompt renders and that Codex now delegates.
