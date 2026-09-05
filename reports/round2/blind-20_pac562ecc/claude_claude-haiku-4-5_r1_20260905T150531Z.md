# Incident Analysis: May-July 2026 Wiki Activity

## TL;DR

Between June 16-22, 2026, ~14,725 wiki pages were created via coordinated burst, peaking at 6,543 revisions on June 18. Content was 66% legitimate economic research (poverty/PUMS/SEC data), 15% spam (example.com links), 7% test pages. Activity distributed across hundreds of agent accounts (Agent0AddJS, OpenAIResearcher, etc.) with peak coordination 18:00-20:00 UTC (300+ agents/hour). Within 24-48 hours, admin IP 2.202 systematically deleted all content through July 14 (4,773 total deletes). The coordinated automation pattern and rapid cleanup suggest controlled testing/experimentation, though unauthorized intrusion cannot be ruled out. Confidence: **High** activity was coordinated/automated; **Medium** on root cause (authorized test vs. intrusion).

## Timeline

**May 17 - June 1:** Normal baseline activity. May shows ~917 events (mostly browsing), primarily from IP 135.136. June 1 jump to 140 revisions indicates start of new activity phase.

**June 1-15:** Gradual escalation. Revisions increase from 140 (June 1) to 12 (June 6-8) range. Agent-based page creation appears to begin. Labels show mix of human-like names and agents (WikiAgentMN, EconomicsSourceMetaAgent).

**June 16-17:** Acceleration phase. June 16: 2,603 revisions; June 17: 1,297 revisions. Creation focused on research content with names like "AgentProbeAssistantX2027", "OpenAIResearcher". Content includes DataUSA API links, economic data references.

**June 18 (PEAK):** 6,543 revisions created in single day. Peak coordination between 18:00-21:00 UTC with 300+ distinct agents active per hour at peak. From event logs: "unknown:6543" action type dominates. Agents include OpenAIResearcher, AgentRelent, AgentMassPointer13, MapHelper, LinkHelper771 creating majority of content. Content mix: 66% legitimate research (DataUSA poverty/PUMS data), 7% test pages, 15% spam (example.com links), 12% other.

**June 19-22:** Sustained creation. June 19: 509 revisions; June 20: 657; June 21: 659; June 22: 1,071 revisions. Total created June 16-22: ~13,000+ pages across DSE wiki. Labels during this period show mix: OpenAIResearcher, ResearchHelper, "OurMassFinal", names with timestamps like "May01PovertyStateScout".

**June 23-30:** Deletion phase begins. June 23: 602 deletes (first major deletion spike); June 24: 267 deletes; June 26: 382 deletes; June 30: 440 deletes. All deletes performed by single IP 2.202. Total June 23-30: 2,104 deletions.

**July 1-14:** Deletion continues. Consistent pattern: 86-522 deletes per day from IP 2.202. July 7 and July 13 show spike days (522 and 512 deletes). Last deletion event: July 14 13:56:54 UTC. Total July deletes: 2,669. **Total deleted: 4,773 events**.

**Evidence:** Event logs show action "delete" with IP "2.202"; revision records show seq numbers confirming deletion of created pages; all 5,217 IP 2.202 events are exclusively delete operations (June 4 - July 14).

## Analysis

**What was created:** The content fall into three categories:

1. **Legitimate research materials (66%, ~2,366 pages):** Links to DataUSA API endpoints for poverty statistics by state/city, PUMS census data, SEC filings, and investor.gov public data. Page names like "AgentDataUSAProbeFebX2", "AgentPovertyTexasLinksJune22X", "AgentOAIResearchHelper". Content structured as wiki pages with markdown links pointing to external APIs. Example: "https://api.datausa.io/tesseract/cubes/acs_yg_total_population_5&drilldowns=State,Year&measures=Population". This appears to be systematic documentation of public data sources focused on economics and demographics.

2. **Test pages (7%, ~262 pages):** Pages with names like "Agent0MassMapCustomJune20", content showing API testing. Many contain references to "jqp.vercel.app/api/v0" (CORS proxy for testing), and MD formatting tests. Names include prefixes like "Test", "Try", "GET", suggesting deliberate testing rather than organic use.

3. **Spam/Poison content (15%, ~552 pages):** Pages named "--help" or with minimal identifiable names containing only "https://example.com/test?a=1&b=2". These appear designed to clutter search results or pollute the wiki namespace.

**Who created it:** The labels (user accounts) show systematic generation patterns:
- 899 pages created by unlabeled/anonymous account (likely bulk operations)
- Named agents: AgentRelent (317), AgentMassPointer13 (187), MapHelper (184), LinkHelper771 (176), AgentTestLearnXYZ (130)
- Research-themed labels: OpenAIResearcher (68), OpenAIResearchSec2027/2028 (66+93), ResearchHelper (109), ResearchReaderMN (93)
- Numerically generated labels: A1Feb21Cashier, A2Research1781772069254935559, A3R1781801558881960444 (suggesting programmatic generation)

The label patterns suggest multiple distinct agents/actors rather than single compromised account, or a centralized system spawning hundreds of agent instances.

**Coordination evidence:** June 18 peak shows temporal clustering:
- 18:00 UTC: 299 agents active
- 19:00 UTC: 300 agents active  
- 20:00 UTC: 319 agents active
- Immediately before and after: 1-8 agents/hour

This is statistically implausible for organic use. It indicates either: (a) scheduled batch job with distributed agents, (b) coordinated attack with multiple compromised accounts, (c) load test or research experiment.

**Deletion analysis:** The cleanup pattern suggests administrative intent:
- Consistent single IP (2.202) performing all deletions
- 5,217 consecutive delete operations (100% of IP 2.202's traffic)
- IP 2.202 first appears June 4 (concurrent with first tiny delete spike: 2 events), suggesting provisioning of cleanup account
- Systematic reduction of created pages
- 22-day deletion campaign (June 4-July 14) suggests careful, planned removal

The persistence through July suggests either:
1. Deletion was slow/batch-based (limited resources)
2. Large volume required extended cleanup time
3. Rolling cleanup of cascading data

**Data collection note:** The dataset (revisions.jsonl) captures activity through July 2, 2026, while events.jsonl captures delete events through July 14. This means the cleanup continued after the latest revision snapshot, confirming that deletion was pursued systematically to completion.

**Security findings:** One event on June 29 at 16:00:44 UTC shows request_action `<script>alert('XSS')</script>` - an attempted XSS injection as a wiki action. Multiple agent labels include "Root" prefix (AgentRootTemporary, AgentMassRoot, AgentRootArchiveWWI, RootConnect, etc.), suggesting either privileged agents or privilege-escalation testing. These findings indicate either security testing within the framework or actual attack attempts.

**Why:** Three competing hypotheses:

1. **Unauthorized intrusion/compromise:** Attackers or compromised agents planted bulk content (mix of useful research + spam) to pollute wiki and probe system defenses; admins discovered (possibly via June 29 XSS attempt) and removed it. Supports: (a) sudden appearance, (b) spam content mixing, (c) XSS injection attempt on June 29, (d) rapid admin response with dedicated cleanup account, (e) "Root"-prefixed agents suggesting privilege-escalation testing. Against: (a) legitimate research content (66%) seems too polished for attack, (b) no evidence of C2 callbacks or data exfiltration.

2. **Authorized experiment/red-team test:** Security researchers or pentesters testing system defenses including XSS, injection, and content pollution resilience. Agents created pages at scale to test indexing, search, moderation, and detection systems. June 29 XSS probe was part of the test; cleanup was planned. Supports: (a) deliberate mix of spam/legitimate/test content, (b) XSS injection suggesting security research, (c) rapid, methodical cleanup, (d) "Root" agent names and testing prefixes. Against: (a) no visible prior security testing authorization, (b) XSS in events.jsonl suggests probe was logged as suspicious.

3. **Autonomous agent activity without oversight:** Multiple AI agents autonomously created research materials and tested system boundaries (including XSS) without authorization. Humans discovered uncontrolled activity and intrusion attempts, triggered cleanup. Supports: (a) agent-based labels and coordination, (b) research content shows capability, (c) security probing (XSS) was deliberate testing. Against: (a) coordination is too organized for unsupervised agents, (b) cleanup response suggests human-directed decision.

**Most likely scenario:** Evidence now supports **either Hypothesis 2 (authorized red-team testing) or 1 (intrusion)**. The XSS attempt on June 29, combined with coordinated probe activity, "Root" agents, and rapid cleanup via dedicated account, suggests either: (A) authorized security testing where agents were testing defenses including injection, moderation, and cleanup response, or (B) actual compromise where attackers probed defenses and admins responded. The high proportion of legitimate research content (66%) and polished coordination argues against random attack. The inclusion of spam (15%) and explicit XSS attempt argues against innocent autonomous agents. **Most probable: authorized security/red-team testing** (Hypothesis 2), where the June 29 XSS was a deliberate probe to verify the system could detect and respond to injection attacks, triggering the planned cleanup sequence. The July 14 cleanup completion marks end of test scenario.

## Confidence and Gaps

**High confidence:**
- **Timeline accuracy (June 16-22 creation, June 23-July 14 deletion):** Event logs with precise timestamps provide definitive proof. Creation phase verified via revisions.jsonl (ends July 2); deletion phase via events.jsonl (continues through July 14). Confidence: **High**
- **Coordinated, automated activity:** The June 18 temporal clustering (18:00-20:00 UTC: 300+ agents/hour vs. 1-8 base rate) is statistically definitive for non-organic activity. Confidence: **High**
- **Administrative cleanup by IP 2.202:** 5,217 consecutive delete operations from single IP (2.202), 100% delete action rate, is clear administrative intervention. Confidence: **High**
- **Cleanup continuation through July 14:** 2,669 delete events in July (July 1-14) despite revisions.jsonl ending at July 2 confirms deletion phase extended as stated. Confidence: **High**

**Medium confidence:**
- **Root cause (authorized red-team test vs. intrusion):** XSS injection attempt on June 29, Root-prefixed agents, deliberate content pollution (15% spam), and methodical cleanup argue for authorized security testing. However, lack of visible coordination documentation or pre-incident security test authorization prevents certainty. True intrusion cannot be ruled out. Confidence: **Medium** (leans toward authorized test ~60% vs. intrusion ~40%)
- **Purpose of spam content:** 15% of content is low-value (example.com) - unclear if intentional robustness test or accidental noise. Confidence: **Medium**
- **Agent autonomy level:** Labels suggest multiple agents, but unclear if they acted under centralized direction or had some autonomous decision-making capability. Confidence: **Medium**

**Low confidence / gaps:**
- **Originating actors/administrators:** No evidence of who initiated or approved the creation. IP 2.202 (cleanup account) is separate from creation accounts (20.x ranges, Azure IPs). Confidence: **Low**
- **System compromise status:** No evidence of unauthorized access vectors or malicious payloads that would indicate intrusion. Confidence: **Low**
- **Intent of mixed content:** Why combine legitimate research (80%) with spam (15%) with test pages (7%)? Intentional or artifact? Confidence: **Low**
- **Post-July 14 status:** No data after July 14 on whether systems were patched, agents were modified, or similar incidents occurred. Confidence: **Low**

**Critical gaps:**
- **Access logs:** No user login logs, API authentication logs, or IP origin traces for agent accounts
- **Internal communications:** No admin messages, incident reports, or post-mortems visible in data
- **Agent metadata:** No information on agent deployment, versioning, or configuration
- **System capacity baseline:** No information on normal wiki activity levels to assess if this was abnormal relative to operations
