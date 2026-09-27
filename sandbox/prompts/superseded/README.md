# Superseded prompts

Prompt files here are kept for provenance but are no longer the default for any
active config. The trial harness resolves a prompt name to
`sandbox/prompts/<name>.txt` (top level only), so nothing in this folder is
selectable unless a config explicitly names `superseded/<name>`.

- `urlquery-blind.txt` — the first urlquery investigation prompt. Superseded on
  2026-09-26 by `../urlquery-blind-v2.txt`, which restarts from the original
  benchmark's `blind-v2.txt` and changes only what the scan dataset forces
  (data described as web scans + a pointer to `data/README.txt`; citations by
  scan ID / transaction index; an inert-evidence safety line). This keeps the
  urlquery eval's prompt aligned with the original eval. `configs/urlquery-10.toml`
  now points at `urlquery-blind-v2`.
