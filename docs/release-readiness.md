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

## Checks still required before deleting the local checkout

1. Test setup and a graded eval in a separate fresh clone. Keep the old checkout
   until its private state is backed up and the fresh-clone test passes.
2. Preserve local historical input variants and legacy raw runs privately.
   An earlier audit found that the local Anthropic variant differed from the
   committed manifest. Rebuilding reproduced the committed hashes, but that
   does not establish which bytes every historical batch consumed. For the
   retained corpus the evidence now points one way:
   `benchmark/rubrics/anthropic/VERSION.json` hashes the `swap_provider.py`
   that built the data its answer key grades, and that hash matches the current
   file; its note names the three batches that ran on the earlier build
   (`20260908T113359Z`, `130708Z`, `132526Z`), none of which appears in any
   staged or graded set; and across the Anthropic-variant reports `/home/ant/`
   and the post-change misspelling `Antropic` occur while `/home/oai/` and
   `/home/claude/` do not. That is inference from quoted tokens, not
   certification. Going forward both runners record `data_files_sha256`, the
   resolved `data_dir`, and a `data_manifest_status` against
   `data/SHA256SUMS.variants`, so a run states for itself whether it read the
   manifest's data. Rebuild the local variant before any further
   Anthropic-setting trial.
3. Confirm the blog uses the current 70/30 combined score and labels incomplete
   cells and model fallbacks. Inspect's raw sheet mean differs from the stricter
   per-finding publication transform.

The sheet scorer records partial grader failures and emits a numeric score over
surviving sheets. Publication aggregation must inspect that failure metadata.
The wheel currently requires a checkout for runtime and grading assets, as
explained in the setup instructions.

Official Inspect Evals registration is separate from a directly runnable task;
see [the registration notes](inspect-evals-registration.md).
