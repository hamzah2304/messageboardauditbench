# Inspect Evals registration handoff

MessageBoardAuditBench is packaged as an externally managed Inspect eval. A
fresh checkout can install it with `uv sync` and run its registered task as:

```bash
scripts/build_data.sh
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=claude -T config=blind \
  -T time_limit_minutes=30 \
  -T min_runtime_fraction=0.75 \
  --model anthropic/claude-opus-4-1 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1
uv run inspect view
```

The local packaging conventions in the [current external-eval registration
guide](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/README.md)
and its [example registration
record](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/example_eval.yaml)
are covered:

- `pyproject.toml` provides PEP 517 packaging and declares `inspect_ai`.
- The package has an `inspect_ai` entry point and exports the `@task` functions.
- The task has a stable sample ID, version `8-A`, and run metadata.
- The source archive and generated variants are checked against committed
  SHA-256 digests, so upstream drift fails loudly.
- Unit tests cover task construction, native trajectory collection, transcript
  conversion, and a complete replay through Inspect and both scorers.
- The default backend uses `inspect_swe.claude_code()` or
  `inspect_swe.codex_cli()`. Inspect controls model calls, provider caching,
  limits, token accounting, sandboxing, and live events.
- The benchmark preserves Inspect SWE's bridge configuration while installing
  native after-tool time/report hooks; hook execution is recorded in sample
  metadata and covered by forced-tool-call Docker smokes.
- A shared `min_runtime_fraction` policy (default 0.75) resumes normal early
  completions in the same agent session until the stated portion of the budget
  has elapsed. Refusals, failures, and hard limits are exempt; the configured
  fraction and minimum seconds are retained in Inspect metadata.
- An explicit `backend=subscription` remains available. Its CLI transcript is
  mapped into Inspect messages after execution; conversion diagnostics and a
  corpus-wide checker guard the necessarily non-native import path.

The register now generates and owns its machine-readable record from the
submission issue; it does not consume an `eval.yaml` shipped inside the
external package. The old local file mixed a legacy schema with current
register fields and was intentionally removed. Contributor identities are
retained as standard package authors in `pyproject.toml`.

## External asset provenance

The generated benchmark data comes from
`https://collusion.wiki/explorer/download/full-wiki-logs.zip`. The expected
archive SHA-256 is
`eb68aa12d26bf189d8bfc4ce47f4d8af66ae5ba7ebbadd429738297a3cbb25ae`;
`scripts/fetch_data.sh` verifies it before extraction, and
`scripts/build_data.sh` verifies every derived variant against the committed
manifest. This is reproducible today, but the source URL itself is mutable.
Registration therefore remains blocked until the same checked archive is on an
immutable project-controlled URL (or another stable host accepted by the
register maintainers).

## What remains before registration

The official listing cannot be created from an unmerged worktree. Complete
these steps after review:

1. Merge this change into the public repository and record the resulting
   40-character commit SHA.
2. Mirror `full-wiki-logs.zip` to immutable, project-controlled storage, update
   `scripts/fetch_data.sh` to use that URL, and retain the SHA-256 check. The
   current collusion.wiki URL is mutable and therefore does not satisfy the
   register's stable-hosting requirement by itself.
3. Publish or identify the arXiv paper describing this benchmark. The register
   submission form requires a versioned arXiv URL.
4. Follow the [current Register Eval Submission
   instructions](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/register/README.md)
   to open the submission issue with:
   - the versioned arXiv URL;
   - a source URL of the form
     `https://github.com/hamzah2304/messageboardauditbench/blob/<commit>/messageboard_audit_bench/task.py#L<task-line>`;
   - any additional GitHub maintainers.
5. Upload complete eval logs for two models as required by the current register
   guide, then review the bot-generated metadata-only register PR. The register entry lives
   in `UKGovernmentBEIS/inspect_evals`; this repository remains the pinned
   upstream implementation.

The register points to a public, immutable commit. Any later behavior change
should bump the task version, land upstream, and update that pinned commit in a
separate register PR.
