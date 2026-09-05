# Benchmark data & rubrics index

Every path below is repo-relative. Build/grading scripts resolve inputs through
`paths.py` at the repo root.

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
- `graded_r2_<agent>_<model>_rep<n>.json` — round 2.

## Graded inputs (`benchmark/graded_inputs/`)
The exact report each grade file corresponds to, keyed to match. These are
byte-identical copies of files in `reports/`, kept so a score can be traced to its
input without reconstructing the mapping.
- `blind_context/` — the blind-20 + context-20 batch (`--batch`).
- `round2/` — the 21 round-2 reports (`--dir round2`); `_index.jsonl` carries run metadata.
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

**Round 2 — blind-10** (`benchmark/graded_inputs/round2/`). Runs on the **verbatim** data
with the hardened blind prompt: 10-minute wall-clock budget, xhigh effort, r1/r2
replicates across 11 model/harness pairs (claude / codex / react). Recall only.
Leaderboard (mean of replicates): react·sol 0.467, codex·sol 0.417, react·glm-5.3 0.383,
react·gemini-flash 0.382, claude·fable 0.367, react·kimi-k3 0.333, claude·opus-5 0.283,
codex·terra 0.259, codex·luna 0.209, claude·sonnet-5 0.145, claude·haiku-4.5 0.067.
The 10-minute budget compresses scores vs the 20-minute blind batch.
