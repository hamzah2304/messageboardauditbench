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

Its report is then graded on two axes against **30 claims** drawn from the human audit:

- **Recall** — of the claims the data can actually support, how many did it find?
- **Precision** — a 1–10 judge score counting assertions that contradict the human report.

Claims are only counted when the dump can support them. A separate feasibility pass
(`benchmark/feasibility/`) checked all 30 against the data; the non-derivable ones are
excluded, so a model is never penalised for missing something unknowable. Claims that
flip between data variants (C21/C22/C28) carry a per-variant note.

Because the budget is part of the condition, a score means nothing without the budget it
was measured at. This measures investigation, not recall of things already known.

## Quick start

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/) and Docker. Full walk-through
with credentials and troubleshooting: [`docs/getting-started.md`](docs/getting-started.md).

```bash
uv sync && scripts/build_data.sh && scripts/doctor.sh      # install, build data/, preflight

CONFIG=blind-30 sandbox/docker/run_trial.sh claude claude-opus-5 1    # one trial -> runs/<run>/report.md

scripts/collect_reports.py                                  # runs/ -> reports/
scripts/stage_graded_inputs.py reports blind-30=my_round:mr
python benchmark/rubrics/grade_with_rubrics.py --dir my_round   # grade it (needs OPENAI_API_KEY)
```

Or run the same trial through Inspect; see [Inspect integration](#inspect-integration).

## Results

Measured results are reported in the accompanying write-up, not here, so that this README
stays a description of the benchmark rather than a snapshot that goes stale every round.

What lives in the repo:

- `benchmark/graded/` — every committed per-claim grade, per report, per round. File names
  encode round, budget, harness, model and replicate.
- `benchmark/graded_inputs/` — byte-identical copies of the reports those grades came from,
  keyed to match, so any score traces to its exact input.
- `reports/` — the full model report corpus, grouped by benchmark config, with an
  `index.jsonl` per set carrying run metadata.
- `viewers/build_*.py` — build browsable HTML over all of it.
- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — every artifact, what
  produced it, and the run history.

`scripts/report_performance.py <graded-dir>` aggregates a graded directory if you want to
recompute numbers yourself.

## Layout

```
benchmark/      ground truth: human_report.txt (answer key), claims, feasibility,
                rubrics, graded results, and the exact reports each grade came from
messageboard_audit_bench/
                the Inspect task package — wraps the sandbox as an inspect eval
sandbox/        isolated trial runner (Docker), API proxy, ReAct scaffold, prompts
scripts/        data build/fetch, grading, report collection, analysis
configs/        trial conditions (budget, prompt, data variant, effort)
experiments/    manifests for the multi-cell rounds and ablations
reports/        the model report corpus, by benchmark config
baselines/      early trial runs (meta + report; transcripts are gitignored)
viewers/        build_*.py -> browsable HTML for every artifact
corpus/         raw message-board and chat exports
data/           gitignored; rebuilt and checksum-verified by scripts/build_data.sh
docs/           design notes, data processing, audits, handoff
tests/          pytest suite for the task package and tooling
paths.py        every script resolves its inputs through this
```

## Running it

Two routes to the same task: the subscription scripts directly, or the
first-class Inspect/Inspect SWE path (see [Inspect integration](#inspect-integration)).
Both use the benchmark image, network-disabled workspace, prompt, and data.
[`docs/getting-started.md`](docs/getting-started.md) walks through setup end to end;
`scripts/doctor.sh` checks the prerequisites and prints the fix for anything missing.

```bash
uv sync                        # or: pip install -e .

scripts/build_data.sh          # fetch + build data/, verify against SHA256SUMS.variants
scripts/build_data.sh --verify # check an existing build

# run a trial: <agent> <model> <replicate>, conditions from CONFIG
# (needs Docker; see sandbox/README.md for credentials)
ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/blind-20.toml sandbox/docker/run_trial.sh claude claude-opus-5 1

# grade a report set against the 30-claim rubrics
python benchmark/rubrics/grade_with_rubrics.py --dir round3_blind120

# rebuild the browsable viewers
cd viewers && for f in build_*.py; do python "$f"; done
python3 -m http.server 8765 --directory viewers
```

All scripts resolve their inputs through `paths.py` at the repo root, so the repo works
from a plain clone.

## How grading works

Two grading paths exist, and they are not the same rubric:

- **`benchmark/rubrics/` — the 30-claim rubrics.** Every committed grade in
  `benchmark/graded/` came from here, via `grade_with_rubrics.py` with a GPT-5.6 Sol
  judge. Each claim was first checked against the data by the feasibility pass, so
  non-derivable claims are excluded. **This is the benchmark's scoring.**
- **`messageboard_audit_bench/rubric.yaml` — the Inspect scorer's rubric.** A smaller,
  LLM-seeded starter rubric: 12 weighted positive leaves (tagged derivable yes/partly)
  plus 3 penalty leaves for specific over-claims, such as asserting this is the same
  swarm that attacked Hugging Face. It has not been human-validated. It exists so an
  `inspect eval` returns a score in one command.

So Inspect is the run-and-inspect harness here, not the source of reported results. Treat
`rubric_scorer` output as indicative until `rubric.yaml` is validated the way the 30
claims were; [`docs/design-notes.md`](docs/design-notes.md) sketches the claim-precision
and citation-support scorers meant to close that gap.

### What the judge sheets carry

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
data variant, the feasibility notes describe the stripped dump, and the rounds graded so
far all used verbatim. Rendering those notes told the judge the correct answer was "not
determinable" and penalised reports for stating something true. Until a sheet knows which
variant it is grading, these three are graded as before.

Grade sets are not comparable across sheet revisions without regrading. The sheet revision
that produced a grade is recorded with it.

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

```bash
uv sync                                    # installs Inspect and this package
scripts/build_data.sh                      # downloads and verifies the dataset
export ANTHROPIC_API_KEY=...               # native Claude + default judge

uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=claude -T config=blind -T time_limit_minutes=30 \
  --model anthropic/claude-opus-4-1 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1

uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_replay  # import runs on disk
uv run inspect view                                                           # browse the .eval logs
```

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
- `experiments/*.toml` are the manifests for multi-cell rounds and ablations.

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

This repository follows the upstream packaging conventions for an externally managed
Inspect eval: PEP 517 packaging, an `inspect_ai` entry point, exported `@task` functions,
versioned task metadata, pinned asset checksums, and an end-to-end mock-model test. It is
not yet listed in the official register, which also requires an immutable dataset host, a
public pinned code commit, and an arXiv paper. See
[`docs/inspect-evals-registration.md`](docs/inspect-evals-registration.md) for the exact
handoff and the source-asset provenance.

## Notes on reproducibility

- `data/` is a build output, not a source. `scripts/build_data.sh` fetches the public dump
  and derives both variants deterministically; the committed `data/SHA256SUMS.variants`
  must reproduce exactly.
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
- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — every artifact, what
  produced it, and the full run history.
- [`docs/ablations-and-baselines.html`](docs/ablations-and-baselines.html) — how we check
  the benchmark measures investigation rather than summarisation.
- [`docs/data-processing.md`](docs/data-processing.md) — every transformation from the
  public dump to the benchmark inputs; [`docs/verbatim-data.md`](docs/verbatim-data.md)
  covers the augmented variant.
- [`docs/discord-corpus-handoff.md`](docs/discord-corpus-handoff.md) — the swarmchasers
  Discord corpus, **including the prompt-injection payloads it contains**. Read this
  before pointing an agent at `corpus/`.
  [`docs/discord-findings-diff.md`](docs/discord-findings-diff.md) diffs it against the
  human report and claims.
- [`docs/design-notes.md`](docs/design-notes.md), [`docs/HANDOFF.md`](docs/HANDOFF.md) —
  design rationale and operational notes.
- [`sandbox/README.md`](sandbox/README.md) — how isolation actually works.
- [`messageboard_audit_bench/README.md`](messageboard_audit_bench/README.md) — the Inspect
  task package in full.

## Working on it

Task work happens in linked worktrees under `.worktrees/`, created with
`scripts/worktree_add.sh <task>`; the primary checkout stays on `main`. The rules for
worktrees, merging and shared run data are in [`AGENTS.md`](AGENTS.md).

Checks: `uv run ruff check . && uv run pytest -q`.

## Licence

MIT — see [`LICENSE`](LICENSE). The licence covers the code and the benchmark material
authored here (claims, feasibility notes, rubrics, prompts, tooling). It does not license
the third-party content reproduced for research: the `corpus/` exports, the human
investigators' report in `benchmark/`, and the model-generated reports in `reports/` and
`baselines/`. `LICENSE` lists these explicitly.
