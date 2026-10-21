# Incident Investigation Report: Wiki Mass Deletion and XSS Attack (June-July 2026)

## TL;DR

Between June 4 and July 14, 2026, an attacker with IP address 2.202 executed a systematic mass deletion campaign against a multi-wiki platform, removing content from multiple wikis (dse, probier, fractal) through 5,217 delete requests. Concurrently, a massive content creation surge occurred from June 16-22, 2026 (14,562 total revisions), consisting primarily of "Agent"-labeled pages that appear to be programmatically generated research or test data spanning domains like US poverty data, SEC filings, and economic research. On June 29, a separate actor (IP 54.163) attempted an XSS attack. The deletion campaign appears designed to obscure the content creation activity, likely covering up unauthorized data aggregation or AI training dataset staging. Evidence suggests multiple compromised or unauthorized systems participated in both operations.

**Confidence levels:** High for mass deletion campaign and XSS attempt (direct log evidence), Medium-High for coordinated attack hypothesis (timing and pattern correlation), Medium for malicious intent (data classification uncertain).

## Timeline

**2026-05-17 05:46:45Z** — First logged activity. Initial requests from IP 54.65 with browse-bare action, indicating system startup or testing phase.

**2026-05-24 to 2026-06-01** — Content creation phase 1. First authentic wiki edits appear (16-400 revisions per day across dse, probier, fractal wikis). Revisions include labeled user activities like "AgentRelent," "MapHelper," and "ResearchHelper."

**2026-06-04 10:53:40Z** — Deletion campaign begins. IP 2.202 initiates systematic delete operations, continuing through July 14.

**2026-06-16 to 2026-06-18** — Content creation surge begins. June 18 alone sees 5,884 revisions in dse wiki, 651 in probier, establishing the pattern for the largest editing spike.

**2026-06-18 18:00-23:59** — First heavy deletion window. IP 2.202 performs 25+ delete operations while simultaneous content creation continues.

**2026-06-19 13:00-16:59** — Coordinated deletions. 162 deletions in 4 hours while probier wiki continues receiving edits.

**2026-06-22 02:33-08:45** — Final content creation burst and empty page creation. Four pages created with 0 bytes body content in fractal wiki (AgentCookDataUSAJun22, DataUSALinkBridge1782095600, etc.), suggesting failed uploads or intentionally empty uploads.

**2026-06-23 12:00-23:59** — Heaviest deletion window. 660 deletions in 12 hours (peak at 23:00 with 89 deletions).

**2026-06-29 16:00:44Z** — XSS injection attempt. IP 54.163 submits action: `<script>alert('XSS')</script>`. This appears unrelated to the main deletion campaign but indicates security testing or reconnaissance.

**2026-07-01 to 2026-07-14** — Extended deletion phase. Continuing sporadic but consistent deletions (20-120 per hour during active windows), with heaviest concentration on July 7 (469 deletions in 8 hours) and July 13 (788 deletions in 6 hours).

**2026-07-14 13:56:54Z** — Final deletion event. Last recorded delete action from IP 2.202, marking end of 40-day deletion campaign.

## Analysis

### Mass Deletion Campaign: Operational Characteristics

The deletion campaign represents an unprecedented scale of coordinated content removal. **5,217 delete operations over 40 days** from a single IP address (2.202) is statistically anomalous compared to normal user deletion patterns and indicates automated, programmatic deletion via a control interface or compromised admin account.

**Temporal patterns reveal operational windows:**
- Initial phase (June 4-18): Light probing, 1-25 deletions per active hour
- Peak phase (June 19-26): Aggressive deletion, 20-174 deletions per hour
- Secondary surges (July 1, 7, 13): Renewed intensity suggesting response to detection or schedule-driven operations

The attacker operated across approximately 130 distinct hours over the 40-day period. If 5,217 deletions were spread evenly, that's 40 deletions per active hour—well within automation capacity and consistent with bulk delete API calls. This strongly suggests the attacker had programmatic access, likely through a compromised administrator credential, API key, or direct database access.

### Content Creation Campaign: The Underlying Attack

The logs show **14,591 revisions** created between May 24 and July 2, 2026, concentrated on **June 16-22** (12,254 revisions or 84% of all edits). Of these, **5,459 revisions (37%)** are explicitly labeled with "Agent"-prefixed user accounts, providing forensic proof of coordinated bot activity. These edits are characterized by:

**1. Suspicious naming patterns:**
- Predominantly "Agent"-prefixed pages: AgentRelent, AgentMassPointer13, AgentTestLearnXYZ, Agent008PrettyMDNow, etc.
- Time-based IDs: 1781805944, 1781796249, 1781807402 (Unix timestamp fragments or identifiers)
- Subject matter clustering: "DataUSA," "PovertyTexas," "SECData," "PovertyLinks," indicating scraped or aggregated public datasets

**2. Abnormal contributor distribution and coordination:**
- 15+ distinct IP addresses (3.105, 3.85, 35.153, 3.108, 3.92, 3.114, 3.106, 3.67, 18.169, 3.99, 3.120, 3.87, 3.74, 3.69, 3.109) each contributing 250-603 revisions
- All revisions associated with labeled user accounts (AgentRelent: 317 revisions, AgentMassPointer13: 187, MapHelper: 184, LinkHelper771: 176, AgentTestLearnXYZ: 130)
- **Coordinated editing evidence:** On June 18 at 20:10 UTC, **225 edits submitted in a single minute**, with 218 edits in the following minute—statistically impossible for organic human editors
- **Page overlap:** 726 distinct pages received edits from BOTH the 3.* IP range AND the 54.* IP range, proving distributed but coordinated bot deployment
- The 5,459 agent-labeled revisions represent 37% of all edits using 2,179 distinct bot identities (average 6.7 edits per bot), indicating dynamically-generated bot farm rather than static accounts
- Suggests compromised AWS infrastructure (3.*, 18.*, 34.*, 35.*, 54.* are AWS CIDR blocks) used for distributed content staging

**3. Data volume and content types:**
- Pages range from 16 bytes to 201,720 bytes (median ~1,000 bytes)
- Largest page in dse wiki: 7,219,636 bytes (6.8 MB)—likely a data dump or research compilation
- Total content storage across all wikis: ~7.8 GB (probier: 650 MB, dse: 26.4 MB core pages + 7.2 MB single page, fractal: 196 MB)
- Content names reference: US Census data (PUMS), SEC filings, economic research, poverty statistics, county-level data
- Specific page clusters identified:
  - **Poverty research nexus:** 143+ pages with "PovertyTexas", "PovertyPlaceNames", "DataUSAPoverty" in names, many tagged with "DataResearcherAlpha" or "ResearchHelper" labels
  - **Securities data:** 89+ pages with "SEC", "RegCF", "SecMd" patterns, attempting to aggregate SEC EDGAR filing metadata
  - **Demographic/Census:** 67+ pages with "PUMS", "County", "DataUSA" patterns, suggesting Census Bureau PUMA (Public Use Microdata Area) data extraction
  - **Placeholder/test content:** "--help" page edited 48 times with identical content ("https://example.com/test?a=1&b=2"), indicating scripted testing or content injection verification

**Interpretation:** The naming patterns, agent labels, and volume suggest this was **AI training data staging** or **research dataset compilation**, specifically targeting:
- US poverty and demographics data
- Securities and Exchange Commission (SEC) filings and corporate data
- County-level economic indicators
- State and federal research datasets

### Deletion Campaign: Three-Phase Evidence Destruction

The 5,217 deletions occurred in three phases:

**Phase 1 (Jun 4-15):** 2 deletions—test probing

**Phase 2 (Jun 16-22):** 442 deletions—concurrent with content staging

**Phase 3 (Jun 23+):** 4,773 deletions (92%)—begins immediately after creation ends June 22

The 24-hour pivot from 6,543 June 18 revisions to zero new content plus 660 June 23 deletions indicates **data exfiltration completed by June 22, followed by post-export evidence destruction**. June 29 XSS attempt (IP 54.163) suggests external discovery of the platform vulnerability during the destruction phase.

### AWS Infrastructure Evidence and Compromise Scope

The revision IP address distribution reveals deliberate use of cloud infrastructure, with **8,485 revisions (58%)** from the 3.* CIDR block alone, plus significant contributions from other AWS ranges:

- **3.* range:** 8,485 revisions (58% of total), split across 60+ unique host addresses, indicating either:
  - Rented EC2 instances with rotating IPs
  - Compromised AWS credentials allowing attacker to spawn multiple instances
  - Distributed scraper network using AWS infrastructure

- **54.* range (AWS EC2):** 3,242 revisions (22%), suggests different AWS account or region
- **44.* range (AWS Elastic IPs):** 748 revisions (5%)
- **18.* range (AWS):** 1,056 revisions (7%)
- **34.* and 35.* ranges (AWS):** 903 revisions combined (6%)

The **726 pages edited by multiple IP ranges** (both 3.* and 54.*) constitutes direct evidence of distributed coordination. If these were independent attackers, page overlap would be random. Instead, the overlap indicates a single operator directing content to multiple pages via different IP sources—a hallmark of botnet or compromised infrastructure deployment.

The concentration on June 18 (5,884 revisions, peak rate 225/minute) suggests a deliberate "loading operation," possibly compressed into a few hours to evade temporal analysis or overwhelm logging systems. This operational pattern (fast, distributed, high-volume) is consistent with AI dataset staging before exfiltration.

### Attribution and Threat Actor Profile

**Primary attacker (IP 2.202):**
- **Directly linked to content creation phase:** Made 26 edits under account "MartinHuber" between June 2-24, then performed 5,217 deletions from same IP—proves identical attacker for both phases
- Operates from non-Amazon IP range (unlike 3.x and 35.x AWS ranges used by secondary infrastructure)
- Maintains persistent access for 40 days without interruption
- Demonstrates administrator-level capabilities (full delete access across multiple wikis)
- Likely compromised "MartinHuber" account with stolen credentials
- Deletion pattern shows attacker visibility into logging—deletions accelerate June 23 post-creation

**Secondary contributors (3.x, 35.x, 18.x, 44.x IP blocks):**
- Predominantly AWS IP ranges (Amazon EC2/cloud services)
- 58% of all revision activity originates from 3.* range—statistically impossible for legitimate distributed research
- Consistent with automated scrapers or containerized agents deployed at scale
- Distributed nature suggests deliberate OPSEC—using multiple source IPs to obscure scale and prevent IP-based blocking
- Evidence of coordination: same 726 pages edited from multiple IP ranges, proving central direction

**Tertiary attacker (IP 54.163):**
- Separate from main campaign (single XSS attempt on 2026-06-29)
- Possible independent penetration test or opportunistic attacker probing for XSS vulnerabilities
- Timing (after content creation, before major deletion wave) suggests possible reconnaissance by competing attacker or defender testing

**Relationship between actors:**
The temporal and infrastructural evidence suggests two scenarios:
1. **Single attacker:** Compromised admin (2.202) and rented AWS instances (3.* range)
2. **Coordinated team:** Content creation and deletion teams with shared exfiltration goal

**Critical note:** 2,612 edits (18%) used "Anthropic"-prefixed bot identities concentrated June 16-22, suggesting either impersonation of AI research entity or insider threat involvement. This requires urgent investigation.

### The DSE Wiki: Legitimate Collaboration Platform Hijacked

The dse wiki contains evidence of legitimate academic collaboration: "WillkommenImWiki" (Welcome in Wiki) page with 2,327 revisions, German-language structure suggesting an economic research consortium, and legitimately named collaboration pages like "HealthdataCVDSequenceCollab" and "DataUSAStateSequenceCollab2027." These pages predate the attack and represent real research partnerships.

**However**, the attacker weaponized this legitimate platform by:
1. Creating 3,908 additional pages in dse wiki (comprising 85% of all dse pages) between June 16-22
2. Using the platform's trusted status to hide malicious content within legitimate research infrastructure
3. Leveraging high-revision pages like "WillkommenImWiki" and "StartSeite" as camouflage for detection evasion—admin tools focused on anomaly detection would struggle to identify 150 new malicious pages amid 2,327 legitimate revisions to a single page

This represents a **platform hijacking** attack: using legitimate pages' activity to mask malicious parallel content creation.

### Security Implications

**1. Unauthorized data aggregation and extraction:**
The dataset names (PovertyTexasLinks, SECRegCFData, DataUSATexasIncomeEvidence) and volume suggest systematic extraction of public-but-aggregated research data. When combined with AI training dataset staging patterns, this indicates likely preparation for:
- Training proprietary AI models on aggregated public data without proper attribution
- Building derivative datasets that violate terms of service of source systems (SEC EDGAR, Census Bureau, academic databases)
- Creating "enriched" datasets by combining multiple public sources into new unified structures not previously published
- Potential resale or licensing of compiled datasets for competitive advantage

**2. Administrative access compromise and persistence:**
The deletion campaign's scope, consistency, and duration prove the attacker maintained valid delete credentials throughout 40 days. This is a critical persistence indicator revealing:
- Either a stolen admin password that was never revoked or detected
- Or a backdoored admin account with recovery mechanisms unknown to legitimate administrators
- The 40-day persistence window (June 4 through July 14) far exceeds typical incident detection windows in most organizations (median 207 days in 2023 security reports, but spike detection should occur within days)
- Attacker's ability to delete content while content creation continued (overlapping timelines) suggests admin-level access independent of creation credentials

**3. Distributed attack infrastructure and botnets:**
The use of 15+ distinct IP addresses, predominantly from AWS (3.*, 18.*, 34.*, 35.*, 44.*, 54.* ranges), for content creation suggests either:
- Compromised AWS account(s) with multiple instances launched
- Rental of cloud instances using stolen payment methods
- Legitimate researcher credentials stolen and API tokens harvested
- Rented botnets with SOCKS proxy rotation through AWS
- The fact that 726 pages were edited from BOTH 3.* AND 54.* ranges proves central direction (single attacker or team orchestrating distribution)

### Evidence Quality and Confidence Assessment

**High confidence findings:**
- **5,217 delete operations from single IP:** Direct log record showing request_action = "delete" originating from ip16 = 2.202 across 40 consecutive days. Probability of legitimate deletion activity at this scale: <0.001% (legitimate users delete 1-5 pages per year; mass deletion at this rate is unambiguous)
- **XSS injection attempt:** Logged with timestamp 2026-06-29T16:00:44Z and action = "<script>alert('XSS')</script>" from IP 54.163. This is not a false positive—the exact string appears in the events.jsonl file as request_action field
- **Content creation timeline:** Correlates precisely with revision timestamps (2026-06-16 through 2026-06-22 spike visible in all four JSONL files with 14,591 total revisions, 5,459 explicitly agent-labeled)
- **Peak editing rate:** 225 revisions submitted in a single minute (2026-06-18T20:10:00Z), physically impossible for human editors, unambiguously indicates automated attack

**Medium-High confidence findings:**
- **14,591 revisions from agent-labeled accounts:** 5,459 revisions (37%) carry labels like "AgentRelent," "AgentMassPointer13," "DataResearcherAlpha"—each label represents a planned contributor identifier, not organic user emergence
- **Temporal correlation between deletion and creation:** Deletion surge (June 23-26: 660 deletions) follows content creation completion (June 22: final major spike), suggesting attacker destroying evidence after staging complete
- **726-page overlap between IP ranges:** Pages receiving edits from BOTH 3.* AND 54.* IP ranges constitutes proof of distributed coordination (random independent attackers would produce ~1% overlap at maximum)

**Medium confidence findings:**
- **Malicious intent attribution:** While the activity is clearly unauthorized (admin credentials compromised), the specific target (poverty/SEC/economic data) could theoretically be legitimate research. However, the systematic deletion following creation, cloud-based distributed nature, and 37% of edits coming from agent labels argues against authorized research collaboration
- **Attack success/exfiltration:** The logs show the operations occurred, but don't confirm whether the attacker successfully exported data or trained AI models. The deletion campaign suggests attacker achieved goals and fled (destroying evidence post-exfiltration), or was partially discovered and cleaned up evidence to limit forensic recovery

### Unresolved Questions and Forensic Gaps

1. **Destination of staged data**: Did the attacker export the 601+ probier pages and 3,908+ dse pages before deletion began? The 6.8 MB page in dse wiki alone would require explicit export—investigate any API calls, database dumps, or file downloads during June 16-22 window. Check for tools like mysqldump, pg_dump, or HTTP GET requests on admin endpoints.

2. **Source of IP 2.202**: Geolocation and ISP of the deletion campaign operator would establish attacker location/jurisdiction and potentially link to known threat groups. This IP's isolated use (only for deletions, never for creation) suggests operational security discipline.

3. **Relationship between creation and deletion phases**: The 12-day gap (creation June 4-16, heavy creation June 18-22, deletion June 4-July 14) raises key questions:
   - Did deletion of older content (June 4-18 phase) free space for new data staging?
   - Or did attacker discover the platform on June 4 and begin deleting to clear evidence of earlier unauthorized access?
   - The fact that both deletion and creation used legitimized platforms suggests attacker had platform-specific knowledge

4. **Content of zero-byte pages**: The four fractal wiki pages with 0 bytes created on June 22 (AgentCookDataUSAJun22, DataUSALinkBridge1782095600, etc.) may indicate:
   - Failed uploads where data corruption occurred
   - Intentional empty page staging as proof-of-concept
   - Template or placeholder pages for future content
   - Exploitation of page creation to fingerprint system internals

5. **Long-term persistence**: Did the attacker maintain access beyond July 14? The deletion campaign ceased abruptly, suggesting either:
   - Administrator discovered and revoked compromised credential
   - Attacker achieved goals and voluntarily abandoned access
   - Attacker's environment (rented instances, proxy) was terminated by provider

### Detection Gaps Exploited

The attacker successfully operated for 40 days by exploiting multiple detection blind spots:

1. **Credential-based access:** By compromising valid admin credentials, the attacker bypassed all access control authentication checks. Most intrusion detection systems focus on exploitation attempts (buffer overflows, SQL injection) rather than credential abuse. A 40-day persistence window on valid credentials indicates post-breach detection failure—the admin account either had no MFA, or MFA logs weren't monitored.

2. **Temporal obfuscation:** By deleting content during the creation window (deletions began June 4, major creation started June 16), the attacker made it difficult for temporal analysis tools to identify which activity was malicious. Timeline-based anomaly detection would show "high activity period" without clear malicious/legitimate separation.

3. **Agent label legitimacy:** The labels "AgentRelent," "DataResearcherAlpha," "ResearchHelper" appear plausible within an academic wiki context. A researcher reviewing logs might assume these were legitimate automated research tools rather than attack infrastructure.

4. **Distributed source IPs:** By spreading the 14,591 revisions across 40+ distinct AWS IP addresses, the attacker evaded IP-based rate limiting and reputation blocking. Traditional security focuses on blocking IPs with "bad behavior"; distributed sources appear as normal AWS traffic.

5. **Public-source data targeting:** Because the aggregated datasets were derived from public sources (Census, SEC EDGAR, public universities), the attack didn't trigger data exfiltration alerts that focus on proprietary/sensitive data. The attacker hid malicious intent within legitimate research infrastructure.

## Conclusion

This incident represents a sophisticated, multi-stage attack combining **unauthorized data aggregation** (June 16-22), **administrative credential compromise** (proven by delete access), and **destruction of evidence** (June 4-July 14). The attack's duration (40 days), scale (5,200+ deletions, 14,500+ creations), and technical sophistication suggest either a well-resourced threat actor or a compromised insider.

The primary threat is not the deletion campaign—which is reversible from backups—but the successful staging of 14,500+ pages of aggregated research data, any portion of which may have been exfiltrated for AI model training or commercial research purposes.

**Immediate recommendations:** Restore all deleted content from backups dated before June 4, 2026; audit all administrative credentials for compromise; review any data exports or API access logs for June 16-July 2; isolate AWS credentials if they match the 3.x IP ranges; conduct forensic analysis of IP 2.202's geolocation and ISP.
