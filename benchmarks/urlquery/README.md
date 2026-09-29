# URLQuery benchmark

An agent investigates a frozen snapshot of urlquery.net scans that Transluce linked
to autonomous agent activity, and writes a report. A judge scores the report against
13 reviewed headline findings. This directory holds the evaluator-only material:
the manifest, the findings rubric and the judge. Nothing here is mounted into a trial.

The benchmark shares the original MessageBoardAuditBench harness and differs only
where its evidence does. The shared parts are the config format, prompt rendering,
the Inspect-native sandbox and agents, the subscription runner
(`sandbox/docker/run_trial.sh`) and the grading plumbing. The URLQuery-specific parts
are listed in [`benchmark.json`](benchmark.json):

- **Dataset:** one hash-pinned snapshot, `2026-09-26-v1`, in the primary checkout's
  gitignored `data/urlquery/`.
- **Configs:** the active trial configs, `urlquery-agents-v6-30` (default) and
  `urlquery-agents-v6-10`, which use the prompt
  `sandbox/prompts/urlquery-agents-v6.txt`.
- **Rubric and judge:** the reviewed findings rubric and judge prompt, the
  headline weights, and the default judge.

`messageboard_audit_bench.benchmarks` reads the manifest. The Inspect task version,
`1-A`, lives there too; see [the version history](../../docs/benchmark-versions.md).

## Run trials

A single trial goes through Inspect, like the original benchmark:

    uv run inspect eval messageboard_audit_bench/urlquery_audit_bench \
      -T agent=codex -T backend=subscription -T subscription_model=gpt-6-astra
    uv run inspect eval messageboard_audit_bench/urlquery_audit_bench \
      -T agent=claude --model anthropic/claude-opus-5-5          # Inspect-native, no network

With `backend=subscription`, the runner installs the exact CLI versions the config pins
and checks the mounted snapshot against the pinned hash inside the container. With
`backend=inspect`, the no-network sandbox builds the image with the same pinned CLI
versions, disables the same Codex features, and runs the same manifest check before the
agent starts.

Model matrices go through the batch launcher. It runs every trial through the same
`run_trial.sh`, and it adds per-subscription queues, a stop on authentication or capacity
failure, fail-closed validation of each run record, and a `plan.json` per arm:

    uv run python -m messageboard_audit_bench.urlquery_pilot --batch configs/urlquery-final-batch.toml          # plan only
    uv run python -m messageboard_audit_bench.urlquery_pilot --batch configs/urlquery-final-batch.toml --launch

`--dataset` defaults to the manifest's snapshot. Retired configs and prompts are kept
in `configs/superseded/` and `sandbox/prompts/superseded/` so older runs stay
reproducible. They are not Inspect conditions.

## Grade

The canonical rubric is `claims/findings_reviewed.json`: 13 headline findings and 51
sub-findings. F1–F12 incorporate the data and fairness audits. F13 is the separately
sourced header-injection finding, recorded in `claims/header_injection.json`.

The judge prompt is `judge/finding_sheet_reviewed.md`. The judge scores one headline
finding and its sub-findings per call. The headline gets a score from 0 to 1 in tenths,
and each sub-finding a score from 0 to 1 in quarters. The report score is the mean over
headlines, with F3 weighted 0.5 because it synthesises F4–F6. Grade files record the
unweighted mean too.

A refusal, a truncated or unparseable answer, or an API error leaves that finding
unscored. It is never recorded as zero. If the judge refuses the first headline, the
report's remaining headlines are skipped. The model report that suggested F13 is not
treated as evidence in its prompt.

The prompt and arithmetic are `messageboard_audit_bench.grading.findings`. Two entry
points share them:

- **Inspect.** `urlquery_audit_bench` scores each fresh trial. `urlquery_grade_reports`
  grades finished run directories:

      uv run inspect eval messageboard_audit_bench/urlquery_grade_reports \
        -T launch=runs/urlquery/final-20260927-agents-v6/launch.json \
        -T judge=openrouter/openai/gpt-6-astra

- **Batch grader.** `judge/grade.py` makes resumable, synchronous API calls and writes
  one grade file per report to the gitignored `reports/urlquery/graded/judge_<model>/`.
  Every file carries the prompt, rubric, article and report hashes. A rerun reuses a
  grade only when all of these match.

      uv run python benchmarks/urlquery/judge/grade.py \
        --launch runs/urlquery/final-20260927-agents-v6/launch.json --workers 8

### Choosing the judge

`judge` is any `anthropic/<model>` or `openrouter/<model>`:

The article context defaults by transport (`--article` or `article_context` overrides
it). A grade directory never mixes contexts: the batch grader refuses to overwrite a
file graded with a different article.

- **Default: `anthropic/claude-opus-5-5`** at effort xhigh, with the article omitted.
  The full source article made this judge refuse. With the article omitted, it still
  reads the reviewed finding, the article's quote excerpts and the scoring notes, and
  each grade's article hash records which context it saw.
- **Final 2026-09-27 run: GPT-6 Astra** at high effort with the full article
  (`openrouter/openai/gpt-6-astra`). OpenRouter refusals are retried on the next run. `judge/grade_openrouter.py` is a preset of
  `grade.py` for it.

For the final run:

- The original 48-report F1–F12 regrade is in `judge_gpt_6_astra_high_fairness_v2/`.
- F13 was judged alone in `judge_gpt_6_astra_high_f13_only/`.
- `judge/combine_f13_grades.py` merged the two into `judge_gpt_6_astra_high_fairness_v3/`
  without changing the earlier 576 judgments.

To reproduce:

    uv run python benchmarks/urlquery/judge/grade_openrouter.py \
      --launch runs/urlquery/final-20260927-agents-v6/launch.json \
      --findings F13 --output reports/urlquery/graded/judge_gpt_6_astra_high_f13_only
    uv run python benchmarks/urlquery/judge/combine_f13_grades.py

The first Opus grades (four reports, 48 calls, 2026-09-27) used the draft v1 rubric. Their
`score_mean` is unweighted. Grade files written from now on also record
`headline_weights` and `score_mean_unweighted`.

Validate grades by hand with `viewers/build_urlquery_audit_ui.py`. It builds a local
page, or with `--artifact PATH` a shared, redacted claude.ai page whose audits save per
auditor. `viewers/build_urlquery_scoring_audit_ui.py` renders the fairness audit.

## How the findings were built

The rubric's lineage is kept in `claims/`:

1. `findings_v1.json` merges three annotators' extractions into 12 findings and 53
   sub-findings (`build_findings_v1.py`).
2. `findings_v2.json` applies the first review (`derive_findings_v2.py`).
3. `findings_reviewed.json` adds the data and fairness audits and F13.

The pre-fairness snapshot is in `superseded/`. `negative_findings.md` lists the
overclaims a report should be penalised for. See
[`docs/findings-authoring-process.md`](../../docs/findings-authoring-process.md).

Candidate findings come from the inert Transluce article:

1. Extract candidates in `viewers/urlquery_findings.html`, which
   `viewers/build_urlquery_findings.py` builds.
2. Write the candidates to `claims/new_claims.json`. Each one records its verbatim
   source quote, the source/report hash and the exact frozen dataset hash. Approve them
   in `viewers/build_new_claims_ui.py --benchmark urlquery`.
3. Check each candidate against the frozen agent input only, and record the result in
   `feasibility/feasibility.json` (`viewers/build_feasibility_ui.py --benchmark urlquery`).

The original benchmark's rubrics never grade URLQuery reports, and URLQuery's judge never
grades message-board reports. The grading entry points reject cross-benchmark input.

Raw downloads, the annotated catalog and acquisition audits live once in the primary
checkout's gitignored `data/transluce/`. The frozen agent files are in
`data/urlquery/<version>/`, with their evaluator-only provenance sidecar next to them,
outside the mount. See the
[preprocessing documentation](../../docs/urlquery-engineering.md).
