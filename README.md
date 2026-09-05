# MessageBoardAuditBench

A benchmark for how well an agent can investigate raw message-board logs and recover findings from a human audit.

This repo is early and will change a lot.

## Goal

Evaluate auditor agents on incident logs such as [collusion.wiki](https://collusion.wiki/index.html). Two task shapes we're exploring:

1. **Open-ended investigation** — write a report, grade it with a rubric.
2. **Treasure-hunt questions** — answer specific questions from the logs.

## Planning doc

Working notes, the candidate task set (68 claims across four difficulty levels), grading
proposals, and a first GPT-5.6 Sol vs Opus 5 scoring run:
[MessageBoardAuditBench (Google Doc)](https://docs.google.com/document/d/1hoSqxTTcpIxNH8tGKBCdg3TeluBF6xkbtxLOXUwj4es/edit)

## Docs

- [Ablations & baselines](docs/ablations-and-baselines.html) — how we check the benchmark
  measures investigation rather than summarisation, and what to baseline against.
