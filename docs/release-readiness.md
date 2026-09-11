# Publication snapshot status

The repository runs as a normal Inspect eval with both benchmark graders
attached. The blog snapshot retains round 4, the followup and provider-swap
ablations, current figures, and grader-validation evidence. Historical rounds
and prototypes are accessible at the `inspect-logs-2026-09-08` tag.

## Verified

- Wiki fresh, replay, and ReAct continuation tasks default to `v2` and `tldrh` grading.
  A grader model role overrides the default judge. `--no-score` defers grading.
- Provider-swapped inputs select the matching answer key; continuation tasks
  preserve parent variants and validate the selected epochs.
- Exports distinguish logs, epochs, rubric variants, and continuation parents.
- The snapshot passes lint and 1,324 tests. Each retained grade is reaggregated
  and checked against its stored result. The test count is lower than before
  cleanup because historical grade files no longer generate test cases.
- The headline, combined-score, and followup figure builders succeed using only
  retained inputs. Their result data are unchanged by the cleanup.
- The [log release](artifacts/inspect-logs.md) contains 111 Inspect logs, checksums,
  and report-to-log mappings. It is pinned to the pre-cleanup source commit.
- The earlier engineering audit built a wheel and source archive and ran a
  Docker smoke with a mock agent and both mock graders in one Inspect log.
  This was not a live-provider or clean-clone end-to-end test.

## What is left before the release is done

Three things, each with the action first. When all three are done, delete this
file — the last section says how.

### 1. Run a graded Docker eval from a fresh clone — passed

Verified on 2026-09-08 in the separate `messageboardauditbench-clean` clone at
`11ff63c`, using the existing local `.env` and Docker installation:

```sh
uv sync --frozen
scripts/build_data.sh --verify
uv run --env-file .env inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=blind -T time_limit_minutes=5 -T min_runtime_fraction=0 \
  --model openrouter/openai/gpt-5.6-sol \
  --model-role grader=openrouter/openai/gpt-5.6-sol \
  --epochs 1 --max-samples 1 --max-connections 2 --max-retries 2 \
  --log-dir logs/release-smoke
```

The eval completed in 8 minutes 38 seconds with a 2,535-word report. All eight
`v2` finding sheets and the one `tldrh` summary sheet graded successfully;
both failure dictionaries were empty, with no eval or sample error. Raw Inspect
scores were 0.405 and 0.800. This is a setup test, not a publication result.
The log records matching dataset hashes and `network_none` isolation.

The local log in that clone is
`logs/release-smoke/2026-09-08T22-10-08-00-00_messageboard-audit-bench_XvvPsZ2zudQdQeXkKcTzCN.eval`.
It is not part of the published log release. An initial one-minute attempt
completed all grading calls but produced no report, so it did not count as a
passing end-to-end test.

`uv sync --frozen`, data checksum verification, lint, and all 1,324 tests passed
in this clone. The smoke reused cached Docker image layers; it does not verify
an uncached image download. `doctor.sh --verify` also passed after pulling
`881d0a5`, which fixes the preflight to check the project's Python rather than
reject a working uv setup because the system Python is older.

The earlier empty-directory check also passed `uv build`, task discovery by
package name, and `scripts/score_reports.py` over the shipped grades.
Keep the old checkout until item 2 is done.

### 2. Copy the historical inputs and legacy runs off that machine — open

This is the only item whose window closes. Everything else can be done later; a
local disk that dies takes this with it.

**Do:** from the primary checkout, copy to private storage, before rebuilding
anything:

- `data/` — the historical variant builds, in particular the
  `verbatim_anthropic` build that the trials actually read
- `runs/` — the legacy subscription CLI transcripts

**The published release does not cover either.** `inspect-logs-2026-09-08`
publishes the native Inspect `.eval` logs for round 4, the provider swap and
both followup cohorts — the retained corpus. Both directories above are
gitignored and local, so neither that release nor Git preserves them.

**Then rebuild** `data/verbatim_anthropic` before any further Anthropic-setting
trial: an audit found the local build differing from the committed manifest.

Background, if you need it. Rebuilding reproduced the committed hashes, but that
does not by itself establish which bytes every historical batch consumed. For
the retained corpus the evidence points one way:
`benchmark/rubrics/anthropic/VERSION.json` hashes the `swap_provider.py` that
built the data its answer key grades, and that hash matches the current file;
its note names the three batches that ran on the earlier build
(`20260908T113359Z`, `130708Z`, `132526Z`), none of which appears in any staged
or graded set; and across the Anthropic-variant reports `/home/ant/` and the
post-change misspelling `Antropic` occur while `/home/oai/` and `/home/claude/`
do not. That is inference from quoted tokens, not certification. Going forward
both runners record `data_files_sha256`, the resolved `data_dir`, and a
`data_manifest_status` against `data/SHA256SUMS.variants`, so a run states for
itself whether it read the manifest's data.

### 3. Proofread the post — mostly confirmed

The 70/30 headline is confirmed: the post states it, and the README and
`scripts/score_reports.py` define and compute it. Two things left to check in
the post itself:

- incomplete cells and model fallbacks are labelled, so an Opus fallback is not
  read as a single-model result;
- no figure quotes Inspect's raw sheet mean, which runs well above the strict
  per-finding transform the headline uses.

### When all three are done

```sh
git rm docs/release-readiness.md
```

Then remove the two links to it, in `README.md` and `docs/getting-started.md`.
Nothing durable is recorded only here: the partial-grader-failure caveat is in
the README's grading section, and the wheel's need for a checkout is in the
setup instructions.

Official Inspect Evals registration is separate from a directly runnable task;
see [the registration notes](inspect-evals-registration.md).
