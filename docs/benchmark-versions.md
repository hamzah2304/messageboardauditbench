# Benchmark versions and the LessWrong results

The [LessWrong post, “How good are slop-vestigators?”](https://www.lesswrong.com/posts/wt4kk6vFPEhkXvF8Q/how-good-are-slop-vestigators)
reports the collusion.wiki round 4 results and the longer-report and
provider-swap followups. Their archived generation logs record Inspect task
version **`6-B`**. This is the run version, even though the repository moved to
later versions while the results were being graded and packaged.

| Inspect task version | What it identifies |
|---|---|
| `6-B` | The September 7–8 round 4, followup, and provider-swap generation runs used in the LessWrong analysis. |
| `7-A` | The September 8 code after inline benchmark grading was added. The `inspect-logs-2026-09-08` Git tag points to this later code snapshot; the archived runs themselves still say `6-B`. |
| `8-A` | Introduced with the September 11 Mythos 5 transfer incident and retained through later changes, including RubyHack and the September 26 report-count changes. It did not define the LessWrong generation runs. |
| `9-A` | New Inspect runs from this checkout. It separates the revised report feedback and word-count rule from earlier runs. |

The version is declared once as `EVAL_VERSION` in
`messageboard_audit_bench/task.py` and assigned to the fresh, replay, and
continuation Inspect tasks. It identifies task behavior, not a result release.
The incident, budget, data variant, prompt, judge, and rubric remain separate
conditions. A score is comparable to a published cell only when those conditions
and the scoring procedure also match.

The archived logs provide direct evidence for the LessWrong run version: the
`task_version` field is `6-B` in the local round 4, followup, and provider-swap
cohorts. Their `revision.commit` fields vary across runs, so there is no single
source commit for every generation run. The [Inspect log archive](artifacts/inspect-logs.md)
and [publication evidence index](benchmark-data-index.md) map selected reports
to logs and the separately retained Fable 5.1 `v2` and `tldrh` grades. The
published headline combines those grades at 70% finding coverage and 30%
holistic TLDR assessment. The Git tag is a way to retrieve the experiment
snapshot; it should not be substituted for the version in each log.
Because `8-A` was retained through behavior changes, use a log's Git revision
and prompt provenance to distinguish runs made during that interval.

## Rule for future changes

Bump `EVAL_VERSION` before collecting results when a change can affect what an
agent sees, what it can do, whether its report is accepted, or how the default
task grades it. Record the reason here and keep the previous logs and grades
under their original version. A new incident or rubric can share task code,
but its results need their own incident and rubric identifiers. For a reportable
result, retain the `.eval` log or equivalent provenance: Inspect task version,
Git revision and dirty status, rendered prompt, corpus digests, budget, model,
scaffold, judge, and rubric. Code-only refactors that preserve behavior do not
require a bump.

`9-A` is warranted by the September 26 changes: agents now receive report and
TLDR counts after report edits, the prompt describes that feedback, and complete
inline Markdown links are excluded from the report word count. Those changes
alter both the agent's information and the acceptance calculation. The revised
count method is also recorded as `whitespace-no-inline-links-v2` in report
metadata.
