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
stripped and verbatim variants, the notes describe the stripped dump, and every run used
verbatim. Rendering them drove C22 to 0.000 across all 76 reports.

## Auditing the judge (`benchmark/audit/`)

`viewers/build_audit_ui.py` builds `viewers/audit.html`: model report beside human report,
every judge quote highlighted and anchored to the passage of the human report the rubric
cites. Per claim it records a verdict (true positive, right find with wrong score, false
positive, true negative easy/hard, false negative, needs investigation), a corrected score,
a rubric flag and a comment. Per paragraph it records relevance, truth where the paragraph
matches no claim, agreement with the judge's rating where it does, and a note. Per report it
holds hypotheses and biases. It autosaves to `benchmark/audit/judge_audit.json` through the
html-viewer's `POST /save`.
