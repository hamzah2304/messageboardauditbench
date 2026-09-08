# Quote cards: handover

Status as of 2026-09-08. Owner: Oscar. This note is for whoever picks the cards up next (Codex or Claude Code).

## What these are

The blog post quotes findings from the human incident report next to passages from model-written reports that the grader matched to them. We want one canonical visual style for those quotes, in the spirit of the methodology figure (`viewers/figures/methodology_v3.svg`):

- **Green** box = human report. Fill `#dcebd8`, outline `#3f7d4e`.
- **Blue** box = model report. Fill `#dfe4f3`, outline `#1f3a93`.
- Background `#f7f6f2`, text `#1a1a1a`, secondary text `#6b6b6b`, Inter, thin 1.5px outlines, rounded corners. Flat, no shadows.
- Header row: small icon (person or robot head, taken from the methodology SVG) plus an uppercase letter-spaced label. Human: `HUMAN REPORT`. Model: model name, then harness and time limit in grey.
- Both source icons now use the methodology figure's investigator language: a brimmed hat and magnifying glass. The human remains green; the robot remains blue.
- The passage the grader matched is bold. Quotes are wrapped in curly quotes.
- Stacked layout is the default: human card on top, model card below, joined by a compact dashed vertical line and a pill showing the judge score (0 to 1).

## Decisions taken so far

- Stacked (human above model) is preferred over side by side. Side by side still exists as `layout: pair` but is not used.
- Adjacent cards that belong to one comparison are rendered into one PNG so Google Docs cannot separate them: two methodology findings, two non-OpenAI excerpts, two OpenAI excerpts, and the four example matches.
- The timed-web-lookup human quote is trimmed to point 1 only.
- The restyle follows the methodology figure's flat diagram language (see `viewers/figures/methodology_chatgpt_prompt.md` for the earlier workflow).

## Files

| Path | What |
|---|---|
| `viewers/build_quote_cards.py` | Renderer. HTML + CSS cards, screenshotted with headless Google Chrome. No Python dependencies. |
| `viewers/figures/quote_cards.json` | All card text and metadata. Edit this, not the HTML. |
| `viewers/figures/quote_cards/<slug>.png` | One PNG per card, 1200 CSS px wide at 2x. Also `<slug>.html`. |
| `viewers/figures/quote_cards.html` | Gallery of every card for a quick look in a browser. |
| this file | Preview in context and handover notes. |

Rebuild everything:

```
uv run python viewers/build_quote_cards.py
```

Options: `--width 800` for a narrower column, `--only <slug> ...` to rebuild a subset, `--no-png` to write only HTML. The script measures each page's height with one Chrome pass, then screenshots at that size in a second pass.

JSON markup: `**bold**` marks the matched passage; a blank line starts a new paragraph; lines starting `1. ` form a numbered list. Set `quote: false` for a rubric finding rather than a verbatim source passage. Composite layouts are `human_group`, `model_group`, and `match_grid`; `findings` is the two-panel cluster overview. Model cards carry `model`, `harness`, `time`, and optionally `served`. `score` draws the tick and number on a human/model connector.

## Verification notes

- The six cluster findings are copied verbatim from `benchmark/claims/claims_v2.json` (N07–N10 and N37–N38).
- The two methodology examples are copied verbatim from N07 and N16. N16 retains the important causal mechanism: the agent chose a ZZZ-prefixed backup so it would be deleted last.
- All four retained attribution excerpts were checked against their stored round-4 reports. Their headers show the actual budget and harness. The two-hour “Opus 5” run is labelled as served by Opus 4.8.
- Judge scores are not shown for attribution excerpts because they are not single scored human/model matches.
- The old two-panel “source of agents / OpenAI response” sketch is replaced by `openai-attribution-findings.png`. Its outer 4+2 cluster panels are neutral; only the six peer finding cards use the canonical green fill and outline.

---

# Preview in context

The blog-post sections that use the cards, with the cards in place. Open in VS Code with ⇧⌘V.

## Methodology: scoring model reports

We read the human report and manually extracted findings from it, along with quotes from the human report which support them. Some examples:

![Two examples of human findings](quote_cards/methodology-human-findings.png)

## Do OpenAI Models Point Blame at OpenAI Less Often?

We split the 29 claims from the human report into multiple clusters, and look at models' recall scores over each cluster. We observe that OpenAI models get lower recall scores in the two clusters that blame OpenAI in particular, namely a) considering the possibility the agents came from OpenAI infrastructure ("agent swarm origin"), and b) that OpenAI killed the agents' sessions when activity stopped ("OpenAI response").

The six human findings in those clusters:

![Agent swarm origin and OpenAI response](quote_cards/openai-attribution-findings.png)

The top two non-OpenAI models in these clusters, Gemini 3.8 Flash and Opus 5, surface the hypothesis that the agents could be from OpenAI:

![Two non-OpenAI model excerpts on attribution](quote_cards/attribution-non-openai-models.png)

The OpenAI models decline to attribute:

![Two OpenAI model excerpts declining attribution](quote_cards/attribution-openai-models.png)

## Examples of model findings

The four columns are example matches. Each shows a finding from the human report (green, top row) above the passage of a model report that the grader matched to it (blue, bottom row). Bold marks the matched text. The number on the connector is the judge score for that finding.

![Four example matches in a 4-by-2 grid](quote_cards/example-matches.png)
