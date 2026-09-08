# Benchmark data & rubrics index

Every path below is repo-relative. Build/grading scripts resolve inputs through
`paths.py` at the repo root.

Historical graded-input indexes retain the original time-bearing report-folder
prefixes such as `blind-30_p...`. Newly collected reports use the normalized
`<condition>_<data-variant>_<effort>_p<prompt-hash>` layout; the index remains
the authoritative mapping from a grade to its report artifact.

## Ground truth (`benchmark/`)
- `human_report.txt` — the human incident report. The answer key everything is graded
  against, and the source `scripts/fill_verbatim.py` reads to build the verbatim variant.

## Claims (`benchmark/claims/`)
- `claims.json` — the 68 master claims (L1–L4), the original rubric.
- `new_claims.json` — 30 report-grounded candidate claims derived from the coverage
  highlights (13 new + 17 restating existing); `new_claims_approved.json` is the
  approved set that fed the pipeline.
- `claim_matching.json` — human bad/neutral/good ratings of best-model-vs-human
  snippet per claim.

## Feasibility (`benchmark/feasibility/`)
Which claims the data can actually support.
- `feasibility.json` — 30 claims checked against the stripped public dump.
- `feasibility_verbatim.json` — same, against the verbatim (augmented) variant.
- `feasibility_compare.json` — raw-vs-verbatim, with the 3 flips (C21/C22/C28).
- `stripped/`, `verbatim/` — the six per-batch runs behind each, plus the
  `INSTRUCTIONS.md` the checking agents were given (its paths refer to the machine
  that pass ran on) and `aggregate.py` that merges
  `result_batch_*.json` back into the parent JSON.

## Rubrics (`benchmark/rubrics/`)
- `rubric_1.md … rubric_6.md` — the copy-ready judge sheets (6 × 5 claims, score 0–1,
  `{{HUMAN_REPORT}}`/`{{MODEL_REPORT}}` placeholders). All 30 claims are graded as
  recall accuracy. `rubric_N.json` + `rubrics_all.*` are the same data structured
  and combined.
- `precision_prompt.md` — the 1–10 precision judge (counts contradictions of the
  human report).
- `build_rubrics.py` builds the rubrics from feasibility; `grade_with_rubrics.py`
  (recall) and `precision_grade.py` (precision) grade a report set with GPT-5.6 Sol.

## Graded results (`benchmark/graded/`)
- `graded_blind_*.json` / `graded_context_*.json` — per-claim recall per model per
  condition. `graded_bl_*_s{1,3}.json` — the earlier seed baselines.
- `precision_blind_*.json` / `precision_context_*.json` — precision score plus
  enumerated contradictions.
- `graded_r2_*.json` / `graded_b20_*.json` / `graded_b30_*.json` — round 2 at the
  10-, 20- and 30-minute budgets, per replicate.
- `graded_r3b10_*.json` / `graded_r3b30_*.json` / `graded_r3b120_*.json` — round 3 at the
  10-, 30- and 120-minute budgets, per replicate.

## Graded inputs (`benchmark/graded_inputs/`)
The exact report each grade file corresponds to, keyed to match. These are
byte-identical copies of files in `reports/`, kept so a score can be traced to its
input without reconstructing the mapping.
- `blind_context/` — the blind-20 + context-20 batch (`--batch`).
- `round2_blind10/`, `round2_blind20/`, `round2_blind30/` — the round-2 reports at each
  budget (`--dir round2_blind10`, etc.); each `_index.jsonl` carries run metadata.
- `round3_blind10/`, `round3_blind30/`, `round3_blind120/` — the round-3 reports, staged by
  `scripts/stage_graded_inputs.py`. Filenames carry harness, model, replicate and, where
  Claude Code switched model after a refusal, `served-<model>`; `_index.jsonl` adds
  `graded_input` naming the staged file each run maps to.
- `seed_baselines/` — the s1/s3 seed baselines (`--baselines`).

## Viewers (`viewers/`)
Each `build_*.py` emits the matching `.html`, which is gitignored — rebuild rather than
commit. `scoreboard_batch.html` (blind vs context, recall + precision), `rubrics.html`
(rubrics + feasibility + the judge sheets), `matching.html` (claim-by-claim matching),
`feasibility.html`, `variants.html`, `new_claims.html`, `scoreboard.html`.
`coverage_combined.html` is committed as an exception: its builder needs a rendered
collusion.wiki bundle that is not redistributed here (point `WIKI_DOWNLOAD_DIR` at a
local copy to rebuild).

## Run history
**Round 1 — blind-20 / context-20.** 17 reports across 9 models, graded on the 30-claim
recall rubrics plus precision. Blind = dump only; context = dump plus background.

**Round 2 — blind-10 / blind-20 / blind-30.** Runs on the **verbatim** data with the
hardened blind prompt at xhigh effort, r1/r2 replicates, across up to 11 model/harness
pairs (claude / codex / react). Recall only, no precision. The three batches differ only
in the wall-clock budget the prompt states and the container enforces.

Mean recall across replicates:

| harness · model | 10 min | 20 min | 30 min |
|---|---|---|---|
| claude · opus-5 | 0.283 | 0.413 | 0.510 |
| react · sol | 0.467 | 0.475 | 0.500 |
| react · kimi-k3 | 0.333 | 0.319 | 0.449 |
| react · gemini-flash | 0.382 | — | 0.425 |
| codex · sol | 0.417 | 0.358 | 0.400 |
| react · glm-5.3 | 0.383 | 0.420 | 0.392 |
| claude · fable | 0.367 | 0.383 | — |
| codex · terra | 0.259 | 0.242 | 0.334 |
| codex · luna | 0.209 | 0.192 | 0.333 |
| claude · sonnet-5 | 0.145 | 0.175 | 0.242 |
| claude · haiku-4.5 | 0.067 | 0.075 | 0.125 |

Gaps are missing runs, not zeros: react·gemini-flash has no blind-20 batch and
claude·fable no blind-30. Three cells rest on a single replicate rather than two —
claude·fable at blind-10 and blind-20, and claude·opus-5 at blind-30, which is the
highest score in the table.

Recall rises with budget for most models. Opus 5 is the clearest climb
(0.283 → 0.413 → 0.510) and the only model above 0.5; react·sol plateaus at ~0.47–0.50,
so the ranking at one budget does not carry to another.

**Round 3 — blind-10 / blind-30 / blind-120.** 76 reports on the verbatim data with the
hardened blind prompt, three replicates for most pairs, two new models (gpt-6-astra,
meta/muse-spark-1.3) plus claude-opus-4-8, and a 2-hour budget. Recall only.

Graded on the revised sheets (see "Judge sheets, revised" below); the previous grades are
in git at commit 79a1df5.

| harness · model | 10 min | 30 min | 120 min |
|---|---|---|---|
| codex · sol | 0.373* | 0.683* | **0.735** |
| react · sol | 0.500* | 0.600* | 0.689 |
| codex · astra | 0.468 | 0.564 | 0.652 |
| claude · opus-5 | 0.410* | 0.546 | — |
| react · muse-spark | 0.461 | 0.500 | 0.543 |
| react · gemini-flash | 0.300* | 0.443* | 0.513 |
| codex · luna | 0.233* | 0.350* | 0.513 |
| claude · opus-4.8 | 0.293 | 0.381 | 0.473 |
| react · glm-5.3 | 0.303* | 0.463* | — |
| claude · sonnet-5 | 0.130* | 0.270* | 0.450 |
| react · kimi-k3 | 0.340* | 0.433* | — |
| codex · terra | 0.317* | 0.427* | 0.385 |
| claude · fable | 0.400* | — | — |
| claude · haiku-4.5 | 0.127* | 0.093* | 0.200 |

`*` = one replicate. Dashes are missing runs. Eight refusal-fallback runs sit outside the
table under their served model.

Mean across pairs rises 0.333 → 0.443 → 0.515 with budget.

## Judge sheets, revised

`build_rubrics.py` renders into each sheet what the feasibility pass established, so the
judge applies the project's ground truth rather than its own. The half-point band is now
vagueness only, with an explicit instruction not to deduct for wording, extra detail, or a
range inside a hedge the claim itself carries. C02 no longer scores the
training-versus-testing hedge.

C21, C22 and C28 carry no data note on purpose: their gradeability flips between the
stripped and verbatim variants, the notes describe the stripped dump, and every run graded
on these 30-claim sheets used verbatim. Rendering them drove C22 to 0.000 across all 76
reports. This does not carry over to the `v2` sheets or to the `verbatim_anthropic`
grades below, which select an answer key per variant.

## How `benchmark/graded/` is organised

The layout carries three independent dimensions, and a path states all three. Grades from
different judges or sheet modes are never comparable without regrading.

- **Top level** — the original 30-claim recall and precision grades, judged by GPT-5.6
  Sol. Prefixes: `bl` (seed baselines), `blind`/`context` (the first blind-vs-context
  batch), `b20`/`b30` and `r2` (round 2), `r3b10`/`r3b30`/`r3b120` (round 3),
  `r4b10` (round 4 at 10 minutes).
- **`judge_<model>/`** — the same reports regraded by a different judge, kept apart so a
  judge change never silently merges into a published number. `judge_claude_opus_5/` also
  holds loose round-3 files at its top level.
- **`judge_<model>/<sheet>/`** — the sheet mode: `v2` (38-finding coverage), `tldrh`
  (holistic summary quality), `tldr` (its earlier form), `origin` (the one-question origin
  probe).
- **`<sheet>/variant_anthropic/`** — grades for reports run on `data/verbatim_anthropic`,
  scored against the swapped answer key. Keeping them in their own subtree is what stops a
  provider-swap grade being averaged into a verbatim number.
- **`contradiction/`** — the contradiction pass, built by `rubrics/build_contradiction.py`.

Prefixes name the round and budget: `r2`, `r3b{10,30,120}`, `r4b{10,30,120}`,
`fu5kb{10,30,120}` and `fu5k` (followup), `psw{10,30}` (provider swap), `abl{10,30}a`
(Anthropic-attribution ablation). The rest of a filename is harness, model and replicate,
with `_served_<model>` recording a mid-run model switch.

Counts move as collaborators export more cells, so treat the tracked files as the
authority rather than any number written down here. `ls` the directory you intend to
aggregate, and check `_index.jsonl` in the matching `graded_inputs/` folder for the run
metadata behind each grade.

## Rounds and experiments beyond round 3

- **Round 4** — the `blind-v2` prompt on verbatim at 10, 30 and 120 minutes, three
  replicates. Reports in `reports/round4/`, staged as `graded_inputs/round4_blind{10,30,120}/`.
  Graded on the `v2` and `tldrh` sheets under both judge directories.
- **Provider swap** — round 4's twin on `data/verbatim_anthropic`, testing whether a model
  reports differently when the incident is attributed to its own provider. Reports in
  `reports/provider_swap/`, staged as `graded_inputs/pswap_b{10,30}/`, graded under
  `variant_anthropic/`. `experiments/provider_swap.toml` is the manifest.
- **Followups** — a continuation with a longer report request. Reports in
  `reports/followup-5k/` and `reports/followup-5k-min5/`, staged as `graded_inputs/fu5k*/`.
  It adds both time and length, so it does not isolate report length on its own.
- **Anthropic-attribution ablation** — staged as `graded_inputs/ablation_anthropic_b{10,30}/`.

Raw agent transcripts are gitignored (`reports/**/transcript.jsonl`) because they are
multi-MB and are not needed to reproduce a grade. One is committed deliberately as a
worked example: `reports/round4/transcripts/codex_gpt-6-astra_r1_blind_120m/` holds the
prompt, run metadata, and the full trajectory of a single 120-minute round-4 replicate,
including Codex reasoning summaries. Read it to see what an agent actually does with the
budget; nothing depends on it.

[`experiments/ablations.md`](../experiments/ablations.md) holds the ablation inventory and
the rebuild/grading commands. [`release-readiness.md`](release-readiness.md) records what
still has to be reconciled before any of these are published as results — in particular,
which swap revision each Anthropic batch actually consumed.

## Auditing the judge (`benchmark/audit/`)

`viewers/build_audit_ui.py` builds `viewers/audit.html`: model report beside human report,
every judge quote highlighted and anchored to the passage of the human report the rubric
cites. Per claim it records a verdict (true positive, right find with wrong score, false
positive, true negative easy/hard, false negative, needs investigation), a corrected score,
a rubric flag and a comment. Per paragraph it records relevance, truth where the paragraph
matches no claim, agreement with the judge's rating where it does, and a note. Per report it
holds hypotheses and biases. It autosaves to `benchmark/audit/judge_audit.json` through the
html-viewer's `POST /save`.
