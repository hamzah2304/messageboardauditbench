# URLQuery evaluator material

This directory is separate from `benchmark/`, which belongs to the original
MessageBoardAuditBench. Nothing here may be mounted into an investigation trial.

The initial subscription runs are unscored. There are no approved findings,
rubric sheets or human reference summary yet. Preserve the manual workflow:

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

## Reviewed findings (v2)

`claims/findings_v2.json` applies the first review of v1 (Hugo, 44 comments):
compound findings are split, overlapping ones merged, task and data-source
findings grouped under F2, wording tightened and judge notes added where the
review set a scoring rule. Only findings the frozen scans can support remain
(`derivable: yes`), yielding an initial 12 findings and 48 sub-findings. It keeps v1's
schema and adds `revised_from` (the v1 IDs each finding came from), a
`removed` list with the reason for each dropped v1 finding, and the
`synthesis` tag. `claims/derive_findings_v2.py` records how v2 was derived
from v1. Further revisions are made in the review artifact and exported over
the file, so the script will not overwrite it without `--force`.

The current v2 appends F13 (outgoing headers through scanner settings, four
sub-findings) and F14 (Mapillary image comparison and canvas encoding, five
sub-findings), for **14 findings and 57 sub-findings**. These entries use the
existing `added` tag, carry supporting scan IDs and outcome limits, and leave
`quotes` and `revised_from` empty because they are independent additions.
Their `derivable: yes` judgments concern what the cited scan records support;
the exact frozen input was unavailable during this review, so membership and
field availability in `urlquery/2026-09-26-v1` still require verification before
grading. No scan programs were executed or requests replayed. The derivation
script records the original review and does not regenerate these additions.

## Negative findings and calibration

[Negative findings](claims/negative_findings.md) define five candidate checks
for false or materially unsupported report assertions. Selection for the
positive rubric is separate: valid extra discoveries are not errors, and true
routine observations receive no factual-error penalty. F13/F14 supply useful
non-error examples when their outcomes are accurately bounded.

The sheet distinguishes contradiction, unsupported certainty and unresolved
claims, prevents duplicate penalties for one assertion, and describes human
calibration using separate positive-coverage and negative-score results. It
includes illustrative cases, not completed human labels. Evidence must be
verified against the frozen input before scoring. Neither these checks nor a
combined score have been connected to automatic grading.
