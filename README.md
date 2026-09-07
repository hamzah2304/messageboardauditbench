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

## Headline result

Round 2, blind prompt on the verbatim data, xhigh effort, mean recall across
replicates at three wall-clock budgets:

| harness · model | 10 min | 20 min | 30 min |
|---|---|---|---|
| claude · opus-5 | 0.283 | 0.413 | **0.510** |
| react · sol | 0.467 | 0.475 | 0.500 |
| react · kimi-k3 | 0.333 | 0.319 | 0.449 |
| react · gemini-flash | 0.382 | — | 0.425 |
| codex · sol | 0.417 | 0.358 | 0.400 |
| react · glm-5.3 | 0.383 | 0.420 | 0.392 |
| claude · fable | 0.367 | 0.383 | — |
| codex · terra | 0.259 | 0.242 | 0.334 |
| codex · luna | 0.209 | 0.192 | 0.333 |
| claude · sonnet-5 | 0.145 | 0.175 | 0.242 |
| claude · haiku-4.5 | 0.067 | 0.075 | 0.125 |

The benchmark is far from saturated: the best configuration recovers about half
the derivable claims, and the weakest recovers an eighth.

Recall is strongly budget-sensitive, which is the point — this measures
investigation, not recall of things already known. Opus 5 climbs steadily with
time (0.283 → 0.413 → 0.510) and is the only model to clear 0.5. react·sol is
strong immediately but plateaus around 0.47–0.50, so ranking at one budget says
little about ranking at another.

Read the top row with some caution: opus-5 at 30 min is a single replicate, as is
claude·fable at 10 and 20 min. Dashes are missing runs, not zeros. Per-claim scores
are in `benchmark/graded/`.

### Round 3 — three replicates, two more models, a 2-hour budget

Same blind prompt and verbatim data, at 10, 30 and 120 minutes. The 10- and
30-minute prompts are byte-identical to round 2's; blind-120 differs only in the
budget it states. 76 reports, graded on the **revised sheets** (see below), so these
numbers are not comparable with round 2's without regrading round 2.

| harness · model | 10 min | 30 min | 120 min |
|---|---|---|---|
| codex · sol | 0.373* | 0.683* | **0.735** |
| react · sol | 0.500* | 0.600* | 0.689 |
| codex · astra | 0.468 | 0.564 | 0.652 |
| claude · opus-5 | 0.410* | 0.546 | — |
| react · muse-spark | 0.461 | 0.500 | 0.543 |
| react · gemini-flash | 0.300* | 0.443* | 0.513 |
| codex · luna | 0.233* | 0.350* | 0.513 |
| claude · opus-4.8 | 0.293 | 0.381 | 0.473 |
| react · glm-5.3 | 0.303* | 0.463* | — |
| claude · sonnet-5 | 0.130* | 0.270* | 0.450 |
| react · kimi-k3 | 0.340* | 0.433* | — |
| codex · terra | 0.317* | 0.427* | 0.385 |
| claude · fable | 0.400* | — | — |
| claude · haiku-4.5 | 0.127* | 0.093* | 0.200 |

`*` marks a cell resting on one replicate; dashes are missing runs, not zeros.

Nothing plateaus at two hours. Every model with a 120-minute cell scores highest
there, and the mean across harness/model pairs rises 0.333 → 0.443 → 0.515. The best
configuration recovers about three quarters of the derivable claims.

Eight runs sit outside the table because Claude Code switched model after a
safeguard refusal; they are graded under their served name, and `model_served` in
`reports/round3/index.jsonl` records each switch.

| nominal → served | 10 min | 30 min | 120 min |
|---|---|---|---|
| claude · fable → opus-5 | 0.470* | 0.600* | — |
| claude · opus-5 → opus-4.8 | — | 0.560* | 0.500 |
| claude · fable → opus-4.8 | — | 0.454 | — |

### What the judge sheets say now

An audit of the strongest 2-hour report (23 of its 30 claims, in
`benchmark/audit/judge_audit.json`) found the sheets were withholding from the judge
the very ground truth the feasibility pass had established. Each claim in
`rubric_N.json` carries a feasibility note, corrections and a trap; `build_rubrics.py`
rendered none of it. The judge got a claim, one quote and a generic three-band scale,
and set its own strictness — docking C10 for saying R1–R6 when the ground truth states
in writing that the R6/R7 tail justifies the claim's own "usually 5".

Three changes followed, and round 3 was regraded on them:

- each claim now carries **what the data supports**, from the feasibility pass;
- the half-point band is **vagueness only**, with an explicit rule not to deduct for
  wording, for extra detail, or for a range where the claim is itself hedged;
- **C02** no longer scores the training-versus-testing hedge as a specific.

Mean recall rose 0.434 → 0.457 across the 76 reports, 58 up and 16 down. The movement
is concentrated where it was aimed: C10 +0.301, C11 +0.266, C02 +0.182. On the audited
report the judge now agrees with the auditor's own score on 20 of 22 claims, up from 18,
and scores it 0.723 against the auditor's 0.717.

**C21, C22 and C28 deliberately carry no data note.** Their gradeability flips with the
data variant, the feasibility notes describe the stripped dump, and every round-2 and
round-3 run used verbatim. Rendering those notes told the judge the correct answer was
"not determinable" and drove C22 to 0.000 across all 76 reports — penalising reports for
stating something true. Until a sheet knows which variant it is grading, these three are
graded as before.

## Layout

```
benchmark/      ground truth: human_report.txt (answer key), claims, feasibility,
                rubrics, graded results, and the exact reports each grade came from
messageboard_audit_bench/
                the Inspect task package — wraps the sandbox as an inspect eval
sandbox/        isolated trial runner (Docker), API proxy, ReAct scaffold, prompts
scripts/        data build/fetch, grading, report collection
configs/        trial conditions (budget, prompt, data variant, effort)
reports/        the model report corpus, by benchmark config
baselines/      early trial runs (meta + report; transcripts are gitignored)
viewers/        build_*.py -> browsable HTML for every artifact
corpus/         raw message-board exports
data/           gitignored; rebuilt and checksum-verified by scripts/build_data.sh
docs/           design notes, data processing, handoff
```

## Running it

Two routes to the same task: the subscription scripts directly, or the
first-class Inspect/Inspect SWE path (see [Inspect integration](#inspect-integration)).
Both use the benchmark image, network-disabled workspace, prompt, and data.

```bash
uv sync                        # or: pip install -e .

scripts/build_data.sh          # fetch + build data/, verify against SHA256SUMS.variants
scripts/build_data.sh --verify # check an existing build

# run a trial: <agent> <model> <replicate>, conditions from CONFIG
# (needs Docker; see sandbox/README.md for credentials)
CONFIG=configs/blind-20.toml sandbox/docker/run_trial.sh claude claude-opus-5 1

# grade a report set against the 30-claim rubrics
python benchmark/rubrics/grade_with_rubrics.py --dir round3_blind120

# rebuild the browsable viewers
cd viewers && for f in build_*.py; do python "$f"; done
python3 -m http.server 8765 --directory viewers
```

All scripts resolve their inputs through `paths.py` at the repo root, so the repo works
from a plain clone.

## Docs

- [`docs/benchmark-data-index.md`](docs/benchmark-data-index.md) — every artifact, what
  produced it, and the full run history.
- [`docs/ablations-and-baselines.html`](docs/ablations-and-baselines.html) — how we check
  the benchmark measures investigation rather than summarisation.
- [`docs/data-processing.md`](docs/data-processing.md) — every transformation from the
  public dump to the benchmark inputs; [`docs/verbatim-data.md`](docs/verbatim-data.md)
  covers the augmented variant.
- [`docs/design-notes.md`](docs/design-notes.md), [`docs/HANDOFF.md`](docs/HANDOFF.md) —
  design rationale and operational notes.
- [`sandbox/README.md`](sandbox/README.md) — how isolation actually works.
- [`messageboard_audit_bench/README.md`](messageboard_audit_bench/README.md) — the Inspect task
  package in full.

## Inspect integration

The repo is packaged as an installable [Inspect](https://inspect.aisi.org.uk/)
eval. `pyproject.toml` registers `messageboard_audit_bench` as an Inspect plugin,
and `messageboard_audit_bench/__init__.py` exports the task functions. After `uv sync`,
Inspect can discover the eval by package name; no task-file path is required.

The default backend is fully Inspect-managed. Inspect creates the Docker
sandbox, selects the model, enforces the agent time limit, records live model
and tool events, and writes its standard `.eval` log. Claude Code and Codex use
the official Inspect SWE agents; ReAct uses Inspect's built-in agent. The
subscription backend remains available for results that must use a logged-in
CLI, but imports that CLI's event stream after the run.

| file | role |
|---|---|
| `task.py` | two tasks: `messageboard_audit_bench` (fresh trials) and `messageboard_audit_bench_replay` (import runs already on disk) |
| `native.py` | runs Claude Code/Codex through Inspect SWE, or Inspect's ReAct agent, and collects `report.md` |
| `solver.py` | `subscription_agent` launches the subscription runner; `replay` imports a finished run |
| `transcripts.py` | loss-aware conversion of subscription/historical CLI events into Inspect messages and tool calls |
| `scorer.py` | report-quality, process, and report-length scorers |
| `rubric.yaml` | the rubric that scorer grades against |

```bash
uv sync                                    # installs Inspect and this package
scripts/build_data.sh                      # downloads and verifies the dataset
export ANTHROPIC_API_KEY=...               # native Claude + default judge
export OPENAI_API_KEY=...                  # native Codex when using OpenAI

# Native Claude Code. The agent model is Inspect's normal --model option.
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=claude -T config=blind -T time_limit_minutes=30 \
  -T min_runtime_fraction=0.75 \
  --model anthropic/claude-opus-4-1 \
  --model-role grader=anthropic/claude-sonnet-4-5 \
  --epochs 3 --max-samples 1

# Native Codex CLI with the same task and Inspect plumbing.
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=codex -T config=blind -T time_limit_minutes=30 \
  --model openai/gpt-5 \
  --model-role grader=anthropic/claude-sonnet-4-5

# Subscription-authenticated CLI (no agent API key/model is consumed by Inspect).
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T backend=subscription -T agent=claude \
  -T subscription_model=claude-opus-5 \
  -T config=blind -T time_limit_minutes=30 \
  -T judge=anthropic/claude-sonnet-4-5 --max-samples 1

# or fold runs already on disk into one eval, without spending model time
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_replay

uv run inspect view                        # browse the .eval logs

# Export native reports for the existing report/grade tooling. This reads logs
# through Inspect's Log API; it does not parse .eval files directly.
uv run python scripts/export_inspect_reports.py --logs logs --out reports/native

# Run one explicit model/agent/config cell. On macOS this prevents sleep.
scripts/run_inspect_matrix.sh --agent claude --config blind \
  --model anthropic/claude-opus-4-1 --epochs 3
```

`-T agent=claude` runs Claude Code, `-T agent=codex` runs Codex CLI, and
`-T agent=react` runs Inspect's model-neutral ReAct agent. Claude Code is the
default. With `backend=inspect`, all three use Inspect's `--model`, provider
prompt cache, scoped limits, and live logging. Every native harness receives a
time note after each tool call; Claude Code and Codex receive it through their
lifecycle hooks, while Inspect ReAct receives it in the wrapped tool result.
The prompt also lets every harness call `time_left` on demand. Both mechanisms
use the same scoped deadline. With `backend=subscription`, use
`-T subscription_model=...`; this deliberately runs outside Inspect's model
provider and then converts the recorded CLI events for the viewer.

The config, time, and minimum-runtime dimensions are independent: use
`-T config=blind|context`, `-T time_limit_minutes=N`, and optionally
`-T min_runtime_fraction=F`. The fraction defaults to `0.75`: a normal finish
before 75% of the configured budget resumes the same investigation, with a
prompt asking the agent to verify evidence and improve `report.md` rather than
idle. The exact fraction and earliest permitted finish are stated in the
prompt. Set the fraction to `0` only for an ablation. Terminal refusals,
failures, and hard limits are not resumed. Time-bearing legacy config names
remain available to direct sandbox scripts but are not part of the Inspect
interface. Subscription agents are told exactly N minutes; their container gets
a five-minute shutdown/write grace, followed by a separate five-minute host
recovery guard so transcript folding is not cut off. A Codex capacity failure
before its first completed turn is relaunched at most twice.
The `blind` config uses the provenance-recorded `blind-v2` prompt; `context`
retains its own prompt. Prompt templates and config names are intentionally
separate.

`--epochs N` is Inspect's standard option for N independent replicates; the
replicate number identifies a run and does not seed sampling. Use
`--max-samples 1` to serialize epochs against a subscription-backed CLI.
`messageboard_audit_bench_replay` reads `runs/`, which is
gitignored — it only has anything to import on a machine that has run trials.

`export_inspect_reports.py` is the bridge from native `.eval` logs to the
report-artifact layout used by downstream graders. It exports only native
`backend=inspect` samples by default. Passing `--backend all` includes imported
subscription samples. Reports are grouped by the actual scaffold, so native and
subscription Claude Code (or Codex CLI) runs can be analyzed together; backend
remains on every index row. The two ReAct implementations stay separate.
`run_inspect_matrix.sh` makes its API retries, request/attempt timeouts,
sample/sandbox/API concurrency, sample retries, and raw API/refusal logging
explicit. It defaults to at most two sample reruns after an error and uses
`caffeinate` on macOS; it intentionally does not impose a disk-space floor.
Muse models always run with an explicit `--max-connections 2`; the wrapper
rejects a conflicting value. Other models default to 4.

The round-3 prompt targets 2,500–3,000 words. Short, nonempty reports are
accepted; reports up to 3,100 words pass the separate length score. The agent
does not see that tolerance. After-tool checks stay silent unless `report.md`
is over 3,000 words. A Claude Code or Codex Stop hook, or the native wrapper's
post-hoc guard, can request one shortening pass when at least a minute remains.
Subscription hooks implement the same policy. Missing, empty, and short reports
are never used to force additional work; normal early completion is resumed only
until the configured minimum runtime. Native log metadata records the configured
fraction, minimum seconds, and whether the PostToolUse and Stop hooks fired.

Provider refusals are retried at most twice through the same model. A terminal
native refusal is recorded from Inspect's `content_filter` stop reason in
sample metadata; no model fallback occurs. The batch runner independently
allows at most two whole-sample retries for actual sample errors.

Provider prompt caching is explicitly enabled on the native backend with
Inspect's `cache_prompt=True`; Inspect's `.eval` usage records separate cache
read and cache write tokens. Subscription/replay logs retain the CLI-reported
cache counters. No converter can make an old external run into an Inspect SWE
run—Inspect SWE is the live execution bridge—but the importer maps its complete
trajectory into the same Inspect chat/tool representation used by the UI.
Sample metadata records both `scaffold` and `backend`: Claude Code and Codex CLI
can be grouped across API and subscription transports, while Inspect ReAct and
the legacy subscription ReAct loop remain distinct scaffolds.

### Which scorer produced the headline numbers

Two grading paths exist, and they are not the same rubric:

- **`benchmark/rubrics/` — the 30-claim rubrics.** Every committed grade in
  `benchmark/graded/` and every figure in the table above came from here, via
  `grade_with_rubrics.py` with a GPT-5.6 Sol judge. Each claim was first checked
  against the data by the feasibility pass, so non-derivable claims are excluded.
  This is the benchmark's scoring.
- **`messageboard_audit_bench/rubric.yaml` — the Inspect scorer's rubric.** A smaller,
  LLM-seeded starter rubric: 12 weighted positive leaves (tagged derivable
  yes/partly) plus 3 penalty leaves for specific over-claims, such as asserting
  this is the same swarm that attacked Hugging Face. It has not been
  human-validated. It exists so an `inspect eval` returns a score in one command.

So Inspect is the run-and-inspect harness here, not the source of the reported
results. Treat `rubric_scorer` output as indicative until `rubric.yaml` is
validated the way the 30 claims were; `docs/design-notes.md` sketches the
claim-precision and citation-support scorers meant to close that gap.

### Official Inspect Evals register

This repository follows the upstream packaging conventions for an externally
managed Inspect eval: PEP 517 packaging, an `inspect_ai` entry point, exported
`@task` functions, versioned task metadata, pinned asset checksums, and an
end-to-end mock-model test. It is not yet listed in the official Inspect Evals
register. Registration also requires an immutable dataset host, a public pinned
code commit, and an arXiv paper. See
[`docs/inspect-evals-registration.md`](docs/inspect-evals-registration.md) for
the exact handoff and the source-asset provenance.

## Notes on reproducibility

- `data/` is a build output, not a source. `scripts/build_data.sh` fetches the public
  dump and derives both variants deterministically; the committed
  `data/SHA256SUMS.variants` must reproduce exactly.
- Generated viewer HTML is gitignored — rebuild with `viewers/build_*.py`. The one
  exception is `viewers/coverage_combined.html`, whose builder needs a rendered
  collusion.wiki bundle that is not redistributed here.
- `benchmark/graded_inputs/` holds byte-identical copies of the reports in `reports/`,
  keyed to match their grade files, so every committed score can be traced to its input.
- `benchmark/legacy_68claim/` is the superseded first-pass pipeline, kept for provenance.
