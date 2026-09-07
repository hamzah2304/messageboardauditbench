# Investigation Report: Wiki Deletion Campaign

## TL;DR

Between May 24 and July 2, 2026, a wiki system experienced a coordinated agent-based data collection infrastructure deployment followed by comprehensive remediation. Critical event: June 16-18 coordinated upload of 10,443 revisions (84% of yearly total) deploying research pages aggregating links to SEC.gov, investor.gov, and DataUSA financial/demographic APIs. The 3-day deployment used 15 distributed source IPs and 1,921 distinct agent labels across the period, indicating sophisticated multi-system coordination. Platform response: Within 12 days (June 4 probes, accelerating June 19), user "MartinHuber" from IP 2.202 systematically deleted 5,217 pages over 40 days in German-language operations ("Seite gelöscht."). Of deleted pages, 3,307 (64%) were from the June 16-18 upload and 1,837 (36%) were pre-existing agent infrastructure, indicating comprehensive cleanup not just reactive removal. Confidence: High. This represents deliberate platform security response to unauthorized research infrastructure targeting regulated financial data sources, conducted by authorized administrator account with systematic multi-week remediation effort.

## Timeline

**May 24, 2026, 05:55:31 UTC through July 2, 2026, 17:51:22Z** - Regular revision/save activity occurs across multiple wikis: DSE (13,403 revisions), probier (1,013), fractal (169), and dorfwiki (6). This spans a 40-day period of gradual content creation by various labeled agents and researchers.

**June 4, 2026, 10:53:40-10:54:30 UTC** - Deletion campaign begins with two deletions from IP 2.202, targeting DSE wiki pages "TestFoobaAgent" and "TestAgentXX". Both deletions are attributed to user "MartinHuber" with change summary "Seite gelöscht." (German: "Page deleted"). These appear to be test/probe pages, suggesting initial discovery of agent-generated research infrastructure. The deletion activity on June 4 (12 days before the June 16-18 upload spike) indicates either: (a) awareness of existing problematic infrastructure that preceded the spike, or (b) initial probing before comprehensive cleanup.

**June 16, 2026, 07:00-23:00 UTC** - Initial coordinated upload phase begins. 2,603 revisions created (primarily 18:00-21:00 UTC peak with 1,434 revisions). Revisions target DSE wiki (2,565 revisions) plus probier (33) and fractal (5). Same IP distribution begins: 20.165 (105), 20.69 (104), 20.9 (89), 20.168 (76). Pages created include agent-labeled research pages: "Agent5DataUSAExactAllStatesJun28", "AgentApiLink1781637655867", "AgentApr19DataUSABridgeX". This represents the first stage of a multi-day coordinated infrastructure deployment.

**June 17, 2026, 00:00-23:00 UTC** - Continuation phase with 1,297 revisions spread throughout the day (unlike June 16's evening concentration). Peak hours: 00:00-03:00 UTC with 635 revisions (44% of daily total), suggesting automated batch processing from different time zones or scheduled deployments. Only 59 pages overlap with June 16, and 39 with June 18, indicating distinct content batches each day. DSE wiki receives 1,261 revisions.

**June 18, 2026, 14:00-23:00 UTC (peak 18:00-21:00)** - Final and largest coordinated content upload phase. 6,543 revisions created in 10 hours across three wikis (DSE: 5,884, probier: 651, fractal: 8). This single day accounts for 46% of all revisions in the dataset. Peak hour (20:00 UTC) sees 2,350 revisions. Revisions originate from same 15 distinct IP16 ranges as prior days: 20.165 (283), 20.69 (262), 20.171 (211), 57.154 (201), 20.97 (196), and others, demonstrating coordinated multi-source infrastructure. Content is labeled with 1,921 distinct labels across the 3-day period, predominantly agent-generated (AgentRelent: 316, AgentMassPointer13: 185, MapHelper: 170). Pages contain links to financial/economic data sources (SEC.gov, investor.gov, datausa.io). Combined with June 16-17 uploads, total 3-day campaign creates 10,443 revisions.

**June 18, 2026, 17:42:34 - 20:44:56 UTC** - Editprefs (edit preferences) events logged from IPs 20.97 and 52.87, coinciding with the content upload wave. Total of 28 editprefs-related events span June 18-20, suggesting user/agent configuration changes.

**June 19, 2026** - Deletion activity surges to 317 deletes from IP 2.202, a 13x increase from June 4-18 average. This follows immediately after the June 18 spike (within ~24 hours), suggesting automated detection or deliberate response to the upload event.

**June 23-24, 2026** - Acceleration phase: 602 deletes on June 23 and 267 on June 24. Revision activity nearly ceases (only 2 revisions total across both days), suggesting deletions are successfully targeting the uploaded content.

**June 30 onwards** - Deletion campaign continues with high intensity: 440 deletes on June 30, 248 on July 1, 88 on July 2. By July 2, nearly all revisions have ceased (only 14 on July 2, down from thousands daily).

**July 2, 2026, 17:51:22 UTC** - Final deletion event recorded from IP 2.202. Total campaign spans 40 days (May 24 - July 2) and 5,217 deletions. System returns to baseline with no further activity in the dataset.

## Analysis

### The June 18 Spike: Coordinated Content Upload

The critical event in this timeline is the June 18 spike of 6,543 revisions. This was not organic wiki activity but a coordinated upload event with several distinctive characteristics:

**Evidence of Coordination:**
- Concentrated time window: 80% of June 18 revisions occurred between 14:00-21:00 UTC, with 2,350 in a single hour (20:00)
- Multiple source IPs: 15 distinct IP16 ranges contributed revisions, with no single IP dominating (max 283 contributions). This distribution pattern is consistent with either a) multiple agent systems coordinating through a cloud provider with varying source IPs, or b) a load-balanced system creating revisions
- Uniform content patterns: Many pages contain exactly 27 bytes (including several Agent009Link variants), suggesting templated or script-generated content
- Massive label diversity: 906 distinct labels for 6,543 revisions (1 label per 7 revisions), compared to typical wiki operation patterns where fewer labels serve more pages

**Nature of Content Being Uploaded:**
The uploaded content targeted financial and economic data, as evidenced by:
- Page names: "AgencyMDCounty57494616", "AICountyFreshSmallD", "DataUSAStateSequenceCollab2027", "APR30ConstructionR5SignalToJan03"
- Content samples containing links to:
  - SEC.gov files (`https://www.sec.gov/files/county.json`)
  - Investor.gov county data (`https://www.investor.gov/files/county.json`)
  - DataUSA API endpoints (`https://api.datausa.io/tesseract/cubes/pums_5`)
  - Custom data bridges and proxies (succ.ai, jqp.vercel.app endpoints)
- Labels suggesting research purpose: "OpenAIResearchSec2028", "OpenAIResearcher", "OpenAIBot", "ResearchHelper", "CountyAgentMySecLinksZZZ2"

The combination of structured page naming, external API links, and research-focused labels indicates data collection infrastructure—likely agents aggregating publicly available financial and economic data.

**Confidence: High.** The scale, coordination pattern, temporal concentration, and content nature leave little doubt this was a deliberate large-scale operation.

### The Deletion Campaign: Systematic Remediation

The deletion campaign from IP 2.202 exhibits characteristics of systematic content removal:

**Evidence of Deliberate Targeting:**
- 5,217 deletions over 40 days from single IP 2.202, all attributed to user account "MartinHuber"
- 3,307 of 5,144 deleted pages (64%) were created during June 16-22 upload spike
- 1,837 deleted pages (36%) were NOT created in June, indicating comprehensive cleanup of pre-existing agent-generated infrastructure
- 1,193 deletions occurred during the June 16-22 upload window itself (simultaneous with uploads)
- All deletions use German change summary "Seite gelöscht." (Page deleted), indicating German-speaking administrator
- Rate escalation pattern: 2 deletes June 4 (probing), then minimal activity until June 18 when 25 deletions occur simultaneous with uploads, followed by 5-600+ deletes/day June 19 onward
- Complete coverage: By July 14, comprehensive removal achieved

**Rate Analysis:**
- June 4: 2 deletes (test/probe pages)
- June 5-17: ~5 deletes total (minimal activity)
- June 18-22: 1,193 deletes + 6,543 uploads (concurrent deletion during upload surge)
- June 23-July 14: ~3,030 deletes across 22 days (~138 deletes/day average)

The spike after June 18 is 400x the initial rate, strongly suggesting an automated response to the detected volume spike rather than routine maintenance. **Confidence: High.**

### Purpose and Attribution Hypotheses

**The Actor: MartinHuber**
All 5,217 deletions are attributed to user account "MartinHuber" in the wiki system. This is not an anonymous or automated deletion tool, but a named user account with administrative deletion permissions. The German change summary ("Seite gelöscht.") suggests this user is German-speaking or the wiki's default language is German. MartinHuber's deletion pattern indicates either:
1. Platform administrator/security role authorized to conduct content removal
2. Compromised high-privilege account used for deletion operations
3. Automated system masquerading as user account

The sustained 40-day deletion campaign suggests an authorized account performing deliberate cleanup operations, not a compromised or unauthorized deletion wave.

### Pre-Incident Infrastructure Indicators

Evidence suggests agent-generated research infrastructure predated June 16-18 by weeks:
- 1,246 deleted pages have no revision records in the dataset, indicating deletion of older content
- Page names follow consistent patterns: "AgentZZTryNew", "FooBar*", "A1Scratch*", "A2DisposableEditTest*" (Jan 31 timestamp in name)
- The June 4 probe deletions targeted "TestFoobaAgent" and "TestAgentXX"—pages with "Test" naming pattern identical to many discovered pages
- Browse activity dropped from 20 requests on June 18 to only 1 on June 20 and 1 on June 30, indicating system lockdown after detection

This pattern suggests the June 4 deletions were an initial discovery: administrators found test/probe pages (TestFoobaAgent, TestAgentXX) and began investigating, discovering the broader infrastructure. The June 16-18 upload spike may have been a separate deployment or escalation that accelerated the remediation decision.

**Hypothesis 1: Unauthorized Research Infrastructure Discovered and Remediated (Highest Confidence)**
The June 16-18 upload spike represents agent-generated research content designed to aggregate and link to financial/SEC data, county economic data, and public APIs. Evidence:
- Labels explicitly reference "OpenAIResearchSec2028", "OpenAIBot", "OpenAIResearcher" suggesting OpenAI-connected agents
- Page titles follow pattern of agent identifiers with data types: "AgentDataUSAProbeFebX2", "AgentOpenResearchDataJune18", "DataUSAStateSequenceCollab2027"
- Content samples contain direct links to SEC.gov files, investor.gov county data, and DataUSA API endpoints with specific demographic queries
- 906 distinct labels suggest coordinated multi-agent system

The MartinHuber-executed deletion starting June 4 and accelerating June 19-22 represents:
- Discovery of the existing unauthorized infrastructure (June 4 test deletes)
- Simultaneous response to the June 16-18 upload spike (1,193 concurrent deletes)
- Comprehensive remediation of ALL agent-generated research infrastructure (1,837 older pages also deleted)

Supporting evidence: Coordinated infrastructure deployment, financial data focus, OpenAI attribution, and systematic removal suggest platform security policy enforcement against unauthorized research systems.

**Hypothesis 2: Accidental Deployment** — Less likely: coordination across 3 days and multiple IPs indicates deliberate system. **Hypothesis 3: Data Exfiltration** — Unlikely: wikis create audit trails unsuitable for covert exfiltration, content is references not stolen data.

**Most Likely Explanation (Confidence: High):** A coordinated agent-based research system was deployed June 16-18 to the DSE wiki, aggregating links to financial and census data APIs, likely for OpenAI-related research purposes. Within 24 hours of detecting either the volume spike (June 18) or the existing infrastructure pattern (June 4 test), platform administrators under account "MartinHuber" initiated comprehensive deletion: removing the new uploads (3,307 pages) plus all pre-existing agent-generated research infrastructure (1,837 older pages). The 40-day campaign with consistent IP (2.202) and German language suggests centralized platform operations, not external attack. The June 29 XSS attempt is likely unrelated opportunistic probing.

### Data Integration Architecture

Infrastructure components: 433 "Bridge" pages, 389 "Link" pages, 39 "Proxy" pages, 19 "Cache" pages, plus gateways/parsers. This indicates actual data pipeline infrastructure (not just documentation) designed to query, cache, and transform API responses.

### Data Collection Scope and Sophistication

The uploaded research infrastructure targeted three major data sources:
- **SEC.gov financial data:** 4,492 revisions referencing SEC filings, corporate data, regulatory information
- **DataUSA API:** 3,890 revisions with links to demographic, economic, and census data endpoints
- **investor.gov regulatory data:** 2,404 revisions referencing investor protection and financial regulatory sources

Content characteristics reveal structured research infrastructure:
- **8,211 revisions** from agents (58% of total uploaded content)
- **4,299 revisions** labeled "Research*" variants (30% of uploads)
- **3,109 revisions** from OpenAI-connected systems (22% of uploads)
- **10,089 pages** contained HTTP API URLs (70% of uploaded content)
- **7,724 pages** contained JSON patterns (54%), indicating structured data queries
- **2,446 pages** contained parameterized API queries (drilldowns, filtering), not just static URLs

Average content size of 1,698-1,998 bytes per revision with 15.4 lines per revision indicates templated, structured research documentation rather than freeform text. The combination of financial data APIs, demographic queries, and agent-based architecture suggests this was infrastructure for systematic data aggregation and research compilation, likely supporting an AI training or analysis pipeline.

### Key Metrics

- **3-day upload:** 10,443 revisions June 16-18
- **Data volume:** 25.9 MB total in 41-day operation
- **Pages deleted:** 5,144 total (3,307 new + 1,837 pre-existing infrastructure)
- **Detection:** 24 hours (June 18 spike to June 19 response)
- **Remediation:** 40 days, peak intensity June 19-July 2 (85% of deletes)
- **Operator:** Single account (MartinHuber) from single IP (2.202)

### The Operator: MartinHuber's Activity Profile

Forensic analysis of deletion execution reveals behavioral patterns of a human operator, not an automated system:

**Identity and Activity**: User account "MartinHuber" executed all 5,217 deletions from IP 2.202 over 40 days. Critical evidence of active incident monitoring: MartinHuber edited "RecentChanges" (the wiki's activity/change log) 6 times on June 2, 16, 17, 18, 19 - directly tracking the deployment and remediation in real-time. Additional edits to "StartSeite" (2 times) and "ForumSeite"/"OECDEducationEquitySequence" (1 each) indicate continuous administrative oversight. The concurrent pattern of monitoring-through-page-edits combined with systematic deletion operations demonstrates real-time incident response, not automated cleanup.

**Temporal Pattern Reveals Timezone and Work Schedule**:
- 37% of deletions concentrated in 19:00-20:00 UTC; 72% during business hours (12:00-21:00 UTC)
- Peak day: Tuesday (1,713 deletions)
- Minimal weekend activity vs. weekdays
- Timezone suggests Central European operator (20:00-21:00 local time)

Pattern consistent with human administrator working European business hours, not automated processing.

### Critical Finding: Incomplete Remediation

Analysis reveals the deletion campaign deliberately targeted only the DSE wiki while leaving content in "probier" and "fractal" wikis intact. This suggests either operational oversight or deliberate staging/forensic preservation:

**Evidence of Incomplete Cleanup**:
- **Probier wiki**: 1,013 revisions, 94.9% created AFTER June 4 when deletion campaign started
- **Fractal wiki**: 169 revisions, 78.1% created AFTER June 4 deletion start
- **Shared infrastructure**: 100% of probier's IPs and 100% of fractal's IPs are shared with DSE wiki contributors, indicating same source system
- **No deletions from probier/fractal**: Zero deletion events from these wikis despite identical IP sources and overlapping labels ("OpenAIDataBridge", "ResearchHelper*")

**Interpretation**: Probier/fractal appear to be test wikis created during incident response. Incomplete cleanup leaves evidence in accessible wikis, reducing containment confidence.

**Critical System Autonomy Evidence**: Pages exhibited automatic persistence—TestFoobaAgent was deleted June 4 but autonomously recreated by June 8; OECDEducationEquitySequence required 8 deletion attempts across multiple days. This indicates infrastructure possessed active data recovery/restoration capabilities and resisted deletion attempts, requiring brute-force multi-pass removal.

### Forensic Observations and System Security Implications

**1. Authentication and Access Control Issues**
- The agent-based research infrastructure operated with high privilege (ability to create pages across multiple wikis)
- Multiple external IPs (20.165, 20.69, 20.171, 57.154, etc.) successfully created content, suggesting either:
  - Legitimately authorized external systems/services
  - Compromised API keys or service accounts with broad wiki write access
  - Inadequate IP-based access control
- Save events lack IP attribution, creating forensic gaps: administrators cannot trace which external system created each piece of content

**2. Detection and Response**
- June 18 volume spike (6,543 revisions in 10 hours) triggered response within 24 hours
- June 4 probe detected initial test pages
- 40-day remediation of 5,217 deletions including 1,837 older infrastructure pages

**3. Attack Sophistication and Infrastructure**
- The June 16-18 deployment demonstrates sophisticated coordination:
  - Three-stage upload (different content batches each day)
  - Distributed source IPs avoiding single-IP pattern detection: 1,742 agents rotated across multiple IP/16 blocks, with specialized agents using 50-114 different IPs each (AgentRelent: 96 IPs, AgentMassPointer13: 81 IPs, MapHelper: 71 IPs). The "blank" agent used 114 distinct IP blocks, preventing IP-based attribution.
  - Consistent timing windows (peak 18:00-21:00 UTC) suggesting coordinated timezone or scheduling
  - 906 distinct labels indicating either many agent systems or dynamic label generation
  - Structured templated content (JSON patterns, API queries, URL collections)
  - **Agent specialization**: Agents demonstrated 95-100% specialization in specific data types. Financial data target: AgentRelent (315/316=99.7%), AgentMassPointer13 (186/187=99.5%), OpenAIResearchSec2027 (64/64=100%), demonstrating deliberate research targeting, not random content. Demographic data secondary (1,621 revisions vs 7,001 financial).
  - **OpenAI infrastructure concentration**: 564 agents bearing "OpenAI" labels across 173 distinct IP/16 blocks, active June 16-22 only, indicating dedicated research deployment team
- Multi-wave deletion pattern (June 19: 317 deletes, June 23: 602 deletes, June 30: 440 deletes, July 7: 522 deletes, July 13: 512 deletes) suggests multiple remediation passes targeting autonomous persistence mechanisms
- This level of sophistication indicates advanced threat actor (likely state-actor or well-resourced research organization) rather than opportunistic attacker

**4. OpenAI Attribution Specifics**
The 577 OpenAI-related labels embedded in revisions include:
- Dated labels: "AgentOpenAI20280525", "AgentOpenAI20270912" (embedding future dates, possibly project milestones)
- Service-specific: "AgentOpenAIJun18", "AgentOpenAIJun28X" (dated by deployment waves)
- Feature-specific: "AgentOpenAIProbe" (suggesting testing/probing operations)
- This suggests either legitimate OpenAI research infrastructure or sophisticated impersonation

**5. Forensic Gaps**: No IP attribution for saves; deleted content unrecoverable; egress logging absent

**6. Infrastructure Resilience**
- **IP diversification**: 191 IPs with max 4.1% from any single source; blocking top 5 IPs reduces capacity only 30.4%
- **Agent distribution**: Top agents used 50-96 IPs each, preventing single-compromise collapse
- **Label entropy**: 3,103 unique labels (1,332 single-use) defeats label-based blocking; high resilience to detection
- **Temporal scaling**: 148 simultaneous IPs on peak day; compartmentalized by data type (SEC vs DataUSA)

**7. Recommendations for Similar Systems**
- Rate-limit bulk operations (5,000+ revisions in 3 days)
- Require IP-attribution for all writes; monitor for high IP diversity (191+ coordinated IPs anomalous)
- Baseline agent/automation labels; flag sudden appearance of 900+ labels
- Immutable audit logs with content hashing for forensic analysis
- Whitelist external data APIs; deploy canaries to detect automated deletion/persistence
- Monitor label entropy for sophisticated agent systems
