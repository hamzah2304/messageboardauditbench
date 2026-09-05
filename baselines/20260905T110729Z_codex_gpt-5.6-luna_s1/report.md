# Incident report: coordinated automated/test editing and cleanup

## Executive summary

Yes. The recent logs show a sustained, highly unusual write campaign, concentrated on the `dse` wiki from 16–22 June 2026. It produced 13,403 revisions in `dse` (of 14,591 revisions across all wikis), including 5,884 on 18 June alone, and touched at least 1,305 pages that day. The pages and edit summaries repeatedly describe themselves as tests, probes, bridges, coordination relays, or mass link work. Many revisions added external URL/proxy/renderer links; a smaller but important subset tested raw HTML, forms, JavaScript, XSS, and alternate request paths.

The strongest interpretation is coordinated automated or semi-automated experimentation/abuse of the wiki's edit and rendering behavior, rather than ordinary editorial work. The data does not establish whether the activity was one person, one program, or a group of users, and it does not prove that any payload executed or that an external system was compromised. The operators responded with four recorded reverts on 19–21 June and then a large moderator-led deletion campaign beginning 4 June and accelerating from 19 June through 14 July. The cleanup produced 5,217 `dse` deletion events affecting 5,144 unique page keys in the supplied event log.

## Timeline

- **17 May:** Three bare-browse probes appear from IP prefix `135.136` (`probe:0`–`probe:2`). This is weak reconnaissance evidence by itself.

- **24 May–11 June:** The activity is intermittent and smaller. There are 35 revisions on 24 May, 436 on 26 May, and generally tens or fewer on most intervening days. Test/bridge content is already present; for example, revision `dse~TmpFederalBridge@2` (24 May) contains an HTML/JavaScript redirect-style payload embedded in a link/comment.

- **16 June:** Volume jumps to 2,603 revisions. The edits span 745 `dse` pages and 714 distinct labels. Revisions to `dse~--help` repeatedly append whitespace and coordination/probe text, including “Safe GET write probe” (`dse~--help@17`–`@19`). A dedicated HTML/form/script test appears in `dse~AgentTempFormXYZ@1`, whose body includes a form posting to `example.com` and a script intended to change the page background.

- **17 June:** 1,297 revisions are recorded. The `--help` page continues to receive “GET write probe”/cohort updates (`dse~--help@17`–`@19`). New pages explicitly call themselves probes, relays, or coordination pages, for example `dse~A2DataProbe173920@1` and `dse~URGENTJul27AZConstructionR5Due124038@1`.

- **18 June:** The main burst: 5,884 revisions, 1,305 pages, 898 distinct labels, and 148 IP prefixes in `dse`. Representative content includes:
  - repeated SEC/Data USA “bridge” and proxy-link construction (`dse~Agent0MassMapCustomJune20@1`–`@18`, `dse~AgentJSLinks99172@1`–`@11`);
  - links to `markdown.new`, `allorigins`, `jqp.vercel.app`, `httpbin.org/base64`, and direct SEC/investor.gov JavaScript/data files (`dse~AgentJSLinks99172@9`, `dse~AgentBase64Test@3`, `dse~AgentMySecLinksZZZ2@4`);
  - edits to the wiki's `StartSeite` adding an external `action=editprefs` URL (`dse~StartSeite@433`–`@435`);
  - explicit raw HTML/JavaScript tests in `dse~TmpJan18HtmlHost987@1`, which contains `<h1>`, `<script>document.write(...)`, and a form;
  - many summaries explicitly saying “test”, “probe”, “coordination”, “mass”, “bridge”, or “GET”.

- **19–22 June:** Activity declines but continues (481, 628, 631, and 816 `dse` revisions respectively). The content shifts heavily toward Data USA API links and further bridge/proxy variants. Four event-log reverts are recorded: pages `OpenAIDataUSAPoliceBridge20260129` and `OpenAIResearchPoliceDataBridge194814` on 19 June, `--help` on 21 June, and `OAITestFoo` on 21 June (`revert:delete:dse:rclog:145962`, `146247`, `146986`, `146029`).

- **4 June–14 July:** Moderator cleanup is visible in the event log. Deletions begin on 4 June (2 events), reach 317 on 19 June, and then continue in large batches: 602 on 23 June, 440 on 30 June, 248 on 1 July, 88 on 2 July, and 512 on 13 July. The last recorded deletion is 14 July 2026 13:56:54Z (`delete:dse:rclog:158016`). Every supplied deletion has actor label `moderator`, IP prefix `2.202`, request action `delete`, and summary `Seite gelöscht.`

## What happened

**High confidence:** A very large number of edits were made to `dse` in a short period, with a sharp peak on 18 June and a broad, coordinated naming/content pattern. This is supported by the revision counts, the diversity of labels/IP prefixes, and the repeated self-identifying summaries and page bodies (for example `dse~Agent0MassMapCustomJune20@1`, `dse~AgentJSLinks99172@1`, and `dse~A2TestProbeXYZ1781767@1`).

**High confidence:** The activity included systematic testing of the wiki's handling of external links, URL encoding, proxy/renderer services, GET-based edits, and HTML/JavaScript. The clearest examples are `dse~AgentTempFormXYZ@1`, `dse~TmpJan18HtmlHost987@1`, `dse~TmpFederalBridge@2`, and the `editprefs` link in `dse~StartSeite@433`. These are stronger evidence than the many ordinary-looking research links because they explicitly exercise browser/server behavior or include executable markup.

**Medium confidence:** The campaign was coordinated across multiple automated or semi-automated clients, or across a group sharing a procedure. On 18 June alone there were 898 labels and 148 IP prefixes, while pages were repeatedly edited by different labels with near-identical bodies and summaries (for example the successive `dse~AgentJSLinks99172` revisions). However, the logs only expose truncated IP prefixes (`ip16`) and labels; those cannot uniquely identify people or machines.

**Medium confidence:** A likely objective was to discover reliable ways to get external content rendered, transformed, linked, or written through the wiki, while coordinating work through disposable pages. The vocabulary (“GET write probe”, “bridge”, “proxy”, “mass”, “coordination”), repeated URL variants, and encoded/nested external URLs support this. Some pages also contain apparently legitimate research references, so the logs do not prove malicious intent for every edit or show what the actors ultimately intended to achieve.

## How it was carried out

The apparent method was to create many disposable pages and repeatedly append or replace short bodies. The bodies used external services as fetchers/renderers/proxies and included nested or encoded URLs, self-links, direct source files, and request-path variants. Examples include:

- external proxy/renderer chains and SEC/JSON/JavaScript references in `dse~Agent0MassMapCustomJune20@1` and `dse~AgentJSLinks99172@9`;
- base64-hosted content in `dse~AgentBase64Test@3` and `dse~AgentCountyGateway991@18`;
- raw HTML, forms, and scripts in `dse~AgentTempFormXYZ@1` and `dse~TmpJan18HtmlHost987@1`;
- an external `editprefs` URL inserted into `StartSeite` in `dse~StartSeite@433`.

The event log also records a concentrated sequence of `form_editprefs` probes from IP prefix `52.87` on 18 June, and a request whose action string is literally `<script>alert('XSS')</script>` on 29 June (`probe:16692`). These are consistent with security probing, but the supplied data does not show HTTP responses, permissions, successful execution, or server-side impact.

## Operator response

**High confidence:** Operators noticed and removed a large amount of the material. The event log records 5,217 `delete` events in `dse` affecting 5,144 unique page keys, all attributed to `moderator` at IP prefix `2.202`, with the standard deletion summary. The sustained batches from 19 June through 14 July are consistent with a manual or scripted cleanup process.

**Medium confidence:** Operators also attempted targeted restoration/reversion during the active period. Four `revert` events are recorded between 19 and 21 June, involving bridge/test pages and `--help`. Because the event records have no `revision_ref`, the exact revision restored is not available.

The response visible in these files is cleanup and targeted reversion. There is no evidence here of account suspension, IP blocking, configuration changes, disclosure, outage, or confirmation that a payload executed.

## Confidence and limits

The incident finding is **high confidence**: the volume spike, coordinated labels/content, explicit probe/test material, and subsequent moderator deletion campaign are all directly present in the logs.

The conclusions about a shared operator or automation are **medium confidence**: the pattern is compelling, but labels are not authenticated identities and the IPs are only truncated prefixes.

The conclusions about motive are **medium-to-low confidence**: experimentation with wiki rendering/edit paths is well supported, but intent beyond testing, research-link collection, or coordination cannot be established.

The logs cannot tell us whether JavaScript/XSS executed, whether any external service was affected, whether data was exfiltrated, whether the edits were authorized experiments, or how many real people/tools were involved. They also do not provide a complete deletion-to-revision mapping, because deletion events have `revision_ref: null`, so the exact content removed per deletion cannot be reconstructed from these files alone.
