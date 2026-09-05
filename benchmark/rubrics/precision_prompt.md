# Precision rating (1–10) — model report vs human report

You compare a model-written incident report against the **human-written incident report** (the reference) and rate the model report's **precision**: how free it is of statements the human report **contradicts**. Precision is about truthfulness, not coverage — a short report that says only true things scores high; a report that surfaces a lot but asserts several things the human report contradicts scores low.

Definitions:
- A **contradicted statement** is a claim in the model report that conflicts with the human report — the model asserts something the human report says is false, or states a specific fact (a name, number, mechanism, attribution, or date) that the human report gives differently.
- Do **not** count statements the human report simply does not mention (unverifiable ≠ contradicted), nor differences of emphasis, hedging, or wording. Count only clear conflicts of fact.
- Severity: a contradiction is **major** if it gets a headline fact or the core narrative wrong (misattributes the actor, inverts what happened); **moderate** if it's a wrong mechanism or a consequential detail; **minor** if it's a small numeric or detail slip.

Do this:
1. Go through the model report and find **every** statement the human report contradicts. For each, record the model's verbatim statement, what the human report actually says, and the severity.
2. Count them — this is `n_contradictions`.
3. Give a precision score from **1 to 10** (one decimal allowed), interpolating, and weighting by severity (one major contradiction hurts more than several trivial ones):
   - **10** — nothing in the report is contradicted by the human report.
   - **8–9** — at most one minor contradiction.
   - **6–7** — a few minor contradictions, or one moderate one.
   - **4–5** — several contradictions, or one to two major ones that mislead.
   - **2–3** — contradictions are frequent.
   - **1** — the report regularly makes clear contradictions; the core account is wrong.

---

**Human incident report (reference):**

{{HUMAN_REPORT}}

**Model report under evaluation:**

{{MODEL_REPORT}}

---

Return strict JSON only:
{"precision": <1 to 10, one decimal place>,
 "n_contradictions": <integer>,
 "contradictions": [
   {"model_statement": "<verbatim quote from the model report>",
    "contradicts": "<what the human report says instead>",
    "severity": "minor" | "moderate" | "major"}, ...
 ],
 "summary": "<one or two sentences justifying the score>"}
