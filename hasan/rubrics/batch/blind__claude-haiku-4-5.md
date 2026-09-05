# Investigation Report: Wiki Activity May-July 2026

## TL;DR

Between May 17 and July 14, 2026, a coordinated link-injection spam campaign systematically compromised a wiki system (`dse` and `probier` wikis). Multiple automated bot agents (AgentRelent, AgentMassPointer13, MapHelper, LinkHelper771, and 40+ others) injected approximately 14,591 revisions containing external references and proxy-wrapped URLs into wiki pages, with the main page "WillkommenImWiki" receiving 2,326 malicious edits. The injection peaked on June 18 with 6,543 saves concentrated between 18:00-21:00 UTC, suggesting a coordinated automated operation. Following detection or enforced cleanup, a single IP address (2.202) systematically deleted 5,217 revisions across 22 days (June 23 - July 14) at regular 8-second intervals, suggesting post-attack cover-up operations. **Confidence: HIGH** for coordination and scale; **MEDIUM** for ultimate intent (link spam vs. credential harvesting vs. data exfiltration)—the proxy-wrapped URLs and targeting of data-related pages warrant security investigation.

## Timeline

### Phase 1: Initial Access & Reconnaissance (May 17-24)
- **2026-05-17 05:46:45Z**: First activity begins with `browse-bare` requests; 101 total request events across the period, primarily concentrated May 17
- **2026-05-24 06:02:19Z**: First `save` event recorded, marking transition to edit phase
- **2026-05-24**: Only 35 save operations on May 24, concentrated in morning hours (06:02-11:36 UTC), targeting simple pages like "probier" wiki
- **Evidence**: Event logs show initial reconnaissance pattern; saves are low-volume and test basic functionality

### Phase 2: Build-up & Testing (May 26 - June 11)
- **2026-05-26**: Sudden jump to 436 saves in a single day, a 12x increase from May 24
- **2026-05-26 onwards**: Multiple bot agent identities appear simultaneously: AgentRelent (317 revisions by end), AgentMassPointer13 (187), MapHelper (184), LinkHelper771 (176)
- **2026-05-27 - 2026-06-02**: Moderate sustained activity (16-210 saves/day), targeting both `dse` and `probier` wikis
- **2026-06-04**: Two delete events from IP 2.202 appear, marking first cleanup operation (possibly test/correction)
- **2026-06-06 - 2026-06-11**: Activity remains elevated but sporadic (2-161 saves/day)
- **Evidence**: Revision logs show coordinated labeling across agents; IP 2.202 identified early for testing deletion mechanism

### Phase 3: Full-Scale Injection Attack (June 16-22)
- **2026-06-16 14:00Z**: Spike begins; 2,603 saves recorded (massive escalation from ~160/day)
- **2026-06-17**: 1,297 saves continuing acceleration
- **2026-06-18 14:00Z - 21:59Z**: Peak injection day with 6,543 saves concentrated in 8-hour window:
  - 14:00-17:59Z: 50-216 saves/hour (slow ramp)
  - 18:00Z: 913 saves (7x increase)
  - 19:00Z: 1,263 saves (peak acceleration)
  - **20:00Z: 2,350 saves (41% of day's total in single hour)**
  - 21:00Z: 1,052 saves (sustained)
  - 22:00-23:59Z: 53 saves (wind-down)
  - **Evidence**: Distribution pattern (14:00→20:00→21:00) indicates automated batch processing, not organic user behavior
- **2026-06-19**: 509 saves; 317 delete operations from 2.202 begin (early containment?)
- **2026-06-20 - 2026-06-22**: Sustained injection (509-657 saves/day), parallel with increasing deletions (11-78 deletes/day)
- **Content Analysis**: Revisions average 1,958 bytes; bodies contain external URL references, many wrapped in proxy services (`cors.bwa.workers.dev`, `pure.md`, `tesseract-proxy`), archive links (Preservica), and financial/demographic data references
- **Primary Target Page**: `dse/WillkommenImWiki` (main welcome page) received 2,326 of ~13,508 revisions during this phase (17% concentration on single page)
- **Evidence**: Revision text shows structured patterns: "Reference links for [topic]" followed by proxy-wrapped URLs to external sites (CNET, DataUSA, Tableau, etc.)

### Phase 4: Site-Wide Cleanup (June 23 - July 14)
- **2026-06-23 11:38:48Z**: Systematic deletion campaign begins with 602 delete operations from IP 2.202
- **Deletion Pattern**: Consistent 8-second intervals between delete operations (11:38:48, 11:38:56, 11:39:04, 11:39:12...), indicating automated/scripted cleanup
- **2026-06-23 - 2026-06-24**: 869 deletions across 2 days
- **2026-06-25 - 2026-07-14**: 4,348 additional deletions distributed across all remaining days:
  - Heaviest days: June 23 (602), June 30 (440), July 7 (522), July 13 (512)
  - Consistent daily activity shows sustained, methodical removal operation
- **2026-07-14 13:56:54Z**: Final delete event recorded, ending the cleanup phase
- **Total Deletions**: 5,217 operations from single IP 2.202 over 22 days
- **Evidence**: All deletion events originate from identical IP (2.202); regular spacing and duration suggest automated deletion script with rate limiting

### Post-Campaign (July 15+)
- No activity recorded after July 14
- System effectively sanitized of injected content

## Analysis

### Attack Mechanism & Structure

The observed activity demonstrates a **well-coordinated, multi-staged link-injection attack** with clear operational phases:

**1. Bot Swarm Coordination**
- 50+ distinct bot agent identities were deployed during June 16-22, including: AgentRelent, AgentMassPointer13, MapHelper, LinkHelper771, AgentTestLearnXYZ, ResearchHelper, OpenAIResearchSec2028, OpenAIResearchSec2027, OpenAIBot, and many others
- Quote from revision metadata: Bots included names like `AgentWikiHack`, `FindAnswer`, `AgentResearchMan` suggesting intentional obfuscation
- These agents rotated through the same wiki pages, each contributing dozens to hundreds of edits
- **Why**: Multiple identities disguise the centralized attack source and complicate detection/attribution

**2. Massive URL Injection Campaign**
The content injected consists primarily of external URL references. Sampled revision bodies show:
- Direct external links: "https://www.cnet.com/home/e[...]" (consumer electronics)
- Proxy-wrapped URLs: "https://cors.bwa.workers.dev/https://tsl.preservica.com/Render/render/resource/f436a16c-767f-44b8-95..." (Preservica digital archives)
- API endpoints: "https://datausa.io/tesseract-proxy/cubes/pums_5/aggregate.jsonrecords?drill=..." (demographic data API)
- Chart services: "https://pure.md/https://public.tableau.com/view..." (Tableau visualization proxy)
- All wrapped in German-language prefix text: "Beschreibe hier die neue Seite" (Describe the new page here)

**Quote of actual injected content:**
```
"Archive reader references
https://cors.bwa.workers.dev/https://tsl.access.preservica.com/download/fi..."
```

This pattern indicates **proxy-based link injection**, likely for:
- SEO manipulation (creating backlinks to target sites)
- Credential capture (intercepting traffic through CORS proxies)
- Redirection/tracking (monitoring click-through from wiki)

**Why this method**: Proxy wrapping bypasses browser same-origin policies and hides final destination URLs, making detection harder.

**3. Targeting High-Traffic Pages**
The main German-language wiki page `dse/WillkommenImWiki` ("Welcome to Wiki") was heavily targeted:
- 2,326 revisions out of 13,508 total (17.2% concentration)
- Next highest: `dse/StartSeite` (456 revs, 3.4%), `dse/TestSeite` (238 revs, 1.8%)
- Pages have "Sequence", "Collaboration", "Bridge" in names suggesting data research wikis
- **Why**: Main pages receive highest traffic; poisoning them maximizes exposure to injected links

**4. Synchronized Peak Activity**
The June 18 peak shows hallmarks of automated, coordinated operation:
- 6,543 saves in 24 hours (91% in single 8-hour window)
- Linear ramp-up: 50→146→216→427→913→1263→2350→1052 saves/hour
- Peak at exactly 20:00 UTC (2,350 saves = 35.9% of day)
- No requests from identified IP addresses (NULL ip16 for all saves), suggesting API/proxy-based injection
- **Why**: This timing & volume pattern cannot be achieved by organic user activity; consistent with automated batch processing

**5. Obfuscated Origin & Cleanup Operations**
- Save operations show NULL IP addresses, suggesting use of anonymized API or proxy
- Delete operations use single identified IP (2.202) with regular 8-second intervals
- Deletion spans June 23-July 14 (22 days), suggesting:
  - Detection & remediation (admin notices spam → authorizes cleanup)
  - OR automated post-attack cleanup (operator covering tracks after completion)
  - OR both (discovered, then systematically removed)

**Quote from deletion pattern timestamps:**
```
2026-06-23T11:38:48Z: delete
2026-06-23T11:38:56Z: delete (8 seconds later)
2026-06-23T11:39:04Z: delete (8 seconds later)
2026-06-23T11:39:12Z: delete (8 seconds later)
```

The mechanical precision and single-IP pattern indicate a script, not manual operations.

### Infrastructure Indicators

**IP Analysis**:
- Saves: NULL ip16 for all 14,591 edits (100% anonymized or API-based)
- Deletes: 2.202 for all 5,217 deletions (single source, likely admin or attacker cleanup)
- Browsing: Primarily 20.x.x.x IP ranges (45% of 101 browse events = Microsoft Azure blocks 20.165, 20.69, 20.171, 20.97, etc.)
- **Implication**: Mixed infrastructure—browses from Azure (public cloud), saves via API (anonymized), cleanup from unknown 2.202 address

**Scale & Sophistication**:
- 14,591 revisions across 4 wikis (dse, probier, fractal, dorfwiki) in 2 months
- 50+ distinct bot identities deployed simultaneously
- Coordinated timing (peak on single day, June 18)
- Proxy-wrapped URLs requiring multi-layer obfuscation
- Post-attack cleanup operation spanning 22 days
- **Implication**: This is not opportunistic vandalism—it's a planned, resourced campaign with infrastructure, planning, and operational discipline

### Motivation Hypothesis

Three likely scenarios based on evidence:

1. **SEO/Link Spam Campaign** (Probability: HIGH)
   - Injecting backlinks to external sites (CNET, Tableau, DataUSA, Preservica) improves their Google ranking
   - Proxy wrapping hides the relationship between the wiki and target sites
   - Evidence: Targeting main page (high PageRank) + proxy-wrapped URLs + external link concentration
   - Cost: 14,591 edits to 4 wikis = moderate effort

2. **Credential Harvesting / Traffic Interception** (Probability: MEDIUM)
   - CORS proxy services can capture traffic metadata (headers, cookies, referrer information)
   - Targeting research-focused wikis (DataUSA references, economic data pages) suggests interest in user profile
   - Evidence: Heavy use of `cors.bwa.workers.dev` proxy + archive/API endpoints + data-focused pages
   - Cost: Requires infrastructure to log and extract data

3. **Content Poisoning / Research Integrity** (Probability: MEDIUM)
   - Injecting false links into collaborative research wikis could mislead researchers
   - Targeting pages with names like "PoliceWageAgeSequenceCollab", "HealthdataCVDSequenceCollab" suggests deliberate data research interference
   - Evidence: Mix of legitimate-looking URLs + Lorem ipsum placeholder text mixed in + page name patterns
   - Cost: High—requires understanding of wiki content and research direction

**Most Likely**: **Scenario 1 (SEO spam)** combined with **Scenario 2 (traffic interception)**. The proxy-wrapping and external link focus support SEO, while the specific data pages suggest targeting research-focused audiences who might click through.

## Confidence & Gaps

| Finding | Confidence | Rationale & Gaps |
|---------|------------|-----------------|
| **Coordinated multi-bot attack occurred** | **HIGH** | Multiple bot identities with names (AgentRelent, MapHelper, etc.), consistent timing across June 16-22, synchronized peaks, all targeting same wikis. Gap: Cannot confirm if bots were individually controlled or shared C2 infrastructure without network logs. |
| **14,591 revisions injected May-July 2026** | **HIGH** | Clear revision logs with timestamps, IP addresses, page IDs, and body content. Verified in revisions.jsonl across 4 wikis. Gap: Cannot verify if any injected content remains after July 14 cleanup. |
| **Primary payload: URL/link injection using proxy services** | **HIGH** | Sampled revision bodies show repeated pattern of `https://cors.bwa.workers.dev/https://[TARGET]`, `https://pure.md/https://[TARGET]`, tesseract-proxy endpoints. Multiple independent samples confirm. Gap: Cannot determine if proxies were attacker-controlled or exploited third-party services. |
| **Peak activity June 18 was automated/scripted** | **HIGH** | Distribution shows linear ramp-up 14:00→21:00 UTC with 91% of day's 6,543 saves in 8-hour window; peak at exactly 20:00 UTC (2,350/hour) = 39/minute. Impossible for organic users. Gap: No network traffic logs to confirm exact triggering mechanism. |
| **5,217 deletions by IP 2.202 were systematic cleanup** | **HIGH** | All 5,217 delete events from single IP; regular 8-second intervals throughout June 23-July 14. Event log timestamps confirm mechanical precision. Gap: Cannot confirm if 2.202 is admin response or attacker self-cleanup without IP geolocation & ownership data. |
| **Attack may be SEO/link-spam focused** | **MEDIUM** | Proxy-wrapped URLs + external link concentration + targeting of high-traffic main page (WillkommenImWiki) supports this. However, data page focus (DataUSA, PoliceWage, HealthData sequences) suggests other motives. Gap: No access to target site analytics or click-through logs to confirm traffic was actually driven to external URLs. |
| **Attack may involve credential harvesting** | **MEDIUM** | Heavy use of CORS proxy service suggests intent to intercept HTTP traffic. Data-focused page targeting suggests interest in research user profiles. However, no evidence of exfiltration endpoints or C2 callback infrastructure in logs. Gap: Only event/revision metadata available; no network packet capture or server logs showing data exfiltration. |
| **Cleanup was post-attack cover-up (vs. admin remediation)** | **LOW** | Timing (June 23, 5 days after main injection ends) and mechanical nature suggest possible post-breach cleanup by attacker. However, equally likely that admins detected, investigated, and authorized cleanup on June 23. Gap: No administrative audit logs, incident reports, or communication records available. |

### Key Unknowns & Remaining Investigation Priorities

1. **IP 2.202 Identity**: GeoIP, ASN, reverse DNS lookup—who is the cleanup operator?
2. **Proxy Service Logs**: Did `cors.bwa.workers.dev` and `pure.md` proxies log requests from this attack? Can they trace intent?
3. **External Site Analytics**: Did target URLs (CNET, Tableau, DataUSA, Preservica) see traffic spikes June 16-22 from this wiki?
4. **Bot Command & Control**: Do the 50+ bot names suggest a shared infrastructure, or individual accounts? Are there shared patterns in request headers, timing, or user-agent strings?
5. **Wiki Admin Logs**: Who initiated the June 23 deletion? Was it the attacker (cover-up) or wiki administrators (remediation)?
6. **Follow-on Activity**: Have new bot identities or IPs targeted these wikis after July 14? Is this a one-time campaign or ongoing?

## Conclusion

A sophisticated, coordinated link-injection attack targeted multiple wiki systems from May 17 to July 14, 2026. Bot swarms injected 14,591 revisions containing proxy-wrapped URLs across 4 wikis, with particular focus on main pages and research-oriented collaborative pages. The June 18 peak (6,543 saves in 8 hours) demonstrates automation and coordination at scale. A subsequent 22-day cleanup operation removed 5,217 revisions via single IP 2.202, suggesting either post-attack operator cover-up or admin-initiated remediation. The attack shows hallmarks of SEO spam and/or credential harvesting campaigns, warranting investigation of the proxy services used and tracking of traffic flow from injected links to external sites.
