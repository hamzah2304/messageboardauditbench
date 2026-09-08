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
and no hints about what it will be graded on. The whole thing is packaged as an
[Inspect](https://inspect.aisi.org.uk/) eval — see
[Inspect integration](#inspect-integration).

The report is then graded against the human audit. The current Inspect task uses the
**38-finding sheets** (`v2`) for coverage and a separate **summary-quality sheet**
(`tldrh`); per-finding credit and judge explanations are saved in the eval log. Earlier
rounds used the 30-claim rubrics in `benchmark/rubrics/`, scored for recall and for a
1–10 precision judge. See [How grading works](#how-grading-works) — the two are different
sheets and their scores are not interchangeable.

Because the budget is part of the condition, a score means nothing without the budget it
was measured at. This measures investigation, not recall of things already known.

## Quick start

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/) and Docker. Full walk-through
with credentials and troubleshooting: [`docs/getting-started.md`](docs/getting-started.md).

```bash
uv sync --frozen
scripts/build_data.sh
# Set OPENAI_API_KEY for this example's agent and grader.
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=blind -T time_limit_minutes=30 \
  --model openai/gpt-5.6-sol --model-role grader=openai/gpt-5.6-sol
uv run inspect view
```

The eval runs the finding (`v2`) and summary (`tldrh`) graders inline by default. Use
`--no-score` to defer grading. [`docs/getting-started.md`](docs/getting-started.md) also
covers the provider-attribution and followup ablations, and `scripts/doctor.sh` checks
prerequisites and prints the fix for anything missing.

## Results

Measured results are reported in the accompanying write-up, not here, so that this README
stays a description of the benchmark rather than a snapshot that goes stale every round.
The public results definition is not yet frozen — see item 3 of
[`docs/release-readiness.md`](docs/release-readiness.md) before quoting any number from
this repository.

What lives in the repo:

- `benchmark/graded/` — every committed per-claim and per-finding grade, per report, per
  round. File names encode round, budget, harness, model and replicate.
- `benchmark/graded_inputs/` — byte-identical copies of the reports those grades came from,
  keyed to match, so any score traces to its exact input.
- `reports/` — the full model report corpus, grouped by benchmark config, with an
  `index.jsonl` per set carrying run metadata.
- `viewers/build_*.py` — build browsable HTML over all of it.
- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — every artifact, what
  produced it, and the run history.
- [`experiments/ablations.md`](experiments/ablations.md) — the provider-attribution and
  followup ablations: staged folders, inventory, and rebuild/grading commands.

`scripts/report_performance.py <graded-dir>` aggregates a graded directory if you want to
recompute numbers yourself. Note that it applies the figures' stricter transform,
`max(2s - 1, 0)` per finding, which is **not** the raw mean the Inspect sheet scorer
reports.

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
paths.py        every script resolves its inputs through this
```

## Running it

Two routes to the same task: the Inspect/Inspect SWE path above, or the subscription
scripts directly. Both use the benchmark image, network-disabled workspace, prompt, and
data.

```bash
uv sync                        # or: pip install -e .

scripts/build_data.sh          # fetch + build data/, verify against SHA256SUMS.variants
scripts/build_data.sh --verify # check an existing build

# run a trial: <agent> <model> <replicate>, conditions from CONFIG
# (needs Docker; see sandbox/README.md for credentials)
ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/blind-20.toml sandbox/docker/run_trial.sh claude claude-opus-5 1

# collect and stage reports, then grade a set
scripts/collect_reports.py
scripts/stage_graded_inputs.py reports blind-30=my_round:mr

# rebuild the browsable viewers
cd viewers && for f in build_*.py; do python "$f"; done
python3 -m http.server 8765 --directory viewers
```

All scripts resolve their inputs through `paths.py` at the repo root, so the repo works
from a plain clone.

## How grading works

Grading has moved; which sheet produced a score matters more than the score.

- **`v2` finding sheets + `tldrh` summary sheet — the current scoring.** The Inspect
  tasks default to `-T rubric=v2,tldrh` and run both graders inline, with
  `openai/gpt-5.6-sol` as the default judge (an Inspect `grader` model role overrides it).
  The scorers live in `messageboard_audit_bench/grading/`. Per-finding credit and judge
  explanations land in the eval log.
- **`benchmark/rubrics/` — the 30-claim rubrics.** The earlier scoring, and the source of
  the historical committed grades in `benchmark/graded/`, via `grade_with_rubrics.py`.
  Each of the 30 claims was first checked against the data by a feasibility pass
  (`benchmark/feasibility/`), so non-derivable claims were excluded and a model was never
  penalised for missing something unknowable.
- **`messageboard_audit_bench/rubric.yaml` — the legacy starter rubric.** A small,
  LLM-seeded sheet that has never been human-validated. It is no longer a default; reach
  it with `-T rubric=legacy` only.

Two consequences worth stating plainly. Grade sets are **not comparable across sheet
versions** without regrading, so read any historical grade with its recorded grading
version. And the default Inspect sheet score is a **mean of per-finding credit**, while
the figure pipeline applies `max(2s - 1, 0)` to each finding before averaging — that is
not a binary fraction of findings above 0.5, and the two produce different rankings as
well as different levels.

The sheet scorer records partial grader failures but still emits a numeric score over the
surviving sheets, so any aggregation meant for publication has to check its failure
metadata.

### What the 30-claim judge sheets carry

Applies to the 30-claim rubrics above, and to the historical grades produced from them.

An audit of the strongest long-budget report (`benchmark/audit/judge_audit.json`) found
the sheets were withholding from the judge the very ground truth the feasibility pass had
established. Each claim in `rubric_N.json` carries a feasibility note, corrections and a
trap; `build_rubrics.py` rendered none of it. The judge got a claim, one quote and a
generic three-band scale, and set its own strictness. Three changes followed:

- each claim now carries **what the data supports**, from the feasibility pass;
- the half-point band is **vagueness only**, with an explicit rule not to deduct for
  wording, for extra detail, or for a range where the claim is itself hedged;
- **C02** no longer scores the training-versus-testing hedge as a specific.

**C21, C22 and C28 deliberately carry no data note.** Their gradeability flips with the
data variant, the feasibility notes describe the stripped dump, and the rounds graded on
these sheets all used verbatim. Rendering those notes told the judge the correct answer
was "not determinable" and penalised reports for stating something true. Until a sheet
knows which variant it is grading, these three are graded as before.

## Inspect integration

The repo is packaged as an installable [Inspect](https://inspect.aisi.org.uk/) eval.
`pyproject.toml` registers `messageboard_audit_bench` as an Inspect plugin and
`messageboard_audit_bench/__init__.py` exports the task functions, so after `uv sync`
Inspect discovers the eval by package name — no task-file path required.

The default backend is fully Inspect-managed: Inspect creates the Docker sandbox, selects
the model, enforces the agent time limit, records live model and tool events, and writes
its standard `.eval` log. Claude Code and Codex use the official Inspect SWE agents;
`agent=react` uses Inspect's built-in agent. The subscription backend remains available
for results that must use a logged-in CLI, and imports that CLI's event stream after the
run.

| file | role |
|---|---|
| `task.py` | fresh, replay, and ReAct continuation tasks |
| `native.py` | runs Claude Code/Codex through Inspect SWE, or Inspect's ReAct agent, and collects `report.md` |
| `solver.py` | `subscription_agent` launches the subscription runner; `replay` imports a finished run |
| `transcripts.py` | loss-aware conversion of subscription/historical CLI events into Inspect messages and tool calls |
| `scorer.py` | report-quality, process, and report-length scorers |
| `grading/` | current finding and summary sheet scorers; `rubric.yaml` is the optional legacy rubric |

The config, time, and minimum-runtime dimensions are independent: `-T config=blind|context`,
`-T time_limit_minutes=N`, and `-T min_runtime_fraction=F`. Add
`-T data_variant=verbatim_anthropic` for the provider-attribution ablation; the sheet
grader selects the matching answer key.

**[`messageboard_audit_bench/README.md`](messageboard_audit_bench/README.md) is the full
reference** — every task option, the three harnesses, the subscription backend, the
integration boundary, minimum-runtime and report-length policy, and log export.

A few things that live at repo level rather than in the package:

- `scripts/run_inspect_matrix.sh` runs one explicit model/agent/config cell, making its
  API retries, timeouts, concurrency, sample retries and refusal logging explicit. It
  defaults to at most two sample reruns after an error and uses `caffeinate` on macOS.
  Muse models always run with `--max-connections 2`; others default to 4.
- `scripts/export_inspect_reports.py` bridges native `.eval` logs to the report-artifact
  layout the graders expect, through Inspect's Log API rather than parsing `.eval` files.
- `scripts/audit_runs.py --runs runs --out audit.json` summarises tool types, failures,
  refusal signals, parallel batches and visible time reminders across runs. See
  [`docs/trajectory-audit.md`](docs/trajectory-audit.md) and
  [`docs/corpus-audit.md`](docs/corpus-audit.md).
- `experiments/*.toml` are the manifests for multi-cell rounds and ablations;
  [`experiments/ablations.md`](experiments/ablations.md) documents the staged archives.

### Isolation

Native containers use `network_mode: none`, with no real provider credentials inside. A
preflight records full JSONL readability, hashes, read-only data mount, visible work
files, and network interfaces. Inspect's model bridge disables hosted browsing.

Normal subscription execution preserves the built-in tools and uses the accepted
restricted-proxy setup — agent commands can reach their credentials and permitted vendor
endpoints, and logs do not establish that communication was impossible. This trade-off is
stated rather than hidden; see [the isolation audit](docs/isolation-audit.md) and
[`sandbox/README.md`](sandbox/README.md).

Synthetic administrator names and the Cyrillic `е` are intentional corpus clues and remain
unchanged.

### Official Inspect Evals register

A clone-based Inspect task does not need to be listed to run, and this repo is directly
runnable as-is. Listing is a separate step: the register requires pinned external assets,
an arXiv URL, a source commit, and full eval logs from two models. The current
collusion.wiki download has a checksum but not an immutable project-controlled URL. See
[`docs/inspect-evals-registration.md`](docs/inspect-evals-registration.md) for the exact
handoff and the source-asset provenance.

## Notes on reproducibility

- `data/` is a build output, not a source. `scripts/build_data.sh` fetches the public dump
  and derives both variants deterministically; the committed `data/SHA256SUMS.variants`
  must reproduce exactly. A local variant can drift from the manifest — verify before
  interpreting a run, and see item 1 of
  [`docs/release-readiness.md`](docs/release-readiness.md).
- Generated viewer HTML is gitignored — rebuild with `viewers/build_*.py`. The one
  exception is `viewers/coverage_combined.html`, whose builder needs a rendered
  collusion.wiki bundle that is not redistributed here.
- `benchmark/graded_inputs/` holds byte-identical copies of the reports in `reports/`,
  keyed to match their grade files, so every committed score can be traced to its input.
- `benchmark/legacy_68claim/` is the superseded first-pass pipeline, kept for provenance.
- Run metadata in older report and grade artifacts records the absolute path of the
  machine that produced it. Those paths are provenance, not configuration.

## Docs

- [`docs/getting-started.md`](docs/getting-started.md) — fresh clone to graded report:
  prerequisites, credentials per harness, smoke test, grading, troubleshooting.
- [`docs/release-readiness.md`](docs/release-readiness.md) — what the release audit
  found and what remains to reconcile before publishing results.
- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — every artifact, what
  produced it, and the full run history.
- [`docs/ablations-and-baselines.html`](docs/ablations-and-baselines.html) — how we check
  the benchmark measures investigation rather than summarisation;
  [`experiments/ablations.md`](experiments/ablations.md) is the archive inventory.
- [`docs/data-processing.md`](docs/data-processing.md) — every transformation from the
  public dump to the benchmark inputs; [`docs/verbatim-data.md`](docs/verbatim-data.md)
  covers the augmented variant.
- [`docs/discord-corpus-handoff.md`](docs/discord-corpus-handoff.md) — analysis of the
  swarmchasers Discord corpus, **including the prompt-injection payloads it contains**.
  Read it before pointing an agent at any copy of that export.
  [`docs/discord-findings-diff.md`](docs/discord-findings-diff.md) diffs it against the
  human report and claims. The export itself is not distributed here: it carries named
  participants' messages and Discord identifiers, and nothing in the benchmark reads it.
- [`docs/design-notes.md`](docs/design-notes.md), [`docs/HANDOFF.md`](docs/HANDOFF.md) —
  design rationale and operational notes.
- [`sandbox/README.md`](sandbox/README.md) — how isolation actually works.
- [`messageboard_audit_bench/README.md`](messageboard_audit_bench/README.md) — the Inspect
  task package in full.

## Working on it

Outside contributors: [`CONTRIBUTING.md`](CONTRIBUTING.md) has the fork-to-pull-request
path and, more importantly, which files are evidence rather than code.
[`SECURITY.md`](SECURITY.md) covers private reporting, and why the adversarial content in
this repository is the subject matter rather than a defect.

Maintainers: task work happens in linked worktrees under `.worktrees/`, created with
`scripts/worktree_add.sh <task>`; the primary checkout stays on `main`. The rules for
worktrees, merging and shared run data are in [`AGENTS.md`](AGENTS.md).

Checks: `uv run ruff check . && uv run pytest -q`.

## License

MIT — see [`LICENSE`](LICENSE). The license covers the code and the benchmark material
authored here (claims, feasibility notes, rubrics, prompts, tooling). It does not license
the third-party content reproduced for research: the captured collusion.wiki pages in
`corpus/`, the human investigators' report in `benchmark/`, and the model-generated
reports in `reports/` and `baselines/`. `LICENSE` lists these explicitly.
