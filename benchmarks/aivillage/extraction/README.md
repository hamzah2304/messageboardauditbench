# Extraction step: prompts and scripts as run on 4 October 2026

The first step of the AI Village answer key: GPT-6.1 Sol reads each source and extracts candidate
findings. The later steps are documented in `../findings/README.md`.

| Source | Prompt | Script | Output (gitignored) |
|---|---|---|---|
| Substack (18 articles, high reasoning) | `substack-findings-prompt.md` | `scripts/extract_aivillage_substack.py`, quotes checked by `scripts/check_aivillage_extractions.py` | `logs/aivillage-substack-failures-20261004` |
| X (157 screened posts, high reasoning) | `../x-findings-prompt.md` | `scripts/x_screen.py`, `scripts/x_extract.py` | `runs/x-extraction-20261004` |
| Discord (1,308 screened conversations, medium reasoning) | `discord-findings-prompt.md` | `discord_extract_all_run.py`, which builds its requests with `discord_extract_sample_run.py` | `runs/discord-extraction-failures-full-medium-20261004` |

The two prompt files are the text under the "Extraction prompt" heading of the Google Doc tabs
"Substack extraction prompt" and "Discord extraction prompt" as fetched on 4 October; the
`*-prompt-provenance.json` files record the tab and the prompt's hash.

The three `discord_*_run.py` files are copies of the scripts exactly as they ran, kept as a record.
Each expects to sit in its run folder next to its inputs (`extraction-prompt.md`, and
`sample-packets.json` or `packets.jsonl`), so they do not run from this folder. The screening that
chose the 1,308 conversations (`discord_screen_run.py`, GPT-6 Luna, low reasoning) used an earlier,
more permissive prompt and was not rerun with the failure criteria.
