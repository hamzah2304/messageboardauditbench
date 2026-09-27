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
