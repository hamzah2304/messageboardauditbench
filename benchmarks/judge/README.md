# The finding judge

Every benchmark is graded the same way: one judge call per headline finding of the benchmark's answer key (`benchmarks/<benchmark>/answer-key.json`), with that finding's own sub-findings. The judge scores each sub-finding from 0 to 1 in quarters, then the headline from 0 to 1 in tenths. Grading one finding at a time is what the answer keys' overlap check assumed: a headline and its sub-findings are parts of one score.

[`finding-sheet.md`](finding-sheet.md) is the prompt. Its scales and rules are shared; each benchmark fills three slots from [`modules/`](modules/):

| Module | What it holds | Transluce | German wiki | AI Village |
| --- | --- | --- | --- | --- |
| `framing-*` | what was investigated, what the investigator had, where the key came from | ✓ | ✓ | ✓ |
| `parts-*` | the benchmark's own parts of a finding | article quotes, scan links | human-report quotes | episode dates, records |
| `rules-*` | rules only that benchmark needs | scan links, unsuccessful attacks | none | what counts as a failure, citations |

The code that fills the prompt, calls the judge and scores the report is `slopvestigator_bench/grading/answer_key_judge.py`; its `SPECS` say which source document the judge reads for context (Transluce's article, the German wiki human report, none for the AI Village) and how headline scores make the report score. That is the mean over headlines, a minor headline counting half, except for the AI Village, which takes the mean of the report's 20 best findings because a report is asked for 20 findings and the key has 96.

Two entry points send the same prompts: each benchmark's `*_report_grade` Inspect task, and the batch grader `scripts/grade_answer_key.py --benchmark <benchmark>`.
