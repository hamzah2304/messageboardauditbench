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

The results-report checkpoint remains pending until the dataset and pilot exist.
