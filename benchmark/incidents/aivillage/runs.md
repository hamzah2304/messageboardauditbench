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
