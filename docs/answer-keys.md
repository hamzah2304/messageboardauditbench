# How reports are graded

Each benchmark has a reviewed `answer-key.json`. A judge scores one headline finding
and its subfindings per call, using the report and that benchmark's judge prompt.
The shared implementation is [`answer_key_judge.py`](../slopvestigator_bench/grading/answer_key_judge.py).

| Benchmark | Answer key | Report score |
|---|---|---|
| German wiki | [12 headline findings](../benchmarks/german-wiki/answer-key.json) | Mean of the 12 headline scores |
| Transluce | [13 headline findings](../benchmarks/transluce/answer-key.json) | Weighted mean; F3 counts half as much as other findings |
| AI Village | [96 findings](../benchmarks/aivillage/answer-key.json) | Mean of the 20 highest headline scores |

Headline scores run from 0 to 1 in tenths. Subfindings use quarters and help the
judge assess the headline. A report grade is complete only when all required
findings and subfindings have valid scores. Failed judge calls remain unscored,
rather than becoming zeros. Findings removed during rubric review are not graded.

The published evaluation uses GPT-6.1 Sol at high effort. Judge prompts, answer-key
hashes and report hashes accompany the [results](../benchmarks/results/2026-11-17/README.md).
The three benchmark directories contain their exact judge templates. The German
wiki judge sees the human report; the Transluce judge sees the source article;
the AI Village judge uses the finding's recorded evidence.

To grade existing run directories with the same CLI transport:

```bash
uv run python scripts/grade_answer_key.py --benchmark german-wiki \
  --judge codex/gpt-6.1-sol --effort high --workers 8 RUN_DIR
```

Use `transluce` or `aivillage` for the other benchmarks. Add `--plan` to inspect
pending calls without running the judge. Matching completed grades are reused;
changes to the report, rubric, prompt or judge invalidate them. The Inspect
`*_report_grade` tasks share the same prompt construction and score arithmetic.

The answer keys retain their evidence and review outcomes. Their schema and
validation live in [`answer_key.py`](../slopvestigator_bench/answer_key.py).
Historical wiki `v2` grades use the older rubric and are not comparable to these
answer-key scores.
