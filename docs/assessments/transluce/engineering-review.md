# Engineering audit record

Opus 5.5 was explicitly requested through the installed Claude Companion plugin
(`--model claude-opus-5-5 --effort high`). Its automatic review hook was unavailable,
so each checkpoint was invoked manually. Reviews were read-only: no trial model
calls, data acquisition, external mutations or edits were delegated to it.

## Preprocessing checkpoint

Three rounds covered the collector, preprocessing and data manifest. Accepted
findings led to the following changes:

| Finding | Resolution |
|---|---|
| HTTP client exceptions could escape a worker; interruption could leave downloads running without audit rows | Catch worker exceptions, stop/cancel pending work, retain completed audit results and an interrupted summary |
| A smoke acquisition looked like a full collection | Separate smoke summary; record limit, scheduled/unscheduled counts and explicit completeness |
| Reused cache lacked hashes | Per-collection cache manifest plus frozen snapshot raw-file provenance |
| HTTP failures lacked useful distinctions and run identity | Separate unavailable/access-denied/transient statuses; audit run ID and config hash |
| A bad downloaded ZIP could poison its pinned cache path | Verify bytes before writing |
| POST bodies were omitted | Preserve `request.post_data` as referenced content with availability and generic decoding |
| Script metadata references collided; `times_seen` was dropped | Unique source pointers and the actual upstream field name |
| Malformed Unicode could abort the corpus build | Escaped JSONL and explicitly marked lossless JSON-string content fallback |
| Dataset hash included acquisition-only settings; canary had no expected hash | Hash preprocessing-relevant config; pin and recheck dataset identity at launch |
| Failed publication could strand provenance | Staged sidecar, exclusive build lock and no-overwrite checks |
| Depth-limit markers reported skipped work where none remained | Emit a limit only when another decodable candidate exists |
| Fixtures missed real resource/transaction shapes | Tests for POSTs, scripts, DOM, content, missingness, labels and malformed Unicode |

Two recommendations were adapted rather than followed literally. Corrupt cached
files fail closed without overwriting another downloader's data; automatic
quarantine is not performed. HTTP 404/410 records are audited as unavailable but
are requested again on an explicit future collection, because public availability
can change. A pilot accepts these gaps only after full acquisition has settled.

An additional diagnostic caught a moving-membership race while the collector was
still running. The builder now fixes membership first and validates that
downloaded plus missing records equals catalog size. The first diagnostic build
is incomplete and cannot pass the pilot validator. It is not a pilot input.

## Runner and benchmark-separation checkpoint

Three rounds, with the first overlapping the last preprocessing round, covered
the shared runner, grading guards, collection, manual UI and pilot launcher.

Accepted findings fixed actual-timeout metadata, distinguished active-limit stops
from generic errors, gave refusal/capacity failures precedence, and blocked direct
grading of exported URLQuery report folders through the original rubric. The
last round found no launch-blocking issue. Its three low-priority findings were
addressed: stop a lane on capacity exhaustion even with exit 124; ignore raw
URLQuery reports pending publication review; and test the launcher with fake
subprocesses, including scoped timeout cleanup.

The final small fixes were tested rather than starting a fourth review round,
following the debate workflow's three-round limit. Additional checks cover the
new manifest-based credential-free Docker preflight, while retaining the
original benchmark's preflight defaults. The subscription trials themselves
still use the existing, weaker provider-only proxy boundary; this is documented,
not presented as credential-free execution.

Plugin job IDs (local audit provenance):

- Collector: `8c3d55a9-333a-4e1b-abba-2f9ac2deb8a5`.
- Preprocessing follow-up: `87bbd1c7-3b6d-4335-ae4c-f596974ce04d`.
- Preprocessing final / runner initial: `3ed8861c-90c8-44d9-ad3b-09c4cf208800`.
- Runner follow-up: `ef56acbb-66b9-473c-a66a-45e9df707557`.
- Runner final: `1976f90f-844e-4d38-86e4-1b842f6facb4`.

## Runtime compatibility checkpoint

The first launch exposed two startup failures, not investigation failures. Opus
5.5 explicitly required Claude Code 2.1.280 or newer; the initial image had
2.1.263. Sol returned a subscription-support error and missing model metadata on
Codex 0.153.4, whereas recent successful repository runs used 0.156.0. URLQuery
now pins Claude Code 2.1.283 and Codex 0.156.1 in its trial config, without changing
the original benchmark's Docker defaults. Retry selection keeps the successful
Astra run and preserves both failed attempts.

Three further Opus 5.5 rounds found no final launch blocker. Accepted low-priority
findings led to versioned image names checked against config pins in both
directions, explicit preflight image selection, real Bash tests for old/default
paths, single-lane launch tests, validation before creating plan directories,
cross-language planner/runner consistency tests, and a check of the actual
binary's version before inference. The original and retry plans and mixed client
versions will be linked explicitly in the results report/index. This adapts the
reviewer's optional plan-schema extension without rewriting either plan.

The final small checks were tested, not sent through a fourth compatibility
round. The running shell was replaced atomically during the first fixes; later
edits were made only after the original pilot processes had finished.

- Initial compatibility review: `1bf7b876-d278-4225-acc2-729b691d5e3e`.
- Follow-up: `89aee55b-5f31-4f33-8c67-ba56cea9988f`.
- Final compatibility review: `9b9a287e-34ab-4b8f-993a-7b266d2af7da`.

## Results-report checkpoint

The first review (`14bde052-7bf6-459a-a2a1-674b14486d06`) raised four issues.
All substantive recommendations were accepted:

- Add timestamps to selected evidence checks. Original transaction-array order
  is not reliably chronological; the report now makes that distinction and
  recommends documenting it in the next versioned input guide.
- Attribute the two refuted analyses to the observed Opus 4.8 segments, with
  transcript line/tool-call pointers, not to requested Opus 5.5.
- Explain differing retry image IDs. Archived inspections differ in OCI index,
  digest/tag/build metadata but have identical runtime config and filesystem
  layers. Each trial invokes a build; no claim of byte-identical image indexes
  is made.
- Require complete exported-report identity metadata and test evidence checks,
  safe output and the render/escaped-notice path. The initial finding that no
  example-check test existed was stale by review completion, but the requested
  security and render coverage was still useful and was added.

The report index also avoids promoting the legacy first-served-model audit field
to a single-model claim. Both Claude trials requested 5.5 and fell back to 4.8
after cyber-safety refusals; no replacement trials were launched. Provider-served
OpenAI identities remain unknown.

The second review (`47e8dc24-d743-4130-8a4a-1b4f13d1a4b7`) caught two provenance
statements invalidated by a concurrent prompt-change commit (`b43a510`). Both
were accepted and corrected: the comparison describes archived run configs,
the old prompt link points to `superseded/`, and the report says explicitly that
none of these runs used the replacement prompt. The concurrent change is
preserved, not reverted or retroactively attributed to these runs.

Its third finding was accepted: nonpositive/missing timestamps are emitted as
null in evaluator checks. The guide recommendation now distinguishes valid
timestamps from missing chronology; source-array order does not repair that gap.
The final third review (`e216738a-efc2-4ee4-9af3-2a451d6bb55d`) reported no
actionable issues. Final full checks for that checkpoint: ruff clean, 1,394 tests
passed. Artifact HTTP and JavaScript/HTML structural checks passed; a live browser
visual inspection was unavailable.

## Smaller-model follow-up checkpoint

The user then requested one ten-minute Haiku, Sonnet, Luna and Terra run.
The explicit matrix extension preserves the original default matrix, records
the expanded plan/source hash, and validates model/agent/replicate fields.
No live runner or planner was edited after launch.

Review `0bad1eeb-0ffe-48f0-9b4c-9687ca54fcde` prompted a generic fallback notice
instead of Opus-specific wording, plus a Sonnet regression case. Its lane-stop
concern was accepted and documented; Haiku and Luna both started successfully.
Its matrix-archive suggestion was adapted: the existing per-run code snapshot
already contains `configs/urlquery-smaller-models.toml`, verified to match plan
SHA `668bfec259ea0effcf3cb5ad974ddb82000c9ba7ebcc246d0675b02cbd9a2290`.
The source is also tracked at launch revision `94acf67`; no provenance is lost
when the worktree is removed.

Follow-up `a7798385-ebfe-401d-90d4-a646447c211b` led to regeneration of the
earlier run index with the updated script hash, exact lane-stop wording, and
tests for absent/non-refusal/incomplete fallback metadata. Category information
is preserved without hardcoding a model.

Final review `a505aa93-8bd1-4148-bd84-946791606c1b` found one low-priority edge
case: titles did not reconstruct a missing chain from `fallback_model`, though
notices did. Accepted and fixed through a shared chain helper, explicit unknown
chain labels, and Opus/Sonnet render tests with and without chain metadata.
The existing archived runs were unaffected. Ruff and 1,408 tests pass. This last
small correction was tested, not sent through a fourth review round, following
the three-round limit. No residual disagreement remains; independent review did
not recheck the last correction.
