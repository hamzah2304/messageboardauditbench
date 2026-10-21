# Grade the AI Village reports

The runner uses GPT-6.1 Sol with medium reasoning and at most 32 concurrent calls. It reads the definitive 32-report manifest copied from commit `7756424`; it does not discover extra reports from folders.

Prepare a plan from the current findings file, then execute that frozen plan. Final adjudication entries marked `keep` or `rewrite` are included, using their current claims. Dropped and screenshot-only entries are excluded. The expected count is 96; preparation fails on a mismatch. Generic pending rewrites without final adjudication fields are excluded.

```sh
ROOT=/home/oscar_gilg18/Dev/MessageBoardAuditBench
uv run python scripts/aivillage/grade_aivillage.py prepare \
  --findings "$ROOT/runs/aivillage-verify-20261004/final-findings.json" \
  --reports benchmarks/aivillage/benchmark-2026-10-04-runs.md \
  --runs-root "$ROOT/runs" \
  --goals "$ROOT/data/aivillage/full-v2-reasoning/village_goals.jsonl" \
  --output "$ROOT/runs/aivillage-grading-medium"

uv run python scripts/aivillage/grade_aivillage.py run \
  --output "$ROOT/runs/aivillage-grading-medium" \
  --concurrency 32 --deadline-minutes 65
```

The report is supplied in full once per call. Each call contains at most three findings from the same goal period, with a usual limit of 12 subfindings. A larger individual finding stays alone. Uncertain dates and episodes spanning periods also stay alone. Supply an optional `--goal-map` JSON object mapping finding IDs to verified goal-period IDs to improve grouping; mappings must be established from the key independently of report coverage.

Only each supplied finding’s attached Substack, tweet or Discord excerpts are included, alongside its log evidence and verification caveats. Other posts and threads are absent. Source image URLs and extracted image quotations are included as text references; image pixels are not fetched. Outside evidence is context and cannot add requirements investigators could not establish from their logs. The v8 scoring rules are preserved; a transport instruction changes the response to an array of independently graded findings. No source fetching or browsing happens during scoring.

A prepared plan snapshots the findings, report text, rubric, model settings and requests. Later source edits cannot change an active run. Each request has a content fingerprint. Re-running reuses successful matching requests; changed evidence or reports generate new fingerprints. Run against a specific snapshot with `--plan PATH` rather than the latest-plan pointer when needed.

The runner saves raw responses, selected rate-limit headers and validated scores. It rejects model fallback, mismatched IDs and invalid scores. Temporary throttling and overload use shared cooldowns and bounded retries; optional `--rpm` and `--tpm` arguments pace request starts for known account limits. The deadline prevents new API attempts; incomplete jobs are explicit and can be resumed. A missing score never becomes zero, and incomplete reports do not get an overall mean. Main-claim contradiction penalties remain pending human review; finding weights are equal.

Scores and progress are in the selected plan’s `grades.json` and `status.json`. Raw requests and responses are under the output folder’s `jobs/` directory. Plans with changed inputs can reuse identical completed jobs. Quote checks are reviewer warnings, separate from content scores.

Resume the same frozen plan through OpenRouter with `--provider openrouter`. This uses `OPENROUTER_API_KEY` and the exact `openai/gpt-6.1-sol` model with medium reasoning, with provider fallbacks disabled. Completed calls retain their original fingerprints and are reused. Each new result records its provider and returned model; `transport-request.json` archives the routed request. HTTP 402 stops queued calls immediately.
