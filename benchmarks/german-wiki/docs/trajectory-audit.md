# Trajectory audit: most completed runs read the corpus; failures are not all tool failures

The saved-run audit converts 366 immediate run directories without conversion errors. It shows extensive shell-based corpus inspection across agents and models. It does not show that every command finished successfully, that every data row was read, or that multiple tool calls actually overlapped.

The audit deliberately separates an empty `rg` or `grep` result from an operational error. Those programs conventionally return exit status 1 when they find no matches. Treating that status as a failed investigation would inflate failure counts and incorrectly label ordinary negative searches as blocked access.

## What the artifact measures

Run the audit from the repository root:

```sh
.venv/bin/python scripts/audit_runs.py \
  --runs ../messageboardauditbench/runs \
  --data data/verbatim \
  --out /tmp/mbab-audit-runs.json
```

The JSON artifact reports tool calls by `agent:model`, per-run conversion diagnostics, and aggregate trajectory totals. It includes immediate run directories only. Nested archival directories contain failed or aborted attempts and are outside this comparison set.

Tool-call counts show what the converted transcript records, rather than a normalized measure of research quality. Agent implementations expose different tool names and may bundle shell work differently. A model with more `bash` calls therefore did more recorded shell interactions, but did not necessarily inspect more evidence.

## Access, refusals, and ordinary negative searches

Successful long runs visibly enumerate and read all four supplied files: `pages.jsonl`, `labels.jsonl`, `events.jsonl`, and `revisions.jsonl`. For example, the GPT-6 Astra trajectory at `../messageboardauditbench/runs/20260907T080039Z_codex_gpt-6-astra_r1_blind-120_1659fd46a446/transcript.jsonl` lists exactly those files in its first filesystem command. The prompt supplied the data directory, not repository documentation; it did not expose the superseded augmentation notes. Absence of a citation to that documentation is therefore expected, rather than evidence of a search failure.

Provider refusals are counted only from explicit raw transcript signals: Claude's `model_refusal_no_fallback` system event or a message whose stop reason is `refusal`. This avoids classifying corpus text that happens to say “refused” or “blocked” as a provider refusal. A concrete refusal is in `../messageboardauditbench/runs/20260906T210436Z_claude_claude-opus-5_r2_blind-120_85b49904098a/transcript.jsonl`.

## Time and parallelism

The prompt provides a time budget and some tool results repeat an explicit remaining-budget message. The audit separately counts visible `date`/`time_left` commands and these returned budget messages. This establishes that time information was available in the trajectory. It does not establish a causal effect on each subsequent decision.

An assistant message can contain more than one tool call. The audit reports the largest such batch and the number of multi-call messages as potential parallelism. It does not infer overlapping execution from that structure: providers and agent wrappers can queue calls, serialize them, or return them in one batch after sequential work.

## Historical counts on 7 September 2026

The 366-run snapshot contains 25,039 converted tool calls and 311 recorded tool
errors. It contains 28 explicit refusal signals across 9 runs; several signals
can describe the same refusal. No empty-search errors matched the conservative
classifier, so that count does not establish that no searches returned zero
matches. Budget feedback appears in 11,563 converted messages.

The following totals mix budgets, conditions, and replicate counts. They describe
log coverage and tool use; they are not a fair ranking of model efficiency.
The JSON artifact retains per-run budgets and the complete tool breakdown.

| Agent:model | Runs | Tool calls | Types and counts |
|---|---:|---:|---|
| claude:claude-fable-5-1 | 22 | 458 | Bash 458 |
| claude:claude-haiku-4-5 | 24 | 530 | Bash 405, Edit 83, Read 21, Write 18, TaskUpdate 2, TaskCreate 1 |
| claude:claude-opus-4-8 | 25 | 1,131 | Bash 812, Edit 245, Read 37, Write 35, TaskStop 2 |
| claude:claude-opus-5 | 31 | 993 | Bash 780, Edit 178, Write 23, Read 12 |
| claude:claude-sonnet-5 | 30 | 2,104 | Bash 1,724, Edit 275, Read 76, Write 27, TaskOutput 1, TaskStop 1 |
| codex:gpt-5.6-luna | 25 | 1,579 | bash 1,233, apply_patch 346 |
| codex:gpt-5.6-sol | 28 | 2,787 | bash 2,207, apply_patch 580 |
| codex:gpt-5.6-terra | 27 | 1,587 | bash 1,173, apply_patch 408, wait 6 |
| codex:gpt-6-astra | 17 | 1,876 | bash 1,742, apply_patch 134 |
| react:anthropic/claude-fable-5.1 | 12 | 132 | bash 122, write_file 10 |
| react:anthropic/claude-opus-4.8 | 2 | 43 | bash 41, write_file 2 |
| react:anthropic/claude-opus-5 | 2 | 114 | bash 111, write_file 3 |
| react:google/gemini-3.8-flash | 27 | 2,068 | bash 2,020, write_file 48 |
| react:meta/muse-spark-1.3 | 24 | 4,759 | bash 4,739, write_file 20 |
| react:moonshotai/kimi-k3 | 22 | 1,405 | bash 1,382, write_file 23 |
| react:openai/gpt-5.6-sol | 24 | 2,507 | bash 2,476, write_file 31 |
| react:z-ai/glm-5.3 | 24 | 966 | bash 939, write_file 27 |
