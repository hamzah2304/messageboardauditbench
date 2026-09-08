# MessageBoardAuditBench

A benchmark for how well an agent can investigate raw message-board logs and recover
the findings of a human audit.

The source incident is [collusion.wiki](https://collusion.wiki/index.html): ~18,000 posts
left on a public wiki by autonomous OpenAI agents that used it to coordinate on a
web-retrieval task. Human investigators wrote up what happened. We give an agent the raw
dump — and nothing else — and score its report against that write-up.

## The task

An agent gets the stripped log dump in a network-isolated container, a time budget, and a
prompt asking for an incident report. It gets no web access, no view of the human report,
and no hints about what it will be graded on. The report is then graded against the human
audit — see [How grading works](#how-grading-works).

Because the budget is part of the condition, a score means nothing without the budget it
was measured at. This measures investigation, not recall of things already known.

## Run it

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/) and Docker.
[`docs/getting-started.md`](docs/getting-started.md) covers credentials, the ablations and
troubleshooting; `scripts/doctor.sh` checks prerequisites and prints the fix for anything
missing.

```bash
uv sync --frozen
scripts/build_data.sh                      # fetch + build data/, verified against checksums

# through Inspect (set OPENAI_API_KEY for this example's agent and grader)
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=blind -T time_limit_minutes=30 \
  --model openai/gpt-5.6-sol --model-role grader=openai/gpt-5.6-sol
uv run inspect view

# or the subscription scripts directly, against the same image, prompt and data
ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/blind-20.toml \
  sandbox/docker/run_trial.sh claude claude-opus-5 1
scripts/collect_reports.py                 # runs/ -> reports/
```

The eval runs the finding (`v2`) and summary (`tldrh`) graders inline; `--no-score` defers
them. Every script resolves its inputs through `paths.py`, so the repo works from a plain
clone.

## Results

Measured results are reported in the accompanying write-up, not here, so this README stays
a description of the benchmark rather than a snapshot that goes stale every round. The
public results definition is not yet frozen — see item 3 of
[`docs/release-readiness.md`](docs/release-readiness.md) before quoting any number from
this repository.

The grades themselves are tracked: `benchmark/graded/` holds every committed per-claim and
per-finding grade, `benchmark/graded_inputs/` the byte-identical report each one came from,
and `reports/` the full corpus with run metadata.
[`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) maps all of it;
`viewers/build_*.py` renders it as browsable HTML.

`scripts/report_performance.py <graded-dir>` aggregates a directory, applying the figures'
stricter `max(2s - 1, 0)` transform per finding — **not** the raw mean the Inspect sheet
scorer reports.

## Layout

```
benchmark/      ground truth: human_report.txt (answer key), claims, feasibility,
                rubrics, graded results, and the exact reports each grade came from
messageboard_audit_bench/
                the Inspect task package — wraps the sandbox as an inspect eval
sandbox/        isolated trial runner (Docker), API proxy, ReAct scaffold, prompts
scripts/        data build/fetch, grading, report collection, analysis
configs/        trial conditions (budget, prompt, data variant, effort)
experiments/    manifests and notes for the multi-cell rounds and ablations
reports/        the model report corpus, by benchmark config
baselines/      early trial runs (meta + report; transcripts are gitignored)
viewers/        build_*.py -> browsable HTML for every artifact
corpus/         captured collusion.wiki pages and site chrome
data/           gitignored; rebuilt and checksum-verified by scripts/build_data.sh
docs/           design notes, data processing, audits, handoff
tests/          pytest suite for the task package and tooling
```

## How grading works

Three sheets exist and they are not the same instrument. Which one produced a score
matters more than the score.

- **`v2` finding sheets + `tldrh` summary sheet — the current scoring.** The Inspect tasks
  default to `-T rubric=v2,tldrh`, judged by `openai/gpt-5.6-sol` unless an Inspect
  `grader` model role overrides it. The scorers live in
  `messageboard_audit_bench/grading/`; per-finding credit and judge explanations land in
  the eval log.
- **`benchmark/rubrics/` — the 30-claim rubrics.** The earlier scoring, and the source of
  the historical grades in `benchmark/graded/`. Each claim was first checked against the
  data by a feasibility pass, so non-derivable claims were excluded and a model was never
  penalised for missing something unknowable.
- **`messageboard_audit_bench/rubric.yaml` — the legacy starter rubric.** Small,
  LLM-seeded, never human-validated. No longer a default; reach it with `-T rubric=legacy`.

Two consequences. Grade sets are **not comparable across sheet versions** without
regrading, so read any historical grade with its recorded grading version. And the sheet
scorer emits a numeric score even when a grader partially fails, so any aggregation meant
for publication has to check its failure metadata.

[`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) records how the 30-claim
sheets were revised after a judge audit, and why C21, C22 and C28 deliberately carry no
data note.

## Inspect integration

`pyproject.toml` registers this as an Inspect plugin, so after `uv sync` Inspect discovers
the eval by package name — no task-file path required. The default backend is fully
Inspect-managed: Inspect creates the sandbox, selects the model, enforces the time limit,
records live events and writes its `.eval` log. Claude Code and Codex run through the
official Inspect SWE agents, `agent=react` through Inspect's own. A subscription backend
remains available for results that must use a logged-in CLI, and imports that CLI's event
stream after the run.

**[`messageboard_audit_bench/README.md`](messageboard_audit_bench/README.md) is the full
reference** — every task option, the three harnesses, the integration boundary,
minimum-runtime and report-length policy, and log export.

Repo-level pieces that live outside the package: `scripts/run_inspect_matrix.sh` (runs one
model/agent/config cell with retries, timeouts and concurrency made explicit),
`scripts/export_inspect_reports.py` (bridges `.eval` logs to the report-artifact layout via
Inspect's Log API), `scripts/audit_runs.py` (summarises tool use, failures and refusals
across runs), and `experiments/*.toml` (round and ablation manifests).

A clone-based Inspect task does not need to be listed to run, and this one is directly
runnable. Official listing is a separate step with its own requirements — see
[`docs/inspect-evals-registration.md`](docs/inspect-evals-registration.md).

### Isolation

Native containers use `network_mode: none`, with no real provider credentials inside, and
a preflight records JSONL readability, hashes, the read-only data mount and network
interfaces. Inspect's model bridge disables hosted browsing.
[`docs/inspect-core-fixes.md`](docs/inspect-core-fixes.md) covers the bridge's capability
and uid posture.

Normal subscription execution is weaker and says so: agent commands can reach their
credentials and permitted vendor endpoints, and logs do not establish that communication
was impossible. See [the isolation audit](docs/isolation-audit.md) and
[`sandbox/README.md`](sandbox/README.md).

Synthetic administrator names and the Cyrillic `е` are intentional corpus clues and remain
unchanged.

## Notes on reproducibility

- `data/` is a build output, not a source. `scripts/build_data.sh` derives both variants
  deterministically and the committed `data/SHA256SUMS.variants` must reproduce exactly. A
  local variant can drift from the manifest — verify before interpreting a run.
- The dump is fetched from one upstream host but does not depend on it: any copy of the
  archive works via `MBAB_DUMP_ARCHIVE` or `MBAB_DUMP_URL`, because the pinned SHA256 is
  what establishes a copy is genuine.
- Generated viewer HTML is gitignored — rebuild with `viewers/build_*.py`.
- Run metadata in older artifacts records the absolute path of the machine that produced
  it. Those paths are provenance, not configuration.
- Every dependency carries an upper bound on purpose, so the benchmark keeps reproducing
  committed grades. Widening one means a lockfile refresh and a full test run.

## Docs

- [`docs/getting-started.md`](docs/getting-started.md) — fresh clone to graded report.
- [`docs/release-readiness.md`](docs/release-readiness.md) — what the release audit found
  and what remains before publishing results.
- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — every artifact, what
  produced it, and the run history.
- [`docs/data-processing.md`](docs/data-processing.md) — every transformation from the
  public dump to the benchmark inputs; [`docs/verbatim-data.md`](docs/verbatim-data.md)
  covers the augmented variant.
- [`docs/ablations-and-baselines.html`](docs/ablations-and-baselines.html) — how we check
  the benchmark measures investigation rather than summarisation;
  [`experiments/ablations.md`](experiments/ablations.md) is the archive inventory.
- [`docs/design-notes.md`](docs/design-notes.md), [`docs/HANDOFF.md`](docs/HANDOFF.md) —
  design rationale and operational notes.

## Working on it

Outside contributors: [`CONTRIBUTING.md`](CONTRIBUTING.md) has the fork-to-pull-request
path and, more importantly, which files are evidence rather than code.
[`SECURITY.md`](SECURITY.md) explains why the adversarial content here is subject matter
rather than a defect.

Maintainers: task work happens in linked worktrees under `.worktrees/`; the rules are in
[`AGENTS.md`](AGENTS.md). Checks: `uv run ruff check . && uv run pytest -q`.

## License

MIT — see [`LICENSE`](LICENSE). It covers the code and the benchmark material authored
here. It does not license the third-party content reproduced for research: the captured
collusion.wiki pages in `corpus/`, the human investigators' report in `benchmark/`, and the
model-generated reports in `reports/` and `baselines/`.
