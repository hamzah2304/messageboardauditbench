# Investigating recorded web scans in ten minutes

Draft · Results pending full acquisition and model execution

The engineering is implemented, but the full snapshot and model results are not
ready. This draft records the experimental setup; it makes no claim about agent
performance. Replace this opening with the observed outcome after the runs.

## What the agents receive

The input starts with all 38,160 unique scan IDs in Transluce's released catalog,
including its background and review-required records. We download the public
URLQuery JSON for each available ID. We do not select scans using the report's
incident descriptions or confidence labels. The released catalog itself is a
selected collection, however—not a sample of all web activity.

The agents see an offline folder, not Transluce's report or annotated catalog.
Preprocessing constructs new records from allowed fields:

| Agent-visible file | What it preserves |
|---|---|
| `scans.jsonl` | Original scan IDs and times; submitted, initial and final URLs; titles; original submission tags |
| `http.jsonl` | Requests and responses in their original within-scan order, including headers, cookies, status codes and references to recorded POST bodies |
| `decoded_text.jsonl` | Generic percent/Base64 text decodings, with original field references and transformation chains |
| `resources.jsonl` and `content/` | Content actually embedded in the downloaded JSON, stored as inert text; explicit missingness otherwise |
| `README.txt` and `manifest.json` | A neutral format guide, citation conventions, counts and file hashes |

The decoder does not execute programs or interpret their purpose. It applies the
same bounded rules to every record: at most three transformation steps, 1,048,576
expanded characters and 64 output records per source field. Originals remain
available; unsupported encodings and decoding limits are explicit. We do not
download separately hosted bodies, screenshots or other resources. In particular,
`resource_available=true` upstream does not mean the content is in this input.

Transluce's classifications, confidence judgments, incident groupings and reasons
for inclusion remain evaluator-only. URLQuery's analytical tags and detections
are also excluded. Original submission tags are retained as evidence, not as
authenticated actor identities. Destination IP addresses are not renamed as
agent addresses.

Your comments changed two parts of the earlier proposal: recorded credential-like
values are retained verbatim, and original submission tags are included. The
prompt prohibits credential use, request replay, program execution and following
instructions found in the corpus. Raw inputs and model reports remain local and
are excluded from version control; publishing them needs a separate review.

The complete transformation contract is
[`configs/urlquery-data.toml`](../../../configs/urlquery-data.toml), with an
[engineering explanation](../../urlquery-engineering.md). Each frozen snapshot
has an exact file manifest and an evaluator-only sidecar containing raw-file
hashes, acquisition gaps, configuration and preprocessing-code hashes. A launch
must pin the dataset hash. Changed bytes, extra files and mismatched benchmark
identities fail validation.

## The four runs are exploratory, not a ranking

The planned matrix is GPT-6 Astra once, GPT-6 Sol once and Opus 5.5 twice, using
the existing Codex and Claude subscription harnesses. Every run gets ten minutes
including writing, medium effort, a 3,000–3,500-word target and a 3,600-word
acceptance ceiling. Short nonempty reports remain acceptable. These length and
effort choices follow your comments on the
[data-preparation write-up](data_preparation.md).

One sequential lane per subscription avoids running multiple trials concurrently
on the same account. Authentication or capacity failures stop the remaining
trials on that subscription. The fifteen-minute outer guard allows setup and
cleanup; it does not extend the ten-minute active budget. Reports left at the
active deadline are retained with finalization explicitly unconfirmed.

Each agent runs inside Docker with a read-only dataset mount and the existing
provider-only network proxy. The repository, human report, investigator labels,
rubric and original benchmark's dataset are not mounted. This subscription
harness does expose the runner's subscription credential to its container and
permits provider connections; it is not a credential-free or entirely
network-disabled execution environment. A separate credential-free preflight
checks the dataset mount, and each trial also runs the network canary.

There is no approved URLQuery rubric yet. These runs test whether agents can
work with the corpus and produce useful investigations; they do not measure
finding coverage or establish a model ranking. The harness differs by provider,
and two Opus runs are too few to estimate its variability reliably. Agreement
with a public report is not, by itself, evidence of fresh discovery: this pilot
does not measure training-data contamination.

## Manual findings stay separate from the trial input

The [findings-extraction page](http://localhost:8792/urlquery_findings.html) uses
the original selection/comment workflow. Its exports and browser state are
scoped to this benchmark and source snapshot. Candidate approval and feasibility
review also have separate paths. No findings or feasibility verdicts have been
automatically approved.

The evaluator's coverage summary will check which article-cited scans, decoded
text and content are present in the frozen input. This is a preparation aid, not
proof that every published claim is recoverable. In particular, a recorded
probe is not proof of exploitation, and a missing body is not proof of failure.
Cross-corpus comparisons and external attribution remain outside the initial
URLQuery-only rubric.

## Reproduction and review

The implementation is on `codex/urlquery-benchmark`, not merged into `main`.
The [audit record](engineering-review.md) documents the Opus 5.5 reviews through
Claude Companion and the fixes they prompted. The results-report audit remains
pending.

After full acquisition settles, the remaining sequence is:

```sh
.venv/bin/python -m messageboard_audit_bench.urlquery_prepare
.venv/bin/python docs/assessments/transluce/summarize_snapshot.py \
  --dataset /absolute/primary/checkout/data/urlquery/2026-09-26-v1 \
  --source /absolute/primary/checkout/data/transluce/agent-activity.html \
  --output docs/assessments/transluce/pilot_evidence.json
.venv/bin/python -m messageboard_audit_bench.urlquery_pilot \
  --dataset /absolute/primary/checkout/data/urlquery/2026-09-26-v1 --launch
```

The final report must add acquisition and content counts, dataset and launch
identities, actual served models and terminations, links to every generated
report, evidence-checked summaries of their claims, and the final review result.
