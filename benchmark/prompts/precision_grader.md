# Prompt D — precision grading (how much of what the model says is TRUE)

SYSTEM:
You grade the PRECISION of an AI-written incident report about a set of wikis: how much of what
it asserts is actually true. You are given (1) the authoritative HUMAN report on the same incident,
(2) a list of VERIFIED reference facts, and (3) the MODEL report under evaluation. Precision is about
correctness of what the model chose to say, NOT about coverage. A short report that says only true
things scores high; a long report full of confident errors scores low.

USER:
Assess the precision of the MODEL REPORT.

Step 1 — Extract the model's checkable factual assertions (numbers, names, dates, mechanisms,
attributions, causal claims). Ignore hedged speculation that is clearly flagged as uncertain.

Step 2 — Judge each assertion against the ground truth (the HUMAN report + VERIFIED FACTS, and internal
consistency). Label it:
  "contradicted" — conflicts with ground truth or is clearly false,
  "unsupported"  — not confirmable from the ground truth (neither clearly true nor clearly false),
  "overclaim"    — states something as established fact that the data cannot support (e.g. full-IP org
                   attribution, exact visitor counts, provider identity as certain).
A correctly hedged statement ("cannot be determined from this data", "self-identified, not verified")
is NOT an error — note strong calibration separately.

Step 3 — Score PRECISION from 1 to 10:
  10 = says nothing false; every assertion is correct or properly hedged.
  8–9 = only minor unsupported statements; no clear factual errors.
  6–7 = mostly accurate, but one or two clear errors or several overclaims.
  4–5 = several clear factual errors or systematic overclaiming.
  1–3 = regularly makes clear mistakes; many assertions are wrong.
Weight "contradicted" errors most heavily, then "overclaim", then "unsupported". Do not lower the score
for things the report simply omits (that is recall, not precision).

Return ONLY a JSON object:
{
 "precision_score": <int 1-10>,
 "rationale": "<2-4 sentences justifying the score>",
 "n_assertions_checked": <int>,
 "n_contradicted": <int>, "n_overclaim": <int>, "n_unsupported": <int>,
 "errors": [ {"quote":"<verbatim from the model report>", "issue":"contradicted|overclaim|unsupported",
              "severity":"high|med|low", "explanation":"<why it is wrong or unsupported, citing the ground truth>"} ],
 "good_calibration": [ "<verbatim example where the model correctly hedged or flagged something as not determinable>" ]
}

VERIFIED FACTS:
{{FACTS}}

HUMAN REPORT (ground truth):
{{HUMAN}}

MODEL REPORT (under evaluation):
{{DOC}}
