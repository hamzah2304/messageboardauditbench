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
| `9-A` | The September 26 report feedback and word-count rule. |
| `10-A` | New `messageboard_audit_bench` runs from this checkout, after the URLQuery merge changed the shared runtime policy and ReAct error handling (below). |

The version is declared once per benchmark in `messageboard_audit_bench/benchmarks.py`
(`SPECS`); `EVAL_VERSION` in `messageboard_audit_bench/task.py` re-exports the
message-board one and is assigned to the fresh, replay, and continuation Inspect tasks. It identifies task behavior, not a result release.
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

`10-A` is warranted by the September 28 unification with the URLQuery benchmark.
The shared runtime policy now counts only an explicit refusal of the task, or a
terminal status such as `error` or `refused`, as a reason to stop. Before, any
mention of "error", "fail" or "I can't" in a status field or the final message counted.
That changes when an agent that stops early is sent back to work. The ReAct scaffold now
also stops on a provider error returned inside an HTTP 200 response, instead of
continuing on it. Prompts, data, rubrics and the judge are unchanged.

## URLQuery

`urlquery_audit_bench` is a separate Inspect task with its own version, declared in
the same registry. Its conditions (dataset snapshot and hash, configs, rubric, headline
weights and default judge) are in `benchmarks/urlquery/benchmark.json`.

| Inspect task version | What it identifies |
|---|---|
| `1-A` | The first Inspect version of the URLQuery task: snapshot `2026-09-26-v1`, prompt `urlquery-agents-v6`, reviewed rubric F1–F13 with F3 weighted 0.5. The final 2026-09-27/28 generation runs used the same prompt, configs and dataset through the batch launcher (`urlquery_pilot`), before the task existed; their run records carry no task version and say `rubric_version: null`, `scoring_status: "unscored_pending_manual_rubric"`. Runs from `1-A` on record `benchmark_version: "1-A"`, `rubric_version: "reviewed"` and `scoring_status: "ungraded"`; filter on the version, not on those labels. |
