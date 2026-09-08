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
The integrated release branch passes lint and all 1,249 tests, including the
new remote grade corpus. A Docker smoke ran the public ReAct task with a mock
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

1. **Reconcile the Anthropic batch's data version.** Identify which swap revision
   each batch actually consumed. The runner records code and config provenance,
   but the current provenance record does not hash each mounted data file.
   Preserve the historical input and its matching rubric version before
   refreshing shared data, once no active trial is reading it. A current
   checksum alone cannot certify the inputs used by a past run.
2. **Finish ablation grading and matched comparisons.** The archive contains
   7 provider-swap reports at 10 minutes and 24 at 30 minutes; no 120-minute
   provider-swap reports appear in the root report index. Followup counts are
   8 exploratory reports and 79 with the five-minute minimum. The newly fetched
   collaborator commit supplies 79 finding-grade files, 86 summary-grade files,
   and a figure using 70 complete matched pairs. The remote also supplies 3
   finding-grade files and 7 summary-grade files for the 10-minute Anthropic
   cohort; the 30-minute cohort remains ungraded. Finish the missing grades
   with the baseline's judge,
   check partial/refusal/fallback labels, and compare by
   parent budget and model actually served. Do not treat archive counts as
   complete planned cells. The followup figure's prose has been corrected: the
   treatment adds ten minutes and a longer report request, so it does not
   isolate report length. Its numerical results were preserved.
3. **Freeze one public results definition.** The README still leads with rounds
   2 and 3 and their old recall scores. The working blog draft describes round-4
   finding coverage. The default Inspect sheet score is a mean of
   per-finding credit; the figures apply `max(2s - 1, 0)` to each finding before
   averaging.
   That is not a binary fraction of findings scoring above 0.5; the blog draft
   currently describes it as one. Regenerate the final README numbers and
   figures from the chosen
   tracked grades and commit them together with the figure code.
4. **Resolve the existing dirty checkout.** Figure code, draft prose, human TL;DR
   scores, plots, extra report exports and an additional provider-swap plan were
   already modified or untracked. This cleanup preserves that work. Its owners
   need to finish and commit the publication artifacts before a release tag.
5. **Choose the repository license.** No tracked license file or project license
   declaration was found. The maintainers must choose terms and distinguish
   their code from the source data; cleanup cannot decide that on their behalf.

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
