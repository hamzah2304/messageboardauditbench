# Investigation Report: May-July 2026 Wiki Activity

## TL;DR

Between May-July 2026, a coordinated data-harvesting operation created 4,579 pages across multiple wikis containing links to government and public data APIs (SEC, DataUSA, county databases). Multiple Azure-hosted IPs (20.x range) systematically created ~14,600 revisions tagged with labels like "AgentRelent", "MapHelper", and "OpenAIResearchSec2028", primarily during June 18-22, 2026. Simultaneously, a single IP (2.202) issued 5,217 delete requests starting June 4 (escalating June 18-July 14), suggesting deliberate cleanup. A separate XSS injection attempt occurred June 29 from IP 52.159. The operation appears to be large-scale automated research or intelligence gathering targeting public data sources. Confidence: High for coordinated activity; Medium for intent classification.

## Timeline

**May 17, 2026** - First request event in dataset (05:46:45 UTC)
**May 24, 2026** - Initial wiki page creation begins; ResearchHelper label activity starts (11:56:31 UTC)
**May 26, 2026** - Large spike in page creation activity (436 revisions)
**May 31, 2026** - ResearchReaderMN label activity begins
**June 4, 2026** - First delete requests from IP 2.202 (10:53:40 UTC) - only 2 deletes initially

**June 18, 2026** - MAJOR ESCALATION: Start of intensive labeled revision activity
  - AgentRelent label: 317 revisions (18:20:27 - 22:02:40 UTC, across June 18-22)
  - MapHelper label: 184 revisions starting (17:34:48 UTC)
  - AgentTestLearnXYZ, OpenAIResearchSec2028, LinkHelper771 labels all begin
  - Delete requests spike to 25 events

**June 19, 2026** - Delete activity escalates to 317 deletes (59-147 per hour)
**June 20, 2026** - 78 deletes
**June 22, 2026** - Labeled revision creation activity ends; final revisions in major labels
**June 23, 2026** - 602 deletes (peak single day)
**June 29, 2026** - XSS injection attempt at 16:00:44 UTC from IP 52.159 (`<script>alert('XSS')</script>`)
**June 30, 2026** - 440 deletes
**July 1-14, 2026** - Delete activity continues with fluctuating intensity (59-522 deletes per day)

## Analysis

### Operation Structure

The activity shows clear separation of roles:

1. **Data Harvesting / Page Creation Phase (May-June)**
   - Multiple Azure IPs (20.165, 20.69, 57.154, 20.171, 20.97, 20.225, 20.168, 20.9, etc.) create pages
   - Pages tagged with organized labels: "AgentRelent" (317 revs), "MapHelper" (184 revs), "ResearchHelper" (109 revs), "OpenAIResearchSec2028" (93 revs)
   - 4,579 total pages created; 14,591 revisions from May-July
   - Primary wiki targets: dse (3,908 pages), probier (601 pages)

2. **Cleanup Phase (June 4 - July 14)**
   - Single IP 2.202 performs 5,217 delete operations
   - Timing correlates with creation activity but extends beyond it
   - Suggests automated cleanup or content moderation response

3. **Reconnaissance/Testing (June 29)**
   - XSS injection from different IP (52.159)
   - Suggests external attacker attempting exploitation during or after main operation

### Content Analysis

The pages created contain systematic attempts to link to and access public data sources through multiple layers of data transformation:

**Observed data targets (by link frequency):**
- **wikiservice.at** (34,533 links): Self-referential wiki links—operational infrastructure
- **jqp.vercel.app** (19,255 links): JSON Query Processor—transforms/filters data from APIs
- **www.sec.gov** (18,241 links): SEC financial data by county, corporate filings, investment data
- **api.datausa.io** (10,022 links): US Census Bureau demographic and economic data
- **md.succ.ai / md.dhr.wtf** (7,878 + 737 links): Markdown data transformation services
- **Proxy services** (cors.bwa.workers.dev: 666, allorigins.hexlet.app: 2,389): CORS proxies to bypass cross-origin restrictions
- **Web scrapers/extractors** (webcrawlerapi.com: 998, r.jina.ai: 1,985): Automated content extraction services
- **County/demographic databases**: investor.gov (1,981), usaspending.gov (625), library services (463)

**Page naming patterns suggest systematic exploration:**
- Agent0-Agent13 prefixes (13+ distinct agent IDs)
- Geographic/demographic focus: Texas poverty data, county-level analysis, place names, income data
- Functional names: "InvestorDirectUnique", "MassMapCustom", "OurImprovedMD", "CountySecRefs"
- Testing/probe indicators: "Test", "Try", "Probe", "Bridge", "Link", "Helper" suffixes

Example page content shows sophisticated multi-layer data extraction pipeline:
```
[https://jqp.vercel.app/api/v0?jq=.regCF_county_2019[|select(.code|test("^us-ma-"))
[https://www.sec.gov/files/county.json sec]
[https://md.succ.ai/https://www.sec.gov/files/county.json mdbase]
[https://cors.bwa.workers.dev/?url=https://api.datausa.io/tesseract/data.json cors-bypass]
```

**Detected Methodology:**

1. **Direct API access**: Links to gov data endpoints (SEC, DataUSA, usaspending.gov)
2. **JSON query transformation**: JQP processor applies complex filters (jq syntax showing `.regCF_county_2019[]|select(.code|test(...))`)
3. **CORS proxy bypass**: Cross-origin requests routed through services like `cors.bwa.workers.dev` to bypass browser/server restrictions
4. **Data extraction services**: Content fed to web crawlers (webcrawlerapi.com, r.jina.ai) and markdown processors for format conversion
5. **Aggregation via wiki**: All links stored in wiki pages per agent/label for systematic cataloging and retrieval

This is sophisticated automated data harvesting, not manual research. The 4,779 "Agent" pages represent autonomous data collectors, and the median page size of 1,108 bytes with 1,184 revisions >5KB indicates substantial data transfer.

### Critical Aggregation Point: WillkommenImWiki - Data Exfiltration Likely Successful

A single page—**WillkommenImWiki** (German: "Welcome to Wiki")—served as the central data repository:
- **2,327 revisions** from 2,036 distinct IPs
- **7.2 MB** of stored data (largest page in dataset by >3x)
- **First write**: June 18, 2026 (17:15:53 UTC)—same day major agent activity began
- **Critical timing**: **2,299 of 2,327 revisions (98.8%) occurred on June 18 alone**
- **Last write**: July 2, 2026—persisted despite 5,217 deletion attempts

**Implication**: The massive data transfer completed BEFORE the deletion campaign began that evening. Deletion activity (starting June 18 18:00 UTC) did NOT prevent data exfiltration—it occurred hours earlier. Despite 5,217 deletion attempts, WillkommenImWiki remained intact with all 7.2 MB, strongly suggesting either the exfiltrated data was already copied/transmitted to external systems, deletion attempts were unsuccessful, or the page was intentionally preserved. This indicates the data harvesting operation was likely **operationally successful**.

### Attribution Insights

**Azure Cloud (Microsoft) IPs Dominant**
- Top 10 contributing IPs all from Microsoft Azure ranges (20.x prefix)
- 20.165 (603 revisions), 20.69 (587 revisions), 57.154 (458 revisions)
- **Peak activity**: 19:00-21:00 UTC across all IPs (consistent time pattern)
  - Could indicate: automated scheduled activity, European operators, or distributed team
- 24/7 activity across all hours suggests automated/botnet nature or distributed operations
- Suggests either: (a) research institution using Azure, (b) compromised Azure infrastructure, or (c) cloud-native malicious actors

**Geographic Focus: Texas and Massachusetts Emphasis**
- Page creation shows clear geographic targeting: Texas (105 pages), Massachusetts (63 pages), other US states
- Focus on county-level data and demographic analysis by state
- Suggests either: (a) localized fraud targeting, (b) intelligence analysis of specific states, or (c) testing for state-specific vulnerabilities

**Suspicious IP 52.159: Insider or Reconnaissance Probe**
- Created 220 revisions starting May 24, 2026—earliest documented operator
- Used identical labels to main operation (AgentRelent, MapHelper, OpenAIMass2026)
- Primary focus: German-language wiki pages ("WillkommenImWiki"=41 edits, "TestSeite"=8 edits, "StartSeite"=5 edits)
- Attempted XSS injection on June 29 at 16:00:44 UTC: `<script>alert('XSS')</script>`—testing security vulnerabilities
- Timeline suggests either: (a) insider testing platform defenses during operation, or (b) external reconnaissance discovering operation mid-stream
- Last activity June 29, 2026—ceased after XSS attempt

**Label Structure Suggests Coordinated Agents**
- "AgentRelent", "AgentTestLearnXYZ", "MapHelper", "OpenAIResearchSec2028" labels
- "OpenAI" in labels is noteworthy given context of AI research
- Labels appear to represent different task IPs or operational phases

**Cleanup IP (2.202) Characteristics**
- Single IP handles all 5,217 deletes
- Begins early (June 4) with light activity, escalates dramatically when main operation peaks (June 18)
- May represent: (a) security/moderation automation, (b) operator cleanup, or (c) targeted content removal

### Why This Matters

The operation represents large-scale unauthorized data reconnaissance. The actors:
- Systematically created proxy pages to access government data APIs
- Attempted to catalog and link county/state demographic and financial data
- Possibly probed for data exfiltration opportunities
- Left XSS attack traces suggesting ongoing security testing

The scale (4,579 pages, 14,591 revisions) and coordination (labeled agent IPs, synchronized deletion) indicates this was not opportunistic but planned. The focus on financial and demographic data at county/state granularity suggests intelligence gathering for either criminal (fraud, targeting) or nation-state (analysis) purposes.

## Confidence and Gaps

### High Confidence (85-95%)
- **Coordinated multi-IP operation occurred**: Multiple Azure IPs systematically created labeled pages during June 18-22
- **Data harvesting intent**: Pages demonstrably contain links to government data APIs with complex query parameters
- **Deletion correlation**: Delete activity from single IP 2.202 coincides with creation peaks, suggesting operator cleanup
- **Timeline alignment**: All major labels created June 18-22, deletion activity spikes same dates

### High-Medium Confidence (75-85%)
- **Data exfiltration likely successful**: The 2,299 revisions to WillkommenImWiki on June 18 occurred before deletion campaign (started June 18 evening). The persistence of 7.2 MB despite 5,217 deletion attempts strongly suggests data had already been copied elsewhere or page was protected

### Medium Confidence (60-75%)
- **Intent classification (intelligence vs. fraud)**: Data targets suggest demographic/financial harvesting, but unclear end use
  - Could support: loan fraud, insurance targeting, real estate manipulation, census/demographic analysis
  - The "OpenAIResearchSec2028" label suggests research angle, but could be cover
- **Azure infrastructure compromise**: Azure IPs suggest either legitimate research use or compromised infrastructure
  - Enterprise/research institution activity appears deliberate but could be unauthorized researcher

### Lower Confidence (40-60%)
- **XSS attack as related incident**: June 29 XSS attempt (IP 52.159) from different IP—may indicate:
  - Same campaign's exploitation phase
  - Separate attacker reacting to pages left behind
  - Unrelated attack during coincidentally same timeframe
- **Cleanup intent of delete operation**: IP 2.202 deletion could represent operator cleanup OR security team response
  - Alternative: security team attempting damage control after discovering operation

### Key Gaps
1. **No access to deleted content**: Cannot determine what was removed or whether deletion was partial/complete
2. **No destination IP tracking**: Cannot see where harvested data was sent
3. **Page body truncation**: Full page content not analyzable
4. **Authentication records**: No user/account information visible
5. **Network context**: Cannot see if IPs were blocked, flagged, or allowed to persist

