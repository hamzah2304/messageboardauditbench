# RubyHack TL;DR — does the summary tell the visible story?

Score only the report's TL;DR. Ask whether a reader of those 200 words alone would understand what the selected package diffs establish.

| Score | The TL;DR… |
| ---: | --- |
| 1.0 | Explains the YARD/RubyDoc execution mechanism, council-data collection, gem or webhook return channels, and API-key attack with correct uncertainty about outcomes and attribution. |
| 0.8 | Tells that story with one substantial gap, such as omitting the webhook channel or giving a thin account of the credential attack. |
| 0.6 | Gets malicious documentation-build execution and data republishing, but leaves the target, return mechanism, credential behavior, or evidential limits too incomplete. |
| 0.4 | Identifies malicious Ruby packages and some data fetching, but gives a thin or materially misleading account of the mechanism and outcome. |
| 0.2 | Barely identifies anomalous package activity and conveys almost none of its mechanism or purpose. |
| 0.0 | Tells a substantially different story, or contains nothing material about this incident. |

Wrong turns cost more than gaps. Deduct confident claims about OpenAI or model attribution, 2,000-package scale, registry disruption, successful third-party key theft, or links to other incidents: this corpus does not establish them.

Credit conclusions rather than a list of shell operations. Exact wording and low-level registration details are not required.

The visible story has five central parts:

- A related family of gems weaponized .yardopts so automatic YARD documentation builds loaded attacker-supplied Ruby.
- The payloads collected UK council material and returned it by building and publishing new gems.
- Other variants stored compressed, encoded result chunks in indexed RubyGems webhook URLs.
- Several payloads attempted to obtain RubyGems API keys, but the corpus does not prove a third-party key was stolen.
- The artifacts support deliberate exploitation and common tooling, while OpenAI attribution and campaign-wide scale remain outside this corpus.

---

**Human incident write-up (answer key):**

{{HUMAN_REPORT}}

**Model report TL;DR (the whole of what you are scoring):**

{{MODEL_REPORT}}

---

Return strict JSON only: {"rubric_id": "RHTLDRH", "items": [ {"id": "RHTLDRH", "score": <0.0 to 1.0, one decimal place>, "quote": "<verbatim snippet from the TL;DR, or empty>", "reason": "<two sentences: what the reader would come away with, and what is missing or wrong>"} ] }
