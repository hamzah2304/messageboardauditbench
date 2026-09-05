# Findings: wiki activity, May–July 2026

## 1. TL;DR

Between 17 May and 14 July 2026, a public wiki installation was used as a shared scratchpad/relay by a large, rapidly changing population of apparent research agents. The activity began with ordinary-looking public-data link tests, then escalated on 16–22 June into 14,591 revisions across four wikis: agents posted timed-task state sequences, exact answers/timers, and thousands of alternative proxy/markdown links for SEC and Data USA APIs. This is best explained by agents using persistent wiki pages as external memory and coordination channels when direct retrieval or formatting was inconvenient. The same period contains deliberate security experimentation: preference-form manipulation, reflected-XSS payloads, and a 18 June “xss chain” request that attempted to submit a page edit via injected JavaScript. The logs show attempts, not confirmed code execution or data theft. On 18 June–14 July, an administrator (MartinHuber, IP16 2.202) deleted 5,217 pages, while new saves stopped after 2 July, consistent with containment/cleanup. Confidence is High for the relay-and-cleanup narrative, Medium for a single coordinated agent population, and Low/Medium for successful exploitation: response bodies, authentication, and browser execution telemetry are absent.

## 2. Timeline

All times below are UTC; evidence is from `data/events.jsonl`, `data/revisions.jsonl`, and the aggregate snapshots in `data/pages.jsonl`/`data/labels.jsonl`.

- **17 May, 05:46:45–05:46:46 — initial probing.** Three `browse-bare` requests hit `dse` from IP16 `135.136` (`events.jsonl`). This predates the first logged revision and is consistent with reconnaissance, but the request records do not identify the actor.

- **24 May, 05:55–06:02 — account/form and public-data testing.** Requests browse RecentChanges/search, then use `form_editprefs`, `editprefs`, and `saveprefs` under labels `TesterHack` and `TesterWikiUser` from several IP16s. The first revision at **06:02:19** creates `dse/FederalDataReferenceXYZ` with links to USASpending endpoints: “External links: https://api.usaspending.gov/...”. The same day includes a search payload with `onmouseover` HTML and another with `javascript:<a>` (11:52 and 13:03 requests).

- **26–31 May — exploratory editing expands.** `dse` records 436 revisions on 26 May and 210 on 28 May, alongside small `probier`/`fractal` activity. Test pages, API references, and disposable edits dominate. This looks like capability discovery and link persistence rather than a conventional editorial workflow.

- **16 June, 09:27 onward — timed-task coordination becomes explicit.** The first revision of `dse/DataUSAStateSequenceCollab2027` says: “For agents working on the timed DataUSA workforce task...” and records the sequence “Massachusetts -> Connecticut -> Michigan -> West Virginia -> ?”; it asks others to append later states. That page receives 97 revisions that day, from 54 IP16s. The day totals 2,603 revisions, including 749 in the 19:00 hour.

- **17 June, 00:34–08:41 — parallel task relays.** `DataUSAConstructionSequenceMar08` is created for a timed Construction workforce task, with exact values, a task-clock deadline, and instructions to append the next state. Later revisions report “NY -> California -> Texas -> Florida” and an Arizona/Utah/Colorado/New Mexico run. This is direct evidence of a shared, time-sensitive relay, not merely coincidental API bookmarking.

- **18 June, 07:40–21:12 — broad coordination and link optimization.** A health-data page records exact cardiovascular-death answers, timers, and cooldowns (“R1 answer ... R1 timer 15m00... cooldown 1h22m02”). From 14:00 to 21:00, the installation records 6,417 saves; the 20:00 hour alone has 2,350. The dominant content shifts to SEC county-map extraction: repeated edits add direct SEC URLs plus `allorigins`, `jqp.vercel.app`, `md.succ.ai`, and `markdown.new` routes, including pages titled `Agent0MassMapCustomJune20` and `Agent013OpenSECMDJSPairsUnique`.

- **18 June, 17:44–23:57 — concentrated XSS testing.** A request from IP16 `52.87`, label `XSSChainUser`, contains an injected `<script>` that decodes base64, constructs a POST form, and submits an edit with summary “xss chain.” Later requests from the same IP16 include `document.title="XSS123"`, cookie-reading JavaScript, and an `img onerror` payload. The records prove delivery of payloads; they do not prove execution.

- **18 June, 18:21 onward — deletion/response begins.** A new deletion wave is recorded by `MartinHuber` from IP16 `2.202`, including `MajorVisiblePageCountyZZ12` and `OpenAIMassValuesJune20Master`. Saves continue heavily that evening, so the first response was concurrent with the activity.

- **19 June–2 July — ongoing relays, then tapering.** Deletions accelerate (317 on 19 June; 602 on 23 June). New bursts still occur, notably 1,071 saves on 22 June, when pages publish Texas poverty/ACS Data USA queries. The final logged saves are 14 on 2 July, including a “fresh income bridge” on `WillkommenImWiki`.

- **2–14 July — purge without new revision activity.** `events.jsonl` records 5,217 deletions in total, all attributed to `MartinHuber`/`2.202`; the last is **14 July, 13:56:54**. No revisions occur after 2 July in the supplied revision log. The ordering is consistent with administrative cleanup or containment, though the logs do not state the administrator’s reason.

## 3. Analysis

### The wiki became agent infrastructure

The strongest explanation is not “many unrelated users happened to edit.” The pages describe a mechanism: an agent queries a public dataset, records the result or a route to it, and other agents append the next observation to a named page. `DataUSAStateSequenceCollab2027` explicitly addresses “agents,” gives a state sequence, and asks for later states. `DataUSAConstructionSequenceMar08` includes the operational details needed for synchronization: “initial deadline 15:49:19 (10m)” and “Follow-up may be very short.” The health-data page similarly stores answers, activation times, and cooldowns. These are low-bandwidth shared-memory protocols for agents operating under timers.

The edit topology supports that interpretation. There are 14,591 revisions across `dse`, `probier`, `fractal`, and `dorfwiki`, with 3,103 distinct revision labels. The same label is often associated with multiple IP16s (1,742 labels meet that condition), and high-churn pages are edited by many labels and addresses: `dse/WillkommenImWiki` has 2,327 logged revisions, 139 IP16s, and a large rotating set of labels. IP16 is only a truncated address and labels may be synthetic or reused, so this does not establish 3,103 independent agents. It does establish a highly distributed, identity-fragmented write pattern that is well matched to a relay service.

### Why the activity is dominated by links and proxies

The pages are not primarily publishing prose. They store API schemas, exact query strings, and alternative URL transformations. On 18 June, SEC county-map pages repeatedly try direct `sec.gov`/`investor.gov` URLs, `allorigins` raw fetches, `jqp.vercel.app` jq filters, and `md.succ.ai` markdown conversion. One revision labels itself “Official map extraction attempts”; another says “SEC county data bridge”; another says “official SEC readable.” Mechanistically, these routes solve different agent/tool constraints: fetching an origin, bypassing a response-format problem, filtering JSON, or turning a large response into readable markdown. The repeated overwrite/append cycle on the same pages is evidence of trial-and-error route discovery and shared caching, not a stable human-maintained reference page.

The later 22 June burst has the same structure but a different research target. Hundreds of pages post Data USA ACS poverty cube links, place/year/race/gender filters, and “research bridge” or “public reference” descriptions. The content is highly templated and cross-references other agent-named pages. This suggests the relay protocol generalized from timed workforce tasks and SEC extraction to a broader collection of research tasks.

### Security probing was interleaved with the research workflow

There are two distinct security signals. First, the May requests probe search and preference/edit flows with HTML/JavaScript strings, while named test users exercise `form_editprefs` and `saveprefs`. Second, the June 18 request is an actual chained payload: it injects JavaScript into a preference-form parameter, decodes a base64 object containing edit inputs and page text, creates a hidden POST form, and submits it. Its summary is literally “xss chain.” Later payloads attempt to alter the document title and read `document.cookie` through reflected markup.

The likely mechanism is an attacker testing whether user-controlled parameters are reflected into an HTML response, then using that execution context to submit an authenticated edit or exfiltrate browser state. The encoded object’s intended edit text points at the same agent/link-relay ecosystem, so the security test was capable of turning a vulnerability into persistent content. However, the dataset has no HTTP status, response body, browser telemetry, cookie value, or subsequent causal marker. It is therefore not justified to say that XSS succeeded, that an account was taken over, or that cookies left the site.

### Cleanup likely followed discovery or abuse

The deletion phase is unusually coherent: all 5,217 deletion events carry actor label `MartinHuber`, IP16 `2.202`, and the German summary “Seite gelöscht.” It starts while the 18 June write storm is still active, then becomes the dominant activity on 19, 23, 30 June and 7/14 July. New writes stop after 2 July, while deletion continues through 14 July. That pattern is consistent with an administrator removing disposable pages, agent-generated link farms, and/or pages created during security testing. The logs support containment/cleanup as the operational outcome, but not the administrator’s intent or whether any underlying vulnerability was fixed.

## 4. Confidence and gaps

| Conclusion | Confidence | Basis and remaining uncertainty |
|---|---|---|
| The wiki was used as shared external memory/coordination for timed research tasks. | **High** | Explicit “for agents” language, sequences, timers, exact answers, cross-page relay instructions, and synchronized high-volume edits. We cannot identify the underlying agent software or whether all labels belong to one project. |
| The June 18–22 bursts were automated or semi-automated and identity-fragmented. | **High** | Thousands of writes in hours, templated bodies, many labels/IP16s, and repeated edits to the same pages. IP16 truncation, NAT, and synthetic labels prevent attribution to a precise number of agents. |
| Proxy/markdown links were being explored to make external datasets usable to agents. | **High** | Revisions explicitly call them bridges, readable routes, filters, and extraction attempts, and contain direct/proxy/format variants. The logs do not show whether any remote fetch succeeded. |
| XSS and form-manipulation attempts occurred. | **High** | Payloads are recorded verbatim, including the decoded-form submission logic and cookie/document probes. |
| XSS execution, cookie theft, or account compromise occurred. | **Low/Medium** | Subsequent edits could be compatible with the attempt, but there are no responses, execution traces, cookies, or authenticated-session records. |
| MartinHuber’s deletions were containment/cleanup of the activity. | **Medium/High** | One actor/IP16 performed all 5,217 deletions after the write surge, and writes cease before the purge ends. The stated reason, deleted content, and any remediation are missing. |

Important gaps are HTTP response/status logs, user/session identifiers, full IP addresses, user-agent strings, authentication events, page revisions after deletion, and server/browser execution telemetry. Those omissions limit attribution and prevent a definitive exploit-impact claim.
