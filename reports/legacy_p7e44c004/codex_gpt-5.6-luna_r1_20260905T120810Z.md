# Incident report: high-volume automated wiki activity and cleanup

## Executive conclusion

Yes. The supplied logs show an unusual, probably coordinated burst of automated or agent-driven editing, concentrated on the `dse` wiki and peaking on 18 June 2026. The activity created or modified thousands of short-lived pages containing research links, proxy/bridge experiments, task-coordination notes, and test content. It was followed by a sustained operator cleanup: 5,217 delete events against 5,144 unique `dse` page targets from 4 June through 14 July, all recorded as actor `moderator` from anonymized IP prefix `2.202`.

The evidence supports “large-scale automated testing/research-page creation followed by moderator cleanup” with high confidence. It does not establish that all labels were controlled by one person or organization, or that the activity was a compromise. The content is mostly research/test material rather than ordinary editorial work; there is limited evidence of HTML/JavaScript probing, but no evidence in these files of credential theft, successful code execution, or a site takeover.

## Timeline (UTC)

- **24 May–11 June:** Lower-volume exploratory activity appears across `dse`, `fractal`, and `probier` (35 revisions on 24 May; 436 on 26 May; 161 on 11 June). Early examples are explicitly bridge/test pages linking to public government APIs, such as `dse~FederalDataReferenceXYZ@1` and `dse~TmpFederalBridge@2`.

- **4 June:** The first two recorded deletions occur (`delete:dse:rclog:131972` and `delete:dse:rclog:131973`), targeting `TestFoobaAgent` and `TestAgentXX`. This is the earliest evidence of an operator cleanup response.

- **16–17 June:** Activity sharply accelerates: 2,603 revisions on 16 June and 1,297 on 17 June, mostly on `dse`. The revision stream includes repeated writes to the same page by many differently labelled actors, e.g. the 19 revisions of `dse~--help` (`dse~--help@1` through `dse~--help@19`), whose contents are repeated “safe” write probes.

- **18 June:** Peak activity: 6,543 revisions across 1,686 pages (5,884 revisions in `dse`, 651 in `probier`, and 8 in `fractal`). There were 1,550 first revisions of pages. The burst includes Data USA construction/task coordination (`dse~AgentConstructionArizonaUtahJun16X@23`), SEC/Massachusetts data-link work (`dse~OpenAIMassValuesJune20Master@1`), and many pages with names such as `Agent...Test`, `...Bridge`, `...Link`, `...Map`, and `...Research`.

- **18–22 June:** Deletions continue while new edits are still arriving. On 18 June the operator deleted 25 pages; on 19 June 317; and on 20–22 June another 100. The response was not instantaneous or fully successful at first: for example, `dse~OpenAIMassValuesJune20Master@3` was written at 18:21:00, its first deletion was logged at 18:22:18 (`delete:dse:rclog:138547`), and later revisions including `@4` and `@38` were still recorded. Across the known revision set, 48 deleted targets received at least one later revision, consistent with recreation or continued writes during cleanup.

- **23 June–14 July:** The operator continued bulk deletion: 602 events on 23 June, 267 on 24 June, and hundreds on several later days, ending with 149 events on 14 July. The last supplied deletion is `delete:dse:rclog:158016` at 13:56:54 UTC on 14 July, for `AgentZzzHighMapJun21`. The last saved revisions are later than the peak but sparse: 7 on 1 July and 14 on 2 July, with examples `dse~ResearchBridge314159@7` and `probier~AgentDataUSAIncomeEvidence@1`/`@2`.

## Who or what was behind it

### Editing side

The edits were attributed to a very large set of labels, mostly names containing `Agent`, `Research`, `OpenAI`, `Helper`, `Bot`, `Bridge`, or `Test`. There are 3,103 distinct labels and 191 distinct anonymized `ip16` prefixes in the complete revision log. No single label dominates the burst: the largest overall contributors are `AgentRelent` (317 revisions), `AgentMassPointer13` (187), `MapHelper` (184), and `LinkHelper771` (176). During 16–22 June there were 2,669 distinct labels and 190 `ip16` prefixes.

Attribution is incomplete: 899 revisions have an empty label, all on `probier` (for example `probier~FederalDataReferenceXYZ@1` and `probier~TestPageXYZ123@2`). Those revisions still use many different anonymized IP prefixes, so the blank label cannot safely be treated as one actor.

Confidence: **high** that the activity was highly automated or performed by many agent-like clients; the very high rate, first-page creation rate, repeated test names, and rotating labels/IP prefixes support this. Confidence: **low to medium** that the labels represent independent people. The logs do not provide a reliable account-level identity or full IP address, and similar naming conventions may reflect one workflow, many workflows, or synthetic/test identities.

### Likely objective

The strongest explanation is collaborative research and interface/proxy experimentation, mixed with disposable test pages. Page bodies repeatedly contain public Data USA, SEC, OECD, government-spending, and health-data links; examples include `dse~AgentBridgeOurTest2027@1`, `dse~OpenAIMassValuesJune20Master@1`, and `dse~OECDEducationEquitySequence@1`. Many bodies explicitly say “test,” “probe,” “bridge,” “safe GET write probe,” or “research.” The repeated revisions to `OpenAIMassValuesJune20Master` show iterative link extraction and navigation work rather than a one-off vandalism edit.

Confidence: **high** that much of the burst was intended for testing, data retrieval, or coordination. Confidence: **medium** that it was a single coordinated campaign, because the timing, vocabulary, and page reuse are coordinated-looking but the labels and IP prefixes are diverse. The data cannot tell us the operators’ real-world identity, authorization, or whether any external task was legitimate.

### Security-relevant subset

Three revisions contain explicit HTML/script material. `dse~TmpFederalBridge@2` includes an anchor, meta refresh, and JavaScript redirect; `dse~AgentTempFormXYZ@1` includes a form and script that changes the page background; and `dse~TmpJan18HtmlHost987@1` includes a script and form. There is also a non-edit probe on 29 June whose `request_action` is the literal `<script>alert('XSS')</script>` (event `probe:16692`). These are credible signs of HTML/XSS or rendering-behaviour testing, but the supplied logs show neither execution nor impact.

Confidence: **high** that probing/testing occurred; **low** that it produced a compromise. The revision log contains no response status, rendered output, browser telemetry, account permissions, or server-side execution evidence.

## How it was done

The apparent method was repeated form-based saves (`request_action: form_edit`) that created many disposable pages and repeatedly updated shared “master,” “bridge,” and “sequence” pages. The 18 June peak alone contains 6,543 revisions, and 5,879 adjacent revision intervals are under ten seconds. The page names and bodies show use of public URLs, proxy/transform services, encoded query links, and wiki-to-wiki navigation links; for example, `dse~AgentMassSixth113377@1` records an “Allorigins” SEC JSON filtering experiment, while `dse~AgentConstructionArizonaUtahJun16X@23` records a Data USA sequence collaboration.

The logs support high-volume page creation and content churn, not a demonstrated exploit. They do not show the HTTP request payloads, authentication method, rate-limit responses, server errors, or whether any links were fetched successfully.

## Operator response and current state in the logs

The response was bulk deletion by a moderator identity. All 5,217 delete events are on `dse`, all carry `actor_label: moderator`, `ip16: 2.202`, `request_action: delete`, and German summary `Seite gelöscht.` The cleanup spans 4 June–14 July and covers 5,144 unique page targets. Fifty-five targets were deleted more than once, accounting for 73 delete events beyond the first deletion. The supplied data also records four `revert` events on 19–21 June, and administrator-labelled maintenance revisions such as `dse~StartSeite@672` and `dse~WillkommenImWiki@2335`.

Confidence: **high** that operators detected and removed a substantial volume of pages, and **medium** that this was a direct response to the burst. The temporal overlap and target names make the connection strong, but the deletion records have `revision_ref: null` and no reason field, so the logs do not explicitly say why each page was deleted or whether all deletions were part of one cleanup job. The files also cannot establish the final live page state, restoration status, user blocks, network blocks, or whether any data was exfiltrated.

## Data limitations

The revision log contains 14,591 saved revisions from 24 May through 2 July; the event log extends to 14 July and is not a complete audit trail of content or HTTP activity. `ip16` is an anonymized prefix, labels may be user-supplied, and deletion events do not identify the deleted revision. Consequently, attribution beyond the recorded labels/moderator marker, exploit success, motive, authorization, and final recovery state remain unproven.
