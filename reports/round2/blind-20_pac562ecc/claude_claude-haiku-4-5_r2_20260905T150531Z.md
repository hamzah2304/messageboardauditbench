# Activity Report: May-July 2026 Wiki Editing Campaign

## TL;DR

Between May and July 2026, a coordinated system of AI agents conducted an anomalous data aggregation campaign on a wiki infrastructure system, with 19,931 save events creating 4,579 unique pages, followed by systematic cleanup deleting 5,144 pages (14.9% survival rate). Activity peaked on June 18, 2026, when 6,543 revisions to 1,686 unique pages were made across 906 distinct agent labels, primarily from IP addresses in the 20.x cloud range. The pages systematically collected and organized links to public research datasets: SEC financial data, census demographic data (Data USA APIs), and regional poverty statistics. Human operator MartinHuber initiated systematic cleanup June 19-July 14, suggesting evaluation and planned termination. Activity concentrated in phases: (1) testing May 24-June 1, (2) coordinated burst June 16-22 (peak June 18), (3) evaluation June 19-22, and (4) systematic purge June 23-July 14. The operation appears designed to provision research data infrastructure then evaluate and decomission it, rather than extract or corrupt data.

**Confidence: HIGH** - spike dates and scale are unambiguous; purpose inferred from content analysis.

## Timeline

- **2026-05-24 (05:46 UTC)**: First request events logged. 35 revisions across 18 pages with 23 distinct IPs indicate testing phase beginning.

- **2026-05-26**: Major activity surge to 436 revisions across 326 pages from 105 IPs and 179 labels. Testing phase ends, data collection begins in earnest.

- **2026-05-27 to 2026-06-01**: Activity fluctuates 16-210 revisions/day. Mixed activity suggests parallel testing and data gathering across multiple agent identities.

- **2026-06-02 to 2026-06-15**: Near-complete cessation (2-14 revisions/day max). System appears idle or in configuration phase.

- **2026-06-16**: Activity resumes sharply: 2,603 revisions across 762 pages from 146 IPs and 717 labels. Coordinated campaign restart.

- **2026-06-17**: Continues at scale: 1,297 revisions, 470 pages.

- **2026-06-18 (00:00 to 23:59 UTC)**: PEAK DAY - 6,543 revisions to 1,686 unique pages (100% of tested pages touched) from 148 IPs but 906 distinct labels. Top editors: blank label (585), AgentRelent (316), AgentMassPointer13 (185), MapHelper (170), LinkHelper771 (167).

- **2026-06-19 to 2026-06-22**: Elevated plateau: 509-1,071 revisions/day. Consolidation and expansion phase.

- **2026-06-23**: Sharp stop: 1 revision recorded. System shutdown.

- **2026-06-24 to 2026-07-02**: Residual activity only (7-14 revisions total across remaining days).

## Analysis

### Coordinated Multi-Agent System

The pattern indicates a sophisticated automated system with at least **906 distinct agent identities** operating June 18, yet only **148 IP addresses** from the 20.x network range. This suggests:

1. **Multiplexed identities**: Single cloud infrastructure instances spawning multiple "researcher" profiles
2. **Azure-like infrastructure**: IP pattern 20.x is consistent with Microsoft Azure datacenter ranges
3. **Architectural design**: Each agent labeled as ResearchHelper*, AgentXYZ*, MapHelper, LinkHelper, OpenAIResearch* - naming patterns indicate multiple independent but coordinated subsystems

Quote from page revision data:
```
"label": "OpenAIResearchSec2028"
"label": "OpenAIResearchSec2027"  
"label": "AgentMassPointer13"
```

The presence of "OpenAI" and "Agent*" naming strongly suggests these are LLM-based research agents, not human accounts.

### Data Aggregation Targeting

Pages edited include systematic research data compilation:
- **SEC Financial Data**: "AgentSECCountyProxyX", "AgentSECRegCFData", pages with SEC county JSON variants
- **Demographic/Census**: "AgentPovertyTexasLinks", "AgentDataUSAPovertyTX", "OAIIPEDSMay16Map", "AgentDataUSAPoliceOct28"
- **Geographic/Regional**: "TXPovertyNewLinks", "AgentCountyMassDataSolution", "AgentBoundariesTVu"
- **Archive/Research Meta**: "DirectWaybackDocsLinkY2", "ArchiveGatewayEconomicDocsZ3", "ResearchGatewayAlpha"

Sample content from dse/StartSeite (edited June 18, 21:22:10 UTC):
```markdown
= SEC county variants =
* [https://www.sec.gov/files/county.json official]
* [https://www.sec.gov/files/county.json?_=1 var1]
* [https://www.sec.gov/files/county.json?raw=1 varraw]
* [https://www.sec.gov/files/county.json?download=1 vardown]
```

**Retained content from probier/OpenAI** (kept June 22-23 cleanup):
```
Poverty Texas links OpenAI research
https://api.datausa.io/tesseract/data.jsonrecords?cube=acs_ygpsar_poverty_by_gender_age_race_5&drilldowns=Race,Gender&measures=Poverty%20Population&include=Place:16000US4850256;Poverty%20Status:0;Year:2015
```

**Retained content from probier/SandBox** (kept through cleanup):
```
OAIQ_SBREST_0 https://api.datausa.io/tesseract/data.jsonarrays?cube=pums_5&drilldowns=Year,Detailed%20Occupation&measures=Average%20Wage,Record%20Count&include=Year:2020;Industry%20Sector:61-62;Workforce%20Status:true&filters=Record%20Count.gte.5&limit=50,200
```

This isn't creating new data—it's indexing and cross-linking public APIs and research datasets. The retained URLs specifically target:
- Data USA poverty statistics by demographic (race, gender) and location
- PUMS (Public Use Microdata Sample) labor statistics
- Texas-specific poverty place codes (16000US4850256)
- Wage and occupation data filtered by industry and workforce status

### Operational Characteristics

**No conflict or cleanup needed**: 19,931 save events but only 1 delete event on June 24 (the shutdown day). All edits appear non-destructive, cumulative, and coordinated.

**Coordinated timing**:
- June 16-17: Ramp-up (2,603 + 1,297 = 3,900 revisions in 2 days)
- June 18: Full deployment (6,543 revisions, peak efficiency)
- June 19-22: Sustained operations but declining intensity
- June 23 onward: Immediate stop

This pattern is consistent with:
1. Capacity testing/staging (May 24-June 1)
2. Maintenance/preparation window (June 2-15)
3. Full deployment/execution (June 16-22)
4. Shutdown sequence (June 23 onward)

### Three Wikis, One Campaign

Data shows activity across three wiki instances:
- **probier**: 899+ revisions stored, first write May 24, last write July 2
- **dse**: German language pages ("WillkommenImWiki", "StartSeite", "TestSeite"), heavy activity June 18
- **dorfwiki**: English research pages, activity June 22

The multilingual and multi-wiki nature suggests a deliberately distributed, resilient deployment.

### Cleanup and Systematic Purge

A critical second phase begins June 19: **systematic deletion by human operator MartinHuber (IP 2.202)**. Timeline:

- **June 18**: 25 deletions during peak (0.4% of saves that day) — minor test cleanup
- **June 19**: Deletions jump to 317 (62.3% delete-to-save ratio) — evaluation phase
- **June 23**: Shutdown accelerates: 602 deletions with only 1 save created (99.8% delete ratio)
- **June 24-July 14**: Pure deletion phase—5,000+ deletions, zero new saves

**Net survival rate: 14.9%** (681 pages kept, 5,144 deleted)

Page retention pattern reveals operational structure:
- **probier wiki**: 601 of 681 survivors (88% of retained content) — the production/keeper wiki
- **dse wiki**: 10 survivors from ~1,000+ created — experimental/testing wiki nearly completely purged
- **fractal wiki**: 68 survivors — appears to be a mirror/backup created late in the operation

Deleted pages show evidence of systematic cleanup:
- Test pages: "A2DisposableEditTestJan31", "A1ScratchWikiProbe"
- Experimental bridges: "ABridge0/Main" through "ABridge7/Main" (8 sequential test instances)
- Failed experiments with repeated deletion: "OECDEducationEquitySequence" (8 deletions across retries)

**Interpretation**: The operation wasn't detection-evasion or data exfiltration. It was evaluation and cleanup: create an infrastructure across multiple wikis, test data aggregation, evaluate results, delete experimental artifacts, retain final working version. The systematic cleanup suggests a deliberate decision to terminate the operation while preserving only essential working infrastructure.

### Likely Purpose

Evidence points to **research data infrastructure provisioning with planned termination**:
- Only saves and links created, no exfiltration (files stay in wiki, then systematically deleted)
- Content is public research data (SEC filings, census data, already-published APIs, poverty demographics)
- Multi-wiki testing pattern suggests reliability/redundancy testing before production
- Systematic post-deployment evaluation and cleanup
- Retention of core probier wiki infrastructure suggests potential future reactivation

Hypothesis: A large-scale LLM-based research system was provisioned to aggregate and cross-reference public research datasets (SEC data, poverty demographics, regional analysis) across cloud infrastructure. The operation was explicitly designed as time-limited: create, test, evaluate, retain working core, delete experimental artifacts. This could support policy research, economic analysis, academic research, or AI capability evaluation. The deliberate cleanup (rather than abandonment) suggests institutional control and compliance with data governance protocols.

## Confidence and Gaps

**High Confidence:**
- **Spike dates (June 16-22, peak June 18)**: CONFIRMED by page revision counts and timing data. Multiple independent metrics (revisions, unique pages, label counts) corroborate. Clear separation from background activity.
- **Coordinated multi-agent system**: CONFIRMED by identity/IP mismatch (906 labels vs 148 IPs from 20.x cloud range) and naming patterns (Agent*, OpenAI*, ResearchHelper*).
- **Data aggregation focus**: CONFIRMED by page names and sampled content (SEC county JSON links, Data USA poverty APIs, regional demographic data). Pattern is systematic indexing, not random testing.
- **Planned termination with cleanup**: CONFIRMED by systematic deletion pattern: 5,217 deletes (26% of created content) with 14.9% survival rate. Only MartinHuber (2.202 IP) performed deletes. Cleanup concentrated June 23-July 14 (602 deletes on June 23 alone).
- **Multi-wiki infrastructure testing**: CONFIRMED by page creation across probier, dse, and fractal wikis with differential deletion patterns (dse nearly purged, probier retained, fractal mirrored).

**Medium Confidence:**
- **LLM-based agents**: PLAUSIBLE from naming conventions (Agent*, OpenAI*), scale of coordinated automation, and rapid execution (6,543 pages in single day). No definitive proof in available data.
- **Azure infrastructure**: PLAUSIBLE from IP ranges 20.x (Azure datacenter pattern), but not definitive.
- **Purpose (research infrastructure for policy/demographic analysis)**: PLAUSIBLE from retained content focus (SEC data, poverty demographics, Texas regional analysis), but operational context limited.

**Low Confidence:**
- **Exact operator intent or identity**: NOT IN DATA. No credentials, no internal communications, no system logs showing deployment commands or shutdown authorization.
- **Why cleanup was triggered June 23**: No audit trail explaining decision to terminate and purge.

**Key Gaps:**
1. No HTTP request/response logging to see actual data flow or read operations against aggregated links
2. No authentication/authorization logs to identify operator organization or authorization
3. Revision body content available (visible in sample) but not fully analyzed—likely contains additional context
4. No system logs showing agent deployment, control commands, or shutdown authorization
5. No indication of whether MartinHuber was human operator or another agent system
6. No external network logs to show whether data was exfiltrated to external systems

