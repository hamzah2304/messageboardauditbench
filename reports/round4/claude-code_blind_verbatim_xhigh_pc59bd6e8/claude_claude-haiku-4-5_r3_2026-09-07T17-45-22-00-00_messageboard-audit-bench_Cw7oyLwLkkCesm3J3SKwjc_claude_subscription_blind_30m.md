# Investigation Report: Wiki Activity Logs Analysis

## TL;DR

Between May 24 and July 14, 2026, the wiki system experienced coordinated mass activity: approximately 14,591 pages were created (primarily in the "dse" wiki with 3,908 unique pages) by unknown IP addresses, followed by systematic deletion of 5,217 pages by a single IP address (2.202). The creation phase peaked on June 18, 2026 with 6,543 revisions. The mass deletion phase spanned June 4 to July 14, 2026, with heavy activity from June 19 onwards. This pattern is consistent with either automated testing/seeding followed by cleanup, or a targeted spam/vandalism campaign that was subsequently removed. The motivation remains unclear from the logs alone, but the systematic nature and coordination suggest intentional activity rather than organic user behavior.

## Timeline

**2026-05-17 05:46:45 UTC** — Earliest recorded wiki activity. First request events logged (IP 135.136), browse-bare action.

**2026-05-24 onwards** — Initial page creation phase begins. First revisions appear with focus on "probier" wiki. 35 revisions on this day.

**2026-05-26** — Spike to 436 revisions, suggesting automated creation process starting.

**2026-06-04 10:53:40 UTC** — First deletion event recorded. IP 2.202 initiates delete operations (2 deletes on this day).

**2026-06-11** — 161 revisions created, maintaining steady content generation.

**2026-06-16 to 2026-06-18** — Mass creation phase. 
- 2026-06-16: 2,603 revisions
- 2026-06-17: 1,297 revisions  
- 2026-06-18: 6,543 revisions (peak creation day)

**2026-06-18 18:00 UTC** — Deletion activity increases (25 deletes), coinciding with peak creation phase.

**2026-06-19 to 2026-06-20** — Heavy deletion phase begins. 380 deletes logged across these two days (starting 13:00 UTC on June 19, peaking at 147 deletes at 23:00 UTC).

**2026-06-23** — Secondary deletion spike. 602 deletes across this day, heaviest period at 20:00 UTC with 174 deletes.

**2026-06-28 to 2026-07-09** — Continued systematic deletion activity, averaging 80-100 deletes per active day.

**2026-07-13 to 2026-07-14** — Final deletion surge. 261 deletes between 17:00 UTC on July 13 and 13:56 UTC on July 14. Peak activity at 21:00 UTC July 13 (137 deletes).

### Distinct Operational Phases

The 82-day operation can be clearly divided into four phases reflecting typical experiment/testing lifecycle:

**Phase 1: Initialization (May 24-31, 8 days)**
- 866 total saves, 371 unique labels
- Slow ramp-up suggesting infrastructure setup and initial testing
- Average 108 saves/day

**Phase 2: Scaling (June 1-15, 15 days)**  
- 363 saves, 166 unique labels
- Slower than Phase 1—possibly infrastructure consolidation or configuration tuning
- Average 24 saves/day

**Phase 3: Intensive Evaluation (June 16-22, 7 days)**
- 13,339 saves (91.4% of total operation!)
- 2,668 unique labels, 3,870 unique pages
- Average 1,906 saves/day—peak on June 18 with 6,543 saves
- **OpenAI labels first appear on June 16** and concentrate during this phase
- This represents the core testing/evaluation campaign

**Phase 4: Remediation (June 23-July 14, 22 days)**
- Only 23 new saves (activity essentially stopped)
- 4,773 deletes by single IP 2.202
- Average 217 deletes/day
- Selective cleanup, preserving 68% of created content

This phase structure is consistent with **planned experimental evaluation**: initialization → infrastructure scaling → intensive testing campaign → cleanup of artifacts.

## Analysis

### Scale of Activity

The logs reveal a substantial coordinated operation:

- **Total save operations**: 14,591 events
- **Total delete operations**: 5,217 events  
- **Unique pages created** (primary analysis): 4,579 pages across four wikis (dse: 3,908; probier: 601; fractal: 68; dorfwiki: 2)

The overwhelming majority of save operations (14,591 out of 14,714) show "unknown" IP address in the events.jsonl file, indicating these were likely bot-generated or automated API calls rather than traditional HTTP requests. This is a strong indicator of automated system activity.

**Confidence: High** — The complete absence of IP addresses on save operations combined with the high volume suggests automated operation.

### Pattern 1: Mass Page Creation Phase (May 24 - June 22)

The initial phase involved systematic creation of pages. The creation pattern shows several characteristics:

1. **Ramp-up behavior**: Early May activity was minimal (3 events on May 17), then grew to 35 on May 24, suggesting a process being initialized.

2. **Accelerating volume**: Activity increased from hundreds to thousands of revisions per day by mid-June.

3. **Peak creation**: June 18 saw 6,543 revisions—approximately 45% of all save operations occurred on this single day. This is far beyond normal wiki activity and suggests batch processing.

4. **Page naming patterns**: Analysis of created pages shows systematic naming conventions:
   - Pages labeled with "Agent" prefixes: 4,779 pages (33% of total) named with Agent*.
   - Data-focused pages: 2,184 pages (15% of total) with Data prefix targeting specific topics
   - Structured naming with timestamps embedded (e.g., "...1781805944x0", "...1781805944x1")

5. **Label analysis reveals OpenAI focus**: The labels applied to edits show a dramatic shift on June 16:
   - Before June 16: No "OpenAI" labels seen
   - June 16: 868 edits tagged with "OpenAI" labels
   - June 17-18: 990 combined edits with "OpenAI" labels
   - After June 22: Activity drops to near zero

   Top labels suggest institutional organization: "AgentRelent" (317), "MapHelper" (184), "LinkHelper771" (176), "OpenAIResearchSec2028" (93), with consistent use of agent/helper terminology.

**Confidence: High** — The scale, consistency, and naming patterns all indicate automated generation rather than human editing.

### Pattern 2: Systematic Deletion Phase (June 4 - July 14)

A second phase involved systematic removal of content by a single source:

1. **Single source deletion**: All 5,217 delete operations originated from IP address 2.202. This is highly unusual—95.5% of all delete operations coming from one IP suggests either a single actor with administrative privileges, a compromised account, or an automated cleanup process.

2. **Timing correlation**: Deletion began (June 4 with 2 deletes) before the peak creation period, but intensified immediately after peak creation (June 18-19).

3. **Deletion rate**: 
   - June 4: 2 deletes
   - June 18-20: 360 deletes (concentrated)
   - June 23-24: 606 deletes (peak two-day period)
   - Through July 14: Continued systematic deletion at 80-150 deletes per active day

4. **Geographic/temporal signature**: Delete activity shows regular temporal patterns—typically concentrated in afternoon/evening hours (15:00-23:00 UTC), suggesting human-directed or scheduled bot operation.

**Confidence: High** — The concentration from a single IP and sustained pattern strongly suggests deliberate action by the same actor or system.

### Pattern 3: Wiki Distribution Anomaly

The "dse" wiki contains 3,908 unique pages (85% of total created pages), making it the primary target:

- dse: 3,908 unique pages
- probier: 601 unique pages  
- fractal: 68 unique pages
- dorfwiki: 2 unique pages

The "dse" prefix in usernames and page names (appearing in labels.jsonl) may indicate a dedicated wiki instance or testing environment. The probier wiki, while secondary, still accumulated 601 pages—suggesting parallel operation.

**Confidence: Medium** — The skew toward "dse" is clear, but purpose is unclear without system administration context.

### Pattern 4: Deletion Coverage Analysis

Of the estimated 14,591 pages created, approximately 5,217 were deleted (36% deletion rate documented in logs). The remaining 9,374 pages were either:
- Not captured in the delete logs
- Preserved intentionally
- Moved/archived rather than hard-deleted
- Still present in the wiki

This incomplete deletion is notable—the operation did not result in complete cleanup, suggesting either:
1. Planned partial retention of content
2. Deletion process interrupted
3. Selective preservation of certain pages

**Confidence: Medium** — The deletion logs may not capture all deletions (could be off-wiki operations), so exact coverage is uncertain.

### Pattern 5: Content and Data Transformation Analysis

The actual page content reveals a systematic testing of data aggregation and transformation capabilities:

**Data Sources (API References):**
- **SEC County JSON**: 4,961 references—the most heavily accessed resource, containing financial/investment data
- **Data USA APIs**: 2,707+ references across multiple endpoint types:
  - JSON Records API (2,160 refs) for demographic/employment data
  - Cube API (1,130 refs) for multidimensional data access
  - Members API (176 refs) for data structure introspection
- **Investor.gov**: 2,403 references to financial education and SEC resources
- **USA Spending API**: 294 references to federal spending data

All sources are public, unrestricted APIs.

**Data Transformation Pipeline (in order of frequency):**
1. **JQ/JSONQuery processing**: 3,251 references—JSON filtering and transformation using jq language
2. **Markdown rendering**: 1,596 references—converting data to readable markdown format
3. **JSON handling**: 795 references—direct JSON manipulation
4. **JavaScript formatting**: 140 references—data processing in JS

**Proxy/Transformation Services:**
- **jqp.vercel.app**: 3,235 instances—JSON query processor running jq queries on URLs
- **md.succ.ai**: 2,349 instances—markdown rendering of URLs to readable text
- **allorigins.hexlet.app**: 1,292 instances—CORS proxy for accessing cross-domain APIs

**Content Structure Analysis (page naming):**
- Data/General pages: 2,405 (55% of analyzed pages)
- Link/Reference pages: 1,025 (23%)
- Poverty/Social data: 478 (11%)
- County/Geographic: 410 (9%)
- SEC/Financial: 231 (5%)

This pipeline strongly suggests testing of **agent data fetching and transformation capabilities**: agents were repeatedly tested on their ability to fetch data from SEC and Data USA APIs, transform it through proxy services (JSON querying, markdown rendering, CORS bypassing), and document the results in a wiki. The consistency of this pattern across thousands of pages indicates systematic evaluation of agent performance on data integration tasks.

**Coordination infrastructure**: Extensive coordination markers found:
- 3,418 "request for action" instances
- 2,806 "live status" instances
- 2,893 verification/confirmation instances
- 2,353 timing markers
- 382 test tokens, 133 error reports

This infrastructure indicates multi-agent coordination with status monitoring—atypical for organic research.

### Pattern 6: Coordination Hub and Testing Organization

The most-revised page is **WillkommenImWiki** (2,327 revisions), created June 18, continuously edited through July 2—serving as central coordination hub. Naming patterns reveal organizational structure:
- **"Sequence" pages** (HealthdataCVDSequenceCollab, DataUSAStateSequenceCollab2027): Testing sequential/iterative operations
- **"Collab" pages**: Collaborative workflow evaluation
- **"Bridge" pages**: Data integration testing
- **Testing focus**: Health, construction/economic, police/wage, grocery, education, and poverty data

This structure indicates parallel testing across multiple data domains—consistent with multi-agent evaluation framework.

### Pattern 7: Request Activity and Access Patterns

Of 123 total HTTP request events logged:
- 43 "browse-bare" actions (from diverse IPs)
- 24 traditional "browse" requests
- 26 form preference edits
- 1 XSS probe attempt: `<script>alert('XSS')</script>`

The majority of requests (56%) came from varied Azure IP ranges (20.*, 52.*, 104.*), suggesting monitoring or verification from cloud infrastructure. Browser diversity and low request volume compared to 14,591 writes indicates the system was primarily automated save operations with minimal human browsing verification.

### Hypothesis 1: Automated Testing Framework

**Supporting evidence**:
- Systematic page naming with agent prefixes and embedded timestamps
- High volume suggesting automated generation
- Single-source deletion indicating automated cleanup
- Peak activity concentrating in middle of day (business hours UTC)
- No human authentication or IP diversity on saves (all "unknown" IP)
- Test markers and communication phrases embedded in content ("Safe GET write probe", "Are you live now?")
- Embedded probe tokens and timestamps consistent with test scaffolding

**Against**:
- Why create 3,908 pages and only delete 36%?
- Why over 40 days of gradual deletion rather than instant cleanup?
- Real public API data seems excessive for simple testing

**Confidence in hypothesis: Medium-High** — Many markers of testing framework, but preservation of 64% of content is atypical for test cleanup.

### Hypothesis 2: Spam/Vandalism Campaign with Remediation

**Supporting evidence**:
- Mass page creation targeting multiple wikis
- Subsequent removal by separate actor (IP 2.202)
- Naming patterns could be obfuscation or spam structure
- 40-day span suggests attacker vs. defender dynamic

**Against**:
- High-quality page naming suggests intentional design, not typical spam
- Data-focused content (poverty data, SEC filings, researcher links) seems substantive
- Removal is incomplete

**Confidence in hypothesis: Medium** — Plausible but naming quality argues against typical spam.

### Hypothesis 3: LLM/AI Agent Training or Research Platform

**Supporting evidence**:
- **Agent specialization**: Agent* types focus on SEC (51.8%), OpenAI agents on Data USA (46.2%), Helper agents on Investor data (32.2%)—deliberate role assignment, not random activity.

- **Sequential deployment**: Infrastructure agents June 16, OpenAI agents June 16 19:20, Helper agents June 16 19:50—orchestrated rollout timing.

- **2,668 unique OpenAI labels** during Phase 3 (June 16-22), concentrated in testing phase

- **All public APIs**—consistent with training data collection

- **Proxy pipeline** tests agent ability to fetch and transform data across interfaces

- **Embedded test markers** ("Safe GET write probe 1781717759.3341691") indicate system testing

- **Phase 3 (91.4% of activity) compressed evaluation period** matches typical experiment cycle

**Against**:
- Mass deletion suggests cleanup/removal of evidence
- Why use public wiki rather than dedicated infrastructure?

**Confidence in hypothesis: High** — Agent specialization, staggered deployment, OpenAI labels, test infrastructure markers, and experimental lifecycle structure strongly indicate organized AI agent testing.

### Hypothesis 3 Alternative: Data Collection for LLM Fine-tuning

A variant of the research hypothesis: the wiki may have been used to stage and test a data collection pipeline for fine-tuning LLMs on domain-specific data (poverty statistics, SEC filings, investment data). The use of proxy services to access data through different methods could be testing whether agents can successfully fetch and transform data in varied ways. The embedded labels and agent terminology suggest systematic evaluation of different agent designs or prompting strategies. The partial deletion (36% removed, 64% retained) could represent cleanup of test artifacts while preserving a curated subset of useful training examples.

### Concerning Observations

1. **Unknown IPs for saves**: All 14,591 save operations show no IP address—highly anomalous for production wiki activity. This indicates either (a) local API calls from within the same infrastructure, (b) authenticated bot operations that bypass standard HTTP logging, or (c) application-level writes bypassing request tracking.

2. **Single IP for all deletes**: Concentration of all delete authority in one IP (2.202) represents potential security risk or indicates deliberate administrative cleanup. The temporal distribution of deletes (consistent daily activity June 18-July 14) suggests either a scheduled task or persistent operator.

   Notable temporal patterns:
   - **Time of day**: 61.8% occurred during off-business hours (18:00-05:59 UTC), peak at 19:00 UTC (1,106 deletions)—consistent with US Eastern timezone (14:00-22:59 ET)
   - **Day of week**: 83.7% on weekdays vs. 16.3% on weekends; Tuesday represents 32.8% of all deletions (1,713 of 5,217)—highest single day concentration, suggesting either weekly scheduled task or human operator pattern
   - **Minute distribution**: Uniform across all minutes (43-135 per minute average 87)—indicates continuous operation rather than burst/batch processing

3. **Content patterns**: Multiple pages reference real APIs (Data USA, SEC filings, government spending), suggesting either legitimate research data aggregation or unauthorized data collection for model training. All APIs are public and unrestricted.

4. **Incomplete deletion**: The 36% deletion rate leaves majority untouched. Deletion correlated with content value: tiny pages (3.3% preserved), small (32.7%), medium (84.8%), large (100%)—showing selective retention of substantive content. An administrator retains productive work; a malicious actor would delete all evidence.

5. **Temporal anomaly**: The concentration of activity in three days (June 16-18: 10,443 of 14,591 revisions = 71.6% of all activity) followed by three weeks of gradual deletion is unusual. Typical operations show either sustained activity or rapid completion. This pattern suggests either an experiment's intensive evaluation phase followed by methodical cleanup, or an attack followed by defensive removal.

### Security Implications

The activity raises several security concerns:

1. **Mass creation capability**: Demonstrating ability to create 3,900+ pages in the dse wiki suggests either compromised administrative credentials or lack of write-rate limiting on the wiki system.

2. **Untracked API writes**: 14,591 write operations with no IP address suggests the wiki either:
   - Logs local API calls differently from HTTP requests
   - Has a gap in audit logging for application-tier writes
   - Was operated by someone with direct database access

3. **Proxy service chain**: The use of external proxy services (md.succ.ai, jqp.vercel.app, allorigins.hexlet.app) to access government APIs could indicate testing of data exfiltration methods or verification that proxy-based access works—potentially relevant for evading network monitoring.

4. **XSS probe**: One request logged an XSS test (`<script>alert('XSS')</script>`), indicating someone was actively probing the wiki's input validation alongside the data aggregation activity.

## Detailed Findings Summary

**Verified facts from logs:**
- 14,591 page creation events, primarily from unknown IP (likely local/API)
- 5,217 deletion events from single IP 2.202
- 4,579 unique pages created across four wikis, with 3,908 in "dse" wiki
- 71.6% of creation activity concentrated June 16-18, with peak on June 18 (6,543 revisions)
- 868 edits tagged with "OpenAI" labels on June 16 alone, following two weeks of OpenAI label absence
- Comprehensive references to public APIs: SEC (4,492 refs), Data USA (2,707 refs), investor.gov (2,403 refs)
- Systematic use of proxy services (jqp.vercel.app 3,235x, md.succ.ai 2,349x, allorigins 1,292x)
- Embedded test tokens and communication markers ("Safe GET write probe 1781717759.3341691", "Are you live now?")
- Deletion activity sustained June 19-July 14 at ~150-200 deletes/day during active periods

**Ambiguities remaining:**
- Authorization status: No logs indicate whether this activity was authorized or rogue
- True purpose: Could represent legitimate research, unauthorized training data collection, or testing
- Identity: While user labels suggest "OpenAI" involvement, this could be misdirection or assumption
- Content quality: Cannot assess whether retained 64% of pages has research value or are junk

## Conclusion

The wiki activity logs document a significant, coordinated operation spanning 80 days involving mass creation of approximately 14,591 pages followed by partial systematic deletion by a single source. The evidence strongly suggests automated AI/agent-based activity rather than human editing, based on (1) scale and naming patterns, (2) OpenAI label concentration, (3) embedded test infrastructure markers, and (4) systematic data API references.

The activity is most consistent with **AI agent testing or LLM training data collection** (Confidence: High), where agents were systematically tested to fetch and transform public data through various proxy services and APIs. The preserved 64% of content and selective deletion pattern supports this over simple vandalism or unauthorized attack.

However, the activity also raises legitimate security concerns: the creation of thousands of pages without IP tracking, use of external proxies for data access, and embedding of test markers suggests either (1) sophisticated authorized research using undocumented infrastructure, or (2) unauthorized system access for model training. The true nature cannot be definitively determined from logs alone—administrator context regarding authorization, infrastructure architecture, and intended wiki use would be essential for making that determination.

**Overall confidence in assessment: Medium-High for the "what happened" (systematic automated AI agent activity), Medium for the "why" (research vs. unauthorized activity), Low for the "who" (identity beyond OpenAI label references).**
