# Feasibility RECHECK against the VERBATIM (augmented) data variant

Same 30 candidate claims as before, but now checked against Oscar's `verbatim`
data variant, which is the public dump PLUS only what the human report prints
verbatim. Your job: for each claim, re-decide whether it is now establishable,
and say whether the augmented data CHANGED the verdict vs the prior pass.

## The data — query with bash (grep/python/jq)
Directory: /workspace/collusion/dump_verbatim/   (events/labels/pages/revisions .jsonl)
What the verbatim variant adds over the stripped dump:
- 8 XSS/injection probe rows gain a `request` field (incl. a ~1,992-char forged-POST chain); 2 gain asserted labels (XSSChainUser, OpenAIJul03Police).
- 12 new `request` events for the 24 May DSEWiki discovery sequence (names TesterHack, TesterWikiUser; exact query strings).
- 7 new `request` events (17 June) with `*.lhr.life` referrers (localhost.run tunnel).
- Redacted name tokens are filled with consistent fictional names: [Admin1]=MartinHuber (also on all deletions), [Admin2]=Friеdrich1982 (spelled with a Cyrillic е, U+0435) + a `...302` variant; plus ONE zero-revision Latin `Friedrich1982` (role=administrator) in labels.jsonl as the look-alike's original. 14 other [PersonN]/[User3] tokens filled with German-style names.
NOTE still absent by design: OpenAI-HQ visits, full IPs / provider attribution, ChatGPT-User fetch reads, other-wiki edits, urlscan. Claims needing those stay not_derivable.

## For each claim (each batch row carries prior_verdict / prior_corrections)
Run real queries against /workspace/collusion/dump_verbatim/, then return:
- verdict: derivable | partial | not_derivable  (for THIS variant)
- changed: true|false  (did the augmented data change the verdict vs prior_verdict?)
- change_reason: 1 sentence — what augmented row(s) changed it, or why it's unchanged.
- confidence: 0.0-1.0
- fact_check: [{token, status, query}] — re-verify the specific tokens; e.g. the Cyrillic е (U+0435), lhr.life, TesterHack, the full XSS payload, names.
- evidence: [{file, query, result}] — concrete, from dump_verbatim.
- corrected_values: value from THIS variant if it differs from the claim, else "".
- can_be_met: yes|partial|no
- notes: 1-2 sentences.

## Output
Write JSON to /workspace/collusion/report/feasibility_verbatim/result_batch_<N>.json:
{ "batch": <N>, "variant": "verbatim", "results": [ {"id","verdict","changed","change_reason","confidence","can_be_met","fact_check":[...],"evidence":[...],"corrected_values","notes"}, ... ] }
Then reply one line: counts per verdict + how many changed. Ground every verdict in a query you ran.
