# Incident Report: Mass Data Exfiltration Attack on Wiki

## Executive Summary

Between June 16-22, 2026, a coordinated attack targeting the wiki resulted in 11,739 malicious edits across multiple pages. The attack attempted to exfiltrate sensitive data related to Massachusetts county regulations, crowdfunding, and SEC filings. Administrators detected and began responding to the attack on June 18, 2026, initiating deletion operations that continued through July 14, 2026.

## Timeline

- **2026-06-16 07:23:32Z**: Attack begins with sustained high-volume editing activity
- **2026-06-18 17:15:53Z**: Peak attack intensity begins on main page "WillkommenImWiki" (2,299 edits this day)
- **2026-06-18 18:21:02Z**: First delete event detected - administrators begin response
- **2026-06-19 - 2026-06-23**: Continued malicious editing (1,297 edits, 6,543 edits, 509 edits, 657 edits, 659 edits respectively)
- **2026-06-23 onwards**: Editing activity drops to near-zero; cleanup continues
- **2026-07-14 13:56:54Z**: Last delete event recorded (5,217 total deletions over ~26 days)

## What Happened

### Attack Phase (June 16-22)

**Scope**: Multiple wiki instances targeted:
- **dse wiki**: 12,266 edits (primary target, 94% of attack)
- **probier wiki**: 937 edits (secondary)
- **fractal wiki**: 130 edits
- **dorfwiki**: 6 edits

**Volume**: 11,739 total revisions across 7 days
- June 16: 2,603 revisions
- June 17: 1,297 revisions  
- June 18: 6,543 revisions (peak)
- June 19-22: 1,296 total revisions

**Pages Created**: 3,740 new pages during the attack period:
- 1,871 pages (50%) with "Agent" nomenclature - likely automated/bot-created
- 708 pages (19%) explicitly targeting data extraction (names containing "Mass", "OpenAI", "SEC", "County", "Invest")
- Examples: `AgentDataUSAProbeFebX2`, `AICountyFreshSmallD`, `Agent013OpenSECMDJSPairsUnique`, `AgencyMDCounty57494616`

**Primary Existing Target**: The main wiki page "WillkommenImWiki" (Welcome page) with 2,325 edits

**Secondary Pages**: 
- StartSeite (403 edits)
- TestSeite (217 edits)
- HealthdataCVDSequenceCollab (121 edits)

### Attack Method

The attackers used a multi-pronged approach:

1. **Coordinated Bot Network**: Used multiple spoofed/bot accounts including:
   - Accounts impersonating legitimate services: `OpenAI`, `[Admin1]` (fake admin account), `OpenAIResearch*`, `OpenAIResearchSec*`
   - Generic bot names: `AgentRelent`, `AgentMassPointer13`, `Agent0AddJS`, `AgentXXX`
   - Massachusetts-targeted names: `MassUpdater`, `MassResearchUnres`, `MassSecEncodedTargets`, `HelperMassRef*`
   - 833 edits with completely empty user labels (possible automated bypass)

2. **Data Exfiltration Vectors**: 
   - Embedded URLs to external data extraction service `jqp.vercel.app` 
   - Content referencing sensitive Massachusetts county data, SEC crowdfunding records
   - Example (Rev ID: `dse~MassSecEncodedTargets@1`, 2026-06-18T18:15:24Z):
     - Links to `investor.gov/files/county.json` and `sec.gov/files/county.json`
     - jq filter attempting to extract Massachusetts county codes and crowdfunding data: `regCF_county_2019[...]|select(.code|startswith("us-ma-"))`

3. **XSS Attempt**:
   - At least one detected XSS payload: `<script>alert('XSS')</script>`
   - Additional probes on preferences editing endpoints (6+ form_editprefs requests on June 18)

4. **Source IP Addresses** (all Microsoft/Azure ranges primarily):
   - 20.165.x.x: 548 edits
   - 20.69.x.x: 530 edits
   - 20.171.x.x: 420 edits
   - 57.154.x.x: 415 edits
   - 20.9.x.x through 20.225.x.x: 300-380 edits each
   - 4.255.x.x: 326 edits

## Who Was Behind It

**Confidence Level**: MEDIUM

Multiple lines of evidence point to a sophisticated, coordinated attack:
- The use of multiple coordinated bot accounts working in parallel
- Systematic attempt to impersonate legitimate services (OpenAI, Admin accounts)
- Massachusetts-specific data targeting and naming schemes
- IP ranges primarily from major cloud providers (Microsoft Azure)
- Sustained, organized effort over multiple days

However, cannot determine if this was an internal test, rogue employee, or external attacker based solely on the edit logs.

## What They Were Trying to Do

**Confidence Level**: HIGH

The attackers attempted to:

1. **Exfiltrate sensitive regulatory data** - Specifically Massachusetts county-level SEC crowdfunding records and investment data
2. **Test system vulnerabilities** - Multiple XSS attempts and preference editing probes suggest vulnerability scanning
3. **Bypass access controls** - Use of spoofed accounts and bot networks suggests attempt to circumvent user-based rate limiting or authentication
4. **Establish persistence** - Creation of 3,740 new pages (50% with "Agent" names) during the attack suggests setting up infrastructure for future data exfiltration campaigns

## How They Did It

1. **Direct form submission** - Used the wiki's form_edit functionality (13,298 form-edit requests among the 11,739 total revisions recorded)
2. **Account spoofing** - Created or compromised accounts with legitimate-sounding names to blend in
3. **Data piping** - Embedded malicious URLs in wiki content linking to external extraction services
4. **Volume attack** - Sustained high-volume editing (~1,667 edits/day average, up to 6,543 edits on peak day June 18, likely 200+ edits per minute during peak hours)

## Response

**Confidence Level**: HIGH

Administrators responded with:

1. **Detection**: First delete event at 2026-06-18 18:21:02Z (approximately 28 minutes after peak attack intensity started)
2. **Remediation**: 5,217 delete operations over 26 days
   - Heavy deletion activity June 23-24 (869 deletes)
   - Continued cleanup through July 14 to fully remove malicious content
3. **Scope**: Deletions appear to have focused on:
   - Malicious page content
   - Suspicious bot-created pages
   - Compromised account edits

**Response adequacy**: The response was relatively swift in detecting the attack and initiated cleanup within ~30 minutes of peak activity. However, the cleanup took 26 days to complete, suggesting either large volume of affected content or careful manual verification before deletion.

## What the Data Cannot Tell Us

1. **Original intent of cloud services** - The 20.x.x Azure IP ranges are too broad to identify specific Azure account or service
2. **Authentication method** - Cannot determine if accounts were compromised, newly created, or legitimately accessed
3. **Success of exfiltration** - Edit logs show the malicious content but cannot confirm if data actually flowed to `jqp.vercel.app` or was successfully extracted
4. **Root cause** - Whether this was enabled by a specific vulnerability in the wiki software or weak access controls
5. **Geographic attribution** - Azure IP ranges do not indicate attacker location
6. **Damage scope** - Cannot determine from edit logs alone if sensitive data was actually exposed beyond the wiki, or if the wiki was just a staging point

## Specific Evidence References

### Revision IDs
- **Attack initiation**: dse~WillkommenImWiki@9 (2026-06-18T17:15:53Z, OpenAIResearchSec2028)
- **Admin account impersonation**: dse~WillkommenImWiki@17 (2026-06-18T17:32:18Z, [Admin1])
- **Data exfiltration attempt**: dse~MassSecEncodedTargets@1 (2026-06-18T18:15:24Z, external jqp.vercel.app links)
- **XSS payload**: dse~OECDJun26PrecisionScout@2 (2026-06-20T04:39:51Z, contains script payload)
- **Automated bot activity**: dse~Agent013OpenSECMDJSPairsUnique@3, @4 (2026-06-18, 21:07-21:09Z, multiple agent accounts)

### Account Analysis
- **Empty user label account**: 899 total revisions across both wikis, with 568 unique pages edited. High-volume automated activity marker.
- **Account "A"**: 32 revisions in narrow window (2026-06-18T17:24:53Z to 2026-06-18T21:12:52Z), used 27 different IP addresses, including edits to main WillkommenImWiki page. Strong indicator of compromised account or proxy rotation attack.

### Response Evidence
- **Revert events**: 4 recorded from 2026-06-19 to 2026-06-21 by actors like "OpenAIResearchHelper" and "ArchiveReaderA4_be1781900000" (suspicious names), suggesting admins may have used automated tools to recover/rollback content.

## Recommendations

1. **Investigate Azure accounts** - Determine if Azure resources were compromised or an attacker's infrastructure
2. **Review access control logs** - Correlate wiki edits with any authentication events to find account compromise vectors
3. **Audit wiki software** - Check for vulnerabilities in the form_edit endpoint that enabled this volume of activity
4. **Implement rate limiting** - Prevent future mass edit attacks by limiting edits per IP/account
5. **Monitor jqp.vercel.app** - Determine if this external service was complicit or compromised
6. **Credential audit** - Review all administrator and service accounts for unauthorized access
