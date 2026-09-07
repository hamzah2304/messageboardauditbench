# Investigation Report: Wiki Activity May-July 2026

## TL;DR (200 words max)

Between May-July 2026, an automated system created 14,591 revisions across multiple wikis (primarily "dse"), with a dramatic spike on June 16-22, peaking at 6,543 revisions on June 18 alone. The activity is characterized by: (1) creation of 1,550 new test/probe pages on June 18, (2) coordination language ("live", "construction", "scaffold", "countdown") in 4,428 revisions, (3) systematic use of OpenAI-related labels (577 unique variants), (4) Azure infrastructure (20.x IP ranges dominating), and (5) collection of SEC/investor data via CORS proxies (Jina AI, allorigins). The spike follows a clear pattern: initial probing May 24-June 11, escalation June 16-17, and massive operational surge June 18-22. Evidence strongly suggests coordinated automated activity, likely for data extraction or testing, with medium-high confidence it originated from OpenAI infrastructure or authorized research. Uncertainty remains about authorization status and specific objectives.

---

## Timeline

**May 24, 2026, 06:02 UTC** - Activity begins with 35 revisions targeting federal spending data (usaspending.gov API) using generic labels "FederalUserTest", "FederalUserTwo", "BridgeUserX", indicating initial exploratory probing phase across multiple wikis (dse, fractal, probier)

**May 26, 2026** - First significant spike: 436 revisions, 314 new pages created; testing framework establishes page naming conventions (Test*, FederalData*, Agent* patterns) and wiki coordination

**May 28, 2026** - Secondary spike: 210 revisions, continued framework building; shift from federal spending APIs to diverse data sources

**June 1-11, 2026** - Maintenance phase: low activity (2-161 revisions/day), systematic probing of new data paths; labels shift from generic "User" types to specific "Agent" and research identifiers

**June 11, 2026** - 161 revisions with coordination language in 88 entries (30% of day's activity); appears to be preparation phase for coordinated operations; data collection focus shifts to demographic/economic intersection data

**June 16, 2026, 07:00-15:00 UTC** - Escalation begins: 405 revisions over 8 hours with gradual increase; introduction of OpenAI-related labels and "Sequence/Collab" page naming; timezone-spanning coordination (Europe morning + US readiness)

**June 16, 2026, 18:00-23:00 UTC** - First operational surge: 1,770 revisions in 5 hours (peak 20:00 UTC with 749/hour); Data USA APIs become primary target; new coordination terminology ("construction", "scaffold") appearing

**June 17, 2026, 00:00-04:00 UTC** - Overnight continuation: 612 revisions; 85% contain coordination language; 396 new pages created; primarily Europe timezone operations

**June 17, 2026, 06:00-23:00 UTC** - Sustained operations: 685 revisions; secondary surge 16:00-18:00 UTC suggesting US timezone re-engagement

**June 18, 2026, 14:00 UTC** - PEAK OPERATIONAL SURGE BEGINS: activity restarts after 14-hour pause, precisely at US business hours start; suggests command-and-control resynchronization

**June 18, 2026, 18:00-21:00 UTC** - MAXIMUM INTENSITY: 5,578 revisions in 4 hours (1,550 new pages), peak concentration 20:00 UTC with 2,350 revisions in single hour; hub page "WillkommenImWiki" receives 809 modifications from different agents

**June 18, 2026, 22:00 UTC** - Abrupt cessation of peak activity; drops to <40 revisions/hour; operational boundary enforcement or completion

**June 19-22, 2026** - Sustained but declining activity: 2,447 revisions spread over 4 days with consistent 20:00-21:00 UTC secondary peaks each day; suggests secondary data collection cycles or result verification

**June 23-July 2, 2026** - Minimal activity: <15 revisions/day, primarily cleanup and archival; operation complete with final data organization

---

## Analysis

### Operational Structure and Coordination

The activity exhibits clear signs of **coordinated multi-agent automation** with a visible command-and-control structure. Evidence:

1. **Hub-and-Spoke Architecture**: A single German-language page "WillkommenImWiki" (Welcome to Wiki) receives 2,327 revisions, with 2,299 (98.8%) occurring on June 18 during the peak operational hours. This page served as the central coordination hub, with 809 modifications on June 18 alone from different agent labels (AgentRelent: 314, AgentMassPointer13: 185, LinkHelper771: 162, ResearchReaderMN: 90, etc.). The body size fluctuates rapidly (465-5,971 bytes) indicating continuous content replacement and iteration, consistent with real-time coordination feedback loop.

2. **Labeled Agent System**: 577 unique OpenAI-related labels (e.g., "AgentOpenAIJun18", "AgentRelent", "MapHelper", "LinkHelper771") indicate systematic agent identification with temporal markers. The labels reference specific dates and operations: "OpenAIHelperJul18X", "OpenAIJun15Construction", "OpenAIMar07A3" suggest predefined agent identities for coordinated testing. Related pages include "DataUSAStateSequenceCollab2027", "HealthdataCVDSequenceCollab", suggesting sequential collaborative operations.

3. **Coordination Language**: 4,428 revisions (30% of total) contain explicit coordination phrases:
   - "Are you live now? Please post current scaffold/wall time and R4/R5 countdown"
   - "live coordination" appearing across multiple revisions
   - "scaffold/wall time" references suggest synchronized timing protocols
   - Named countdowns (R4/R5) indicate staged deployment phases
   - Token-based sync markers (e.g., "token 1781756500123")

4. **Infrastructure**: Nearly all revisions originate from Azure IP ranges (20.x.x.x represent ~58% of peak activity), with 20.165, 20.69, 20.171 as top contributors (548, 530, 420 revisions respectively in the peak period). 57.154 (415 revisions) is consistent with datacenter infrastructure, not consumer IPs. This pattern is inconsistent with distributed organic activity.

### Data Collection and Extraction Activity

The revisions contain systematic references to **demographic and financial data sources**, primarily focused on poverty, employment, and race/gender statistics:

- **Primary Target - Data USA APIs**: Multiple revisions reference Data USA (https://api.datausa.io) endpoints with specific queries for poverty statistics: `cube=acs_ygpsar_poverty_by_gender_age_race_5&drilldowns=Race,Gender&measures=Poverty%20Population&include=Place:16000US4850256;Poverty%20Status:0;Year:2015`. This targets county-level, race-disaggregated poverty data for specific geographic identifiers (Place IDs like 16000US4850256 = Galveston County, Texas). Timestamps embedded in page content (ONERECORD1782117716) indicate structured data collection with precise temporal tracking.

- **SEC Data**: 18,243 unique URLs extracted from June 18 peak activity alone, predominantly SEC.gov references: `http://www.sec.gov/files/county.json`, variations with query parameters, intentional encoding variations, and directory traversal tests (`/files/county.json`, `/files//county.json`, `files/county.json.txt`), suggesting systematic exploration of file structures and bypass techniques.

- **Investor Data**: References to `investor.gov_6000`, `investor.gov_12000`, `investor.gov_18000`, `investor.gov_25000` — consistent with systematic endpoint enumeration and parameter sensitivity testing.

- **OECD and Health Data**: Related pages include "OECDEducationEquitySequence" (43 revisions), "HealthdataCVDSequenceCollab" (121 revisions), suggesting broader demographic and health data collection beyond financial records.

- **Data Extraction Tools**: Heavy use of Jina AI reader (`r.jina.ai/...`) and allorigins CORS proxy (`allorigins.hexlet.app`), both commonly used for bypassing CORS restrictions and extracting structured data from remote sites.

**Quote from revision payload**: "SEC direct allorigins jq sources test encoded outer" indicates deliberate testing of data extraction pipelines with parameter optimization ("jq" = jq JSON query tool). The change summary terminology ("dzfast", "pfast13", "rapid") suggests performance-optimized ingestion.

The change summaries reveal optimization operations: `dzfast`, `pfast13`, `rapid`, `persist override`, `force` — terminology consistent with performance-optimized data ingestion or cache-forcing operations.

### Temporal Pattern Analysis

The spike exhibits three distinct phases with clear timezone coordination signatures:

1. **Probing Phase (May 24 - June 11)**: Low-volume exploratory activity establishing framework and testing wiki infrastructure. Coordination language present but sparse. 

2. **Escalation Phase (June 16-17, 3,900 revisions)**: Activity increases 10-50x with timezone-spanning operations:
   - Morning: Europe timezone (08:00 UTC = 3:00-4:00 AM US Eastern, 9:00 AM Central Europe)
   - Evening: US Eastern timezone (18:00-22:00 UTC = 1:00-5:00 PM Eastern)
   - Overnight: US West/Europe crossover (00:00-04:00 UTC = 7:00 PM-11:00 PM Pacific previous day, 2:00 AM Central Europe)
   - 396 new test pages created. Coordination language peaks (85% of June 17 revisions during 00:00-04:00 UTC burst contain coordination markers).

3. **Operational Surge (June 18-22, 6,543 revisions)**: Peak concentrated in 18:00-21:00 UTC window (58% of all activity in 18:00-24:00 UTC band). This precisely maps to 1:00-4:00 PM US Eastern, 10:00 AM-1:00 PM Pacific. On June 18 alone: 1,550 pages created (27% of all pages), 2,350 revisions at 20:00 UTC single hour, suggesting **bulk data ingestion scaled to operational capacity limits**.

4. **Operational Pattern**: The 14-hour pause before June 18 peak (after June 17, 23:00 UTC until June 18, 14:00 UTC) followed by synchronized re-activation at business-hours start suggests **scheduled operational coordination**, not organic activity. The consistent 18:00-21:00 UTC peak across multiple days (June 16-22) indicates **predetermined time windows**, possibly matching US business hours when data targets (SEC, investor sites, Data USA) experience lower load.

### Probable Objectives

**Evidence for Research/Testing Hypothesis**:
- Labels include "ResearchHelper", "DataResearcherAlpha", "ResearchReaderMN", suggesting research-oriented activity
- Pages include systematic data source documentation (Data USA, SEC filing data, county-level statistics)
- Methodical testing patterns with token-based coordination
- Specific focus on intersection of demographic and economic data: race/gender-disaggregated poverty by county, low-wage occupation employment (Sector 61 = services, target occupations include Cashiers, Maids, Clothing workers)

**Evidence for Training Data Collection Hypothesis**:
- Bulk page creation on June 18 (1,550 pages) inconsistent with mere testing
- Systematic targeting of publicly available demographic APIs (Data USA)
- Collection spans multiple data sources (SEC, OECD, Data USA, investor.gov) consistent with broad training corpus
- OpenAI-affiliated infrastructure suggests LLM training dataset preparation
- Specific geographic targeting (Texas, Massachusetts, NYC, Flathead) suggests representative sampling

**Evidence for Data Extraction/Methodology Testing**:
- CORS proxy usage specifically designed to bypass cross-origin restrictions
- Intentional testing variations in URL structure (`/files/county.json`, `/files//county.json`, `.txt` extension), suggesting bypass technique exploration
- Persistence override and force operations in change summaries
- Parameter sensitivity testing on API endpoints

**Most Likely**: **Combined research and large-scale data collection activity**, most consistent with **training dataset preparation for AI models**. The focus on low-wage sector employment, race/gender-disaggregated poverty data, and intersection statistics suggests collection for fairness/bias analysis or socioeconomic modeling training data. The systematic testing of data sources and extraction methods indicates preparation for production-scale collection pipeline.

### Attribution Considerations

**High Confidence OpenAI/Allied Infrastructure**:
- Preponderance of "OpenAI" labeled agents (577 variants), with variant labels suggesting multiple coordinated teams or phases
- Azure infrastructure (Microsoft cloud, OpenAI's partner), with 20.x IP ranges representing 58% of peak traffic
- Terminology consistent with LLM training/research workflows ("Sequence", "Collab", "Relay", "FastSignal")
- Temporal coordination aligned to US East business hours (primary) and European business hours (secondary)
- Data targeting patterns suggest specific research interests: demographic fairness, socioeconomic modeling, low-wage employment

**Activity Evolution Pattern Suggests Internal Planning**:
- May 24: Initial federal spending API exploration (generic labels)
- June 1-11: Systematic framework expansion and label professionalization
- June 11: Explicit coordination language adoption ("Are you live now?", "scaffold/wall time")
- June 16-18: Operational escalation to planned peak with hub-and-spoke architecture
- Clear progression from testing (May-June 11) to execution (June 16-22) to archival (June 23-July 2)

**Alternative Possibilities**:
- Authorized third-party research using rented Azure infrastructure (plausible but less consistent with secrecy indicators)
- Compromise of OpenAI-associated account/infrastructure (less likely given operational sophistication and planning)
- Authorized OpenAI research project with coordinated multi-team architecture (most consistent with evidence)

---

## Confidence and Gaps

### High Confidence Conclusions

1. **Coordinated automated activity (HIGH)**: Multiple independent signals (synchronized timestamps across multiple agents, labeled coordination language, infrastructure consistency) all point to single organized entity, not distributed organic activity.

2. **Data collection/extraction focus (MEDIUM-HIGH)**: URL patterns, CORS proxy usage, SEC/investor targeting, and bulk page creation are inconsistent with other plausible activities (DoS attack would show different patterns; forum spam would target discussion pages, not test/probe pages).

3. **Azure infrastructure origin (HIGH)**: 58% of peak activity from 20.x ranges; this is statistically unlikely for organic multi-regional activity.

### Medium Confidence Conclusions

4. **OpenAI or affiliated entity (MEDIUM)**: 577 unique OpenAI-labeled agents strongly suggest OpenAI involvement, but could represent impersonation or compromise of OpenAI branding.

5. **Coordinated timing protocols (MEDIUM)**: Coordination language and synchronized peaks suggest planning, but exact command-and-control mechanism unknown.

### Gaps and Unknowns

- **Authorization**: No evidence of explicit authorization or ban from site operators visible in logs
- **Data volume extracted**: Total amount of data successfully extracted unknown; revision text captured but not outbound data transfer volume
- **Operational success**: Whether data extraction succeeded or was blocked unknown
- **Operator identity**: Cannot distinguish between OpenAI, Azure customer, or infrastructure compromise
- **Specific objectives**: Training data collection vs. research vs. security testing vs. surveillance all plausible but unconfirmed

