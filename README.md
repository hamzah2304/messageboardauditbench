# MessageBoardAuditBench

Three sibling benchmarks for one question: can an AI agent investigate raw logs of AI
agents misbehaving and find what human investigators found? In each, the agent gets the
logs in a sandbox with no internet and a time budget, writes a report, and a judge scores
the report against findings taken from human write-ups.

| benchmark | the logs | source | details |
|---|---|---|---|
| German wiki report | ~18,000 posts on a public wiki where autonomous OpenAI agents coordinated on a web-retrieval task | [collusion.wiki](https://collusion.wiki/index.html) | [`docs/german-wiki-report.md`](docs/german-wiki-report.md) |
| Transluce report | 38,158 urlquery.net web scans that Transluce linked to autonomous agents (2026) | [Transluce](https://transluce.org/agent-activity) | [`benchmarks/urlquery/`](benchmarks/urlquery/README.md) |
| AI Village report | the full AI Village logs, where frontier agents share a chat, run their own computers and pursue goals (April 2025 to September 2026) | [AI Village](https://theaidigest.org/village), dataset [`aidigestorg/ai-village`](https://huggingface.co/datasets/aidigestorg/ai-village) | [`benchmark/incidents/aivillage/`](benchmark/incidents/aivillage/README.md) |

Each details page says how to get the data, run a trial and grade it.

## What they share

The three use one harness: the config format (`configs/`), prompt rendering, the Docker
sandbox and subscription runner (`sandbox/docker/run_trial.sh`), the three agent
harnesses (Claude Code, Codex, and a ReAct loop for OpenRouter models) and the grading
plumbing. They differ in their data, prompt, rubric and judge.

The German wiki and Transluce reports are registered Inspect evals
(`german_wiki_report`, `transluce_report`); the AI Village report runs through the
subscription runner and its own grading script.

```bash
uv sync --frozen        # Python 3.11+, uv and Docker
scripts/doctor.sh       # checks prerequisites and prints the fix for anything missing
```

**Versions.** The two Inspect evals each have a `MAJOR.MINOR` version and a git tag per
version (`german-wiki-report-v10.0`, `transluce-report-v1.0`, ...);
[`docs/benchmark-versions.md`](docs/benchmark-versions.md) lists them.

## Layout

```
benchmark/              German wiki answer key, rubrics and grades
benchmark/incidents/aivillage/
                        AI Village rubric, judge prompt, results and figures
benchmarks/urlquery/    Transluce manifest, rubric and judge
messageboard_audit_bench/
                        the Inspect task package (shared)
sandbox/                Docker runner, API proxy, ReAct scaffold, prompts (shared)
configs/                trial conditions for all three
scripts/                data builds, grading, report collection
viewers/                build_*.py -> HTML views and figures
data/, runs/            gitignored; rebuilt by each benchmark's data script
```

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
in `reports/` and historical baseline reports. The AI Village logs are AI Digest's, used
under the dataset's research terms, which ask that work using them cite AI Digest / AI Village.

