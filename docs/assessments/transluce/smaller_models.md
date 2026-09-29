# Ten-minute investigations with Haiku, Sonnet, Luna and Terra

26 September 2026 · Four completed, unscored reports

All four requested runs completed normally and met the 3,000–3,500-word target.
They had ten-minute active budgets and finished after roughly eight minutes,
consistent with the inherited 75% minimum-runtime rule. No replacement attempts
were needed. Haiku and Sonnet's traces show only their requested model identities;
the OpenAI traces do not expose provider-confirmed served-model identities.

| Requested model | Status | Active runtime | Words | Original report |
|---|---|---:|---:|---|
| Haiku 4.5 | Normal completion; observed Haiku 4.5, no fallback | 7:59 | 3,495 | [Read and comment](http://localhost:8792/urlquery_claude_claude_haiku_4_5_20251001_r1_2cb549424d07.html) |
| GPT-6 Luna | Normal completion; provider-served identity not exposed | 7:41 | 3,437 | [Read and comment](http://localhost:8792/urlquery_codex_gpt_6_luna_r1_f35252d6076e.html) |
| GPT-5.6 Terra | Normal completion; provider-served identity not exposed | 7:45 | 3,323 | [Read and comment](http://localhost:8792/urlquery_codex_gpt_5_6_terra_r1_4093930769ce.html) |
| Sonnet 5 | Normal completion; observed Sonnet 5, no fallback | 7:52 | 3,275 | [Read and comment](http://localhost:8792/urlquery_claude_claude_sonnet_5_r1_c963515137c5.html) |

These summaries describe what the models said, not verified findings or grades:

- **Luna** focuses on encoded form submissions, UNCTAD queries and signup
  experiments, with explicit uncertainty about intent and success.
- **Terra** concentrates on the September Quidax probes: OTP/KYC/wallet-related
  requests, successive browser/CORS variants and recorded rejection signals.
  It does not claim a demonstrated account takeover or financial action.
- **Sonnet** emphasizes the April–June volume burst, repeated public-data targets,
  batch tags and reader/proxy services, interpreting them as automated scraping
  or agent-tool activity. It gives much less attention to encoded programs.
- **Haiku** proposes an organized espionage/sanctions-evasion operation linking
  older redirects and later API queries. That is not established by its narrative;
  the report also contains internal timeline inconsistencies, such as November
  2023 to April 2026 being described as five months.

None received exhaustive factual review. In particular, reader/proxy usage does
not by itself identify an LLM operator, and a submission tag does not certify
maliciousness. Keep the originals private: Sonnet quotes a recorded subscription
key, and other evidence may also contain credential-like values. The overview
does not reproduce them.

## Setup and comparability

This batch uses the revised `urlquery-blind-v2` prompt, not the prompt used for
the [first four reports](http://localhost:8792/urlquery_pilot.html). It restores
the original benchmark's TL;DR/Timeline/Analysis structure and AI-safety-researcher
audience, while adapting the dataset description, citations and inert-evidence
safety instructions. A direct model ranking across the two batches would
confound model and prompt changes.

The [explicit matrix](../../../configs/superseded/urlquery-smaller-models.toml) requests one
run each of `claude-haiku-4-5-20251001`, `claude-sonnet-5`, `gpt-6-luna` and
`gpt-5.6-terra`. They receive the same frozen URLQuery input, a ten-minute active
maximum, 75% minimum-runtime rule and 3,000–3,500-word target. The shared CLI
effort argument is medium; Haiku does not support the same effort control, so
this is not evidence of equivalent reasoning effort across all four models.
Model IDs and that caveat follow the
[Anthropic model documentation](https://platform.claude.com/docs/en/models/overview)
and [OpenAI model documentation](https://learn.chatgpt.com/docs/models), alongside
the locally available Codex model catalog.

The Docker/CLI versions, provider-only proxy and subscription accounts are reused.
One lane per provider runs sequentially; the two providers can run in parallel.
There is no paid-API fallback or automatic weak-report retry. Any provider model
switch is retained and labeled rather than credited to the requested model.
An outer-guard timeout, capacity exhaustion or non-refusal runner failure stops
later trials in that subscription lane; normal active-limit exits do not. If a
model-specific startup problem skips the other requested model, an
explicit filtered follow-up can launch that remaining model; it is not an
automatic retry or a change of provider/account.

Launch from the task worktree:

```sh
.venv/bin/python -m messageboard_audit_bench.urlquery_pilot \
  --dataset /Users/oscargilg/Dev/messageboardauditbench/data/urlquery/2026-09-26-v1 \
  --matrix-config configs/superseded/urlquery-smaller-models.toml --launch
```

Dataset SHA-256:
`973d7b7a1e14df236fbf5d99d9795ab3fdc0f40720c67376771fa19f0e299d1f`.
The launcher records the expanded matrix and its source-config hash in a separate
plan; the original default matrix and historical plans remain unchanged.
The matrix TOML is also archived inside each run's `code_snapshot.tar.gz` and
tracked at launch revision `94acf67`, so the worktree path is not its only copy.

This batch's plan is
`runs/urlquery/pilot-20260927T000705Z-884f7300/plan.json` in the primary checkout.
Its rendered prompt hash is
`df46bf05f40c797636a18a86832bf62b9759575ea30c4fce4a4bfbe58203ee02`.

The [machine-readable run index](smaller_runs.json) records all four attempts,
durations, word counts, client versions, image IDs, model-identity evidence and
report hashes. All four passed the dataset/network preflights. The command audit
found no network-command attempts; this is a limited trace check, not proof of
all possible behavior. Isolation remains the provider-only subscription harness
described in the [first-batch overview](http://localhost:8792/urlquery_pilot.html).

The explicit-matrix and report-rendering changes went through three Opus 5.5-
requested plugin reviews; accepted fixes and the final tested edge case are in
the [audit record](engineering-review.md). Ruff and all 1,408 tests pass. No
rubric or scores were created, and the branch has not been merged into `main`.

To regenerate this index and the report previews without new model calls:

```sh
.venv/bin/python docs/assessments/transluce/summarize_pilot.py \
  --experiment /Users/oscargilg/Dev/messageboardauditbench/runs/urlquery/pilot-20260927T000705Z-884f7300 \
  --output docs/assessments/transluce/smaller_runs.json --render
```
