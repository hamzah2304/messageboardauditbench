# URLQuery evaluator material

This directory is separate from `benchmark/`, which belongs to the original
MessageBoardAuditBench. Nothing here may be mounted into an investigation trial.

## Judge

The canonical reviewed rubric is `claims/findings_reviewed.json`: 13 headline
findings and 51 sub-findings. F1–F12 incorporate the data and fairness audits;
F13 is the separately sourced header-injection finding, recorded in
`claims/header_injection.json`. `judge/render_sheet.py` combines the rubric with
`judge/finding_sheet_reviewed.md`, scoring one headline and its children per
call. The source report that suggested F13 is not treated as evidence in its
judge prompt. Grade files go to ignored `reports/urlquery/graded/` directories
and carry prompt, rubric, article-context, and report hashes.

Use `--launch` to select completed reports from **both** plans referenced by the
ongoing final launcher. Re-run the same command as more reports finish. The
full source article caused the judge to refuse; `--omit-article` retains the
reviewed finding, the relevant article quote excerpts and scoring notes, and
records the changed prompt context in each grade's article hash.

    .venv/bin/python benchmarks/urlquery/judge/grade.py \
      --launch runs/urlquery/final-20260927-agents-v6/launch.json \
      --omit-article --workers 8

For the final 2026-09-27 run, use a **single judge**: GPT-6 Astra at high
reasoning effort via synchronous OpenRouter chat-completion calls. The direct
API runner reads both plans from the final launch file; it never reuses Claude
scores. The original 48-report F1–F12 regrade is preserved in
`reports/urlquery/graded/judge_gpt_6_astra_high_fairness_v2/`. F13 was judged
alone with the same model and effort in
`reports/urlquery/graded/judge_gpt_6_astra_high_f13_only/`, then combined into
`reports/urlquery/graded/judge_gpt_6_astra_high_fairness_v3/` without changing
the earlier 576 judgments. To reproduce that F13-only pass and combination:

    .venv/bin/python benchmarks/urlquery/judge/grade_openrouter.py \
      --launch runs/urlquery/final-20260927-agents-v6/launch.json \
      --findings F13 --workers 32 \
      --output reports/urlquery/graded/judge_gpt_6_astra_high_f13_only
    .venv/bin/python benchmarks/urlquery/judge/combine_f13_grades.py

Validate grades by hand with `viewers/build_urlquery_audit_ui.py` (local page, or
`--artifact PATH` for a shared, redacted claude.ai page whose audits save per auditor).

## Building findings

Preserve the manual workflow:

1. Extract candidate findings from the inert Transluce article in
   `viewers/urlquery_findings.html` (generated with
   `viewers/build_urlquery_findings.py`). Write each finding and its
   sub-findings in your own words, attach supporting quotes, mark whether the
   scans can check it, then Export JSON.
2. Write candidates in `claims/new_claims.json` with their verbatim source quote,
   source/report hash and exact frozen dataset hash. Reuse
   `viewers/build_new_claims_ui.py --benchmark urlquery` for approval.
3. Check each approved candidate using **only** that frozen agent input. Save
   `feasibility/feasibility.json`, including the exact local query, record IDs,
   output, narrowed supported wording, missing evidence, and a verdict of
   derivable / partial / not_derivable. Render with
   `viewers/build_feasibility_ui.py --benchmark urlquery`.
4. Approve a dataset-matched rubric before adding automated grading. Do not
   substitute the original benchmark's rubric or automatically certify the
   source report's conclusions.

The candidate and feasibility input objects require
`meta.benchmark_id="urlquery"`, `meta.report_sha256` and `meta.dataset_sha256`.
The latter two must be full SHA-256 hex strings. Candidate state and exports are
namespaced separately. Findings exports use the original source HTML hash plus
a rendered-article hash, because passage offsets depend on the inert rendering.

Raw downloads, the annotated catalog and acquisition audits live once in the
primary checkout's ignored `data/transluce/`. Frozen agent files live under
`data/urlquery/<version>/`; their evaluator-only provenance sidecar is adjacent,
outside the mount. See [preprocessing documentation](../../docs/urlquery-engineering.md).

## Consolidated findings (draft v1)

`claims/findings_v1.json` merges three annotators' extractions into 12 findings
and 53 sub-findings, plus 14 excluded article sentences with the reason each
cannot be reached from the frozen scans (wiki/DseWiki, external news, other
incidents, Transluce's own labels). Headline findings are deliberately general;
dates, counts and specifics are sub-findings. Each item has a `kind`, a
`derivable` tag, `tags`, full-sentence article quotes, `evidence_scans` (the
scan IDs Transluce links for that statement, all present in
`urlquery/2026-09-26-v1`) and `judge_notes`, scoring instructions that are
empty unless an item needs one (for example, penalise a report that says a
hacking attempt succeeded). The file carries no weights: the judge is
configured separately. Rebuild with
`uv run python benchmarks/urlquery/claims/build_findings_v1.py`. Under review.
