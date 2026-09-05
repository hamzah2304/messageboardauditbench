# MessageBoardAuditBench — data & rubrics index

Canonical eval artifacts (mirrored from /workspace/collusion/report). Every
`build_*.py` reads these and emits the matching `*.html` viewer in this folder.

## Claims
- `claims.json` — the 68 master claims (L1–L4), the original rubric.
- `new_claims.json` — 30 report-grounded candidate claims derived from the
  coverage highlights (13 new + 17 restating existing); `new_claims_approved.json`
  is the approved set that fed the pipeline.

## Feasibility (which claims the data can support)
- `feasibility.json` — 30 claims checked against the stripped public dump.
- `feasibility_verbatim.json` — same, against Oscar's verbatim (augmented) variant.
- `feasibility_compare.json` — raw-vs-verbatim, with the 3 flips (C21/C22/C28).

## Rubrics (`rubrics/`)
- `rubric_1.md … rubric_6.md` — the copy-ready judge sheets (6 × 5 claims,
  score 0–1, `{{HUMAN_REPORT}}`/`{{MODEL_REPORT}}` placeholders). All 30 claims
  are graded as recall accuracy. `rubric_N.json` + `rubrics_all.*` are the same
  data structured / combined.
- `precision_prompt.md` — the 1–10 precision judge (counts contradictions of the
  human report).
- `build_rubrics.py` builds the rubrics from feasibility; `grade_with_rubrics.py`
  (recall) and `precision_grade.py` (precision) grade a report set with GPT-5.6 Sol.
- `batch/*.md` — the model reports under evaluation (blind-20 + context-20).

## Results (`rubrics/`)
- `graded_blind_*.json` / `graded_context_*.json` — per-claim recall scores per
  model per condition. `graded_bl_*_s{1,3}.json` — the earlier seed baselines.
- `precision_blind_*.json` / `precision_context_*.json` — precision score +
  enumerated contradictions per model per condition.
- `claim_matching.json` (in the parent folder) — human bad/neutral/good ratings
  of best-model-vs-human snippet per claim.

## Viewers (this folder, served by the html-viewer)
scoreboard_batch.html (blind vs context, recall+precision), rubrics.html
(rubrics + feasibility + grading .md), matching.html (claim-by-claim matching),
feasibility.html, variants.html, new_claims.html.

## Round 2 — `blind-10` batch (`rubrics/batch_r2/`, `rubrics/graded_r2_*.json`)
Oscar's second-round runs on the **verbatim** data with the hardened blind
prompt: 10-minute wall-clock budget, xhigh effort, r1/r2 replicates across 11
model/harness pairs (claude / codex / react). Graded on the same 30-claim recall
rubrics (`grade_with_rubrics.py --dir batch_r2`); recall only, no precision.
- `batch_r2/*.md` — the 21 reports (`_index.jsonl` carries run metadata).
- `graded_r2_<agent>_<model>_rep<n>.json` — per-claim recall scores.
- Leaderboard (mean of replicates): react·sol 0.467, codex·sol 0.417,
  react·glm-5.3 0.383, react·gemini-flash 0.382, claude·fable 0.367,
  react·kimi-k3 0.333, claude·opus-5 0.283, codex·terra 0.259, codex·luna 0.209,
  claude·sonnet-5 0.145, claude·haiku-4.5 0.067. The 10-min budget compresses
  scores vs the 20-min blind batch.
