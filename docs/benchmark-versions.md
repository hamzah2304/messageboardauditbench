# Benchmark versions

The repository holds three benchmarks, each a separate Inspect eval with its own version.
Each version is a git tag, and one flag runs any tagged version. The published LessWrong
results were run at German wiki report version `6.1` (labelled `6-B` at the time).

| benchmark | Inspect task | current version | storage id |
|---|---|---:|---|
| German wiki report | `german_wiki_report` | `10.0` | `messageboard` |
| Transluce report | `transluce_report` | `1.0` | `urlquery` |
| AI Village report | `aivillage_report` | `1.0` | `aivillage` |

The storage id is what run records, configs and grade files write as `benchmark_id`. It
predates the public names and does not change. The tasks were called
`messageboard_audit_bench` and `urlquery_audit_bench` before 2026-09-29, and the Python
package was `messageboard_audit_bench` until 2026-10-21, so the tasks were
`messageboard_audit_bench/german_wiki_report` and so on. `scripts/run_eval.py --version`
uses whichever package and task names the tagged version had.

## What a version means

A version is `MAJOR.MINOR` and names the behaviour of the task code: what the agent
sees, what it can do, whether its report is accepted, and how the default grading scores
it.

- **MAJOR** goes up when a change can make results incomparable with earlier runs.
- **MINOR** goes up for a change that keeps results comparable, such as a renamed option
  or a new optional feature.

Code-only refactors that preserve behaviour need no bump. The version is declared once
per benchmark, in `SPECS` in `slopvestigator_bench/benchmarks.py`. Every Inspect log
records it as the task version.

The version does not pin everything a score depends on. The config (budget, prompt, data
variant, effort), the model, the judge and the rubric are separate conditions. A score is
comparable to a published cell only when the version and those conditions all match.

## Running a specific version

Use `scripts/run_eval.py`. Everything after `--` goes to `inspect eval`:

```bash
# this checkout's version (the task's own version guard confirms it)
uv run python scripts/run_eval.py german-wiki-report -- -T agent=codex --model openai/gpt-5.6-sol

# an earlier version, from its tag
uv run python scripts/run_eval.py german-wiki-report --version 9.0 -- -T agent=codex --model openai/gpt-5.6-sol

# grade, replay or continue at a version
uv run python scripts/run_eval.py transluce-report --version 1.0 --task grade -- -T launch=runs/urlquery/<final>/launch.json

uv run python scripts/run_eval.py german-wiki-report --list        # tagged versions
uv run python scripts/run_eval.py german-wiki-report --version 8.0 --dry-run -- ...
```

**This version.** The eval runs in this checkout, with `-T version=<MAJOR.MINOR>` added.

**Any other version.** The launcher checks the tag `<benchmark>-v<version>` out, detached,
into `.worktrees/version-<tag>/`. It gives the checkout its own `.venv` and links in the
primary checkout's `data/`, `runs/`, `logs/` and `.env`, so the old code reads the same
inputs and writes to the same archive. The checkout is created once and reused.
Versions before `10.0` / `1.0` predate the task rename and the version guard; the
launcher uses the task name that version had.

**The version guard.** You can pass `-T version=` directly to `german_wiki_report` or
`transluce_report`. The task refuses to start if the checkout is a different version, and
the error names the command to run instead. `10`, `10.0`, `v10.0` and the old label
`10-A` all mean `10.0`.

## German wiki report

The [LessWrong post, "How good are slop-vestigators?"](https://www.lesswrong.com/posts/wt4kk6vFPEhkXvF8Q/how-good-are-slop-vestigators)
reports the collusion.wiki round 4 results and the longer-report and provider-swap
followups. Their archived generation logs record Inspect task version `6-B`, now `6.1`.
That is the run version, even though the repository moved to later versions while the
results were being graded and packaged.

The old labels were `<major>-<letter>`, and they convert one-to-one: letter A is minor 0,
B is minor 1. Each tag points at the last commit that carried its version.

| version | old label | tag (commit) | What it identifies |
|---|---|---|---|
| `6.1` | `6-B` | `german-wiki-report-v6.1` (`45350ea`) | The September 7–8 round 4, followup and provider-swap generation runs used in the LessWrong analysis. |
| `7.0` | `7-A` | `german-wiki-report-v7.0` (`438392c`) | The September 8 code after inline benchmark grading was added. The older `inspect-logs-2026-09-08` tag also points into this version; the archived runs themselves still say `6-B`. |
| `8.0` | `8-A` | `german-wiki-report-v8.0` (`d347133`) | Introduced with the September 11 Mythos 5 incident and kept through later changes, including RubyHack and the September 26 report-count changes. It did not define the LessWrong runs. |
| `9.0` | `9-A` | `german-wiki-report-v9.0` (`e52e499`) | The September 26 report feedback and word-count rule. |
| `10.0` | `10-A` | `german-wiki-report-v10.0` | The shared runtime changes merged with the Transluce report (below). Also the task rename and version flag, which do not change behaviour. |

The archived logs provide the direct evidence for the LessWrong run version: the
`task_version` field is `6-B` in the local round 4, followup, and provider-swap cohorts.
Their `revision.commit` fields vary across runs, so no single source commit covers every
generation run. The `v6.1` tag is the last `6-B` commit, a way to rerun that behaviour. It
should not be substituted for the revision in each log.

The [Inspect log archive](../benchmarks/german-wiki/docs/artifacts/inspect-logs.md) and the
[publication evidence index](../benchmarks/german-wiki/docs/benchmark-data-index.md) map selected reports to logs and
to the separately retained Fable 5.1 `v2` and `tldrh` grades. The published headline
combines those grades at 70% finding coverage and 30% holistic TLDR assessment.

`8.0` was kept through behaviour changes, and its tag holds only the last of them. To
tell apart runs made during that interval, use each log's Git revision and prompt
provenance.

### Why each bump

**`9.0`.** Agents now receive report and TLDR word counts after every report edit, and
the prompt describes that feedback. Complete inline Markdown links no longer count
towards the report word count. These changes alter both what the agent is told and the
acceptance calculation. The revised count method is recorded as
`whitespace-no-inline-links-v2` in report metadata.

**`10.0`.** The runtime policy shared with the Transluce report changed in two ways:

- **Stop rule.** The runtime policy decides when an agent that stops early is sent back
  to work. It now treats only two things as a reason to stop: an explicit refusal of the
  task, or a terminal status such as `error` or `refused`. Before, any mention of
  "error", "fail" or "I can't" in a status field or the final message counted.
- **ReAct errors.** The ReAct scaffold now stops on a provider error returned inside an
  HTTP 200 response, instead of continuing.

Prompts, data, rubrics and the judge are unchanged. Two further changes in `10.0` do not
alter behaviour:

- The task was renamed from `slopvestigator_bench`.
- The Mythos 5 and RubyHack drafts are no longer selectable as configs; they are drafts
  for separate evals.

For a short while on 2026-09-28 the code said `10-A`, with the old task name and
identical behaviour.

## Transluce report

The conditions are in `benchmarks/transluce/benchmark.json`: dataset snapshot and hash,
configs, rubric, headline weights and default judge.

| version | old label | tag | What it identifies |
|---|---|---|---|
| `1.0` | `1-A` | `transluce-report-v1.0` | The first Inspect version: snapshot `2026-09-26-v1`, prompt `urlquery-agents-v6`, reviewed rubric F1–F13 with F3 weighted 0.5. |

**The final run.** The final 2026-09-27/28 generation runs used the same prompt, configs
and dataset. They went through the batch launcher (`urlquery_pilot`) before the task
existed, so their run records carry no version. They also say `rubric_version: null` and
`scoring_status: "unscored_pending_manual_rubric"`.

**New run records.** Runs from this version record `benchmark_version: "1.0"` (`"1-A"`
for the few made before the rename), `rubric_version: "reviewed"` and
`scoring_status: "ungraded"`. Filter on the version, not on those labels.

## AI Village report

The conditions are `configs/aivillage-v12-30.toml` and its `-subagents` twin, the
rubric `benchmarks/aivillage/findings/final-findings.json` (96 findings) and
the judge prompt `judge-prompt-v8.txt`, judged by GPT-6.1 Sol at medium effort.

| version | tag | What it identifies |
|---|---|---|
| `1.0` | `aivillage-report-v1.0` | The first Inspect version: prompt `aivillage-v12`, 30 minutes, data `aivillage/full-v2-reasoning`, score = mean of the 20 best finding scores. |

**The published runs.** The 34 reports in `benchmarks/aivillage/results/` ran
through the subscription runner before the task existed and were graded by
`scripts/aivillage/grade_aivillage.py`. The task sends the same judge requests; its native
backend gives the agent the same prompt, but not the subscription CLIs' logins.

## The standard rerun (version number to be set at the rerun)

The standard condition (`configs/standard.toml`, launched by `scripts/run_matrix.py`) changed on
2026-10-22. These changes belong to the version the rerun will carry; Oscar sets its number at
the rerun. The published versions above are unchanged and stay reproducible from their tags and
configs.

- **German wiki prompt.** `wiki-std-10` and `wiki-std-30` now use `wiki-v3`: a ranked list of
  findings, the AI agents named, 4,500–5,500 words (accepted up to 6,050). They used `blind-v2`
  at 2,500–3,000 words before, under the same config names.
- **Every standard config's hash changed.** All six generated configs (`wiki`, `urlquery`,
  `aivillage` at 10 and 30 minutes) gained `safeguard_retry_limit` and
  `safeguard_retry_message`, so each has a new `config_sha256`. `scripts/run_matrix.py` and
  `slopvestigator_bench/results.py` count a run only if its recorded `config_sha256` matches
  today's config (`standard.same_condition`): standard runs made under the 2026-10-21 configs,
  on any machine, are left out of the results and would be launched again. Filter on
  `config_sha256`, not the config name. The hashes (old at `68ec9dc`, new from 2026-10-22):

  | config | 2026-10-21 | 2026-10-22 |
  |---|---|---|
  | `wiki-std-10` | `9511526e…` | `8272d310…` |
  | `wiki-std-30` | `be7ee858…` | `ac285969…` |
  | `urlquery-std-10` | `e58f28c1…` | `539755fb…` |
  | `urlquery-std-30` | `837c8091…` | `c2a2c571…` |
  | `aivillage-std-10` | `57792f60…` | `6c5d0f23…` |
  | `aivillage-std-30` | `50a55cd7…` | `5f3ec319…` |

  List them with `git show <commit>:configs/<name>.toml | sha256sum` (old) and
  `sha256sum configs/*-std-*.toml` (current); a run records the full hash in `meta.json`.
- **Judge.** Every Inspect grader and scorer defaults to the standard judge, `openai/gpt-6.1-sol` at high effort
  (`standard.toml` `judge`, `judge_effort`): the German wiki sheets (published with Fable 5.1;
  the code default was GPT-5.6 Sol), the Transluce per-finding judge (v1.0 grades: GPT-6 Astra
  through OpenRouter; code default Opus 5.5) and AI Village (GPT-6.1 Sol at medium). Grades
  from the new judge are not comparable with published ones; reproduce a published number at
  its tag with its judge (`scripts/run_eval.py --version <MAJOR.MINOR>` now runs a tagged
  version from its tag even when this checkout carries the same version number). The
  exceptions reproduce published grades and keep their judges:
  `scripts/aivillage/grade_aivillage.py`, the AI Village batch grader (GPT-6.1 Sol at medium,
  checked by its frozen v1.0 plans), and the Transluce presets
  `benchmarks/transluce/judge/grade_openrouter.py` and `grade_openai_batch.py` (GPT-6 Astra,
  high).
- **Safeguard retries.** A turn that Claude's real-time safeguards flag (an intermittent API
  error, `[cyber]`) is retried by continuing the session, up to three times per run
  (`safeguard_retry_limit`); the next flag ends the run as a refusal. Runs record
  `safeguard_retries` next to `safety_flags`, and a run that survived its flags is eligible.
  Before, the first flag that ended a turn ended the run. Configs without the setting (the
  published ones) keep the old stop logic exactly. Separately, for every config and every
  refusal category, a refusal event that the agent worked past (more tool results or model
  turns follow it) no longer marks the run a refusal.
- **Inspect runs** take the config's minimum-runtime fraction (0.9) instead of the task's
  0.75 default, and native Codex with subagents off gets the stripped model catalog, as the
  runner does.
- **Memory note.** The German wiki and Transluce prompts no longer tell the agent to query
  `village.db`, which only the AI Village data has.
- **Lineup.** Gemini 3.8 Flash is dropped (13 models).

The AI Village tag `aivillage-report-v1.0` points at `68ec9dc`, the last commit before these
changes (a local tag until it is pushed).

## Releasing a new version

1. **Bump.** Change the version in `SPECS` before collecting results with the new code.
2. **Record why.** Add a row and a "why" paragraph here.
3. **Tag.** Tag the commit that ships it as `<benchmark>-v<version>`, then push the tag
   (`git push origin <tag>`).
4. **Keep the old runs.** Keep earlier logs and grades under their original version.

For a reportable result, keep the `.eval` log or equivalent provenance: benchmark
version, Git revision and dirty status, rendered prompt, corpus digests, budget, model,
scaffold, judge and rubric.

A new incident or rubric can share task code, but it becomes its own eval, with its own
name and version, rather than a new config of an existing one.
