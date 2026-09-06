# Inspect Evals registration handoff

MessageBoardAuditBench is packaged as an externally managed Inspect eval. A
fresh checkout can install it with `uv sync` and run its registered task as:

```bash
scripts/build_data.sh
uv run inspect eval messageboard_audit/messageboard_audit \
  -T agent=claude -T model=claude-opus-5 -T config=blind-20 \
  --epochs 3 --max-samples 1
uv run inspect view
```

The local packaging conventions in the [official Inspect eval template](https://github.com/Generality-Labs/inspect-evals-template)
are covered:

- `pyproject.toml` provides PEP 517 packaging and declares `inspect_ai`.
- The package has an `inspect_ai` entry point and exports the `@task` functions.
- The task has a stable sample ID, version `1-A`, and run metadata.
- The source archive and generated variants are checked against committed
  SHA-256 digests, so upstream drift fails loudly.
- Unit tests cover task construction and transcript conversion; a mock-model
  test replays a complete run through Inspect and both scorers.

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
4. Run the complete eval with two different models and retain the `.eval` logs.
   Inspect Evals asks for both logs during review and may publish them, so check
   them for local paths or other identifying information first.
5. Open a [Register Eval Submission](https://github.com/UKGovernmentBEIS/inspect_evals/issues/new?template=register-submission.yml)
   with:
   - the versioned arXiv URL;
   - a source URL of the form
     `https://github.com/hamzah2304/messageboardauditbench/blob/<commit>/messageboard_audit/task.py#L<task-line>`;
   - any additional GitHub maintainers.
6. Upload the two full logs when the generated register PR requests them.

The register points to a public, immutable commit. Any later behavior change
should bump the task version, land upstream, and update that pinned commit in a
separate register PR.
