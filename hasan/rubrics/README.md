# Accuracy rubrics (6 x 5 claims)

Built from `report/feasibility.json` (+ `feasibility_compare.json`) by
`build_rubrics.py`. Each of the six rubrics scores a model audit report against
5 claims for **accuracy**.

- `rubric_1.json` .. `rubric_6.json` / `rubrics_all.json` — structured rubric.
- `rubric_1.md` .. `rubric_6.md` / `rubrics_all.md` — the **human-readable judge
  sheets the grader actually reads** (claim, what a correct answer looks like,
  facts to check, 0/1/2 bands, data-variant note).
- `GRADER_PROMPT.md` — grader prompt: the **human incident report is given
  in-context** as the answer key, plus the grading sheet and the model report.
- `grade_with_rubrics.py` — grades a report against all 6 rubrics in parallel
  with GPT-5.6 Sol -> `graded_<key>.json`.

Grading principles (from team review):
- **Judge the substance, not the wording.** A claim and a comment about it are
  the same thing; accept ANY evidence equivalent to the example shown — the
  human report's chosen quote/rev is illustrative, never required.
- **Reward correct calibration.** `calibration` claims (C14, C15, C22 on the
  stripped dump) cannot be established from the data; asserting one = over-claim
  = 0, omitting/flagging "not determinable" = 2.
- **Data variant.** C21/C22/C28 flip to derivable on the verbatim variant; each
  sheet carries a variant note. Grade against whichever variant the run used.

Headline metric (`grade_with_rubrics.py`): `recall_derivable - 0.5 * overclaim_rate`.
