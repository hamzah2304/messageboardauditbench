# MessageBoardAuditBench

A benchmark for how well an agent can investigate raw message-board logs and recover
the findings of a human audit.

The source incident is [collusion.wiki](https://collusion.wiki/index.html): ~18,000 posts
left on a public wiki by autonomous OpenAI agents that used it to coordinate on a
web-retrieval task. Human investigators wrote up what happened. We give an agent the raw
dump — and nothing else — and score its report against that write-up.

The repository also contains runnable transfer incidents based on Anthropic's
released Mythos 5 cybersecurity transcript and the malicious-package evidence
cited by the RubyHack investigation. Their narrower evidence boundaries,
freshness, and judge-independence questions prevent treating them as published
comparable cells. See the [Mythos 5](benchmark/rubrics/mythos5/README.md) and
[RubyHack](benchmark/rubrics/rubyhack/README.md) incident notes.

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

Select `config=mythos5` or `config=rubyhack` for a transfer incident. RubyHack's
selected corpus is small enough for the 10-minute exploratory condition:

```bash
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=rubyhack -T time_limit_minutes=10 \
  --model openai/gpt-5.6-sol --model-role grader=anthropic/claude-fable-5-1
```

## Publication snapshot

This checkout contains the round-4 benchmark and the followup and provider-swap
ablations used for the blog. Earlier rounds, seed baselines, prototype results,
and superseded design notes are available in Git history at
[`inspect-logs-2026-09-08`](https://github.com/hamzah2304/messageboardauditbench/tree/inspect-logs-2026-09-08).

The headline score is **70% finding coverage and 30% holistic TLDR assessment**.
Finding coverage is the mean of `max(2s - 1, 0)` across the 38 findings; the TLDR
score is graded separately. The Inspect logs expose the component scores. The
headline figures combine them using `viewers/build_headline_figures.py` and
`benchmark/figures/combined_score.json`.

Start with:

- [Results figures](viewers/figures/results_figures.md), with the plot sources and captions.
- [Evidence index](docs/benchmark-data-index.md), linking the current reports, grades,
  rubric-validation evidence, and ablations.
- [Inspect log downloads](docs/artifacts/inspect-logs.md), with checksums and a manifest
  linking the archived logs to reported samples.

The figures generally show three runs per model and budget. Missing samples and
model fallbacks are recorded in the figure data and report indexes; do not treat
all archived runs as headline samples or an Opus fallback as a single-model result.

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
viewers/        build_*.py -> browsable HTML for every artifact
data/           gitignored; rebuilt and checksum-verified by scripts/build_data.sh
docs/           setup, data processing, audits, and publication evidence
tests/          pytest suite for the task package and tooling
```

## Evaluate your own agent

The `-T agent=` harnesses are `claude`, `codex` and `react`, and there is no plugin
point for a fourth. To evaluate a scaffold that is not one of those, run it yourself
against the same conditions and grade the report it writes.

**The conditions.** A trial is comparable to the published cells only if all of these
hold:

| | |
|---|---|
| prompt | `sandbox/prompts/blind-v2.txt`, verbatim |
| data | `data/verbatim/`, mounted read-only, and nothing else |
| network | none — the agent must not reach the web or the source incident |
| budget | wall-clock; 10, 30 and 120 minutes are the published cells |
| output | one Markdown report, 2,500–3,000 words (accepted up to 3,200) |
| judge | `anthropic/claude-fable-5-1`, or your number is not comparable |

The agent must not see `benchmark/` — it holds the answer key.

**Grade it.** Put the reports in a folder as `.md` files, one per run; any absolute path
works and no index file is needed.

```bash
# both sheets, into an Inspect log each
uv run inspect eval messageboard_audit_bench/grade_reports \
  -T dir=/abs/path/to/my-reports -T rubric=v2 \
  --model-role grader=anthropic/claude-fable-5-1
uv run inspect eval messageboard_audit_bench/grade_reports \
  -T dir=/abs/path/to/my-reports -T rubric=tldrh \
  --model-role grader=anthropic/claude-fable-5-1

# file the grades where the tooling reads them
uv run python scripts/export_grades.py logs/<the-v2-run>.eval
uv run python scripts/export_grades.py logs/<the-tldrh-run>.eval

# the headline score, per report and averaged
uv run python scripts/score_reports.py benchmark/graded/judge_claude_fable_5_1
```

`score_reports.py` prints the headline beside the raw mean and the above-half fraction,
because those are the two numbers most easily mistaken for it. It reproduces the
published composite exactly for the project's own runs. `--json` gives machine-readable
output; `--v2` and `--tldrh` take the two grade directories separately.

## How grading works

The default task runs two independent graders over the submitted report:

- `v2`: eight sheets covering 38 findings extracted from the human investigation.
- `tldrh`: a holistic assessment of the report's summary against the human account.

Both receive the matching answer key. Provider-swapped inputs select the
Anthropic variant of the sheets and human report. `--model-role grader=...`
sets the judge; the published headline figures use Fable 5.1. The quick-start
example uses Sol and will therefore produce a different judge configuration.

The judge is never also a subject: Fable 5.1 appears in no run manifest and
authors none of the graded reports, so no model grades its own work.

The instructed length is 2,500–3,000 words throughout. The acceptance ceiling
is 3,200; round-4 cells recorded 3,100 and the scorer honours the ceiling each
run recorded, so `configs/blind-anthropic.toml` pins 3,100 to keep the
provider-swap twin comparable with round 4.

Per-finding grades and explanations are retained in the Inspect log. The
publication finding score applies `max(2s - 1, 0)` to each finding before averaging;
the headline score combines that with the holistic TLDR grade at weights 70/30.

When a sheet fails to grade, the scorer records the failure and still emits a score
over the sheets that survived. Any aggregate meant for publication has to read that
failure metadata rather than the score alone.
See [the evidence index](docs/benchmark-data-index.md) for source grades and
human validation records. Alternative grading sheets remain available for
compatibility and validation, but do not define the headline metric.

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
- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — the publication
  evidence index: the reports, grades, ground truth and logs behind the headline
  figures. Historical rounds sit at the `inspect-logs-2026-09-08` tag, not here.
- [`docs/data-processing.md`](docs/data-processing.md) — every transformation from the
  public dump to the benchmark inputs; [`docs/verbatim-data.md`](docs/verbatim-data.md)
  covers the augmented variant.
- [`docs/ablations-and-baselines.html`](docs/ablations-and-baselines.html) — how we check
  the benchmark measures investigation rather than summarisation;
  [`experiments/ablations.md`](experiments/ablations.md) is the archive inventory.

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
collusion.wiki pages in `corpus/`, preserved Ruby package diffs in generated data,
the human investigators' reports in `benchmark/`, and the model-generated reports
in `reports/` and historical baseline reports.
