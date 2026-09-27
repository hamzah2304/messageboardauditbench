# A separate benchmark using the same trial infrastructure

The URLQuery benchmark uses the existing Docker subscription runner, proxy,
time/length hooks, transcript capture, usage accounting and per-run audit. Its
input, prompt, run archive, reports and future rubric are separate from the
original benchmark. The first runs are exploratory and **unscored**: Oscar has
not yet extracted and approved the reference findings.

This implements the design in the September 26 assessment and data-preparation
follow-up, with three later decisions: retain recorded credential-like values as
inert research evidence; retain original submission tags; and run the exploratory
pilot before manual rubric construction. These overrides are intentional.

## What preprocessing does

`configs/urlquery-data.toml` is the versioned acquisition/preprocessing contract.
The pinned ZIP SHA-256 selects all 38,160 unique IDs in `all-reports.csv`, including
background and review-required rows. This is still Transluce's selected
collection, not a census of URLQuery or all agent activity. We do not further
select by confidence, incident, source label, or whether the source report cites
a record. The existing explorer cache is reused only after schema/ID validation;
each reused file is hashed and recorded as a reused cache file, not claimed as a
new download with known acquisition history.

| Raw information | Agent-visible transformation |
|---|---|
| Submitted, initial and final URLs, title, time | `scans.jsonl`; keep distinctions and original text |
| HTTP transactions | `http.jsonl`; preserve scan ID, array order, timestamps, status, requests, headers and cookies |
| URL encodings and embedded text | `decoded_text.jsonl`; generic percent/Base64 UTF-8 decoding, original source pointers and transformation chains |
| DOM, scripts, response data | `resources.jsonl`; explicit availability and hash-addressed inert text when actually embedded |
| Investigator confidence, classes, reasons, caveats, source assignments | Evaluator-only catalog; never mounted |
| URLQuery detections, analytical tags, summaries, fingerprints, alerts | Excluded via field allowlists, not text matching |
| Submission-time tags | Retained as original submission evidence, not authenticated identity |
| Recorded credential-like strings | Retained verbatim; no execution, replay, or credential use |

The decoder is bounded to three transformation steps, 1,048,576 expanded
characters and 64 output records per source field. It never runs JavaScript or
classifies an episode. Size/depth limits are explicit. Unknown or non-UTF-8
encodings remain in original observations. External resource retrieval is off:
an upstream `resource_available=true` is **not** evidence that a body is present
in the downloaded JSON. Missing bodies are not replaced by human explanations.
POST bodies, dynamically evaluated/written scripts and console text are retained
when present. JSONL uses escaped Unicode so malformed UTF-16 surrogate values
round-trip. Content is UTF-8; a malformed Unicode string instead gets a
lossless JSON-string representation with `content_encoding` explicitly marked.

The builder writes a new staging directory, verifies every listed file, and
renames it into a versioned snapshot. It refuses to overwrite an existing
snapshot. The evaluator-only provenance sidecar records raw-file hashes, config,
catalog hash, missing IDs and the builder hash. `manifest.json` in the agent
folder contains only neutral counts, missingness, version and file hashes.
Symlinks, additional files, changed bytes and wrong benchmark identities fail
validation. A read-only bind mount prevents agent changes during a trial.
Snapshot membership is fixed before decoding and scans are ordered by raw scan
date and ID. HTTP transactions retain their original array order. The launch
config must pin `dataset_sha256`; the host and Docker canary both verify it.
Acquisition is settled only after the full catalog has been attempted and every
remaining gap is recorded as HTTP 404/410. Transient failures or pending requests
block a pilot. Diagnostic incomplete builds are explicitly marked and rejected
by the launch validator.

The labels are retained as an auxiliary research reference. For example,
`custom_program` concerns task-specific supplied code, while `significant` and
`suggestive` are qualitative confidence judgments. Neither proves authenticated
AI authorship, shared operators or successful exploitation. They cannot replace
an evidence-checked finding rubric.

## Paths and run contract

| Purpose | Original benchmark | URLQuery |
|---|---|---|
| Definition | `messageboard` | `urlquery` |
| Evaluator material | `benchmark/` | `benchmarks/urlquery/` |
| Raw downloads | Existing wiki inputs | Primary checkout `data/transluce/` |
| Frozen agent input | Existing data variants | Primary checkout `data/urlquery/<version>/` |
| Trial archive | `runs/` | `runs/urlquery/` |
| Exported reports | `reports/` | `reports/urlquery/` |
| Logs | `logs/` | `logs/urlquery/` |

`configs/urlquery-10.toml` sets ten minutes including writing, medium effort, a
2,400–2,900 word target, acceptance up to 3,000 words, and minimum runtime fraction
0.75. The target matches the source report's findings prose: 2,633 words across the
introduction, key findings, executive summary, the three incident sections and the
six timeline descriptions, excluding the appendix (421) and footnotes (81) that the
earlier 3,135-word count included (`docs/assessments/transluce/source_word_count.json`). The active process is stopped at ten minutes; the fifteen-minute
outer setting is not permission for additional investigation.
The active timeout has a one-second termination grace. Deadline stops are
recorded as `active_time_limit`, distinct from harness errors; their reports are
retained but marked `report_finalization=not_confirmed`. Raw exit codes remain
available. A report present at the deadline is not proof it was fully finalized.

Subscription execution uses the existing provider-only proxy. Agent containers
have subscription credentials and can reach allowlisted provider endpoints;
this is **not** the stronger credential-free, network-disabled Inspect backend.
The repository, human report, annotations, rubric and other benchmark inputs are
not mounted. Every trial runs the existing network canary and validates the
dataset again inside Docker. No target website should be contacted.

The existing original benchmark task remains unchanged in purpose. New runs
cannot be resumed or replayed through it or staged into its grading inputs.
URLQuery automated grading fails closed until a rubric is approved. Future
rubric work should extend `BenchmarkSpec`, not make `data_variant` silently pick
an unrelated answer key. Continuation of URLQuery trials is intentionally not
implemented for this first pilot.

## Reproduction

From the task checkout (Python 3.11+; Docker for trials):

```sh
.venv/bin/python -m messageboard_audit_bench.urlquery_data
.venv/bin/python -m messageboard_audit_bench.urlquery_prepare
# Creates a resolved config and explicit matrix; --launch is required for calls:
.venv/bin/python -m messageboard_audit_bench.urlquery_pilot \
  --dataset /absolute/primary/checkout/data/urlquery/2026-09-26-v1 --launch
.venv/bin/python scripts/collect_reports.py --benchmark urlquery --include-partial --include-rejected
```

The collector is resumable and records unavailable records separately from
transient failures. It stops on access denial or a 12 GiB free-space guard.
Never run two writers against the raw cache; the full collector holds a lock,
but the older explorer does not share that lock. Do not run the model commands
until acquisition/preprocessing and isolation checks pass. Exact pilot model
identities, hashes, outcomes and limitations belong in the results report.
The initial matrix is GPT-6 Astra and GPT-6 Sol once each, and Opus 5.5 twice.
There is one sequential lane per subscription, with the two providers running
in parallel. The launcher writes a unique plan, resolved config, per-trial logs
and results; it does not silently resume or repeat a previous plan. Authentication
or capacity failures stop that subscription's remaining lane. The host applies
a 900-second per-trial guard, outside the active ten-minute Docker timeout.

The URLQuery trial config also pins Claude Code 2.1.283 and Codex 0.156.1.
These become Docker build arguments and a versioned image name; the original
benchmark's Docker defaults remain unchanged. Pins and image-name suffixes must
agree in both directions, including manual launches. The first attempt exposed
an explicit Opus 5.5 minimum-client error and a Sol support error with missing
model metadata on the older client. Those attempts remain archived. Explicit
`--agent` and `--model` filters select retries from the existing matrix without
automatically repeating successful trials or switching models/accounts.
The successful initial Astra trial used Codex 0.153.4. The explicit retry selects
Sol and two Opus trials on the newer clients; it does not replace that Astra
report. The results index must link both experiment plans and retain the two
failed startup attempts. Cross-model comparisons therefore also mix client
versions. Runtime version output is checked against configured pins before
inference, not merely recorded after the Docker build.

Observed execution adds a separate caveat: both requested Opus 5.5 trials
switched to Opus 4.8 after a cyber-safety refusal, through the original harness's
permitted provider fallback. They are mixed-model outputs, not pure Opus 5.5
measurements. The report index preserves the full observed model list and
fallback metadata; the legacy audit's single first-served-model field is not
sufficient. No replacement trial was launched to work around the refusal.

Sources: [Transluce report](https://transluce.org/agent-activity),
[URLQuery field definitions](https://urlquery.net/help/search), and the pinned
ZIP's README/methods files. Raw evidence stays local; this work does not publish
the corpus or credentials.
The raw agent reports under `reports/urlquery/` are gitignored: agents may quote
credential-like strings despite the dataset guide's advice not to do so. Four
reviewed publication copies of the initial pilot reports live under
`reports/urlquery/published/`, with credential and personal-identifier spans
redacted and archived report hashes retained in their headers.
The pilot summary links to local report previews, not a public deployment.

## Browsing trajectories

`uv run python scripts/view_urlquery_runs.py` rebuilds unscored Inspect logs from
the local `runs/urlquery/` directories and opens `inspect view`. There is one log per
prompt-and-budget group (for example "urlquery-swarm-v4 · 10 min"); each sample is
one run, named `<model> r<replicate> · <run-id prefix>`, with agent, config, prompt
hash, termination and report length in its metadata and report words / active
minutes as sortable columns. `--since 20260927T06` limits it to newer runs and
`--no-view` only builds. The logs land in the gitignored `logs/urlquery-runs/` and,
like the run directories, stay local: transcripts include raw scan data with
recorded credentials, and this repository is public.

## Manual findings remain a separate step

`viewers/build_urlquery_findings.py --source <cached agent-activity.html>` reuses
the original selection/comment template without executing the downloaded page.
Exports and browser state include benchmark and source/rendered-article hashes;
imports for another benchmark or source version are rejected. The article's
scripts, SVG, event handlers and remote embeds are not loaded. Quoted code remains
escaped text. This is an evaluator tool and is never in the agent mount.

The existing candidate approval and feasibility builders accept
`--benchmark urlquery`. Their inputs live under `benchmarks/urlquery/claims/`
and `benchmarks/urlquery/feasibility/`; metadata must carry benchmark, source
report and dataset hashes. Output HTML names and candidate browser state are
separate from the original benchmark. No approved candidates or feasibility
verdicts are fabricated to make the first pilot look scored.
