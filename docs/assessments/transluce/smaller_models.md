# Ten-minute investigations with Haiku, Sonnet, Luna and Terra

Requested follow-up · Results pending execution

This batch uses the revised `urlquery-blind-v2` prompt, not the prompt used for
the [first four reports](http://localhost:8792/urlquery_pilot.html). It restores
the original benchmark's TL;DR/Timeline/Analysis structure and AI-safety-researcher
audience, while adapting the dataset description, citations and inert-evidence
safety instructions. A direct model ranking across the two batches would
confound model and prompt changes.

The [explicit matrix](../../../configs/urlquery-smaller-models.toml) requests one
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

Launch from the task worktree:

```sh
.venv/bin/python -m messageboard_audit_bench.urlquery_pilot \
  --dataset /Users/oscargilg/Dev/messageboardauditbench/data/urlquery/2026-09-26-v1 \
  --matrix-config configs/urlquery-smaller-models.toml --launch
```

Dataset SHA-256:
`973d7b7a1e14df236fbf5d99d9795ab3fdc0f40720c67376771fa19f0e299d1f`.
The launcher records the expanded matrix and its source-config hash in a separate
plan; the original default matrix and historical plans remain unchanged.
