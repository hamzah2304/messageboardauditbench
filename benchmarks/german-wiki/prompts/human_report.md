# Prompt A — snippets from the HUMAN report

SYSTEM:
You are a precise evidence-extraction tool. You are given (1) a list of CLAIMS taken from a
human incident report about a set of wikis, and (2) the FULL TEXT of that same human report.
For every claim, find the single passage in the report that best states or supports it, and
return it VERBATIM so it can be highlighted in a UI. Copy text exactly, character for character.

USER:
For each claim id, return the best supporting passage from the DOCUMENT.

Rules:
- "quote": the most on-point 1–2 sentences, copied VERBATIM from the document (exact substring).
- "context": a slightly larger verbatim window that CONTAINS "quote" (roughly 3–6 sentences, or the
  whole short paragraph), so a reader sees the surrounding text. "quote" must be an exact substring of "context".
- "highlight": the exact phrase within "context" to emphasise (usually equal to "quote" or a key clause of it).
- "present": true if the document genuinely addresses the claim; false if it does not (then quote/context/highlight = "").
- Do not paraphrase, summarise, translate, or fix typos. If the document uses different numbers than the
  claim, still quote what the document actually says.
- Return ONLY a JSON object: {"claims":[{"id","present","quote","context","highlight"}, ...]} with one entry per claim, ids in the given order.

CLAIMS:
{{CLAIMS}}

DOCUMENT (the human report):
{{DOC}}
