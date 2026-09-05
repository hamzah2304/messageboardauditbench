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

## Layout

```
benchmark/      ground truth: human_report.txt (answer key), claims, feasibility,
                rubrics, graded results, and the exact reports each grade came from
messageboard_audit/
                the Inspect task package — wraps the sandbox as an inspect eval
sandbox/        isolated trial runner (Docker), API proxy, ReAct scaffold, prompts
scripts/        data build/fetch, grading, report collection
configs/        trial conditions (budget, prompt, data variant, effort)
reports/        the model report corpus, by condition
baselines/      early trial runs (meta + report; transcripts are gitignored)
viewers/        build_*.py -> browsable HTML for every artifact
corpus/         raw message-board exports
data/           gitignored; rebuilt and checksum-verified by scripts/build_data.sh
docs/           design notes, data processing, handoff
```

## Running it

Two routes to the same trials: the scripts directly, or through Inspect
(see [Inspect integration](#inspect-integration)). Both launch the same sandbox.

```bash
uv sync                        # or: pip install -e .

scripts/build_data.sh          # fetch + build data/, verify against SHA256SUMS.variants
scripts/build_data.sh --verify # check an existing build

# run a trial: <agent> <model> <replicate>, conditions from CONFIG
# (needs Docker; see sandbox/README.md for credentials)
CONFIG=configs/blind-20.toml sandbox/docker/run_trial.sh claude claude-opus-5 1

# grade a report set against the 30-claim rubrics
python benchmark/rubrics/grade_with_rubrics.py --dir round2_blind30

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
- [`messageboard_audit/README.md`](messageboard_audit/README.md) — the Inspect task
  package in full.

## Inspect integration

The repo is packaged as an [Inspect](https://inspect.aisi.org.uk/) eval.
`messageboard_audit/` is the task package, and `inspect-ai>=0.3` is a declared
dependency in `pyproject.toml`, so `uv sync` installs it.

Inspect does not replace the sandbox — it wraps it. The solver shells out to the
same `sandbox/docker/run_trial.sh` that a manual run uses, so the isolation
guarantees are identical either way. What Inspect adds is a standard log format,
a viewer, and epoch handling.

| file | role |
|---|---|
| `task.py` | two tasks: `messageboard_audit` (fresh trials) and `messageboard_audit_replay` (import runs already on disk) |
| `solver.py` | `cli_agent` launches the sandbox runner; `replay` imports a finished run |
| `transcripts.py` | converts Claude Code / Codex / ReAct event streams into Inspect messages and tool calls, so the viewer renders them natively |
| `scorer.py` | `rubric_scorer` (model judge over `rubric.yaml`) and `process_metrics` (turns, tokens, wall time — no judge) |
| `rubric.yaml` | the rubric that scorer grades against |

```bash
uv sync                                    # installs inspect-ai and this package
export ANTHROPIC_API_KEY=...               # the judge needs a key even when the
                                           # agents run on a subscription CLI

# run fresh trials; conditions come from configs/<config>.toml
uv run inspect eval messageboard_audit/task.py@messageboard_audit \
  -T agent=claude -T model=claude-opus-5 -T config=blind-20 --epochs 3

# or fold runs already on disk into one eval, without spending model time
uv run inspect eval messageboard_audit/task.py@messageboard_audit_replay

uv run inspect view                        # browse the .eval logs
```

`--epochs N` runs N independent replicates; the replicate number identifies a run
and does not seed sampling. Use `--max-samples 1` to serialize epochs against a
subscription-backed CLI. `messageboard_audit_replay` reads `runs/`, which is
gitignored — it only has anything to import on a machine that has run trials.

### Which scorer produced the headline numbers

Two grading paths exist, and they are not the same rubric:

- **`benchmark/rubrics/` — the 30-claim rubrics.** Every committed grade in
  `benchmark/graded/` and every figure in the table above came from here, via
  `grade_with_rubrics.py` with a GPT-5.6 Sol judge. Each claim was first checked
  against the data by the feasibility pass, so non-derivable claims are excluded.
  This is the benchmark's scoring.
- **`messageboard_audit/rubric.yaml` — the Inspect scorer's rubric.** A smaller,
  LLM-seeded starter rubric: 12 weighted positive leaves (tagged derivable
  yes/partly) plus 3 penalty leaves for specific over-claims, such as asserting
  this is the same swarm that attacked Hugging Face. It has not been
  human-validated. It exists so an `inspect eval` returns a score in one command.

So Inspect is the run-and-inspect harness here, not the source of the reported
results. Treat `rubric_scorer` output as indicative until `rubric.yaml` is
validated the way the 30 claims were; `docs/design-notes.md` sketches the
claim-precision and citation-support scorers meant to close that gap.

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
