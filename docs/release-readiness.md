# Publication snapshot status

The repository runs as a normal Inspect eval with both benchmark graders
attached. The blog snapshot retains round 4, the followup and provider-swap
ablations, current figures, and grader-validation evidence. Historical rounds
and prototypes are accessible at the `inspect-logs-2026-09-08` tag.

## Verified

- Fresh, replay, and ReAct continuation tasks default to `v2` and `tldrh` grading.
  A grader model role overrides the default judge. `--no-score` defers grading.
- Provider-swapped inputs select the matching answer key; continuation tasks
  preserve parent variants and validate the selected epochs.
- Exports distinguish logs, epochs, rubric variants, and continuation parents.
- The snapshot passes lint and 1,303 tests. Each retained grade is reaggregated
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

### 1. Run one graded eval and one Docker trial from a fresh clone — assigned

On a machine with provider credentials and Docker running:

```sh
git clone https://github.com/hamzah2304/messageboardauditbench fresh && cd fresh
uv sync --frozen && scripts/build_data.sh && scripts/doctor.sh
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=blind -T time_limit_minutes=10 \
  --model openai/gpt-5.6-sol --model-role grader=openai/gpt-5.6-sol
```

That single command covers both: it builds the Docker sandbox and grades the
report it produces. Keep the old checkout until this passes and item 2 is done.

Everything that does not need credentials has already been checked from a clone
of `main` into an empty directory: `uv sync --frozen`, `ruff check .`, the full
suite (1,324 passing), `uv build`, task discovery by package name,
`scripts/doctor.sh`, and `scripts/score_reports.py` over the shipped grades.
`doctor.sh` correctly named the only two things missing on a bare machine,
Docker and an unbuilt `data/`.

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
