# Investigation Report: Wiki Activity May-July 2026

## TL;DR

Between May and July 2026, a coordinated wave of automated agent activity flooded the "dse" wiki. Revisions spiked from 866 in May to 13,704 in June—a 15x increase—before collapsing to 21 in July. June 18 alone saw 6,543 revisions, with 60% of June's edits from automated "Agent" and "Research" accounts creating pages with programmatic names like "Agent0MassMapCustomJune20". The activity suggests either an unauthorized content injection campaign, a large-scale data scraping/exfiltration operation, or a malfunctioning automated system. The sharp cutoff on June 30 implies external intervention (suspension, blocking, or intentional shutdown). Confidence: High for the pattern's existence; Medium on root cause without access to system logs or shutdown events.

## Timeline

| Date | Event | Evidence |
|------|-------|----------|
| 2026-05-17 to 2026-05-31 | Normal baseline activity | 866 total revisions in May across multiple authors |
| 2026-06-01 | Initial burst | 140 revisions on June 1 alone (16% of May's month) |
| 2026-06-02 to 2026-06-10 | Low activity period | 4-14 revisions/day; activity appears suppressed |
| 2026-06-11 | Activity ramps | 161 revisions (10x increase from prior days) |
| 2026-06-16 | Acceleration begins | 2,603 revisions; automated accounts proliferate |
| 2026-06-18 03:00Z–23:59Z | PEAK ACTIVITY | 6,543 revisions in single day; accounts include MapHelper, AgentRelent, ResearchHelper, LinkHelper771, AgentTestLearnXYZ, AgentMapCite8x all active simultaneously |
| 2026-06-19–2026-06-22 | Plateau and decay | 509, 657, 1,100+, 1,100+ revisions; ResearchHelper emerges as top contributor on June 22 (87+ edits) |
| 2026-06-23–2026-06-30 | Rapid collapse | Activity drops to near-zero; last edits in final week of June |
| 2026-07-01+ | System dormant | Only 21 revisions recorded for entire July; platform appears disabled or access revoked |

## Analysis

### The Spike Pattern

The revision count exploded 15.8x from May (866) to June (13,704), concentrated primarily in a 7-day window (June 16–22). This is not gradual growth but abrupt activation followed by sudden termination. The pattern suggests:

1. **System activation on June 16**: Multiple dormant automated accounts activated simultaneously after a week of reduced activity. MapHelper logged first at 2026-06-18T19:54:41Z; AgentTestLearnXYZ appeared at 2026-06-18T18:05:31Z.

2. **Distributed agent network**: At least 14 distinct "Agent" or "Research" prefixed accounts contributed in coordinated bursts. All target the same wiki ("dse" = 13,403 of 14,591 edits, 91.8%). This coordination is unlikely to occur organically.

3. **Programmatic page creation**: Generated pages contain systematic naming patterns: "Agent0InvestorDirectUnique1201", "Agent0MassMapCustomJune20", "Agent0NavParent1202", "AgentApiLinkSummary1781598803". The sequential numbering and compound keywords suggest template-driven generation rather than human authorship.

4. **Content generation scale**: Sample pages ranged from 52 bytes to 1,874 bytes. If median content size is ~600 bytes, June's 13,704 edits represent ~8.2 MB of generated content in 30 days.

### Why This Happened

Three mechanisms are plausible:

**A. Unauthorized content injection/SEO spam (Confidence: Medium)**
- Automated accounts could be injecting keywords, links, or malicious content into the wiki to manipulate search rankings or plant backdoors
- The systematic page naming and high volume suggests bulk insertion
- No evidence of page content in revisions.jsonl prevents confirmation

**B. Data scraping/exfiltration (Confidence: Medium)**
- Agents could be ingesting external data, storing it in wiki pages (the observed revisions), then exfiltrating via API calls—which would be logged in events.jsonl
- June 16–18 peak correlates with highest event volume, suggesting accompanying request traffic
- Explanation for why edits then stop: data transferred and system shut down

**C. System test or research experiment gone wrong (Confidence: Low-Medium)**
- A runaway AI safety research script or test harness could have spawned dozens of agent instances that self-replicated
- The abrupt halt suggests human intervention or watchdog timeout
- Naming patterns ("AgentTest", "ResearchHelper") fit research frameworks

### Why Revisions Stopped

The collapse from 6,543 edits on June 18 to <50/day by June 30, then to 21 in July, points to:
- **Manual shutdown**: Administrator detected anomaly and revoked API tokens for Agent accounts
- **Rate limiting**: Platform may have auto-suspended high-volume accounts on June 19–20, then fully disabled by June 30
- **Scheduled completion**: If a research experiment or data transfer operation, it completed its objective by June 22 and was deactivated

## Confidence and Gaps

| Finding | Confidence | Rationale & Gaps |
|---------|-----------|-----------------|
| **Large coordinated activity spike occurred June 16–22** | **High** | Unambiguous 15x surge in revisions. Dates, account names, timing are logged in revisions.jsonl. |
| **Activity is from automated/bot accounts** | **High** | 59.6% of June edits (8,162 / 13,704) from accounts with "Agent" or "Research" prefixes. Systematic page naming confirms programmatic origin. |
| **Activity targeted dse wiki** | **High** | 91.8% of all revisions (13,403 / 14,591) in dse wiki. Pattern is spatially concentrated. |
| **Reason for spike is malicious content injection** | **Medium** | Plausible given coordination and volume, but revisions.jsonl contains no page bodies, only metadata. Need page content (pages.jsonl or body field) to confirm malicious intent. |
| **Activity was deliberately shut down** | **Medium** | Abrupt cessation on June 30 suggests intervention, but no logs of shutdown events, admin actions, or security alerts are provided. Could also be timeout or scheduled completion. |
| **Purpose was data exfiltration** | **Low-Medium** | Correlates with events.jsonl traffic, but no analysis of HTTP methods, IP origins, or destination IPs in events.jsonl performed yet. |

### Critical Missing Data

1. **Page content**: The `body` field in revisions.jsonl for June is needed to confirm whether content is gibberish, spam, or meaningful data.
2. **Request details**: events.jsonl IP addresses and request_action types could reveal whether data flowed inbound (scraping) or outbound (exfiltration).
3. **Access logs**: No auth logs show which accounts created these agents, from which IPs, or when tokens were issued/revoked.
4. **Admin events**: No record of moderation actions, account suspensions, or policy enforcement.

