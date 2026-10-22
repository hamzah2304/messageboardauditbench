# Answer keys (answer-key-v1)

One JSON file per eval, `benchmarks/<eval>/answer-key.json`. The format is defined and validated in
`slopvestigator_bench/answer_key.py`; QA output, the review page and (later) the grader read it.

| File | Built by |
|---|---|
| `benchmarks/german-wiki/answer-key.json` | `scripts/build_german_wiki_answer_key.py` (12 section findings over the 38 v2 points, headlines drafted by `scripts/draft_answer_key_headlines.py`), then `scripts/run_answer_key_qa.py german-wiki <out> --merge` and `scripts/check_answer_key_citations.py german-wiki` |
| `benchmarks/aivillage/answer-key.json` | `scripts/aivillage/build_aivillage_answer_key.py` from `benchmarks/aivillage/findings/final-findings.json` (QA'd earlier), plus the open review items |

The v2 grading path still reads `benchmarks/german-wiki/claims/claims_v2.json`; nothing here changes it.

## QA

`scripts/run_answer_key_qa.py` runs one sandboxed Claude Code agent per finding
(`sandbox/docker/run_trial.sh` with `PROMPT_FILE_OVERRIDE`, configs `configs/answer-key-qa-<eval>.toml`),
on the same read-only data the investigators get. The prompt `sandbox/prompts/answer-key-qa-v1.txt` is
filled with the modules in `benchmarks/qa/modules/` (finding description and the eval's addendum,
derivability, data note), the finding and the rest of the key. The agent writes `/work/qa/<id>.json`;
the driver keeps it under the run's output folder and `--merge` folds it into the key.

## Review decisions

The review page (`scripts/viewers/review/answer_key_review.html`, published as the claude.ai artifact
https://claude.ai/artifact/GCeBdTwFJWkNNcuaa5WCRz with the keys as
`keys/<eval>.json`) saves each decision to the artifact's database, collection `decisions`, document id
`<eval>~<item>`: `<item>` is a finding id, a subfinding id, `<finding>.headline` for a drafted
headline, or `_page` for a comment on the whole key. Fields: `eval`, `item`, `kind`
(finding, subfinding, headline, page), `parent`, `decision` (accept, edit, reject, or empty),
`text` (the edited wording when the decision is edit), `comment`, `shown` (the text and QA block the
reviewer saw, to detect decisions made on older content), `updated_at`, `by` (an opaque user id).
Agents read them with the ArtifactData tool: `list` on collection `decisions` of the artifact.
