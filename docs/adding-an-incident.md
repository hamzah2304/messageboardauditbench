# Adding an incident to the benchmark

This benchmark scores one thing: **can an agent investigate raw evidence, blind,
and recover what a human investigation found?** It began with the collusion.wiki
dump and now has two transfer-study implementations: the Claude Mythos 5
transcript and the package diffs cited by RubyHack. Structurally different
incidents test whether the method transfers or is overfit to one dataset. This
document gives the shared recipe; `benchmark/rubrics/mythos5/` and
`benchmark/rubrics/rubyhack/` are the worked examples.

## What you need before you start

Two things, and the benchmark is meaningless without both:

1. **A raw corpus** — the messy source data an agent investigates. It must be
   something the agent could plausibly be handed with no context (a log dump, a
   transcript, a capture). Whoever produced it must not have folded their
   conclusions into it.
2. **A human write-up** — an authoritative account of what happened, to grade
   against. This is the answer key.

If you have only one of these, stop: a corpus with no write-up can't be graded, and
a write-up with no raw corpus is a reading-comprehension test, not an investigation.

## The stages you reuse, and the ones you build

The run harness, the isolated sandbox, the two-judge grading structure, and the
scoring math are **incident-agnostic** — you do not rebuild them. What you build is
the corpus preparation and the answer key. Concretely:

| stage | reused as-is | per-incident work |
|---|---|---|
| data prep | `scripts/build_data.sh` pattern, checksum discipline | strip *your* corpus of the investigators' analysis |
| run | Docker sandbox, `blind-v2.txt` prompt, Inspect task | dataset name, allowed file shape, config |
| grade | 0–1 scale and judge structure | findings, derivability split, finding sheets, incident-specific TL;DR sheet |
| score | `score_reports.py`, 70/30 formula | point it at the incident's finding and TL;DR grade directories |

## Step 1 — Extract the findings and split by derivability

This is the intellectual core; everything else is mechanical. Go through the human
write-up finding by finding, and for each one decide: **can an agent establish this
from the corpus the agent is actually given?**

Three buckets:

- **Derivable** — the corpus contains the evidence. These become scored points.
- **Partial** — the substance is derivable but a specific quantity, name, or moment
  is missing (redacted, or only in the investigators' side channels). These are
  scored points *with a note telling the grader what not to require*.
- **Not derivable** — the evidence isn't in the corpus at all (it rested on data the
  investigators had and the agent doesn't). These do **not** become "you missed it"
  misses. Keep them as candidates for a separate **calibration rubric**: an agent
  that says "not determinable" is right; one that asserts them confidently is
  over-claiming. The current recall sheets do not score this behavior, so implement
  and validate that rubric before publishing a calibration number.

> **Watch for redactions.** A finding can read as obvious and still be unrecoverable.
> In the Mythos 5 transcript the opening (the task brief) and the climax (the
> credential theft) are redacted, so "was told it had no internet" and "accessed the
> vendor's database" are *not* derivable despite being central to the story. Anchor
> every derivable finding to a specific location in the corpus; if you can't point at
> the evidence, it isn't derivable.

Record this as a per-claim file. `benchmark/feasibility/` is the wiki's version;
`benchmark/rubrics/mythos5/claims_m5.json` is a compact version where each claim
carries its answer-key quote, a scoring note, a `derivable` verdict, and a pointer
to where the evidence sits in the corpus.

## Step 2 — Strip the corpus

Same discipline as [`data-processing.md`](data-processing.md): the agent gets what
the source itself recorded, plus anything the write-up prints verbatim, and **nothing
that encodes the investigators' analysis**. On the wiki that meant dropping fields
like the authors' `page_family` classification and their human-vs-bot labels; a
Sonnet run once "found" the admin impersonation only because an authors' label leaked.
For a transcript corpus the equivalents are any post-hoc annotations, verdict tags, or
section labels the investigators added. When in doubt, remove it — a leaked conclusion
silently inflates every score.

Build the stripped corpus deterministically and pin it with a checksum, the way
`scripts/fetch_data.sh` pins the dump by SHA256 (it verifies content, not source, so
any mirror works via `MBAB_DUMP_ARCHIVE` / `MBAB_DUMP_URL`). Never commit the raw,
un-stripped corpus — it holds the answer fields.

## Step 3 — Build the grading sheets

Turn the derivable and partial findings into judge sheets. Reuse the shared 0–1
scale and the two scoring rules so rubrics can't drift:

- **Inference vs evidence** — a report that recites the evidence for a conclusion
  without *drawing* it caps at 0.5. Listing what the agents did is not the same as
  concluding they colluded.
- **Search the whole report** — a finding may live in a summary, a table, or an
  appendix.

`benchmark/rubrics/build_rubrics_m5.py` is the template. It mirrors
`build_rubrics_v2.py`: it parses the `SHEET_SCALE` literal out of
`build_rubrics.py` (rather than importing it, which would regenerate the v1 rubric
as a side effect), and only swaps the **answer key** and the **worked examples**.
Copy it, point it at your `claims_*.json` and your answer-key text file, and
regenerate. The answer key is spliced into every sheet at the `{{HUMAN_REPORT}}`
placeholder; keep it scoped to *this* incident so other material can't leak in.

## Step 4 — Wire it into the harness

The prompt is already incident-agnostic, but the harness validates data shape and
selects incident-specific graders. Update all of these:

- **Allowed datasets** — `messageboard_audit_bench/task.py` (the `data_variant not
  in {...}` guard, currently around line 246). Add your variant.
- **Named config and default graders** — add a config and map the incident's data
  variant to its finding and TL;DR modes. Do not overload `VARIANT_FOR_DATA`;
  that mapping represents provider-rewritten copies of the same incident.
- **Data-shape preflight** — `sandbox/isolation_preflight.py` accepts exact supported
  JSONL file sets. Add the new set so the native sandbox still rejects missing or
  unexpected files. Generalise any direct launcher path that assumes a particular
  wiki filename.
- **Answer-key and sheet loader** — add grading modes whose sheet directory,
  answer key, sheet count, and rubric IDs point at the new incident.
- **Holistic summary rubric** — write incident-specific TL;DR anchors. Reusing the
  wiki `tldrh` sheet would grade the new report against the wrong story.
- **Corpus build** — add a build-time fetch, pinned source hash, deterministic
  stripping step, and derived digest alongside `scripts/build_data.sh`.

## Step 5 — Before you trust a number

Adding an incident is not the same as adding a *comparable* incident. Check:

- **Contamination.** Is the corpus fresh, widely reported, or self-identifying? The
  wiki prompt can hide the source because the dump doesn't name itself; a
  press-covered transcript that names the tools involved can't be hidden the same
  way. Watch canary reuse too — if the new corpus carries the same canary GUID the
  repo already uses, a canary hit can't tell you which source leaked.
- **Judge independence.** "The judge is never a subject" must still hold. If the new
  incident's subject shares a provider with your judge, swap the judge.
- **Redaction-aware key.** The answer key must be built against the corpus the agent
  *actually gets*, not the full write-up the investigators saw. Never demand coverage
  for a finding whose evidence was redacted out from under the agent.
- **Transfer ≠ generalisation.** Two incidents show the method ports. They do not
  prove the metric generalises; that argues for synthetic corpora with planted ground
  truth as a third leg, not just more real ones.

## Checklist

- [ ] Raw corpus **and** human write-up in hand.
- [ ] Every write-up finding tagged derivable / partial / not-derivable, each
      derivable one anchored to evidence in the corpus.
- [ ] Corpus stripped of the investigators' analysis; built deterministically; pinned
      by checksum; raw corpus never committed.
- [ ] `claims_*.json` + answer-key text file written.
- [ ] Sheets regenerated from the shared scale via a `build_rubrics_*.py` clone.
- [ ] `task.py`, `scorer.py`, `grading/core.py`, and a fetch script updated.
- [ ] Contamination, judge independence, and redaction-awareness checked before any
      number is reported.
- [ ] `uv run ruff check . && uv run pytest -q` green.
