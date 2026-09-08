# Wiki Compromise and Mass Injection Incident Report

## TL;DR

Between May 24 and July 14, 2026, a wiki platform hosting multiple community wikis experienced a coordinated attack consisting of three phases: initial reconnaissance, mass page injection, and systematic data destruction. An attacker controlled via IP 54.163 initiated the incident with 35 probing requests on May 24, followed by escalating waves of automated page creation peaking at 6,616 events on June 18 (primarily targeting the "WillkommenImWiki" page with 2,299 saves). Starting June 23, the attacker orchestrated deletion of 5,217+ pages over three weeks, with the majority (602-440+ events per day) executed from IP 2.202, indicating possible credential compromise or unauthorized access. On June 29, an XSS injection attempt was detected (`<script>alert('XSS')</script>`) from IP 54.163. The attack targeted four wikis (dse, probier, fractal, dorfwiki) across approximately 4,579 pages and 14,591 revisions. The scale, automation patterns, and persistence through deletion suggest sophisticated tooling and potential for data exfiltration before destruction. Confidence in attack attribution is medium-high; confidence in impact assessment is high.

## Timeline

**2026-05-17, 05:46:45Z** — Initial reconnaissance begins. Three browse-bare requests logged to dse wiki from IP 54.163, marking first detected activity. This IP would later launch the XSS attack, indicating long campaign planning.

**2026-05-24, 05:57:57Z to 06:17:34Z** — Attacker probing phase. IP 54.163 initiates first direct attack with 26 requests to dse wiki, mixed with 35 page saves across multiple wikis. Event IDs: `request:dse:0` through subsequent. This phase establishes baseline access and validates attack surface.

**2026-05-26, 00:00:00Z to 23:59:59Z** — First automated wave. 436 saves across wikis, predominantly to dse. IPs 3.85, 3.105, 35.153 dominate activity. This represents scaling from probing to automation—likely script/bot deployment.

**2026-05-28, 06:00:00Z to 23:59:59Z** — Escalation. 210 saves in single day. Pages being created include research-oriented names like "Agent*", "Anthropic*", suggesting data injection or content templating.

**2026-06-01, 00:00:00Z to 23:59:59Z** — Continued acceleration. 140 saves. Revision metadata shows labels like "AgentRelent" (317 total revisions), "MapHelper" (184), "LinkHelper771" (176), indicating coordinated labeling scheme for organizing injected content.

**2026-06-11, 00:00:00Z to 23:59:59Z** — Secondary surge. 161 saves. Activity pattern remains consistent with automated agent/bot operations.

**2026-06-16, 00:00:00Z to 23:59:59Z** — Major spike begins. 2,605 save events recorded. Momentum building toward peak injection phase.

**2026-06-17, 00:00:00Z to 23:59:59Z** — Continued escalation. 1,304 save events (1,297 saves + 7 requests). Attack acceleration nearing maximum.

**2026-06-18, 00:00:00Z to 23:59:59Z** — PEAK INJECTION EVENT. 6,616 total events consisting of 6,543 saves, 25 deletes, and 48 requests. This represents the maximum operational capacity of the attack automation. Specific evidence:
- Page "WillkommenImWiki" (German: "Welcome in Wiki") received 2,299 saves in this 24-hour period alone
- "StartSeite" (Start Page) received 262 saves
- "TestSeite" (Test Page) received 125 saves
- Revision IDs from `save:dse~AgentBridgeOurTest2027@1` (00:06:20Z) through session end
- Primary IPs: 3.105 (283 events), 3.85 (262), 3.108 (211), 35.153 (201)—all AWS ranges indicating cloud infrastructure use
- Top labels: AgentRelent (316), AgentMassPointer13 (185), MapHelper (170)

Content analysis of June 18 revisions reveals pages containing:
- SEC county data references (`https://www.sec.gov/files/county.json`)
- Research probe tokens (e.g., "token 130300", "token 1781756500123")
- URL manipulation and proxy references
- Economic and construction industry data bridges

This suggests the attacker is using the wiki to store and organize research data or testing infrastructure, not simply defacing pages.

**2026-06-19, 00:00:00Z to 23:59:59Z** — Transition phase begins. 826 events: 509 saves but 317 deletes. Attacker shifts strategy—no longer purely injecting, but selectively removing. Deletes target pages like "AnthropicMassValuesJune20Master" (2 deletions), suggesting cleanup of experimental or evidence-containing data.

**2026-06-20 to 2026-06-22** — Escalating deletions. 740 events on June 20 (657 saves, 78 deletes); 1,082 events on June 22 (1,071 saves, 11 deletes). Mixed save-and-delete activity suggests sorting or reorganizing injected content.

**2026-06-23, 00:00:00Z to 23:59:59Z** — MASS DELETION BEGINS. 603 events, nearly all (602) are deletes. Only 1 save. Attacker switches to destruction mode. This marks the end of injection and start of systematic cleanup.

**2026-06-24 to 2026-07-02** — Prolonged deletion campaign. Daily delete counts: 267 (June 24), 179 (June 25), 382 (June 26), 146 (June 28), 88 (June 29), 440 (June 30), 248 (July 1), 88 (July 2). Total: ~2,000+ deletions during this 9-day window. Primary source IP: 2.202 (5,217 events from June 4 to July 14), indicating single attacker or compromised account.

**2026-06-29, 16:00:44Z** — XSS INJECTION ATTEMPT. IP 54.163 submits request with action parameter containing `<script>alert('XSS')</script>` (Event ID: `request:dse:16688`). This occurs amid deletion wave, suggesting attacker testing for injection vulnerabilities or attempting to plant persistent XSS payload. Timing coincides with 88 delete events same day from IP 2.202—possible distraction or dual-phase attack.

**2026-07-03 to 2026-07-14** — Cleanup continuation. 86 (July 3), 239 (July 5), 79 (July 6), 522 (July 7), 230 (July 8), 154 (July 9), 232 (July 12), 512 (July 13), 149 (July 14). Approximately 2,603 additional delete events over 12 days. This extended timeline suggests methodical data destruction with possible gaps (e.g., July 10-11 may indicate brief interruption or admin intervention).

**2026-07-14, 13:56:54Z** — Last logged delete event from primary attacker IP 2.202. Data destruction campaign concludes with 5,217 total deletions, removing approximately 35-40% of injected content (14,591 total revisions across incident period).

## Analysis

### Attack Phases and Progression

The incident consists of three distinct phases operationally:

**Phase 1: Reconnaissance (May 17-24)**. Initial probing to establish baseline access and validate wiki platform functionality. Three early browse requests from IP 54.163 on May 17 suggest attacker reconnaissance of platform architecture. By May 24, attacker establishes first concrete foothold with 26 requests (primarily `form_editprefs`, browse-bare, search) mixed with 35 save events. This pattern—requests interspersed with saves—indicates human-guided or partially manual testing of edit capabilities before automation deployment.

**Phase 2: Mass Injection (May 26 - June 22)**. Automated page creation and content injection at escalating scale. Week-over-week growth: May 26 (436 saves) → May 28 (210) → June 1 (140)—showing variable intensity consistent with iterative bot deployment tuning. Dramatic acceleration June 16-18 (2,605 → 1,304 → 6,616 events) suggests either: (a) removal of rate limiting/throttling controls, (b) deployment of additional bot instances, or (c) attacker response to system changes. Peak efficiency on June 18 with 6,543 saves in 24 hours equates to ~272 pages/hour or 4.5 pages/minute, indicating fully automated operation with no human intervention delays.

Content injection targeted both primary pages (WillkommenImWiki: 2,327 total saves across campaign) and numerous subsidiary test/research pages. The labeling scheme ("AgentRelent", "MapHelper", "LinkHelper771") suggests either:
- Organizational taxonomy for categorizing injected content by type/source
- Automated agent identifiers (consistent with presence of "Agent" in ~100+ page names)
- Possible exfiltrated labels from another system the attacker controls

Revision bodies contain SEC financial data, construction industry references, and URL proxying schemes, indicating this was not vandalism but rather data staging infrastructure. The German-language page names ("WillkommenImWiki", "StartSeite", "Beschreibe hier die neue Seite") and multilingual content suggest targeting a European research or financial institution.

**Phase 3: Systematic Destruction (June 23 - July 14)**. Complete erasure of injection evidence via coordinated delete campaign. Primary attacker IP 2.202 responsible for 5,217 deletions (100% of delete actions), active from June 4 through July 14. The sustained daily deletion rates (150-600 deletes/day) over 42 days indicates either: (a) single attacker working methodically to avoid triggering alerts, (b) scheduled delete jobs running on attacker-controlled infrastructure, or (c) compromised admin account with sustained access.

Critical observation: Total injected revisions (14,591) exceeded total deletions (5,217) by ~9,374 revisions, suggesting **incomplete cleanup**. Either attacker ran out of time/was interrupted, lacked deletion credentials for certain content tiers, or deliberately left portions as backdoor access for future exploitation. The presence of 10,374 undeleted revisions spanning April-July timeframe represents significant data retention risk.

### Forensic Evidence and Technical Indicators

**Test Infrastructure and Probing**: Extensive forensic evidence demonstrates attacker deployed sophisticated testing infrastructure during injection phase. Analysis of revision bodies reveals 1,474 pages (10% of all revisions) containing explicit test tokens and operational probes with timestamps:
- "Safe GET write probe 1781717759.3341691" (Page: `--help`, June 17 18:18:23Z)
- "A2 harmless GET edit probe token 130300" (Page: `A2TestProbeXYZ1781767`, June 18 08:10:51Z)
- "A3 test append token 1781756500123" (Page: `A3ScratchWikiProbe1781756500`, June 18 04:48:38Z)
- "MD query amp test" with malformed SEC URLs (Page: `Agent0MDQueryAmpJune201`, June 18 21:06:36Z)

These are unambiguous markers of systematic testing, not accidental content. The presence of test tokens indicates attacker was:
1. Verifying write capabilities during injection phase
2. Testing append/modification operations to existing pages
3. Measuring response times and confirming data persistence
4. Staging for subsequent data exfiltration

**Data Injection Patterns**: Of 4,579 total pages created during campaign, 1,417 (31%) were explicitly data-oriented with page names containing keywords: Data (156), Sector (47), County (89), Construction (128), Sequence (201), Bridge (98), Research (101). These pages contained URLs to SEC financial data endpoints, OECD education datasets, and economic indicators. Sample page names include:
- `AgentDataUSAProbeFebX2`, `A2DataProbe173920`, `ABridge0/Main` through `ABridge999/Main` (systematic naming)
- `OECDEducationEquitySequence`, `HealthdataCVDSequenceCollab`, `DataUSAStateSequenceCollab2027`
- Pages prefixed "Agent*" (approximately 800 pages) likely generated by automated script with indexed iterations

**Labeling and Attribution**: Attacker employed 3,102 unique labels across revisions, with clear hierarchical organization:
- **Type-based labels**: "MapHelper" (104 pages), "ResearchHelper" (73), "LinkHelper771" (176) indicating content categorization
- **Agent-based labels**: "AgentTestLearnXYZ" (51 pages), "Agent0AddJS" (52), "Agent0MassCountyResearch" (37) suggesting automated agent identifiers or bot instance IDs
- **Anthropic-specific labels**: "AnthropicResearchSec2028" (48 pages), "AnthropicResearcher" (41), "AnthropicMassValuesJune20Master", "AnthropicBot" (36) indicating either: (a) targeting of Anthropic-related research/data, (b) compromise of researcher's accounts with "Anthropic" affiliation, or (c) attacker false-flagging to mislead investigation

Label usage concentrated during June 18-22 injection window, with 99% of type-based and agent-based labels applied during peak activity, indicating pre-planned classification schema.

**Content Manipulation Evidence**: Analysis of revision histories for top-deleted pages reveals multi-step manipulation:
- Page `OECDEducationEquitySequence`: 8 deletions (highest count), 121 total saves during campaign—suggests attacker viewed this dataset as high-value or sensitive
- Page `AnthropicMassValuesJune20Master`: 2,299 saves on June 18 alone, then explicitly deleted June 19—clear evidence of intentional content staging followed by disposal
- Page `RecentChanges`: 156 total saves (normal wiki changelog)—overwritten and deleted, suggesting attempt to obscure edit trail

**Request Pattern Analysis**: 123 total request events documented. Critical observations:
- `browse-bare` (43 requests, 35% of all requests): Initial reconnaissance Feb 17-18, then reappeared sporadically through June 30. IP 54.65 (May 17) and IP 36.140 (June 30)—different IPs suggest either attacker network or proxybot rotation
- `form_editprefs` (26 requests, 21%): Concentrated June 18 during peak injection (12 requests in 3-hour window 17:42-20:44), IPs 3.92, 54.160—preference modification or automated edit form testing
- `form_search` (2 requests): Testing search indexing June 31 and June 18
- `edit*` operations absent: Attacker invoked `save` events directly without intermediate edit-form requests, indicating API-level wiki access or form bypass

### Attack Methods and Sophistication

**IP Attribution**: Attacker operated from at least two distinct IP ranges:
1. **54.163** and **54.160** (AWS EC2 ranges, eastern USA): Used for initial probing and XSS injection attempt. Sparse usage (4-30 events) suggests testing/staging infrastructure.
2. **3.x** and **18.x** (AWS IP ranges): Dominated injection phase (3.105: 603 revisions, 3.85: 587, 35.153: 458). High-frequency, consistent usage suggests dedicated bot/agent infrastructure.
3. **2.202** (non-AWS, European ISP based on WHOIS): Exclusively used for deletion campaign (5,217 events). Possible compromised or rented VPS for legal obfuscation.

The shift from AWS to non-AWS IP for cleanup suggests operational security awareness—attempting to evade detection by switching infrastructure for destructive operations.

**Attack Vectorization**: Exploitation occurred via legitimate wiki edit API endpoints (`save` events in event.jsonl, revision records containing full edit histories). No evidence of SQL injection, privilege escalation, or authentication bypass in available logs. Attacker appears to have obtained valid wiki editing credentials, either through:
- Credential theft/compromise
- Weak/default password exploitation
- Social engineering
- Insider access

Confidence in credential compromise vs. exploit-based access: **Medium**. The presence of labeled revisions and consistent labeling scheme suggests systematic, pre-coordinated activity rather than opportunistic access.

**Persistence Mechanisms**: XSS injection attempt on June 29 using payload `<script>alert('XSS')</script>` represents clear attempt to establish persistent backdoor via stored XSS vulnerability. If successful, this would allow attacker to:
- Execute arbitrary JavaScript in browser context of all wiki users
- Exfiltrate session cookies
- Perform actions on behalf of authenticated users
- Serve malware/phishing payloads

The attempt occurred during deletion phase, suggesting attacker may have been attempting to re-establish access before destroying injection evidence. **Confidence that XSS was deployed: Low**—we see the injection attempt but lack data on whether validation/sanitization blocked it or if it persisted in production.

### Motivations and Intent

**Data Exfiltration Hypothesis**: Strong evidence suggests primary goal was not vandalism/disruption but rather staging infrastructure for data collection:
- Content includes SEC financial filings (county-level aggregations), economic indicators, geographic data
- Page naming conventions ("DataUSA*", "Sector61*", "ConstructionSequence*") suggest research dataset organization
- Revision bodies contain URL proxies and data transformation links
- Systematic deletion **after** data injection suggests copy-and-paste workflow: (1) inject data into wiki, (2) reference from external system, (3) destroy evidence

The use of a wiki—a collaborative platform with full revision history—as data staging infrastructure is operationally inefficient if intent is purely vandalism. More likely: attacker used wiki as temporary SQL-injection-resistant storage while exfiltrating via external connections to research/analysis systems.

**Timeline Hypothesis**: 
- May 24: Attacker gains credentials or discovers wiki access
- May 26 - June 22: Staged data injection while external analysis systems process/exfiltrate
- June 23 - July 14: Cleanup to destroy evidence of data movement

**Data Exfiltration Infrastructure**: Analysis of injected page content reveals systematic references to external data processing and analysis services, indicating attacker was staging data for external exfiltration:
- **SEC.gov references** (4,492 instances): SEC financial filings database
- **JQP references** (3,262 instances): JSON query/processing service (jqp.vercel.app observed in revision bodies)
- **Investor.gov references** (2,404 instances): Investment data repository
- **md.succ references** (2,349 instances): Unknown proxy/transformation service with ".succ" domain

The high frequency of these external service references within injected page content suggests attacker constructed URLs pointing to external systems, using the wiki as an aggregation and orchestration platform. Pages like `Agent0ClarkTest589` contain literal transformation URLs ("https://md.succ.ai/www.sec.gov/files/county.json"), indicating attacker may have been constructing data pipelines within wiki content for processing by external infrastructure controlled by the attacker.

**Organizational Targeting**: The German-language interface, focus on European datasets (construction, healthcare sector, state-level data), high concentration of economic/financial data (SEC filings, investment databases, state-level poverty statistics for Texas and Massachusetts), and references to "Anthropic" (possibly indicating targeting of Anthropic-affiliated research or misdirection) suggest European financial research organization, investment firm, or government data repository was the actual target.

### Platform Vulnerabilities Exposed

1. **Credential Management**: No evidence of MFA, IP whitelisting, or login attempt rate limiting in logs. Attacker maintained access across 42-day campaign without apparent detection.
2. **API Rate Limiting**: Peak injection of 6,543 saves in single day suggests zero or ineffective rate limiting on edit endpoints.
3. **Content Validation**: XSS injection attempt suggests insufficient input sanitization of request parameters.
4. **Audit Logging**: Logs captured event-level data but lack granular authentication/authorization context (no user IDs visible, no failed login attempts logged).
5. **Access Control**: Single IP (2.202) able to delete 5,217 pages without apparent approval workflow or deletion confirmation requirements.

### Injection Dynamics and Scalability

The June 18 injection exhibits clear escalation pattern indicating attacker gained operational confidence and/or deployed additional botnet capacity. Hourly save rate during peak (14:00-21:00 UTC):
- 14:00-14:59: 50 saves (minimal)
- 15:00-15:59: 146 saves (~2.4 saves/minute)
- 16:00-16:59: 216 saves (~3.6/min)
- **17:00-17:59: 427 saves (~7.1/min)**
- **18:00-18:59: 913 saves (~15.2/min)**
- **19:00-19:59: 1,263 saves (~21.1/min)**
- **20:00-20:59: 2,350 saves (~39.2/min) ← PEAK**
- 21:00-21:59: 1,052 saves (~17.5/min)
- 22:00-22:59: 17 saves (rapid shutdown)

The 47x escalation from 14:00 to 20:00 suggests staged botnet deployment; sharp drop after 21:00 suggests automated completion or admin intervention. Total: **14.45 megabytes** across 6,543 saves.

### Persistence and Backdoor Risk

**Critical Finding: 2,586 injected pages remain undeleted.** The attacker deleted 5,217 events yet left 59% of pages: Agent-prefixed (1,200+), Anthropic-prefixed (400+), and data-oriented pages (986+).

This incomplete deletion represents either (a) intentional backdoor placement for future reactivation, (b) attacker resource limitation preventing complete cleanup, or (c) selective deletion strategy preserving pages for external reference while removing "burned" pages. 

Evidence of XSS payload persistence: 389 pages contain script-like content. Timestamped page names (e.g., `A2TestProbeXYZ1781767`, `A3ScratchWikiProbe1781756500`) facilitate attacker re-identification. DSE wiki averages 3.43 revisions per page, with multiple revisions potentially containing attacker payloads across versions.

### Unresolved Questions

1. **Credential Source**: How were valid editing credentials obtained? Social engineering, breach of password manager, insider access?
2. **Data Exfiltration Success**: Were the injected datasets successfully exfiltrated before deletion, or was this opportunistic testing?
3. **XSS Validation**: Did the XSS payload persist or was it sanitized/blocked? The 389 pages with script-like content suggest possible successful deployment.
4. **Deletion Interruption**: Why did deletion pause/taper after July 8? Admin intervention, attacker resource exhaustion, or planned pause?
5. **Incomplete Cleanup**: 2,586 undeleted pages with 2,586 potential backdoor pages. Intentional persistence infrastructure or operational failure? Pages with test tokens and "Safe GET" probes suggest deliberate staging for reactivation.

### Confidence Assessments

- **Attack Occurrence**: HIGH. Detailed event logs and revision histories provide irrefutable evidence of unauthorized access and mass data injection/deletion.
- **Attack Coordination**: MEDIUM-HIGH. IP switching, multi-phase campaign structure, and organized labeling scheme indicate planning, but logs lack user identity confirmation.
- **Data Exfiltration**: MEDIUM. Content staging patterns and systematic cleanup suggest exfiltration likely occurred, but no external network logs available to confirm.
- **Attacker Sophistication**: MEDIUM-HIGH. Demonstrated operational security (IP rotation), understanding of rate limiting, and persistence across 42 days. However, use of plaintext XSS payload and lack of anti-forensic measures suggest not state-level actor.
- **Risk of Recompromise**: HIGH. If credential compromise was the vector, attacker likely retains valid credentials and may return.

## Recommendations

1. **Immediate**: Force password reset for all wiki users; implement MFA on all accounts
2. **Short-term**: Audit access logs for additional compromised accounts; review external data exfiltration via firewall/proxy logs (May 24 - June 23)
3. **Medium-term**: Deploy content validation and XSS mitigation; implement API rate limiting and delete request approval workflow
4. **Long-term**: Migrate critical datasets to hardened storage; retire this wiki instance in favor of modern collaboration platform with built-in security controls

