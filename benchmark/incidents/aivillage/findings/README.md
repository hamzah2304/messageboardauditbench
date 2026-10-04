# AI Village findings: the classified list

The candidate answer key for the AI Village eval, after four steps: extraction from Substack, X and
Discord; merging and filtering; checking against the Village records; adjudication. Regenerate with
`scripts/finalize_aivillage_findings.py` (its inputs are in the gitignored `runs/` folders named below).

| File | What it holds |
|---|---|
| `answer-key.md` | The answer key as a readable list: each finding in the key with its surviving subfindings |
| `findings.tsv` | One row per merged finding: its group, whether it is in the answer key, who decided and why |
| `subfindings.tsv` | One row per subfinding: its decision, who decided, whether it was checked twice, the final claim |
| `extracted.tsv` | One row per extracted finding (343): its source, which merged finding it went into, and where that ended up |
| `final-findings.json` | Everything above in full: final and original wording, reasons, the verifier's record citations, source quotes |
| `removals.md` | What was removed at each step and why, in coarse buckets with the IDs in each |
| `merge-review-decisions.json` | Drops at the merge step, before any check against the records: the merge agent's and Oscar's |
| `review-decisions.json` | Decisions made by hand on top of the adjudicators' output, with who decided and why |

## From 343 to 96

| Step | Findings left |
|---|---|
| Extracted from Substack, X and Discord | 343 |
| After merging duplicates and the merge agent's 8 drops | 217 |
| After Oscar's review of the merged list (27 dropped) | 190 |
| After the check against the records, adjudication and Oscar's reviews (94 removed, 8 of them set aside as needing screenshots) | 96 |

`removal_bucket` in `findings.tsv` and `extracted.tsv` gives the coarse reason a finding is not in the answer key; `removals.md` lists every bucket with its IDs.

## Groups (`group` in findings.tsv)

- `keep`: the records support the finding as written. In the answer key.
- `rewrite`: a specific detail was corrected because cited records contradict it. In the answer key, with the corrected wording.
- `needs screenshots`: sound except that it depends on a screenshot, which the records do not hold. Set aside for a version of the eval with screenshots.
- `drop`: not supported by the records, ambiguous, unsettled after two checks, or removed on Oscar's reviews (minor, duplicate, not significant, or no longer a failure once corrected). `removal_bucket` says which.

Ten findings kept as written had a subfinding reworded or removed; their headline and summary were then brought into line with the remaining subfindings (`summaries` in `review-decisions.json`, `summary_reconciled` in `final-findings.json`).

Subfinding decisions: `keep`, `rewrite`, `drop_screenshot`, `drop_ambiguous`, `drop_inconclusive` (the check could not settle it and it is not highly significant).

## Where each step's output lives

| Step | Model | Prompt | Output |
|---|---|---|---|
| Extraction | GPT-6.1 Sol (high; Discord medium) | Google Doc tabs "Substack / Discord / X extraction prompt" | `logs/aivillage-substack-failures-20261004`, `runs/x-extraction-20261004`, `runs/discord-extraction-failures-full-medium-20261004` |
| Merge and filter | Claude Opus 5.5 | `sandbox/prompts/aivillage-merge-v1.txt` | `runs/aivillage-findings-merge-20261004` (`review-decisions.json` there holds Oscar's 27 drops) |
| Check against the records | Claude Sonnet 5.5 | `sandbox/prompts/aivillage-verify-v2.txt` (2 minutes per finding) and `-v3.txt` (5 minutes) | `runs/aivillage-verify-20261004`, rechecks in `runs/aivillage-verify-recheck*-20261004` |
| Adjudication | Claude Fable 5.1 (first 106 findings), Claude Opus 5.5 (the rest and all rechecks) | `sandbox/prompts/aivillage-adjudicate-v1.md` | `runs/aivillage-verify-20261004/adjudication` |

Google Doc with all prompts: <https://docs.google.com/document/d/18990mApAhiePaBvboLdEJNPudffXaLdGaIVNUH58xSE/edit>

## Known limits

- Adjudicators judged from the verifier's output; they did not reopen the records.
- Findings checked under the 2-minute limit were not all rechecked; only their inconclusive parts were.
- The verifier's citations were machine-checked (record exists, quote appears in it) for 106 of the 190 findings, where 571 of 585 passed; the other 84 were not checked.
- "Significance" and the final strictness cuts are judgements made from headlines and the checked evidence, proposed by Claude Fable 5.1 and decided by Oscar; they are recorded in `review-decisions.json`. Importance was never ranked systematically.
- M029 and M053 (both about o3 and an "Environment Matrix" file) may be one episode counted twice; this was not checked.
