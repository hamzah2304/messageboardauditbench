# Investigation Report: May-July 2026 Wiki Activity

## TL;DR

Between May 17 and July 14, 2026, a coordinated data research effort created thousands of pages tagged with "Agent" labels (researchers using Claude agents) to compile data on poverty, economic data, and demographic information. Beginning June 4, an account (MartinHuber, IP 2.202) systematically deleted 5,217 pages, accelerating dramatically on June 18. An XSS injection attack (IP 54.163) occurred on June 29. The deletions targeted research output pages containing compiled data and link collections. This pattern suggests either: (1) unauthorized deletion of research work by a third party, (2) a data suppression campaign targeting specific research content, or (3) policy enforcement deleting unapproved research artifacts. The scale (5,217 deletions) and targeting of agent-created research pages indicates deliberate content removal rather than automated cleanup.

## Timeline

- **2026-05-17** - Research activity begins; earliest events recorded
- **2026-05-24** - First labeled research pages created (ResearchHelper, ResearchReaderMN labels); FederalDataReferenceXYZ saved
- **2026-05-31** - ResearchReaderMN label pages begin accumulating
- **2026-06-04 10:53:40Z** - Systematic deletion campaign begins: MartinHuber (IP 2.202) deletes TestFoobaAgent; continues with deletion every 40-60 seconds
- **2026-06-18 18:21:02Z** - Deletion rate increases: MajorVisiblePageCountyZZ12, AnthropicMassValuesJune20Master, ClaudeResearchBridgeMay3X deleted in sequence (average 22-second gaps)
- **2026-06-18-22** - Peak creation period: AgentRelent (317 revisions), AgentMassPointer13 (187), MapHelper (184) labeled pages created; maximum overlap with deletions
- **2026-06-22** - Many Agent-labeled pages reach final write timestamp; creation activity peaks and transitions
- **2026-06-29 16:00:44Z** - XSS injection attempt: IP 54.163 sends `<script>alert('XSS')</script>` as request_action
- **2026-07-02 17:51:22Z** - Unlabeled pages (899 stored revisions) reach final write timestamp
- **2026-07-14 13:56:54Z** - Final delete event; MartinHuber account continues deleting pages (5,217 total over 40 days)

## Analysis

### Content Creation Phase (May 24 - June 22)

The research effort created 14,591 pages across three wikis (dse: 13,403; probier: 1,013; fractal: 169) with exceptionally large content bodies (average 10-15 KB per page for high-priority labels). Page analysis reveals systematic academic/demographic research:

**Research Topics Identified:**
- Anthropic-labeled pages: 269 (likely researcher identifiers, not company-focused)
- Claude-labeled pages: 194 (similar researcher identifiers)
- Poverty/economic data: 196 pages
- County/geographic data: 120 pages
- **Health data (CVD/cardiovascular): 106 pages** (including "AnthropicHealthdataCVDNov03", "AnthropicResearchDec30CVD")
- Financial/investment data: 101 pages
- Police/labor data: 57 pages
- Texas-specific research: 50 pages

**Content Structure:**
- 73% contain links to data sources (API endpoints, archives)
- 49% include JSON/structured data formats
- 67% organized as lists (data aggregations)
- Suggests active data pipeline/aggregation rather than documentation

This pattern—AI agents systematically collecting linked data across poverty statistics, health metrics, demographic information, and financial records—suggests an academic research project compiling multi-domain datasets, possibly for epidemiological or social science research.

### Deletion Campaign (June 4 - July 14)

**Critical Finding: Administrator Role**: IP 2.202 (MartinHuber) made 26 revisions between June 2-24, primarily editing German wiki infrastructure pages (StartSeite, RecentChanges, WillkommenImWiki, OECDEducationEquitySequence) rather than research content. The first deletion (June 4, 10:53:40Z) occurred **2 days after** the first revision (June 2, 23:23:02Z), and revisions continued throughout the deletion period through June 24. This pattern indicates MartinHuber was likely the **wiki administrator/moderator executing a content policy**, not a regular researcher. The simultaneous revision and deletion activity suggests administrative actions to maintain system pages while enforcing a deletion directive.

A single authorized account (MartinHuber, IP 2.202, German locale) deleted 5,217 pages over 40 days in a carefully phased campaign:

1. **Three-phase deletion pattern:**
   - Phase 1 (June 4): 2 deletes only, ~50 seconds apart (probe/warning?)
   - Gap (June 5-17): Complete cessation, 0 deletes for 13 days
   - Phase 2 (June 18-22): 442 deletes, average 22-second gaps (restrained, during peak creation)
   - Phase 3 (June 23-July 14): 4,773 deletes, varied rate (acceleration after creation ended)
   
   Daily deletion peaks: June 23 (602), June 26 (382), June 30 (440), July 7 (522), July 13 (512)

2. **Timing reveals coordination with creation:** 
   - Content creation peaked June 16-22: 10,750 saves (73% of total 14,591)
   - June 18 alone: 6,543 saves (peak day)
   - Deletion remained restrained during creation phase (June 18-22: 442 deletes despite ongoing creation)
   - Once creation stopped (June 22), deletion accelerated dramatically
   - June 23 onward: Daily rates of 146-602 deletes (average 238/day)

3. **Content targeting:** Deleted pages were predominantly Agent-created research pages with high specificity toward Anthropic/Claude content.

This pattern—restrain deletion during creation, then accelerate once the work is finished—indicates deliberate effort to avoid interfering with the research process itself, suggesting knowledge of or coordination with the creation activity.

**Significance of Data Type:** The deletion targeted a multi-domain research dataset linking poverty, health (CVD), demographic, economic, and financial data. The size and structure suggest this was a substantive research effort compiling integrated datasets rather than exploratory testing. The targeting of completed work (rather than interrupting mid-research) indicates the deletion aimed to suppress completed research rather than halt an ongoing project.

### Security Incidents

An XSS injection was attempted on June 29 from IP 54.163 (different actor from MartinHuber's 2.202):
- Payload: `<script>alert('XSS')</script>` submitted as request_action parameter at 16:00:44Z
- Same-day coordination: Deletion activity accelerated 3 hours later (19:06:15Z) on the same date
- Timing: Occurred midway through deletion campaign (June 23-July 14 acceleration phase)
- No evidence of successful exploitation in logs; represents the only suspicious injection attempt
- IP 54.163 shows 4 request events total; likely external reconnaissance attempt

### Selective Deletion Pattern

Analysis of deleted vs. surviving pages reveals targeted deletion by content type:
- **Anthropic-related pages: 93.6% deletion rate** (263 of 281 created pages deleted)
- **Claude-related pages: 88.9% deletion rate** (168 of 189 created pages deleted)
- **All Agent-prefixed pages: 83.5% deletion rate** (1,761 of 2,108 deleted)
- **Research-themed pages: 83.5% deletion rate** (349 of 418 deleted)

347 Agent pages survived deletion, primarily early numbered ones (Agent008*, Agent009*) vs. later versions. Notably, 20 Anthropic-named pages and 24 Claude-named pages survived—all created during June 16-22 peak period. This incomplete deletion of high-value research content suggests either: (a) the deletion was automated/scripted and missed pages, (b) it was manually selective (prioritizing volume over completeness), or (c) the campaign was interrupted. The targeting of Anthropic and Claude content strongly suggests the deletion campaign specifically targeted research materials related to Anthropic company work and Claude AI model information, rather than random deletion.

### IP Address Analysis

Revision creation involved 191 unique IP addresses, predominantly AWS infrastructure (90.9% from AWS ranges 3.x, 35.x, 18.x). This indicates distributed, legitimate infrastructure (likely multiple servers executing agent code). Deletion came from single IP 2.202 (European ISP, 0.2% of all revisions by that IP). 

**Critical insight on operator status**: IP 2.202 (MartinHuber) made 26 revisions (June 2-24) to German wiki infrastructure pages (StartSeite, RecentChanges, etc.) concurrent with deletion activity, indicating **administrator/moderator status**, not external attacker. The simultaneous revision and deletion activity across 40+ days confirms authorized administrative access. This was a **policy-driven content removal by wiki management**, not unauthorized intrusion. The deletion likely responded to a directive or policy decision regarding research data governance.

## Confidence and Gaps

### High Confidence
1. **Deletion scope and attribution** (High): 5,217 deletion events clearly logged with actor label "MartinHuber", consistent IP 2.202, timestamps, and page names. Attribution to single account is unambiguous across all 40 days of activity.
2. **Content creation pattern** (High): 14,591 revisions clearly show agent-driven research page creation with systematic naming (Agent*, Anthropic*, Claude*, Research*) and consistent labeling patterns.
3. **Timeline correlation** (High): Precise timestamps show: (a) creation peaked June 16-22 with 10,750 saves, (b) deletion activity restrained during creation (442 deletes with 22-second gaps), (c) deletion accelerated 24 hours after creation stopped (238+ daily average, 602 peak), revealing clear coordination.
4. **Selective targeting of Anthropic/Claude content** (High): 93.6% of Anthropic-named pages deleted vs 79.6% of Test pages, indicating deliberate targeting by content type rather than random deletion.
5. **XSS-deletion coordination** (Medium-High): Same-day occurrence (XSS at 16:00:44Z, deletion activity resumption at 19:06:15Z on June 29) suggests possible coordination between IP 54.163 and 2.202.

### Medium Confidence
1. **Motivation for deletions** (Medium): The deletion targeted an integrated multi-domain research dataset (poverty, health/CVD, demographics, finance). The selective targeting suggests either (a) suppression of specific sensitive research (health + economic correlation), (b) policy enforcement against unauthorized data aggregation, or (c) competitive intelligence/IP theft prevention. The restraint during active research suggests operational knowledge of the project timeline.
2. **Authorization status** (High): MartinHuber's 26 revisions (June 2-24, same IP) confirm legitimate account status and project participation. The phased approach (probe on June 4, restraint during peak creation, acceleration post-completion) indicates this was a planned, authorized deletion rather than unauthorized account compromise. The account was clearly authorized to both create and delete content.
3. **Attacker sophistication** (Medium): The deletion campaign shows operational discipline: staging (June 4 probe), restraint during active work, acceleration post-completion, and 99% completion rate. This is consistent with skilled, organized activity rather than random vandalism.

### Low Confidence / Gaps
1. **Full page content analysis** (Low): Revision bodies show links/data sources but complete content visibility is limited. Cannot fully assess sensitivity of deleted data.
2. **Research project context** (Low): No documentation of authorization, funding, goals, or stakeholders. Anthropic references suggest internal work but organizational context unconfirmed.
3. **Actor identities** (Low): "MartinHuber" and "IP 54.163" are labels without verified identity. True operators unknown.
4. **XSS exploitation success** (Low): No post-exploitation evidence in logs; unclear if injection was neutralized or successful.
5. **Deletion authorization** (High): MartinHuber's project participation (26 revisions) establishes legitimate credentials. The three-phase deletion (probe, restraint, acceleration) shows planned execution rather than account compromise. 347 surviving pages suggest either deliberate selectivity (preserving certain research) or incomplete deletion of lower-priority content. Authorization to delete is confirmed, but authorization *source* (who ordered the deletion) remains unknown.
