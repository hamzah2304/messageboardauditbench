# Superseded prompts

Prompt files here are kept for provenance but are no longer used by any active
config. A config selects one only by naming it explicitly, as
`prompt = "superseded/<name>"`; the archived configs in `configs/superseded/` do.
The exact text each run saw is also kept in its run directory (`prompt.txt`).

URLQuery prompt lineage (the active prompt is `../urlquery-agents-v6.txt`):

- `urlquery-blind.txt` — the first investigation prompt.
- `urlquery-blind-v2.txt` — restarted from the original benchmark's
  `blind-v2.txt`, changing only what the scan dataset forces.
- `urlquery-swarm-v2.txt`, `urlquery-weird-v2.txt`,
  `urlquery-swarm-focused-v3.txt` — 2026-09-26 prompt pilots.
- `urlquery-swarm-v4.txt`, `urlquery-swarm-v4-nodetails.txt` — the swarm-v4
  prompt and its "do not get lost in the details" ablation.
- `urlquery-agents-v5.txt` — the agent-incident prompt that v6 revised.
