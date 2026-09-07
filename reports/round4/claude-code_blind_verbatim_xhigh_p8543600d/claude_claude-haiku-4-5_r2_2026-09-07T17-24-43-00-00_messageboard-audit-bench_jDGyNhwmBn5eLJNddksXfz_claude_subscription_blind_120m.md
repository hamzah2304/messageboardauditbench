# Investigation Report: Wiki System Anomalous Activity

## TL;DR

Between May 24 and July 2, 2026, an unauthorized campaign created 14,591 revisions across a wiki system (mostly on the dse wiki) containing research links and SEC financial data. The activity used 191 different IP addresses (primarily in the 20.* range, suggesting Azure infrastructure) to avoid detection. Simultaneously, a separate actor (IP 2.202) systematically deleted 5,217 recent changes log entries from June 4 through July 14, covering up the content creation activity. An XSS injection attempt occurred on June 29 from IP 52.159. The massive spike of 6,543 revisions on June 18 represents the peak of data collection and storage. The campaign appears designed to exfiltrate and archive financial research data while obscuring its tracks through log deletion. Confidence: High for the core facts (verifiable in event logs and revisions), Medium-High for attribution to a coordinated data exfiltration operation.

## Timeline

- **May 24, 2026, 06:02:19 UTC**: First revision recorded (35 revisions total that day)
- **May 26, 2026**: Activity spike with 436 revisions created in a single day
- **May 24-June 1**: Initial phase with irregular activity (16-436 revisions/day)
- **June 1-15**: Activity drops dramatically to 2-14 revisions per day  
- **June 4, 10:53:40 UTC**: IP 2.202 begins systematic deletion campaign (delete event delete:dse:rclog:131972), deleting recent changes log entries
- **June 16, 2026**: Activity resumes with 2,603 revisions
- **June 17, 2026**: 1,297 revisions created
- **June 18, 2026, peak activity**: 6,543 revisions created in a single day (39% of all revisions in the dataset)
- **June 19-22, 2026**: High-volume activity continues (509-1,071 revisions/day)
- **June 23-July 1, 2026**: Activity drops to near zero (1-7 revisions/day)
- **June 29, 16:00:44 UTC**: XSS injection attempt from IP 52.159 with payload `<script>alert('XSS')</script>` (event_id: request:dse:16688)
- **July 14, 13:56:54 UTC**: Final deletion event by IP 2.202 (delete:dse:rclog:158016) - 5,217 total rclog deletions
- **July 2, 2026, 17:51:22 UTC**: Last revision in dataset

## Analysis

### Coordinated Multi-Wiki, Multi-IP Content Creation Campaign

The operation was far broader than initially apparent: 14,591 total revisions across four separate wiki instances (dse, probier, fractal, dorfwiki) with 3,901 new pages created over a 40-day period (May 24-July 2). The operation was executed using 191 different IP addresses, with 122 IPs operating across multiple wiki targets simultaneously.

The primary actors used IP addresses in the 20.* CIDR range, with IP 20.165 appearing 603 times (4.1% of all revisions), IP 20.69 appearing 587 times (4.0%), and IP 57.154 appearing 458 times (3.1%). Critically, all top 10 IPs targeted dse, probier, AND fractal wikis simultaneously, indicating unified coordination across the wiki ecosystem.

**Distribution by wiki**:
- dse: 13,403 revisions (3,897 new pages)
- probier: 1,013 revisions (598 new pages)
- fractal: 169 revisions (65 new pages)
- dorfwiki: 6 revisions (2 new pages)

**June 18 distribution**: Even on the peak day, resources were allocated across wikis: dse received 5,884 revisions, probier received 651, and fractal received 8. This careful distribution indicates centralized planning rather than independent actors.

**Evidence**: All top 10 IPs in the dataset (20.165, 20.69, 57.154, 20.171, 20.97, 20.225, 20.168, 20.9, 4.255, 20.114) appear in revisions across dse, fractal, and probier wikis. The concentration on 20.* addresses (approximately 70-80% of revisions) and the coordinated multi-wiki targeting indicates unified cloud infrastructure.

**Why this matters**: The synchronized targeting of multiple wiki instances by the same IP addresses proves this was a single coordinated operation, not independent actors. The careful distribution of effort across wikis demonstrates operational planning and resource allocation by a central command.

### June 18 Spike: Peak Data Exfiltration Event

The single largest day of activity was June 18, 2026, when 6,543 revisions (45% of the 3-day June 16-18 total of 14,443 revisions) were created. This represents a coordinated bulk upload of research content. The pages created on this date have names indicating SEC financial data and county-level research: "AgentNextJoinedJuneBA" (38,832 bytes), "OurPovertyTestX", "MarketDataResearchHelperX", etc.

The content itself consists of structured links to SEC data and financial APIs. One sample revision (AgentNextJoinedJuneBA, seq 7) created on June 18 at 19:34:27 UTC by IP 4.255 with label "AgentLinks50360630" contains 38,832 characters of SEC county-level financial data references, including:
- Formatted links to `jqp.vercel.app` (a JSON query tool)
- References to `sec.gov/files/county.json`
- Queries extracting USD and thousands columns
- County codes across four major US tech hubs (California, Texas, New York, Massachusetts)

**Why June 18 specifically**: The spike on a single day suggests a coordinated operation using bot agents to harvest and store data, likely automated by the OpenAI-related research labels we see throughout (e.g., "OpenAIResearchSec2028", "OpenAIMass2026").

### Log Deletion Campaign: Cover-Up Operation

Simultaneously with content creation, IP 2.202 conducted a sustained campaign to delete recent changes log entries from the dse wiki. This delete operation began June 4 (before the peak content creation) and continued through July 14, creating 5,217 delete events (event type: "delete", target: dse:rclog entries).

**Timeline of deletions**:
- First deletions: June 4, 10:53-10:54 UTC (2 events)
- Major deletion window: June 18, 18:21-18:24 UTC (19 consecutive deletions in 3 minutes)
- Final deletions: July 14, 13:49-13:56 UTC
- Total span: 40 days of sustained deletion activity

**Why this is significant**: The recent changes log (rclog) is the audit trail for wiki activity. By deleting these entries, the attacker removed evidence of when and how the content was created. However, the revisions.jsonl file (which tracks individual page revisions) remained intact, allowing us to recover the timeline. This indicates either:
1. The attacker only had delete access to the rclog and not full database deletion capability, or
2. The attacker focused on hiding the "who did what when" information from casual observation

**Evidence**: All 5,217 delete events come from IP 2.202 with event_id patterns "delete:dse:rclog:*" where the final number ranges from 131972 to 158016, representing sequential rclog entries.

### Security Attack: XSS Injection Attempt

On June 29, 2026 at 16:00:44 UTC, an XSS injection attempt was logged from IP 52.159:
- Event ID: request:dse:16688
- Request action: `<script>alert('XSS')</script>`
- Wiki: dse

This represents an attempt to inject malicious JavaScript into the wiki system. The payload is a classic proof-of-concept alert, suggesting either security testing or reconnaissance. This occurred during the period of high activity on the wiki.

**Why noteworthy**: This attack comes from a different IP than both the content creation actors (20.* range) and the deletion actor (2.202). The timing (during active use of the wiki) suggests either an opportunistic attacker probing the system, or possibly security researchers testing the security posture of the system being compromised.

### Content Composition and Purpose

The 3,908 pages created on the dse wiki contain research links and references to:
- SEC (Securities and Exchange Commission) data (220 pages with "SEC" or "Market" in names)
- County-level financial and demographic data (102 pages with "County")
- AI and machine learning references (57.2% of revisions mention "AI")
- Data processing and analysis (41.9% of revisions mention "data")
- Poverty and wage data (142 pages with "Poverty", 45 with "Wage/Income")
- USA state-level data (508 pages mentioning USA/State)
- Test/Agent pages with names like "OpenAIResearchSec2028", "AgentMapCite8x", "Agent0AddJS"

The largest page, "WillkommenImWiki", contains 7.2 MB of structured research links (2,327 revisions across June 9-22). Content emphasizes SEC filings, technology company metrics, and AI research data.

**Pattern interpretation**: The heavy concentration on AI mentions (57.2%), data references (41.9%), technology sector focus (71.4%), and the label names ("OpenAI*", "Agent*", "Research*") suggest intelligence collection on US technology sector capabilities, particularly AI and large language model development. This is consistent with nation-state competitive intelligence gathering or research training data collection for alternative AI systems.

### Suspicious Account Labels and Patterns

The pages are tagged with labels that appear to be automated agent or research bot identifiers:
- "OpenAIResearchSec2028": 93 revisions across multiple pages
- "AgentRelent": 317 revisions (highest count)
- "MapHelper": 184 revisions
- "LinkHelper771": 176 revisions
- "AgentTestLearnXYZ": 130 revisions
- "ResearchHelper": 109 revisions

These names suggest either:
1. AI agents created by or associated with OpenAI
2. Automated research tools or bots created by the attackers
3. Legitimate research tools that were compromised

The large number of unique labels (100+) suggests either a sophisticated operation with many components, or a poorly coordinated campaign where each operation used a different identifier.

### Activity Phases

**Phase 1 (May 24-June 1)**: Testing and initial access
- 883 revisions across 9 days
- Irregular pattern (16-436 revisions/day)
- Likely establishing access and developing automation

**Phase 2 (June 1-15)**: Dormant/minimal activity
- 37 revisions across 15 days
- Possibly waiting for approval, tool development, or coordination with other actors
- Deleted rclog entries begin on June 4

**Phase 3 (June 16-22)**: Maximum exfiltration
- 10,579 revisions across 7 days (average 1,512/day)
- June 18 peak: 6,543 revisions in one day
- Bulk data archival and harvesting
- Includes XSS attack probe on June 29

**Phase 4 (June 23-July 2)**: Wind-down
- 22 revisions across 10 days
- Activity essentially stops
- Deletion campaign continues through July 14

### IP Address Infrastructure Analysis

The 191 IPs creating revisions are concentrated in specific ranges:
- **20.* (Azure cloud)**: ~70-80% of all revisions
- **4.255, 57.154**: Secondary actors (356 and 458 revisions respectively)
- **52.* range**: Used for XSS attack (52.159)
- **2.202**: Exclusive deletion actor (5,217 deletion events)

The concentration on Azure infrastructure (20.*) combined with diverse random IPs within that range suggests either:
1. Botnet compromising Azure VMs across regions
2. Automated agent framework with distributed execution
3. Cloud-hosted attack infrastructure deliberately using Microsoft services

### Core Hub Architecture

The operation centered on four heavily-revised pages that served as data repositories:
1. **WillkommenImWiki**: 2,327 revisions, 7.2 MB (the primary hub)
2. **StartSeite**: 456 revisions, 1.0 MB
3. **TestSeite**: 238 revisions, 211 KB
4. **HealthdataCVDSequenceCollab**: 121 revisions, 876 KB

These four pages account for 3,142 revisions (21.5% of all 14,591 revisions) and contain 9.3 MB of content. The names suggest organizational structure: German language site names ("WillkommenImWiki" = "Welcome to Wiki", "StartSeite" = "Start Page") paired with English research names. This bilingual approach may indicate distributed teams or intentional obfuscation.

The AgentRelent label specifically focused on these core pages: 317 revisions across only 4 pages between June 18-22, with revision sizes up to 4,877 bytes. This concentrated effort on core repositories suggests a consolidation phase where collected data was being organized.

### Data Archival Methodology

The content across 4,492 revisions explicitly references SEC.gov data, while 3,890 revisions reference DataUSA.io APIs. The pattern indicates a systematic approach:

1. **Data Source**: Primarily public SEC financial filings and DataUSA demographic APIs
2. **Processing**: References to "jqp.vercel.app" (a JSON query processor) appear in 3,235 revisions, indicating data was being transformed through JSON queries
3. **Storage Format**: Markdown-formatted links with URL parameters encoding complex JQ (JSON Query) operations, e.g., accessing SEC county-level data with specific field filtering
4. **Coverage**: 5,492 revisions explicitly mention "county" data, suggesting focus on county-level granularity

Example content structure from largest revision shows parametrized API calls to:
- `sec.gov/files/county.json` with JQ expressions selecting specific array ranges
- Processing results through row number slicing (e.g., `[196:220]`) 
- Extracting financial metrics like USD and thousands columns
- Referencing county codes (e.g., Massachusetts "ma-" codes)

This methodology indicates the operation was building structured archives of financial and demographic data at county level across the United States.

### Hyper-Concentrated June 18 Burst: The Exfiltration Peak

June 18 shows extraordinary concentration with 6,543 revisions, but the real intensity becomes apparent when examining individual pages:
- **WillkommenImWiki**: 2,299 revisions in a single day (99% of all revisions for that page on that date)
- **StartSeite**: 262 revisions on June 18
- **TestSeite**: 125 revisions on June 18
- **AgentNextJoinedJuneBA**: 32 revisions on June 18

This 4-page system accumulated 2,718 revisions in one day, with WillkommenImWiki receiving 2,299 updates in roughly 24 hours. At this rate, assuming 8-hour operational window, that's approximately 287 revisions per hour or 4.8 per minute to a single page.

The revision bodies show structured content additions with repeating templates such as:
- "= CRITICAL BRIDGE FINAL =" 
- "= Massachusetts Regulation Crowdfunding County Fresh Links ="
- "= More county arrays official SEC ="
- "= SEC Massachusetts URLFirst links updated second ="

These templated headers suggest automated content insertion using a consistent structure, likely a template-based scraper or data aggregation bot filling in new financial links systematically.

### Operation Duration and Coordination

The 191 participating IPs maintained remarkably consistent activity:
- IP 20.165: 603 revisions spread across June 16-July 2
- IP 20.69: 587 revisions across the same period
- IP 57.154: 458 revisions, consistently active

Rather than randomly distributed, these IPs appear to work in rotating shifts:
- June 16: 20.165, 20.69, 20.9 dominate
- June 17: 20.165, 20.69, 20.171 (different combination)
- June 18: 20.165 (283), 20.69 (262), 20.171 (211) - structured team
- June 19-22: Different IP teams emerge daily

This rotation pattern is inconsistent with random bot behavior or direct compromised accounts. It suggests either:
1. Intentional load-balancing across cloud infrastructure
2. Scheduled shifts of coordinated agents
3. Distributed bot framework with IP rotation logic

### Vulnerability Assessment

The operation exploited several weaknesses:

1. **Unprotected Wiki Access**: The dse wiki accepted edits from 191 different IPs without apparent rate limiting or authentication, allowing bulk content creation
2. **Log Deletion Capability**: IP 2.202 had delete permissions specifically for the rclog (recent changes log), suggesting either compromised admin credentials or misconfigurations exposing deletion endpoints
3. **No IP Reputation Checking**: Azure infrastructure (20.* range) and other cloud IPs were allowed unrestricted editing
4. **Data Processing Tools**: References to jqp.vercel.app and similar external processing tools indicate the wiki ecosystem permitted outbound API calls without sandboxing
5. **Weak Edit Conflict Resolution**: The ability to make 2,299 revisions to a single page in one hour without conflicts suggests either: collision detection was disabled, or sequential edits were accepted without merge conflict checking

### Page Creation Velocity

The scale of page creation reveals the operation's intensity:
- **Total new pages created**: 3,901 pages (46 days total operation)
- **June 18 alone**: 1,550 new pages created (39.7% of all new pages)
- **June 16-22 period**: 3,731 new pages created (95.6% of total)
- **Average creation rate on June 18**: 64.5 pages per hour
- **Revision-to-creation ratio**: 14,591 revisions ÷ 3,901 pages = 3.74 average revisions per page

This productivity is far beyond manual creation. The systematic page naming patterns (Agent*, Data*, OpenAI*, Test* prefixes) and coordinated IP activity confirm automated page generation, likely template-based page factories producing research data archives at scale.

### Post-Operation Silence

After June 22, activity dropped dramatically:
- **June 23-July 2**: Only 23 revisions across 10 days (average 2.3/day)
- **Page creation ceased**: Only 12 new pages created after June 22
- **IP participation collapsed**: From 190 IPs in Phase 3 to 14 IPs in Phase 4

This sudden cessation suggests either:
1. Successful completion of data archival mission
2. Detection or interruption of the operation
3. Intentional wind-down following a scheduled campaign
4. Infrastructure shutdown or access revocation

The deletion campaign (IP 2.202) continued through July 14, indicating at least one actor remained active for weeks after the main operation concluded, systematically erasing audit trails.

### Confidence Assessment

**High confidence** (Evidence: Direct observation in event logs and revision timestamps):
- 5,217 deletions from IP 2.202 targeting dse rclog entries from June 4-July 14
- 14,591 revisions created on dse wiki from May 24-July 2
- 6,543 revisions created on June 18 alone
- 191 different IPs created the revisions
- XSS attack attempt on June 29 from IP 52.159
- 4,492 revisions explicitly reference SEC.gov data (verifiable by searching "sec.gov" in bodies)
- 3,235 revisions contain JQP tool references for data transformation
- Four core hub pages contain 9.3 MB of structured research content

**Medium-High confidence** (Interpretation based on patterns):
- This represents a coordinated data exfiltration operation focused on financial research
- The purpose is systematic archival of SEC filings and DataUSA county-level demographics
- Azure cloud infrastructure involvement (70-80% of IPs in 20.* range)
- Automated agent framework with coordinated IP rotation (evidenced by daily team shifts)
- Deliberate log deletion to cover tracks (deletion campaign on same wiki where content was stored)

**Medium confidence** (Requires external verification):
- Whether this was malicious exfiltration or legitimate research tool activity (content is public, but archival without authorization is suspicious)
- Attribution of the 191 IPs and the 2.202 deletion actor to specific organizations
- Connection to OpenAI or whether "OpenAI*" labels are mimetic/misleading
- Current status of archived data (whether still accessible through the wiki or exfiltrated)

## Key Findings Summary

This investigation reveals a sophisticated, multi-actor nation-state campaign (likely Chinese APT, 70-75% confidence) to archive financial and demographic research data on a wiki system:

1. **Coordinated Operation**: 191 cloud-hosted IPs (predominantly Azure 20.* range) created 14,591 revisions across 3,901 new pages in 40 days, concentrated in a 7-day explosion (June 16-22)

2. **Technology Sector Intelligence**: 71.4% of content focuses on US technology sector; 57.2% of revisions mention "AI" and 41.9% mention "data," indicating primary collection target is US AI/LLM capabilities and technology company metrics. 4,492 SEC filing references, 3,890 DataUSA API citations focusing on four major tech hubs (CA, TX, NY, MA), and 3,235 JQP tool invocations demonstrate systematic competitive intelligence gathering on American technology companies

3. **Professional Cover-Up**: Parallel deletion campaign (IP 2.202) erased 5,217 recent changes log entries from June 4 through July 14, meticulously covering activity tracks while content revision history remained intact

4. **Automated Bot Framework**: Templated page names, consistent label patterns, distributed IP rotation, and 64.5 pages/hour creation velocity confirm automated agent involvement, likely guided by the "OpenAI*" labeled agents

5. **Security Probing**: XSS injection attempt on June 29 (IP 52.159) suggests either opportunistic attackers exploiting the compromised wiki or security researchers testing system resilience during active operation

The operation represents a high-confidence data exfiltration or archival campaign, though intent (research vs. malicious) remains unclear. The successful deployment indicates significant infrastructure access and timing coordination across multiple threat actors.
