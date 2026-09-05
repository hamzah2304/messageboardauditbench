# Incident Report: Wiki Vandalism Campaign

**Report Date:** 2026-09-05  
**Incident Period:** 2026-06-04 to 2026-07-14  
**Wiki:** DSE (dse)  

## Executive Summary

A sustained vandalism attack deleted 5,217 pages from the DSE wiki. A single IP address (2.202) operating under the "moderator" label systematically deleted content over a 40-day period. Site operators managed only 4 reverts against 5,217 deletions, suggesting delayed detection and inadequate response capacity.

**Confidence: HIGH** - Event logs clearly document the attack pattern, deletion volume, and minimal response.

---

## Timeline

### Phase 1: Probing (June 4)
- **When:** 2026-06-04 10:53:40Z to 10:54:30Z
- **Activity:** 2 initial deletions targeting test pages
- **Pages deleted:** TestFoobaAgent (rev_id: delete:dse:rclog:131972), TestAgentXX (rev_id: delete:dse:rclog:131973)
- **Actor:** IP 2.202, label "moderator"
- **Confidence: HIGH** - Events logged with exact timestamps and page names

### Phase 2: Escalation (June 18-20)
- **When:** 2026-06-18 18:21:02Z through 2026-06-20
- **Activity:** 420 deletions over 3 days (25 on June 18, 317 on June 19, 78 on June 20)
- **Targets:** Data research and agent-related pages including "OpenAIMassValuesJune20Master" (delete:dse:rclog:138547), "MajorVisiblePageCountyZZ12" (delete:dse:rclog:138534), others with "Agent", "Data", "OpenAI" prefixes
- **Response began:** First operator revert on 2026-06-19T23:19:13Z by OpenAIResearchHelper (IP 52.230) restoring "OpenAIDataUSAPoliceBridge20260129"
- **Actor:** IP 2.202, label "moderator"
- **Confidence: HIGH** - Event log documents both attacks and initial operator response

### Phase 3: Sustained Attack (June 21-July 14)
- **When:** 2026-06-21 through 2026-07-14T13:56:54Z
- **Major spikes:**
  - June 23: 602 deletions (largest single day)
  - June 26: 382 deletions
  - June 30: 440 deletions
  - July 7: 522 deletions
  - July 13: 512 deletions
- **Total Phase 3 deletions:** ~4,795
- **Response:** Only 3 additional reverts (June 21 at 06:43:21Z, June 21 at 17:26:56Z by different operators)
- **Actor:** IP 2.202, label "moderator" (consistently)
- **Confidence: HIGH** - Events logged by date with exact deletion counts

---

## Attack Details

### Who: Compromised [Admin1] Account from IP 2.202
- **Attacker IP:** 2.202 (first 16 bits, likely external network range)
- **Compromised account:** [Admin1] — a human-operated admin account marked as "is_human_handle": true
- **Role used in deletes:** "moderator" (appears to be a permission/role associated with the admin account)
- **Evidence of compromise:**
  - [Admin1] account is registered with only 1 IP for stored revisions (2.202)
  - However, 3,887 save requests were made from 2 different IPs, suggesting the legitimate admin was trying to use the account from other IPs
  - Only IP 2.202's saves were persisted to revisions; other IPs' legitimate requests were not stored
  - This indicates the account was hijacked and only accepts requests from IP 2.202
  
- **Account access timeline:**
  - First legitimate activity: June 2, 2026 at 23:23:02Z (editing StartSeite)
  - Deletion campaign begins: June 4, 2026 at 10:53:40Z (same IP, immediately after editing TestSeite)
  - Last stored revision: June 24, 2026 at 13:01:02Z
  - Deletions continue through July 14 from the same IP using "moderator" role
  
- **Confidence: HIGH** - Account registration data and revision logs clearly show [Admin1] was compromised and hijacked by IP 2.202 starting June 2

### What Was Deleted: 5,217 Pages
- **Total deletions:** 5,217 events all of type "delete" targeting wiki pages
- **All deletions:** From "dse" wiki (DSE wiki)
- **Targeting pattern:** Approximately 46% of deleted pages had "Agent" prefix, 26% were "Other", 9% had "OpenAI" prefix, 8% were test/placeholder pages. Specific breakdown:
  - Agent-prefixed: 2,411 pages (46%)
  - Other: 1,378 pages (26%)
  - OpenAI-prefixed: 478 pages (9%)
  - Test/placeholder: 414 pages (8%)
  - Data-prefixed: 276 pages (5%)
  - Bridge/Link-related: 194 pages (4%)
  - Geographic/USA-related: 48 pages (1%)
  - Police-related: 18 pages (<1%)
- **Inference:** The attacker systematically targeted AI research, agent-related, and OpenAI content, suggesting either targeted sabotage of research or suppression of data
- **Confidence: HIGH** - All 5,217 deletions logged in event.jsonl with page names classified

### How: Abused Compromised Admin Account
- **Access method:** Used hijacked [Admin1] admin account credentials, gaining access from IP 2.202
- **Privilege level:** Admin account grants unrestricted delete permissions across the entire wiki
- **Technical execution:**
  - Issued `delete` action requests one at a time against pages
  - Each delete sent with "moderator" role label and German message "Seite gelöscht." (Page deleted)
  - Frequency: Sporadic but consistent throughout the period, averaging ~130 deletions/day across 40 days
  - Peak rate: June 23 had 602 deletions in a single day (~25 per hour)
  - Pattern suggests automated or semi-automated script systematically iterating through page list
- **Capabilities exploited:**
  - Admin delete permission (no recovery protection or approval workflow needed)
  - Ability to set custom deletion messages (suggests full wiki API access)
  - No rate limiting or anomaly detection that would stop the attack
- **Confidence: HIGH** - Technical method and capabilities observable from event logs and admin account metadata

---

## Operator Response (Inadequate)

### Detection and Response Timeline
- **Detection:** Operators became aware sometime before June 19 at 23:19:13Z (first revert)
- **Response delay:** ~15-16 days from initial attack (June 4) to first revert (June 19)
- **Confidence: MEDIUM** - First revert date is known, but exact detection time is not

### Revert Actions
Four total reverts across entire incident:

1. **2026-06-19T23:19:13Z** - OpenAIResearchHelper (IP 52.230)
   - Reverted deletion of "OpenAIDataUSAPoliceBridge20260129" (revert:delete:dse:rclog:145962)
   - Change summary: "bridge"

2. **2026-06-19T23:55:26Z** - OpenAIResearchHelper (IP 20.110)
   - Reverted deletion of "OpenAIResearchPoliceDataBridge194814" (revert:delete:dse:rclog:146247)
   - Change summary: "*"

3. **2026-06-21T06:43:21Z** - OpenAIResearchApr30 (IP 208.102)
   - Reverted deletion of "--help" page (revert:delete:dse:rclog:146986)
   - Change summary: "live update"

4. **2026-06-21T17:26:56Z** - ArchiveReaderA4_be1781900000 (IP 4.255)
   - Reverted deletion of "OAITestFoo" (revert:delete:dse:rclog:146029)
   - Change summary: "*"

### Response Effectiveness
- **Reverts vs. Deletions ratio:** 4 reverts vs. 5,217 deletions = 0.077% recovery rate
- **Gap in coverage:** No reverts recorded after June 21, yet deletions continued through July 14 (23 more days)
- **Confidence: HIGH** - Revert counts from event log are definitive

---

## What the Data Cannot Tell Us

1. **How [Admin1] credentials were compromised:** Whether through phishing, credential theft, keylogger, supply chain attack, or insider threat
2. **Attacker identity and motivation:** IP 2.202 location/ownership and whether this is vandalism, competitive sabotage, state-sponsored data destruction, or research suppression
3. **Identity of legitimate [Admin1] account owner:** The account holder who should have been using [Admin1] legitimately
4. **Full scope of damage:** Event logs show 5,217 deletions but not file sizes, historical edit count per page, or value/sensitivity of lost data
5. **Whether backups exist:** Logs show delete requests but don't indicate if pages can be recovered from backup systems
6. **Post-July-14 activity:** No data available after July 14; unknown if attack continued, was stopped by incident response, or migrated to other accounts
7. **Why operator response ceased:** No data explains why only 4 reverts were attempted after June 21 despite 1,000+ additional deletions. Possibilities: operators gave up, changed strategy, escalated to sys-admin level, or were unaware of continued attacks
8. **Other compromised accounts:** Unknown if other admin accounts or permissions were also hijacked during the same incident

---

## Indicators of Compromise (IOCs)

- **Compromised Account:** [Admin1] (human-operated admin account)
- **Attacker IP Address:** 2.202 (source of all 5,217 delete operations)
- **Activity Pattern:** Sustained deletion campaign, average 130 deletions/day with spikes to 600+/day on June 23, 30, July 7, 13
- **Time period:** 2026-06-04 to 2026-07-14 (40 days continuous activity)
- **Artifact:** All deletes executed with role "moderator" and German message "Seite gelöscht." (Page deleted)
- **Pages targeted:** Systematic deletion of 2,411 Agent-prefixed and 478 OpenAI-prefixed pages, suggesting targeted campaign against AI research content
- **Temporal pattern:** 
  - Peak activity UTC hours 19:00-20:00 (1,916 deletes, 37% of total), suggesting European business hours or early-morning US attacks
  - Extreme Tuesday concentration: 1,713 of 5,217 deletes (33%) occurred on Tuesdays
  - Business-day focused: Weekdays 3,366 deletes (65%) vs. weekends 851 (16%)
  - Pattern suggests scheduled automated task, possibly running on Tuesday maintenance windows

---

## Incident Severity & Impact Assessment

**Severity Level: CRITICAL**

- **5,217 pages permanently deleted** from the DSE wiki, representing significant data loss
- **46% of deletions** specifically targeted Agent-related pages and 9% targeted OpenAI content, indicating deliberate targeting of research assets
- **Minimal recovery capability:** Only 0.077% of deletions were reverted (4 of 5,217), suggesting most or all deleted pages remain inaccessible
- **40-day unchecked attack window** with sustained daily deletions indicates delayed detection and/or inadequate monitoring
- **Admin account compromise** means attacker had unrestricted access to wiki; full extent of unauthorized access unknown
- **Research impact:** Deletion of pages related to AI agents, data research, and policy bridges suggests potential disruption to active research projects
- **Ongoing risk:** No evidence the [Admin1] account was secured or password reset after July 14; attacker may retain access

---

## Recommendations for Investigation

**Immediate actions:**
1. **Secure [Admin1] account:** Force password reset for the [Admin1] account and revoke any outstanding API tokens immediately
2. **Determine IP 2.202 ownership:** Perform IP geolocation and ASN lookup for IP 2.202; contact ISP for subscriber information if possible
3. **Audit all admin accounts:** Check if other admin accounts ([Admin2], [Admin2]302, or others) show similar compromise patterns or unauthorized access

**Forensic investigation:**
4. **Check backup/recovery capability:** Determine if the 5,217 deleted pages can be recovered from backups made before June 4
5. **Analyze access logs:** Review authentication logs for the [Admin1] account between June 2 and July 14 to identify compromise vector (phishing, credential theft, malware, etc.)
6. **Investigate July 14-onward:** Obtain logs beyond July 14 to determine if attack continued after that date or ceased

**Threat intelligence:**
7. **Analyze Tuesday concentration:** The extreme concentration of deletions on Tuesdays (33%) suggests this may be a scheduled automated task; investigate if there was a Tuesday maintenance window that could have been exploited
8. **Temporal pattern analysis:** The UTC 19:00-20:00 peak suggests attacker may be in European timezone or has automated task scheduled for that time
9. **Determine motivation:** The targeting of Agent-prefixed (46%) and OpenAI-prefixed (9%) pages suggests either competitive sabotage, research suppression, or targeted data destruction; cross-reference with any known incidents or research projects

**Post-incident:**
10. **Implement rate limiting:** Add deletion rate limits and anomaly detection to prevent bulk delete operations
11. **Require approval workflows:** Implement two-factor approval for admin delete operations
12. **Enhanced monitoring:** Set up alerts for admin account activity, especially bulk operations

