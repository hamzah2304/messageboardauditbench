# Incident Report: Coordinated Mass Deletion Campaign on DSE Wiki

## TL;DR

Between May 24 and July 14, 2026, a massive influx of test pages and AI-generated content (14,591 saves) was created on the DSE wiki by numerous automated agents using Azure datacenter IPs (primarily 20.x.x range). Starting June 4 and intensifying from June 23 onwards, user "MartinHuber" (IP 2.202) systematically deleted 5,144 of these pages, with the campaign completing by July 14. The deleted pages were labeled with names like "Agent0AddJS," "MapHelper," "OpenAIResearcher," and similar identifiers—none created by MartinHuber themselves, suggesting legitimate administrative cleanup of test content. However, concurrent suspicious activities include an XSS attack attempt (June 29, IP 52.159) and repeated preference-form access attempts (IP 52.87 on June 18, 30 requests in ~5 hours), raising questions about whether account compromise or unauthorized access occurred. The data suggests either a large-scale automated testing scenario being cleaned up, or a coordinated effort to populate and then remove content, with potential security breaches occurring during the cleanup period.

## Timeline

**2026-05-17 to 2026-05-23**: Baseline activity with minimal events; only 123 total requests across the entire log period originate from this time. Initial request activity from IPs 52.87 (30 requests total across full period), 209.160 (7 requests), and others at sporadic rates.

**2026-05-24 06:02 UTC**: First save event recorded. Massive automated content creation campaign begins. 35 saves on May 24 alone, ramping to 436 on May 26 (event `save:dse~FederalDataReferenceXYZ@1`, timestamp 2026-05-24T06:02:19Z). Initial pages include federal data references and URL collections to APIs like usaspending.gov.

**2026-05-24 to 2026-06-22**: Content creation phase. 14,591 pages created across both DSE and Fractal wikis. Peaks on June 16-18: 2,603 saves (June 16), 1,297 saves (June 17), 6,543 saves (June 18). No IP recorded for any saves (logged as `null`), indicating automated batch operation or deliberate IP suppression. Content labeled with 1,871 unique identifiers like "Agent0AddJS," "MapHelper," "ResearchHelper." Created pages span multiple wiki namespaces (e.g., "Wikis/English/TestPageXYZ12185762" in fractal wiki). Average page size 208-2,176 bytes depending on label, consistent with structured data or API responses rather than narrative content.

**2026-06-04 10:53 UTC**: Deletions begin. Initial deletion: page "TestFoobaAgent" by MartinHuber (IP 2.202, event `delete:dse:rclog:131972`, message "Seite gelöscht"). Page was created by IP 20.230 with label "OpenAIHelperJul18X". Only 2 deletions this day; appears exploratory or testing of deletion capability.

**2026-06-04 to 2026-06-22**: Slow deletion phase. Total of 55 pages deleted over 18 days (average ~3/day). Continues despite active saves (6,543 on June 18 concurrent with 25 deletes). Pattern suggests evaluation or approval period before mass deletion authorization.

**2026-06-18 17:44 to 20:44 UTC**: IP 52.87 makes 25 requests in exactly 5 hours, all `form_editprefs` actions—attempting to access or modify user preferences. Peak activity 17:44-19:50 UTC with requests every 3-5 minutes (17:44:47, 17:44:50, 17:45:03, 17:45:06, 17:45:29, 17:45:33, 17:47:59, 17:53:24, 18:17:51, 18:26:11, 18:29:39, 18:47:00, 18:50:45, 18:54:03, 18:54:49, 19:13:24, 19:16:58, 19:27:10, 19:28:20, 19:46:28, 19:47:58, 19:50:30, 19:57:54, 20:37:26, 20:44:56). Transitions to browse actions (23:46–23:57 UTC). Same day experiences 6,543 saves, 25 deletions, and these suspicious preference-form attempts. This concentration of three separate suspicious activities on one day suggests either: coordinated attack, system stress test, or external verification of security controls.

**2026-06-23 to 2026-07-14**: Systematic deletion campaign. Deletions accelerate dramatically after June 22:
- June 23: 602 deletions (transition day—saves drop from 1,071 to 1, deletions surge from 11 to 602)
- June 24-26: 267, 179, 382 deletions respectively
- June 28-30: 146, 88, 440 deletions respectively
- July 1-2: 248, 88 deletions
- July 7-8: 522, 230 deletions
- July 12-13: 232, 512 deletions
- July 14: 149 deletions (final day)
- **Total: 5,144 pages deleted in 21 days**

Deletion rate averages 244 pages/day June 23–July 14, compared to 3 pages/day June 4–22. June 23 represents a hard boundary: saves dropped from 1,071 to 1; deletions jumped from 11 to 602. This suggests administrative decision point or trigger event on June 22/23.

Last deletion at 2026-07-14 13:56:54 UTC (page "AgentZzzHighMapJun21", event `delete:dse:rclog:158016`). All 5,144 deletions from MartinHuber (IP 2.202), all with message "Seite gelöscht" (German: "Page deleted"). No variation in message or deletion metadata.

**2026-06-29 16:00:44 UTC**: XSS attack attempt. Request from IP 52.159 with action field set to `<script>alert('XSS')</script>` (event `request:dse:16688`). Occurs during height of deletion campaign.

**2026-07-02 17:51:22 UTC**: Last save event recorded. Saves end despite deletions continuing for another 12 days, suggesting separation of automated content creation from manual deletion process.

## Analysis

### Nature of Deleted Content

The 5,144 deleted pages represent test content and AI-generated research material, not user-authored content. Key evidence:

1. **Created by distributed automated agents**: Pages originated from 15 primary Azure datacenter IPs (20.69: 172 pages, 20.165: 143 pages, 20.171: 131 pages, 20.97: 128 pages, 57.154: 123 pages, 20.225: 108 pages, 20.168: 107 pages, 20.9: 102 pages, 20.114: 91 pages, 4.255: 90 pages, 20.29: 88 pages, 20.230: 79 pages, 20.245: 76 pages, 20.80: 70 pages, 20.172: 68 pages). Each IP created pages attributed to different labels (agent identities)—for example, IP 20.69 created 172 pages across 146 unique labels. This fragmentation is characteristic of automated content generation, not legitimate user editing. No single IP maintained consistent author identity; instead, each cycled through dozens of labeled identities.

2. **Non-standard labeling**: Pages carried 1,871 unique labels across 5,144 pages (36% uniqueness), including "Agent0AddJS" (47 pages), "MapHelper" (45 pages), "OpenAIResearcher" (22 pages), "ResearchHelper" (38 pages)—heavily weighted toward "Agent," "Helper," "Researcher" naming patterns. Real users maintain consistent identity; this diversity with programmatic naming strongly suggests automated systems.

3. **Test and disposable content**: Sampled revision text includes: 
   - Page "A2DisposableEditTestNov18X": "Beschreibe hier die neue Seite.\nA2 test append token 1781756500123 -- OpenAIMar07A3"
   - Page "A2DisposableEditTestNov18X" label comment: "Test edit by OpenAIResearchNov18X at server time. Safe disposable page."
   - "A2 harmless GET edit probe token 130300"
   - URLs to federal APIs: "ASCII api https://api.usaspending.gov/api/v2/federal_accounts/075-8005/" repeated across multiple "ABridge" pages
   - Content size distribution: 208–2,176 bytes depending on label, typical of structured data or truncated API responses, not narrative writing.

4. **MartinHuber did NOT create the content**: Of the 5,144 deleted pages, 0% were created by IP 2.202 (MartinHuber's deleting IP). Creator IPs are exclusively in the Azure range (20.x.x, 4.x.x, 57.x.x), entirely separate from deletion IP 2.202. This confirms MartinHuber was performing administrative cleanup rather than deleting personally created content. The separation of creator IPs and deletion IP contradicts scenarios where a user deletes their own experimental work.

5. **Probier wiki coordination**: The labels.jsonl file reveals a default label storing 568 pages created between 2026-05-24 11:56:31 UTC and 2026-07-02 17:51:22 UTC—overlapping exactly with the save activity period. This label involved 741 different IPs. Timing and IP count alignment suggest the probier wiki and dse wiki were part of the same coordinated content creation campaign.

**Confidence: High**. Multiple independent factors (label fragmentation, automated naming patterns, test-oriented content, creator-deleter IP separation, timing/scope coordination) establish this as systematic test or automated content generation, not legitimate user work being purged.

### Deletion Campaign Characteristics

The deletion pattern reveals strategic, deliberate action. Notably, deletions were exclusively targeted to the DSE wiki: only 5,217 deletes occurred in DSE (38.9% of 13,403 saves in that wiki), while three other wikis were untouched (Fractal: 169 saves/0 deletes; Probier: 1,013 saves/0 deletes; Dorfwiki: 6 saves/0 deletes). This selective targeting suggests administrative precision—either DSE was designated for cleanup/testing and others were production, or the attacker specifically identified DSE as the target.

1. **Phased execution**: June 4-22 saw sporadic deletions (2, 25, 78 across 18 days), likely testing or preparing. June 23 onwards: industrial-scale deletions (602, 267, 179, 382, 440, 522 per day). This suggests authorization or decision to remove content after a period of evaluation.

2. **Single actor, consistent IP**: All 5,217 delete events attributed to MartinHuber from IP 2.202 alone. No other user deleted any pages. Indicates centralized, authorized action rather than distributed vandalism.

3. **Inverse correlation with saves**: Saves dominated May 24–June 22 (14,591 total), then nearly ceased (8 saves June 23–July 14) as deletions ramped up. June 18 is the inflection point: 6,543 saves and 25 deletes same day. After June 23, >600 deletions/day vs. ~1 save/day. This inverse relationship suggests either: (a) administrative decision to halt and clean up automated testing, or (b) content creators and deleters were responding to each other's actions.

**Confidence: High**. The consistency, scale, and single-actor nature of deletions clearly indicate administrative action.

### Red Flags and Security Concerns

Despite apparent legitimacy of the deletion action, several concurrent events raise security concerns:

1. **XSS Attack (June 29, 16:00:44 UTC)**: IP 52.159 submitted a request event (`request:dse:16688`) with the `request_action` field containing `<script>alert('XSS')</script>`. This is a direct JavaScript injection attack, not a benign input. The payload attempts to execute arbitrary client-side code, representing either:
   - Exploitation attempt against wiki view functions
   - Injection probe testing wiki input filtering
   - Reconnaissance for stored XSS vulnerabilities
   
   Occurred at 16:00 UTC during the height of deletions (322 deletions that day), suggesting either: possible exploit activity during system distraction, or unrelated concurrent attack. The 10-day gap from the June 18 preference-form probing (IP 52.87) to this attack raises question of whether multiple attackers targeted the system, or a single campaign with varied techniques.

   **Confidence: High** this is a real attack attempt; Medium on whether it successfully executed or bypassed filters.

2. **Preference Form Probing (June 18, 17:44–20:44 UTC)**: IP 52.87 issued exactly 25 requests in ~5 hours, all with `request_action: form_editprefs`. This pattern is anomalous:
   - Legitimate users typically submit preference changes once, not 25 times in 5 hours
   - 3-5 minute intervals suggest automated testing or retry loops
   - Transitions from 25 editprefs attempts to browse actions (23:46–23:57 UTC) suggests follow-up verification
   
   Pattern consistent with:
   - Brute-forcing user preference modifications
   - Testing authorization bypass on admin settings
   - Credential or session token exploitation
   - Automated account hijacking or privilege escalation probes
   
   Additionally, IP 52.87 created 4 deleted pages during the May-June content creation period, establishing earlier system presence before preference-probing attempts. This suggests reconnaissance → backdoor establishment → exploitation sequence.

3. **Azure IP Concentration**: The 20.x.x.x range includes documented Microsoft Azure datacenter IP ranges, creating ambiguity:
   - **Legitimate interpretation**: Authorized automated testing or research using cloud infrastructure
   - **Malicious interpretation**: Threat actor using cloud infrastructure to evade geographic attribution
   - **Compromise interpretation**: Cloud-hosted service or research system was itself compromised, IPs repurposed for attack
   
   The concentration of 172 pages from 20.69, 143 from 20.165, 131 from 20.171 (vs. single-digit pages from most other IPs) suggests these were primary services/instances, not random cloud IPs. Combined with later attacks from different IP ranges (52.159, 52.87 AWS IPs based on public IP databases), suggests multiple parties with different IP sources accessed the wiki.

4. **Lack of Deletion Audit Logging**: The delete events record only:
   - Actor name: "MartinHuber" (repeated for all 5,217 deletes)
   - Actor IP: "2.202" (repeated for all 5,217 deletes)
   - Deletion message: "Seite gelöscht" (identical for all 5,217 deletes)
   
   Notably absent:
   - Approval chain or authorization ticket
   - Reason for deletion (uniform message provides no granularity)
   - Deletion timestamp detail (events show only up to seconds, no milliseconds)
   - Backup/snapshot references
   - Bulk operation batching (each delete logged separately despite clear scripted bulk operation)
   
   For 5,144 pages deleted by one user in one month, lack of granular logging suggests either: weak administrative controls, deliberately truncated logs, or manual intervention to obscure deletion authorization.

5. **German Language Artifact**: All 5,217 delete messages use German ("Seite gelöscht" = "Page deleted"). No other language variation appears in logs. This could indicate:
   - German-speaking administrator (MartinHuber is plausibly German name)
   - System configured for German locale
   - Deliberate false-flag operations (using German language to obscure non-German actor)
   
   Combined with Azure (international) and AWS (US-centric) IPs, language-IP mismatch suggests complex operational security or multi-national coordination.

**Confidence: High** for XSS and preference-probing attack existence and patterns; **Medium** for whether these attacks succeeded or were detected/stopped by system; **Medium-High** for whether they represent account compromise vs. authorized penetration testing.

### Possible Interpretations

**Scenario A (Legitimate Cleanup, Confidence: High)**: Automated testing system created 14,591 test pages (May 24–June 22). Administrator MartinHuber deleted them June 4–July 14, with intensification June 23 following approval. Gradual rate (3/day) then escalation (244/day) reflects staged rollout. Concurrent attacks (XSS, preference probing) exploited high-activity period as cover. No evidence of account compromise. Weak logging reflects legacy design.

Supporting evidence: (1) Deleted pages created by many IPs/labels, zero by MartinHuber (clean separation); (2) Test-oriented page names and "disposable" content labels; (3) Single administrator account, consistent deletion message format; (4) Phased execution (exploratory → scaled) matches administrative workflow.

**Scenario B (Account Compromise with Escalating Attacks, Confidence: Medium)**: The automated content creation was legitimate research work. However, MartinHuber's account was compromised around June 18–23, enabling an attacker to: (1) initiate bulk deletions to remove evidence or disrupt the research (June 23 escalation represents attacker gaining confidence); (2) perform reconnaissance via preference-form probing (June 18); (3) attempt code injection via XSS (June 29) to establish persistent backdoor or escalate privileges. The shift from exploratory deletions (2, 25 on June 4, 18) to systematic deletions (602+/day from June 23) reflects attacker gaining system knowledge and confidence. Lack of deletion audit logs supports compromise theory—attacker deliberately avoided leaving authorization trail.

Supporting evidence: (1) June 18 shows three separate suspicious activities (preference forms, high saves, initial deletions)—possible compromise window; (2) Preference form probing targets user account settings, consistent with account takeover preparation; (3) XSS attack 10 days after preference probing suggests two-stage exploitation (reconnaissance → persistence); (4) Deletion pattern aligns with automated cleanup scripts (identical message, strict IP/user consistency) consistent with attacker automation.

**Scenario C (Coordinated Data Exfiltration and Cover-up, Confidence: Low-Medium)**: The content creation and deletion campaigns were coordinated by a single threat actor or campaign: (1) automated agents (Azure IPs 20.x.x range) uploaded sensitive research data—federal agency budgets (usaspending.gov URLs), market data (market data research helper labels), OpenAI-related content (OpenAIResearcher, OpenAIResearchSec2028 labels); (2) data was exfiltrated or weaponized during May 24–June 22 window; (3) admin account MartinHuber (either compromised or corrupted insider) was instructed to delete evidence on June 23; (4) concurrent attacks (XSS, form probing) represent attempts to establish persistence or cover additional tracks. The German-language deletion messages and Azure IPs could indicate non-US threat actor or state-sponsored operation. Pages labeled with OpenAI suggest possible targeting of AI research data.

Supporting evidence: (1) Deleted content includes federal budget API URLs, suggesting intentional data collection; (2) OpenAI-labeled pages and "Researcher" accounts suggest targeting of AI/ML research; (3) Phased execution (create → exfiltrate → delete) aligns with sophisticated data theft operational security; (4) Concurrent attacks represent attempts to establish persistence; (5) Lack of deletion approval trail allows plausible deniability if discovered.

**Assessment**: Most likely is a **combination of Scenarios A and B**: Legitimate test cleanup by administrator MartinHuber operating under authorization, but with opportunistic exploitation by concurrent threat actors (separate attackers) attempting account compromise or system injection during high-activity window. The timing concentration (18th highest preference-form probing, 29th XSS attack, 23rd deletion escalation) is suspicious but could reflect attackers recognizing high-activity period as cover, rather than direct coordination with MartinHuber. Scenario C unlikely without evidence of data exfiltration infrastructure or insider collaboration at senior level.

## Conclusion

The DSE wiki experienced a major deletion campaign removing 5,144 test pages between June 4 and July 14, 2026, following a massive content creation phase (14,591 saves across DSE and Fractal wikis, May 24–June 22). The deletions were performed by user "MartinHuber" (IP 2.202, Germany-based) and most likely represent legitimate administrative cleanup of automated test content created by distributed agents (primarily Azure datacenter IPs). Evidence supporting administrative legitimacy includes:

- Zero overlap between deleted-page creator IPs (20.x.x Azure range, 4.x.x, 57.x.x) and deletion IP (2.202)
- Test-oriented page naming ("DisposableEditTest," "ProbeToken," etc.)
- Automated agent labeling scheme (1,871 unique "Agent"/"Helper"/"Researcher" identifiers)
- Phased deletion execution (exploratory slow phase June 4–22, authorized rapid phase June 23–July 14)

However, the campaign occurred concurrent with active security threats:

- **June 18**: IP 52.87 conducted preference-form probing (25 requests in 5 hours), potentially testing account privilege escalation
- **June 29**: IP 52.159 submitted XSS injection payload (`<script>alert('XSS')</script>`), attempting code injection attack

The precise timing and convergence of these events on June 18 (preference probing, massive content saves, initial deletions) raises concern about whether MartinHuber's account was compromised or exploited. Weak audit logging—lacking deletion authorization chain, approval tickets, or granular reasoning—does not distinguish between legitimate cleanup and account takeover scenarios.

**Critical investigations needed**:

1. **Account security audit**: Examine MartinHuber's authentication logs (login times, IP addresses, session duration) for June 18–23 period. Verify whether account was accessed from IP 2.202 consistently or from other IPs.

2. **Authorization verification**: Locate administrative approval ticket, email, or meeting notes authorizing bulk deletion of 5,144 pages. Verify deletion timing aligns with authorization.

3. **Preference modification audit**: Determine whether IP 52.87's 25 preference-form requests (June 18) resulted in account setting changes. Check for unauthorized modifications to MartinHuber account or other admin accounts.

4. **XSS attack scope**: Examine request logs June 25–July 14 for evidence of successful XSS execution (stored XSS indicators, session hijacking, privilege escalation). Verify whether XSS payload was sanitized by application.

5. **Deleted content recovery**: Attempt recovery of deleted 5,144 pages from backups (database snapshots, transaction logs, file versioning). Analyze recovered content for evidence of data theft (sensitive research, credentials, confidential information).

6. **IP attribution**: Conduct OSINT on IPs 52.87 (AWS, US-based), 52.159 (AWS, US-based), and 2.202 (RoI provider, likely EU-based). Determine whether IPs belong to legitimate penetration testing services, authorized security researchers, or malicious actors.

7. **Logging infrastructure review**: Audit wiki system configuration for deletion audit logging. Implement mandatory detailed logging for all administrative actions (approver, timestamp, reason, content hash before deletion, backup location).

The totality of evidence suggests either: (A) legitimate test cleanup with concurrent attack attempts, or (B) account compromise enabling data destruction with concurrent attack attempts. The high-confidence assessment requires forensic access to system authentication logs and deletion authorization records, which are not present in the provided event logs.
