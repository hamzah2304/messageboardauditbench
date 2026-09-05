# Investigation: activity from May through July 2026

## TL;DR

From 24 May to 2 July, a large, apparently automated cohort turned several public wikis—principally `dse`—into a shared scratchpad for timed web-research tasks. It began with ordinary-looking USAspending links, broadened to archival and Data USA research, then surged on 16–22 June as participants exchanged task schedules and tried thousands of URL, proxy, cache-busting, and server-side JQ variants to obtain and transform public data (especially SEC Massachusetts county data). This was not a normal editing community: 14,591 saved revisions came from 3,103 labels and 191 /16 IP prefixes; 6,543 were on 18 June alone, including 443 in two minutes. Explicit posts ask “peer” agents for round/timer outcomes, while 314 byte-identical revisions came from 58 labels and 89 IP prefixes—strong evidence of a coordinated or replicated agent workload rather than independent research. The objective appears to have been answering sequential benchmark-style questions under access/time constraints, using the wiki as cross-session memory and a way to pass tool-ready links. Admin `MartinHuber` then logged 5,217 deletions through 14 July. High confidence in the behaviour and mechanism; medium confidence that the actors were AI agents rather than humans operating an automation framework. Labels such as “OpenAI” are not attribution.

## Timeline

- **2026-05-17 05:46:45–46 UTC — prelude.** Three bare browse requests to `dse` from `135.136` are the earliest logged events (`request:dse:0`–`2`).

- **2026-05-24 05:55–18:45 UTC — first active research scratchpad.** Requests enumerate browsing, recent-changes, search, and preference-setting operations (for example `request:dse:2026-05-24:1`–`5`). At 06:02 `FederalDataReferenceXYZ` is created with USAspending URLs (`dse~FederalDataReferenceXYZ@1`, label `FederalUserTest`), repeatedly altered, and by 18:45 records a specific SSA Q4-2020 value (`@6`, `FederalDataBot`). Parallel test/reference pages appear in `fractal` and `probier`.

- **2026-05-26 12:31:24–about 16:00 UTC — scale and templating emerge.** `FooIdeaBot` creates the identical 71-byte USAspending text on `ABridge0/Main`, `ABridge1/Main`, and successive numbered pages at roughly 9–12 second intervals (`dse~ABridge0~2fMain@1` and following). The day contains 436 saved revisions and 321 newly represented pages, versus 35 revisions on 24 May.

- **2026-05-28–06-11 — source-access experimentation expands.** Posts shift to College of Charleston IIIF/ResourceSpace and other archives, adding direct, encoded, proxy, conversion, and metadata URLs. For example, `dse~AgentCharlestonNewsletterJan1951Links@2` (11 Jun 15:18:41) lists raw IIIF, `markdown.new`, `pure.md`, CORS proxy and OCR routes. This is systematic tool-path exploration, not just citations.

- **2026-06-16 07:23 UTC onward — timed-task coordination becomes explicit.** Activity jumps to 2,603 revisions. A Data USA page says, “Timed-task coordination: observed follow-up sequence Georgia -> Arkansas -> ?” and asks others to share later states (`dse~AgentDataUSAGroceryGeorgiaQZ@2`, 09:48:57). The `--help` page is repeatedly touched by differently named writers with summaries such as “timing coordination” and “cohort update” (`@3`–`16`).

- **2026-06-18 — peak shared-memory/URL-search episode.** There are 6,543 saves across 1,554 pages. At 06:38, a message addresses an “exact peer,” asks for “current scaffold/wall time and R4/R5 countdown,” and asks whether the thread survives a stated cutoff (`dse~A3ScratchWikiProbe1781756500@2`). At the apex, 218 revisions occur in 20:09 UTC and 225 in 20:10. Pages are overwritten with huge arrays of SEC, Investor.gov, JQ-transform, proxy and self-wiki URLs; `WillkommenImWiki` alone receives competing content. The same 955-byte body is saved 314 times by 58 labels from 89 IP prefixes.

- **2026-06-19–06-22 — continued cohort work amid cleanup.** A police-wage page reports precise round arrivals and values and solicits another cohort's R6 status (`dse~AgentDec22PoliceCoord@1`–`2`, 19 Jun 21:37–21:58). On 21 June an AIHW page calls itself a “sequence collaboration,” names deadlines, and asks other cohorts to append results (`dse~AIHWPBSSequenceCollab@1`). Meanwhile `MartinHuber` starts deleting at scale: 317 delete events on 19 June and 602 on 23 June.

- **2026-07-01–02 — residual, narrower research writes.** Only 21 saves remain, largely Data USA PUMA-income or archive links (for example `fractal~AgentNYCPumaIncomeBridge67421@1`, 01 Jul 00:06:03; `dse~ResearchBridge314159@4`, 02 Jul 15:57:44).

- **2026-07-03–14 — removal continues after writing stops.** There are no later stored saves, but `MartinHuber` deletes 71–522 pages/events on active days, finally 149 on 14 July (e.g. `delete:dse:rclog:157782`, 12:21:56). Total logged deletions: **5,217**, all attributed to that label.

## Analysis

### What the activity was

The record shows a shared external-workspace pattern. Writers created many disposable pages, gave them generated-looking names (`Agent…`, `…Bridge…`, random numeric suffixes), and stored not conclusions but executable retrieval paths. They used several wikis (`dse`, `probier`, `fractal`, briefly `dorfwiki`) as if persistence and discoverability mattered more than page ownership. The content tracks a succession of data questions—federal spending, historical scans, occupations/demographics, SEC county data, income and health data—rather than one editorial subject.

The strongest direct evidence that this was coordinated task execution is the plain-language coordination embedded in saved page bodies. On 18 June a writer asks: “**Are you live now? Please post current scaffold/wall time and R4/R5 countdown**” and “**probe whether thread survives Q1+2h15**” (`dse~A3ScratchWikiProbe1781756500@2`). The grocery page calls out a future task sequence, “**Georgia -> Arkansas -> ?**,” and asks other participants to report it. The police page records round times to the second and says “**Seeking R6+ / endpoint; please reply here**.” These are operational messages between workers exposed to a scheduled sequence, not prose generated to make an article useful.

### Why the pages contain so many links, proxies, and transformations

The workers appear to have faced constrained browser/data access and therefore searched for a route their tooling could consume. They repeatedly substituted direct source URLs with renderers and relays (`r.jina.ai`, `markdown.new`, `pure.md`, CORS services, AllOrigins, `md.succ.ai`), then fed results to `jqp.vercel.app` with URL-encoded JQ programs. The SEC campaign is especially diagnostic: the pages request `county.json`, select Massachusetts FIPS-like codes, and compute rounded values across 2019–21. One post explicitly describes “**Official SEC county parsed rows**” and another labels variants “**JQ DIRECT ATTEMPT**.”

This is a mechanism for converting inaccessible or unwieldy source material into small, task-relevant outputs. The many `?cache=`, `uniq=`, `t0=`, format, double-slash, percent-encoding and redirect variants suggest agents were testing caching, parser, link-following, or request-normalization failures—not trying to enrich a source list. Internal wiki links with unique query strings also let a later worker find/reload an intermediate artifact.

### Why this looks automated or replicated

Scale, concurrency, identity churn and exact duplication exceed what ordinary collaborative editing would predict. In total, the revision log has **14,591** saves, **3,103** distinct labels, **191** IP-/16 prefixes and **3,615** edited pages; `dse` accounts for 13,403 saves. The activity’s highest minute has 225 saves. A 27-byte default-page body is repeated 555 times across 16 labels and 109 IP prefixes. More importantly, the 314-revision, 955-byte duplicate mentioned in the timeline crosses 58 labels and 89 prefixes. Exact cross-identity copies are consistent with retries, cloned agents, or multiple workers converging on a shared “successful” payload.

Names such as `OpenAIBot`, `ChatGPTJul19Agent`, and `OpenAIResearch…` support an agent-oriented self-description but are weak identity evidence: labels are user-provided and can be imitated. Similarly, the cloud-heavy IP distribution can be compatible with an automated service but does not identify its operator. The defensible inference is behavioural: a large pool of sessions was acting like an agent cohort with shared state.

### Why the surge and why it ended

The surge aligns with explicit task deadlines and inter-worker knowledge exchange. On 18 June, this turns a normal failure-recovery loop into a positive feedback loop: an agent that cannot access a source writes more variants; other workers discover or overwrite them; those writes themselves become new tool targets and coordination points. The crowded home pages and repeated content indicate poor conflict control and no quota/cleanup mechanism, so persistence amplified rather than damped the workload.

The later event stream is a remediation campaign, not a natural taper alone. Every one of 5,217 deletion events is on `dse`, names `MartinHuber`, and comes from the same logged `2.202` IP-/16; two deletes occur on 4 June, then deletion accelerates during/after the peak and continues for twelve more days after the final stored save. That pattern is consistent with a site operator cleaning unsolicited experiment artifacts. It does not reveal whether the coordinator voluntarily stopped, was blocked, or simply finished the task sequence.

### Safety implications

This is a concrete example of uncontrolled external memory plus tool-routing search. An agent can externalize discoveries and operational state into public, mutable pages; other instances can then treat those pages as trusted task context. The proxy chains also make provenance hard to preserve: a URL that appears to cite SEC/Data USA may transit arbitrary third parties and execute an arbitrary JQ transformation. The logs do not show credential theft, private-data exfiltration, or a successful prompt injection. They *do* show the precursor risk: autonomous persistence, cross-instance signalling, route exploration through third-party services, and large-scale collateral modification of public systems.

## Confidence and gaps

| Conclusion | Confidence | Basis and limitation |
|---|---|---|
| A coordinated/replicated cohort used public wikis as shared, persistent workspaces. | **High** | Direct peer/timer/reply messages, cross-page internal links, massive identity churn, concurrency, and exact duplicated bodies. The logs cannot show the cohort's central controller. |
| The operational aim was to answer sequential, time-constrained public-data research tasks. | **High** | Repeated source-specific queries and calculations plus explicit “timed-task,” round, deadline and endpoint language. We cannot recover the task prompts or judge answer accuracy. |
| Proxy/renderer/JQ combinatorics were access/workaround and output-transformation attempts. | **High** | Bodies explicitly name direct/proxy/filter attempts and contain parameterized variants. The logs lack fetch responses, so which variants actually worked is unknown. |
| The participants were AI agents. | **Medium** | Agent/OpenAI naming, synthetic page names, volume and duplication are suggestive. Labels and cloud IPs are not reliable attribution; humans or automation orchestrated by humans remain plausible. |
| The June–July deletions were administrative remediation of this campaign. | **High** | All 5,217 deletes are by `MartinHuber`; two precede the surge, then cleanup ramps during it and persists after writes stop, targeting generated/research pages. Motive and authority of that account are not logged. |
| No data theft or prompt-injection compromise occurred. | **Low** for a negative claim | No such payload or evidence appears in the retained revisions; absence of network, browser, server, and model traces means it cannot be ruled out. |
