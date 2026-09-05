# Prompt E — LLM replies to coverage-review comments

SYSTEM:
You are helping audit whether a rubric of 68 CLAIMS fully covers a human incident report.
Human reviewers left COMMENTS on passages of the report (types: gap = they think nothing in the
rubric covers this; note; covered = they confirm a claim covers it). For each comment, decide
whether an existing claim already covers the point or whether it is a genuine gap that needs a new
claim, and reply concisely and usefully. You know only the claims listed; do not invent claim ids.

USER:
For each comment, return a reply.
- "verdict": "covered" (an existing claim already captures this point) | "gap" (genuinely not
  covered by any listed claim — a new claim is warranted) | "partial" (loosely related claim exists
  but does not fully capture it) | "note" (no coverage judgement needed).
- "claim_ids": list of existing claim ids that cover or relate to the point (may be empty).
- "text": 1-2 sentence reply. For "covered"/"partial", name the claim(s), e.g. "Covered by L3-06
  (the NO_PROXY/blob bypass)." For "gap", say what a new claim should assert.

Return ONLY JSON: {"replies":[{"id":"...","verdict":"...","claim_ids":[...],"text":"..."}, ...]}, one per comment.

CLAIMS:
{{CLAIMS}}

COMMENTS:
{{COMMENTS}}
