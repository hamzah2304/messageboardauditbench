# Incident lifecycle: choose, build, run, review, publish

An incident is useful here only when a blind agent can investigate primary
evidence and its report can be compared with a human investigation. The
repository treats selection and validity as part of the benchmark, rather than
as informal work that happens before the code is added.

Start with the current inventory:

```bash
uv run python scripts/incident_pipeline.py list
uv run python scripts/incident_pipeline.py guide rubyhack
```

Each incident has one manifest under `benchmark/incidents/`. That manifest is
the source of truth for its corpus variants and file shape, public configs,
default time, finding and summary rubrics, evidence limitations, review gates,
and results status. The task, sandbox, corpus builder dispatcher, score tool,
worktree helper, and validation command all read it. Adding an incident no
longer requires editing separate allowlists in those components.

**A new incident is a draft for its own eval.** Only the collusion.wiki incident is
part of the German wiki report (`german_wiki_report`). Every other manifest, such as
Mythos 5 and RubyHack today, is a draft. It shares the harness (config format, corpus
builders, sandbox, subscription runner, sheet grader), and the pipeline below validates
it offline, but it is not an Inspect condition of any eval. You pilot it through the
subscription runner. Once it reaches `reviewed`, give it its own Inspect task with its
own name and version: a thin wrapper around the shared builder `_audit_task` in
`messageboard_audit_bench/task.py`, registered in `benchmarks.py` the way
`transluce_report` is. Then list it in
[`benchmark-versions.md`](benchmark-versions.md).

## The four lifecycle states

| state | meaning | numbers may be presented as |
|---|---|---|
| `candidate` | evidence and a human account exist; corpus and rubrics are being built | exploratory only |
| `pilot` | the complete pipeline has run and its artifacts are archived | pilot results, with limitations |
| `reviewed` | corpus boundary, derivability, rubric, judge choice, and runs have been independently reviewed | incident-specific benchmark results |
| `published` | the selected result set and presentation are committed and linked from the manifest | published results |

A green technical check proves that a candidate is executable. It does not
promote the candidate or make its score comparable with the original wiki
study. Change `maturity` and `results.status` only when the recorded review gates
have actually been completed.

## Gate 1: decide whether the incident belongs

Before writing a builder, answer these questions in a short candidate note:

1. **Is there primary evidence?** A raw log, transcript, repository history,
   package set, or capture must contain investigative work for an agent to do.
2. **Is there an independent human investigation?** It must say what happened
   and why. A corpus without an account cannot be graded; an account without a
   corpus becomes reading comprehension.
3. **Can the two be separated?** The agent corpus must exclude the human
   conclusions, labels, and answer-key metadata.
4. **Are enough central findings derivable?** Anchor each candidate finding to
   the exact evidence the agent will receive. If the important conclusions rely
   on private telemetry or redacted material, the incident is a poor recall
   benchmark.
5. **Does it add a useful transfer test?** Prefer a new evidence structure or
   investigative challenge over another incident that differs only in topic.
6. **Can the corpus be rebuilt and redistributed responsibly?** Pin source
   bytes, record selection rules, remove live credentials and personal data,
   and state third-party licensing limits.
7. **Can contamination and judge conflicts be described honestly?** Fresh,
   famous, or self-identifying corpora can still be pilots, but their scores
   should not be described as clean generalisation evidence.

Reject or defer the incident when the source cannot be reconstructed, the
answer key cannot be separated, nearly all important findings are unavailable
to the agent, or the corpus is mainly the investigators' own narration.

## Gate 2: scaffold one candidate

Use the scaffold so the manifest, config, corpus builder, answer key, claims,
rubric builder, README, and ignored data directory receive consistent names:

```bash
uv run python scripts/incident_pipeline.py new example-incident \
  --title "Example incident" \
  --investigation-url https://example.org/investigation \
  --data-file records.jsonl \
  --prefix EX \
  --minutes 20
```

The generated files deliberately contain `TODO` markers and do not pass the
incident check. Fill them on a task branch. The failing check is the work list:

```bash
uv run python scripts/incident_pipeline.py check example-incident
```

## Gate 3: build the blind corpus

The builder is incident-specific, but its contract is fixed:

- verify every input by a pinned digest or a committed source manifest;
- document the selection rule and the evidence that was unavailable;
- remove editorial summaries, verdicts, classifications, and other answer
  leakage;
- redact usable credentials while retaining stable fingerprints when reuse is
  evidential;
- emit deterministic UTF-8 JSONL under `data/<variant>/`;
- give each independently citable record a stable ID;
- validate the expected record/file shape before replacing the output; and
- write through a temporary file so a failed rebuild cannot damage shared data.

Register the builder and exact JSONL filenames in the incident manifest.
`scripts/build_data.sh` dispatches every registered incident builder and checks
all outputs against `data/SHA256SUMS.variants`. The generated corpus stays
gitignored; the checksums and builder are committed.

The agent receives only the registered JSONL files in `/work/data`. The Docker
preflight rejects missing files, extra files, writable data, credentials, and
non-loopback networking.

## Gate 4: create a corpus-scoped answer key

Read the human investigation and make a claim ledger. For every finding record:

- a stable claim ID and a single assessable conclusion;
- the corresponding human-report passage;
- one or more precise corpus anchors;
- `yes`, `partial`, or `no` for derivability; and
- a note defining any quantity or outcome the grader must not require.

Only `yes` and defensibly scoped `partial` findings enter the recall sheets.
Keep non-derivable conclusions in the answer-key limitations: a strong report
should distinguish what the corpus establishes from what it cannot establish.
Do not silently turn missing evidence into a model miss.

Generate several small finding sheets and one incident-specific holistic TL;DR
sheet. Reuse the shared 0–1 scale and the rules that require the report to draw
the conclusion and tell the grader to search the whole report. Never use an
existing incident's TL;DR sheet for a new story.

Manual review should include someone who did not write the claim ledger. They
should attempt to derive every scored claim from the built corpus alone and
record disagreements before any paid grading.

## Gate 5: prove that it runs without spending model credits

Run the complete static check and native Docker preflight:

```bash
uv run python scripts/incident_pipeline.py check example-incident --docker
uv run ruff check .
uv run pytest -q
```

The incident check verifies the manifest, config, config-default budget, built
file set, JSONL contents, pinned checksums, claim-to-sheet parity, answer-key
prompt construction, task construction, four attached scorer roles, lifecycle
metadata, and the isolated Docker mount. It does not call an agent or judge.

The repository's tests run the public task and both incident rubrics with mock
model responses. This proves orchestration and grade aggregation without
claiming that a real provider call will be available or affordable.

## Gate 6: run an ungraded pilot and inspect it

The guide prints the registered default. Keep generation and grading separate
for a new incident so a bad corpus or rubric does not multiply costs:

A draft is not an Inspect condition, so pilot it through the subscription runner,
which accepts any config:

```bash
CONFIG=example-incident sandbox/docker/run_trial.sh react <provider/report-model> 1
```

Inspect the run directory it prints (`transcript.jsonl`, `report.md`, `meta.json`).
Once the incident has its own Inspect task, pilot through that instead, with
`--no-score --epochs 1 --max-samples 1`. Confirm that:

- only the intended corpus was visible;
- the report was produced within the recorded wall-clock budget;
- the run metadata says `data_manifest_status=matches_manifest`;
- no source identity or answer-key text leaked through the corpus;
- failures, fallbacks, refusals, and partial reports are labelled; and
- the report demonstrates enough investigative signal to justify a matrix.

Collect the accepted report and stage it for later grading:

```bash
scripts/collect_reports.py
scripts/stage_graded_inputs.py reports example-incident=pilot_example:pex
```

(For an Inspect pilot, `scripts/export_inspect_reports.py --logs logs --out reports/native
--graded-inputs pilot` does both.) Staging prints the exact directory. Review its Markdown and
`_index.jsonl`; do not grade rejected or partial reports as ordinary samples.

## Gate 7: grade with a declared independent judge

Choose the judge before looking at comparative scores. The judge should differ
from the report-generating model. Record any relationship between the judge's
provider and the incident itself; for Mythos 5 this is a material design choice,
and for RubyHack attribution claims require similar care.

Run the registered finding and summary modes separately over the same staged
folder. The sheet grader is shared, so this uses the German wiki report's grading task
with the draft's own modes:

```bash
uv run inspect eval messageboard_audit_bench/german_wiki_report_grade \
  -T dir=<staged-folder> -T rubric=<finding-mode> \
  --model-role grader=<provider/judge-model>
uv run inspect eval messageboard_audit_bench/german_wiki_report_grade \
  -T dir=<staged-folder> -T rubric=<summary-mode> \
  --model-role grader=<provider/judge-model>

uv run python scripts/export_grades.py logs/<finding-grade-run>.eval
uv run python scripts/export_grades.py logs/<summary-grade-run>.eval
uv run python scripts/score_reports.py \
  --incident example-incident benchmark/graded/judge_<judge> \
  --json-out benchmark/results/example-incident/scores.json \
  --markdown-out benchmark/results/example-incident/README.md
```

Inspect per-finding reasons and quotes before accepting the aggregate. Audit a
sample against a second human or judge, record parse failures, and never average
grades from different judges as if they were one instrument.

The shared headline is 70% strict finding coverage and 30% holistic TL;DR.
Strict coverage transforms each finding credit `s` with `max(2s - 1, 0)` before
averaging. Report the raw finding mean and strict coverage alongside the
headline so readers can see what changed.

## Gate 8: publish a reviewable result set

A result release should let a reader move from a plotted number back to the
actual report, grade, rubric, corpus digest, prompt, model, scaffold, budget,
judge, and eval log. Commit or archive:

- the accepted report set and `_index.jsonl`;
- finding and summary grades under their incident modes and judge directory;
- the exact manifest, config, prompt digest, corpus digests, and Git commit;
- the source `.eval` logs or a checksum-addressed download manifest;
- a machine-readable score table and the rendered table/figure built from it;
- exclusions, missing replicates, model fallbacks, and run failures; and
- a short methods/limitations page stating maturity and comparability.

Use the original wiki publication as the presentation pattern: name the model,
scaffold, budget, replicate count, judge, component scores, and headline; link
the evidence index and individual artifacts. Do not add candidate results to the
wiki headline figure. Give each incident its own result table until the review
establishes which comparisons are defensible.

Finally update `results.status` and `results.path` in the manifest, rerun the
incident check, and include the generated result artifacts in the same commit as
the status change.
