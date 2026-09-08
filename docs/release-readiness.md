# Release readiness, 8 September 2026

The repository can run a normal Inspect eval with the benchmark graders attached.
The release still needs its data versions and published results reconciled.
The engineering changes below close the immediate execution gaps; they do not
establish that the blog's historical comparisons are ready to publish.

## What changed

- Fresh, replay and ReAct continuation tasks default to the existing `v2`
  finding sheets and `tldrh` summary sheet. The older starter rubric is explicit
  (`rubric=legacy`). A grader model role overrides the default Sol judge.
  Task version is now `7-A`; historical grade and prompt bytes are unchanged.
- The fresh task accepts `data_variant=verbatim_anthropic`. Continuations inherit
  the parent's variant. Indexed report grading retains variant metadata and
  selects the swapped answer key per sample; unindexed folders can specify it.
- Continuations accept parent logs whose default Inspect backend was omitted
  from task arguments and reject missing or ambiguous parent epochs.
- Grade export distinguishes fresh eval logs and epochs, and keeps multiple
  rubrics separate even with an explicit output directory. Report staging keeps
  followup parent budgets and epochs distinct and refuses differing overwrites.
- All 118 indexed ablation reports are staged with provenance. Their inventory
  and rebuild/grading commands are in [experiments/ablations.md](../experiments/ablations.md).
- The quick start uses current Inspect arguments. Source builds exclude local
  data symlinks, run archives and credentials.

## Evidence

The pre-change checkout passed lint and 1,064 tests. Added regression checks run
both default graders through Inspect with canned model responses, exercise
Anthropic variant selection, parent validation, and export collision handling.
After integration with current main, the release branch passes lint and all
1,532 tests, including the expanded grade corpus. A Docker smoke ran the public ReAct task with a mock
agent writing `report.md`
and both mock graders completing in the same `.eval` log. This checks the
sandbox-to-report-to-grader path without paid calls. It does not validate live
provider behavior or re-test the Claude Code and Codex model bridges.

The wheel and source archive build successfully. The archive contains the
configs, Docker runtime, original sheets and Anthropic sheets, with no symlinks.
The wheel still requires a checkout for runtime and grading assets; this is
explicit in the setup instructions.

`build_data.sh --verify` passed all eight original/verbatim files and failed all
four local Anthropic-swapped files. Rebuilding only the swapped variant into a
temporary directory reproduced all four committed digests exactly. The shared
local variant is therefore stale relative to the current code and manifest.
It was not overwritten during this audit.

## Work remaining before publishing the blog

1. ~~**Reconcile the Anthropic batch's data version.**~~ Resolved for everything
   staged and graded, and the gap that raised it is closed going forward.

   The batch: `benchmark/rubrics/anthropic/VERSION.json` hashes the
   `scripts/swap_provider.py` that built the data its answer key grades against,
   and that hash matches the current file. Its own note names the three batches
   that ran on the earlier build rendering the OAI shorthand as `Claude`
   (`20260908T113359Z`, `130708Z`, `132526Z`); none of the three appears in any
   staged or graded set. The staged reports agree: across all 88
   Anthropic-variant reports, `/home/ant/` and the post-change misspelling
   `Antropic` occur and `/home/oai/` and `/home/claude/` do not, and the runs
   began at 14:50, after the 14:47 rule change. That is inference from quoted
   tokens rather than certification — `ablation_anthropic_b30` quotes no paths
   either way — but no evidence of a stale build survives in the corpus.

   The gap: run records named the variant but hashed no data file, so `data/`,
   a gitignored build output, could be older than the code committed beside it.
   Both runners now record `data_files_sha256`, the resolved `data_dir`, and a
   `data_manifest_status` checking those digests against
   `data/SHA256SUMS.variants`, so a future run says for itself whether it read
   the manifest's data.

   Still worth doing: whichever checkout failed `build_data.sh --verify` during
   the audit should rebuild `data/verbatim_anthropic` before launching further
   Anthropic-setting trials. Past runs are unaffected; the next one would not be.
2. **Check ablation grading and matched comparisons.** Since the initial audit,
   collaborators have exported the complete provider-swap round and added
   grades. Use the current tracked report indexes and grade files to establish
   completeness rather than the initial archive counts. The followup figure now
   uses 78 matched finding-grade pairs. Check partial/refusal/fallback labels,
   and compare by parent budget and model actually served. The followup adds
   ten minutes and a longer report request, so it does not isolate report length.
3. **Freeze one public results definition.** The README no longer publishes
   results at all: the rounds 2 and 3 tables were removed and it now points here
   and to the tracked grades, so the definition below has to be settled for the
   blog rather than for the README. The working blog uses a 70/30 combination of round-4 finding coverage
   and holistic TLDR assessment. The default Inspect sheet score is a mean of
   per-finding credit; the figures apply `max(2s - 1, 0)` to each finding before
   averaging.
   That is not a binary fraction of findings scoring above 0.5. Regenerate the final published numbers and
   figures from the chosen
   tracked grades and commit them together with the figure code.
4. **Resolve the existing dirty checkout.** Figure code, draft prose, human TL;DR
   scores, plots, extra report exports and an additional provider-swap plan were
   already modified or untracked. This cleanup preserves that work. Its owners
   need to finish and commit the publication artifacts before a release tag.
5. ~~**Choose the repository license.**~~ Done: the maintainers chose MIT, and
   `LICENSE` now distinguishes the code and benchmark material authored here
   from the third-party content reproduced for research (the `corpus/` exports,
   the human investigators' report, and the model-generated reports). The
   README carries a matching summary.

The current sheet scorer records partial grader failures but still emits a
numeric score over surviving sheets. Publication aggregation must check its
failure metadata; making incomplete grading categorically unscored would be a
separate grading-policy change. A real provider smoke remains advisable before
advertising the current CLI/model combinations as verified.

## Official Inspect listing is a separate step

A clone-based Inspect task does not need to be listed to run. The current
[Inspect Evals Register guide](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/README.md)
requires pinned external assets, an arXiv URL, a source commit, and full eval
logs from two models. The current collusion.wiki download has a checksum but
not an immutable project-controlled URL. Resolve the asset hosting and paper,
then submit against the final public commit and provide the two logs. These
requirements need not block a blog that accurately describes a directly
runnable repository rather than claiming an official listing.
