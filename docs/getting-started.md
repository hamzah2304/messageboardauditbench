# Getting started

Fresh clone to graded report. If a step fails, run `scripts/doctor.sh`: it checks
every prerequisite and prints the fix.

You need **Python 3.11+**, **[uv](https://docs.astral.sh/uv/)**, **Docker** with a
running daemon (macOS: `colima start` or Docker Desktop), and about **10 GB** of free
disk. You do not need Claude Code or Codex on the host: the sandbox image downloads
pinned copies when it is first built.

## 1. Install

```bash
git clone https://github.com/hamzah2304/messageboardauditbench && cd messageboardauditbench
uv sync                  # Python deps, Inspect, and this package
scripts/build_data.sh    # fetch the 4 MB public dump, build data/, verify checksums
uv run pytest -q         # ~200 tests, ~15 s, no Docker needed
scripts/doctor.sh        # preflight
```

If `build_data.sh` reports a checksum mismatch, stop and open an issue: grades on
non-matching data are not comparable.

## 2. Credentials

Pick the harness you want to run. Files under `runs/` are gitignored.

| harness | what to do |
|---|---|
| `claude` (Claude Code) | `claude setup-token` on the host, save the token to `runs/.claude-oauth-token` |
| `codex` (Codex CLI) | `codex login` on the host |
| `react` (any OpenRouter model, no subscription needed) | save an OpenRouter key to `runs/.openrouter_key` |

Why a token file for Claude: macOS keeps the host login in the Keychain, which the
Linux container cannot read. The runner also accepts `CLAUDE_CODE_OAUTH_TOKEN` in the
environment or an in-container login via `sandbox/docker/claude_login.sh`, but the
token is preferred because concurrent trials otherwise race on refreshing one shared
credential.

## 3. Run a trial

Start with a short smoke test. The env overrides shrink the budget and the kill
timeout, and the report will be poor. That is fine: you are testing setup.

```bash
CONFIG=blind BUDGET_MIN=3 TIMEOUT=6m sandbox/docker/run_trial.sh react google/gemini-3.8-flash 1
```

Then a real one. Arguments are `<agent> <model> <replicate>`; the config sets the
prompt, budget, data variant and effort. `blind` is the benchmark condition at 20
minutes; `blind-30` and `blind-120` state longer budgets.

```bash
CONFIG=blind-30 sandbox/docker/run_trial.sh claude claude-opus-5 1
CONFIG=blind-30 sandbox/docker/run_trial.sh codex  gpt-5.6-sol   1
```

Each run writes `runs/<stamp>_<agent>_<model>_r1_<config>_<id>/` with `report.md`,
`transcript.jsonl`, `meta.json`, `canary.log` and `proxy.log`. Exit 124 means the
timeout fired; exit 3 means the isolation canary failed.

Useful extras: `python3 sandbox/watch.py runs/<run>` tails a live trial;
`sandbox/docker/run_batch.sh matrix.txt` runs many trials from a file
(see `sandbox/README.md`).

**Through Inspect instead.** Same sandbox and runner, plus `.eval` logs and a viewer.
Use `-T model=`, not Inspect's `--model`: the model runs inside the CLI in the
container. `--max-samples 1` runs epochs one at a time, which a subscription CLI needs.

```bash
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=claude -T model=claude-opus-5 -T condition=blind -T time_limit_minutes=30 \
  --epochs 3 --max-samples 1
uv run inspect view
```

## 4. Grade

Use the 30-claim rubrics in `benchmark/rubrics/`. They produced every number in the
README. (The Inspect scorer's `rubric.yaml` is a smaller starter rubric that has not
been human-validated.) The judge is GPT-5.6 Sol, so set `OPENAI_API_KEY` in the
environment or in `.env` (`cp .env.example .env`).

```bash
scripts/collect_reports.py                                  # runs/ -> reports/ + index.jsonl
scripts/stage_graded_inputs.py reports blind-30=my_round:mr # copy reports to benchmark/graded_inputs/my_round/
python benchmark/rubrics/grade_with_rubrics.py --dir my_round           # recall: 0..1 per claim
python benchmark/rubrics/grade_with_rubrics.py --dir my_round --contra  # contradiction: -1..0 per claim
```

Grades land in `benchmark/graded/`. The staging step keeps a byte-identical copy of
each graded report, so every score can be traced to its input. `--force` regrades.

To score with Inspect instead, set `ANTHROPIC_API_KEY` and drop `--no-score`, or
import finished runs without spending agent time:

```bash
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_replay
```

## 5. Browse

```bash
(cd viewers && for f in build_*.py; do python "$f"; done)
python3 -m http.server 8765 --directory viewers    # open http://localhost:8765
```

## Troubleshooting

| symptom | fix |
|---|---|
| `no data at data/verbatim` | `scripts/build_data.sh` |
| `only N GB free` | free disk, or lower `MIN_FREE_GB`. A full disk has corrupted Docker mid-batch before. |
| `no Claude credentials` | step 2 |
| exit 3, canary failed | read `<run>/canary.log`; on colima, restart it |
| exit 124 but `report.md` exists | the timeout fired; `collect_reports.py --include-partial` keeps it, flagged partial |
| Claude Code switched model mid-run | a safeguard refusal triggers a fallback (fable → opus-5 → opus-4.8). `meta.json` records `model_fallback`; grade under the served model |
| grader cannot import `dotenv` or `openai` | `uv sync`, then run the grader with `uv run python ...` |
