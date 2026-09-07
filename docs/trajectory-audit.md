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
