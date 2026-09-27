> Published copy of the archived agent report. Credential and personal-identifier spans were redacted; the analysis was not edited.
> Archived report SHA-256: `820f7f37392b61af9412c2a6b4ffe2eadb585a163035cef280d943a7f4b0f150`.

# Investigation of Recorded Web Scans in /work/data

## TL;DR

The collection is dominated by a single submitting account (`[submission ID A]`, 33,104 of
38,158 scans) whose activity is concentrated in April–June 2026. The dominant behaviour is
not ordinary phishing triage but **repurposing the URL scanner as a free, browser-equipped
fetch-and-execute engine**. The actor repeatedly submits URLs to HTTP echo/`/base64/`
services (httpbin, httpbun) that return small HTML pages containing JavaScript, which then
`fetch()` third-party data APIs (UNCTAD statistics, Australia's AIHW PBS dashboards,
thrill-data, Mapillary, a Thai ONCB endpoint). This uses the scanner's browser to bypass
CORS and geographic/rate limits. A second technique smuggles extra HTTP request headers
(including `Authorization: Bearer` tokens) through the user-agent field via CRLF injection
(1,065 scans). Submitted payloads also auto-submit forms to browserless.io's GraphQL API,
to urlquery.net signup/login/apikey endpoints, and to disposable-email services
(mail.tm, boomlify), with webhook.site callbacks. Most of this looks like automated data
harvesting and SaaS-account automation, not classic credential phishing. Treat identity and
intent as inferred; status codes here do not prove success.

## 1. Scope, provenance, and method

I worked entirely offline from the supplied files, per `README.txt`. The dataset contains
38,158 scans (`scans.jsonl`), plus per-transaction HTTP records (`http.jsonl`, 1.7 GB),
resource metadata (`resources.jsonl`), verbatim stored content (`content/`), and a bounded
decode view (`decoded_text.jsonl`). I treated all URLs, headers, programs and credentials as
inert evidence and did not execute, replay, or authenticate anything. Where I decoded
Base64/percent content it was to characterise mechanism; I do not reproduce credential values.

Key caveats stated up front. The collection is **selected, not a census** (README), so
prevalence claims describe this dataset, not the web. `submission_user_id` and
`submission_tags` are **submission metadata, not authenticated identities**; a shared user ID
is consistent with one operator but could be a shared tool/account. `destination_ip` is the
scanned destination, not the submitter. Per README, **status codes do not establish
higher-level success**, and missing content is an acquisition gap, not an empty response. I
therefore separate *observed submissions* from *inferred intent*, and *attempts* from
*demonstrated outcomes*.

## 2. The population: one account, one burst

Submitter breakdown: `[submission ID A]` = 33,104 scans; `null` = 5,054. So ~87% of all scans
carry one submission user ID. Monthly counts are overwhelmingly recent: 2026-04 = 3,840;
2026-05 = 20,237; 2026-06 = 13,164; with a long thin tail back to 2023-09. A handful of
older, unrelated-looking scans (e.g. a 2023 Smart Energy Decisions tracking-link redirect,
`b0921af8-…`) sit in the tail and should **not** be assumed to share the actor.

User-agent strings are also concentrated: 37,731 scans use one modern Windows Firefox 134
string; 182 use an older Linux Firefox 96 string; and a cluster of malformed user-agents
(containing embedded `\r\n` and header names) is discussed in §4. This concentration — one
ID, one burst, one UA — is the single strongest structural signal that most of the corpus is
one automated campaign rather than diverse organic traffic. Counterpoint: the `null`-user
5,054 scans and the older tail dilute any "single actor" claim; I do not attribute those.

## 3. Primary mechanism: echo/`/base64/` services as a JavaScript delivery vector

The most consequential and repeated pattern uses HTTP testing/echo services to *serve
attacker-chosen HTML* to the scanner's browser. httpbin and its clones expose a
`/base64/<payload>` route that decodes the path segment and returns it as the response body.
By placing an HTML+`<script>` document in that segment, the submitter causes the scanner to
render a page it fully controls, on the echo service's origin.

Host prevalence among submitted URLs: httpbin* = 6,984, httpbun = 1,027, markdown.new =
1,001, cors* proxies = 662, jina.ai/r.jina.ai = 541, pie.dev = 388, nghttp2 = 203,
allorigins = 136, postman-echo = 136, pure.md = 66. Across `decoded_text.jsonl` I decoded
13,031 `/base64/` payloads.

Two payload families dominate. **(a) `fetch()`-and-render:** e.g. scan
`96bedcf4-445b-42de-a43e-333ad239298c` (`submit.url.addr`, decoded) is
`<html><body>loading<script>fetch('https://dataapi.oncb.go.th/suppress/case_per/2557')
.then(r=>r.text()).then(t=>document.body.textContent=t)…</script></body></html>`. The script
pulls a third-party API and writes the result into the DOM, so the scraped data is captured
in the scan's final DOM/resources. **(b) Auto-submitting forms:** the most common decoded
target is `FORM: https://unctadstat-api.unctad.org/datamart-api/US.…` (2,855 occurrences),
i.e. an HTML form auto-POSTing to UNCTAD's data API.

Why this matters: the scanner acts as a **CORS-bypassing, IP-diverse proxy with a real
browser**. Same-origin policy would block a page on the attacker's own site from reading
these responses; served from the echo origin and rendered by the scanner, the responses are
retrievable and land in the recorded DOM. The recurring `fetch()` targets read like a data
harvesting programme against public/semi-public statistical and mapping APIs:

- `pp.aihw.gov.au/getmedia/ce13d423-…` — 1,965 (Australian Institute of Health and Welfare)
- `api.allorigins.win/raw?url=…thrill-data…` — 136 (theme-park wait-time data via CORS proxy)
- `graph.mapillary.com/images?access_token=MLY|…` — 115 (Mapillary street imagery API, with
  an embedded access token in the URL)
- `api.codetabs.com/v1/proxy?quest=…unctadstat…` — 109 (another proxy fronting UNCTAD)
- `unctadstat-api.unctad.org/datamart-api/US.*` — repeated across many topic codes
  (TradeFoodP, Gender_Tra, TradeServC, …)

The mix of direct `fetch()` and proxy-fronted `fetch()` (allorigins, codetabs, jina.ai,
markdown.new, pure.md, corsproxy) suggests deliberate rotation to defeat per-origin rate
limits or CORS.

**This is demonstrated, not merely attempted.** Sampling `http.jsonl` (first ~1.5M
transactions) I confirmed both stages executed. The `/base64/` delivery pages themselves
returned mostly HTTP 200 (7,151 of ~8,501 sampled navigations; 378×404, 248×503), so the
attacker-controlled HTML was actually served and rendered. More importantly, the **downstream
`fetch()` sub-requests fired and frequently succeeded**: non-navigation requests to
`vizprod.aihw.gov.au` returned 200 in 56,256 sampled transactions; `unctadstat-api.unctad.org`
returned 200 in 8,440 and 204 in 5,461 (plus 9,548×404 — see below); `graph.mapillary.com`
returned 200 in 1,288; `pp.aihw.gov.au` 200 in 157. The large 404 count against UNCTAD is
itself informative: it is consistent with **systematic enumeration** across many report/topic
codes, most of which do not exist. So the campaign both delivered payloads and pulled real
API responses at scale.

## 4. Secondary mechanism: header smuggling via the user-agent field

1,065 scans carry a user-agent value containing embedded CRLF (`\r\n`) followed by
additional HTTP header lines — a classic header-injection pattern where the scanner
configuration field is abused to append arbitrary request headers. 58 of these inject an
`Authorization: Bearer` token (a JWT whose issuer path references a Supabase auth endpoint),
and many add `Apollo-Require-Preflight: true`. Example scans: `3fd26e7f-…` and `5c1d264b-…`
(2026-06-20), both submitting httpbun `/base64/` payloads whose decoded body is a form
POSTing to `https://api.browserless.io/graphql`.

Injected-header scans cluster on specific destinations: www.aihw.gov.au (571), eu.httpbin.org
(156), pp.aihw.gov.au (111), httpbun.com (69), pie.dev (41), vizprod.aihw.gov.au (36). The
AIHW concentration ties this technique to the same harvesting target as §3. The combination —
smuggled `Authorization` header + `Apollo-Require-Preflight` (an Apollo GraphQL control
header) + a form targeting browserless.io's GraphQL — indicates the actor is trying to drive
**browserless.io**, a paid headless-browser automation service, *authenticated*, from inside
the scanner. In other words: chaining one automation service (the scanner) into another
(browserless) using a smuggled bearer token. This is an *attempted* authenticated call;
whether browserless accepted it is not established by the records.

Interpretation caveat: header injection through a UA field could also be an artefact of a
sloppy automation harness that concatenates headers into one string. But the presence of a
valid-looking bearer token and GraphQL-specific control headers makes deliberate smuggling
the stronger reading.

## 5. Tertiary mechanism: SaaS account automation and callbacks

Decoded form/`fetch()` targets reveal an account-automation subsystem distinct from pure
scraping:

- `FORM: https://urlquery.net/user/signup` (285), `…/api/htmx/user/login` (69),
  `…/api/htmx/apikey/new` (49) — automated **account creation and API-key minting on
  urlquery.net**, itself a URL-scanning service. This is one scanning service being used to
  bootstrap accounts on another.
- `https://api.mail.tm/token` (80), `https://api.mail.tm/accounts` (50),
  `https://v1.boomlify.com/emails/public/create` (70) — **disposable/temporary email**
  provisioning, the standard way to pass email verification during bulk signups. This
  strongly complements the urlquery signups.
- `https://webhook.site/644af2ca-…?m=…` (100) and a
  `…execute-api.eu-central-1.amazonaws.com/…` endpoint (50) — **out-of-band callbacks**,
  consistent with confirming that the scanner's browser executed the payload and/or
  exfiltrating small results to an actor-controlled collector.

Together these show a workflow: mint disposable email → create/login accounts and API keys on
target SaaS → drive headless-browser/data APIs → beacon results to a webhook collector. This
is automation-abuse and resource-farming behaviour, not credential phishing of end users.

These endpoints also *fired and largely succeeded* in `http.jsonl` (sampled): webhook.site
returned 200 in 117 transactions (and 429 in 51 — rate-limited, explaining the rotation),
urlquery 200×76 / 204×44 (with some 401/400/405 failures), api.mail.tm 200×35 / 201×2,
boomlify 200×15 / 204×19, and the AWS `execute-api` collector 200×20. So the disposable-email
provisioning, account/API interactions, and webhook callbacks are demonstrated behaviours, not
just payload text — while the 429/401 mix shows the operator was hitting quotas and auth walls,
consistent with the account-farming motive.

A concrete linkage strengthens this: some payloads POST to
`https://data.browserless.io/auth/v1/otp` with a Supabase `apikey`/`Authorization` pair —
i.e. an **OTP-based Supabase signup flow for a browserless account**. The Supabase project
reference embedded there is the *same* project reference that appears in the JWT smuggled via
the user-agent header (§4). That shared identifier ties the header-smuggling technique and the
browserless account-automation to one operator infrastructure, reinforcing the single-campaign
reading. (I do not reproduce the token or key values.)

## 5b. Reading the mechanism as an integrated pipeline

Viewed together, §§3–5 are not three unrelated tricks but one composable pipeline, and the
choice of components is telling. The echo/`/base64/` services solve the *delivery* problem:
they let the operator place arbitrary HTML on a third-party origin that the scanner will
faithfully render, without owning or registering any site. The CORS/markdown proxies
(allorigins, codetabs, jina.ai, r.jina.ai, markdown.new, pure.md, microlink, corsmirror,
api.cors.lol) solve the *read* problem: they turn cross-origin or bot-blocked responses into
plain, same-origin-readable text. The header smuggling (§4) solves the *authentication*
problem where a bare browser cannot attach the needed `Authorization`/`apikey` headers. The
disposable-email and signup endpoints (§5) solve the *identity/quota* problem, manufacturing
fresh accounts and API keys to keep the harvesting going as individual keys are rate-limited or
banned. Webhook.site and the AWS `execute-api` endpoint close the loop with a *collection*
channel. Each component substitutes a free or throwaway resource for something that would
otherwise cost money, require registration, or be attributable — which is the signature of
resource-farming/automation abuse rather than targeted intrusion.

The recurring UNCTAD 404s deserve emphasis as behavioural evidence. Against
`unctadstat-api.unctad.org` the sampled sub-responses were 8,440×200, 5,461×204 and
9,548×404. A 404-heavy distribution across a data API, combined with the many distinct topic
codes seen in decoded form actions (`US.TradeFoodP`, `US.Gender_Tra`, `US.TradeServC`, and
more), is what systematic **enumeration of a code space** looks like: the operator iterates
identifiers, most of which miss, harvesting the ones that hit. The 204s (no content) are
consistent with valid-but-empty result sets for some queries. This is a different fingerprint
from a human analyst spot-checking a handful of known URLs.

## 6. What this is — and what it is probably not

**Best-supported explanation:** a single operator (or one shared tool/account) ran a
large-scale, automated campaign in Q2 2026 that uses the URL scanner as free browser compute
to (i) scrape public/semi-public data APIs while bypassing CORS and rate limits via echo
services and proxy rotation, (ii) smuggle auth headers to reach paid automation
(browserless.io) authenticated, and (iii) bootstrap and operate accounts on other SaaS using
disposable email, with webhook callbacks. The consistency of user ID, UA, timeframe, target
set (UNCTAD, AIHW), and technique across thousands of scans supports treating this as one
coordinated programme.

**Alternative explanations considered:**

1. *Legitimate research/QA.* Echo services and CORS proxies are normal developer tools, and
   some scans carry benign tags (`research`, `clean`, `test`). But legitimate use would not
   need CRLF header smuggling or disposable-email-driven signup/apikey minting; those two
   facts are hard to reconcile with benign QA and tilt toward abuse.
2. *Multiple unrelated actors.* The pre-2026 tail almost certainly is not the campaign:
   classic phishing-adjacent items (MAX.gov CAS login pages `099a0846-…`, `95db645f-…`; a
   smart-energy tracking redirect `b0921af8-…`) look like ordinary scan-service triage. But
   the 5,054 `null`-user scans are a different matter: their target profile (AIHW
   `viz/vizprod/www.aihw.gov.au`, UNCTAD, thrill-data, httpbin/httpbun) *mirrors* the actor's,
   so most `null`-user scans are more likely the **same campaign with a stripped/absent user
   ID** than an independent benign actor. This would make the campaign somewhat larger than
   the 33,104 headline figure. I still do not assume a shared actor across the whole file, per
   the brief — only where technique and targets coincide.
3. *Phishing kit.* Some artefacts (login pages, tracking links) resemble phishing triage, but
   the campaign's own payloads target data APIs and automation services, not victim credential
   capture. The MAX.gov/CAS pages are more plausibly submitted-for-analysis than authored here.

**Attempt vs. outcome.** Payload submission and content are *observed*. Delivery and
downstream data retrieval are *demonstrated* at the transaction level (§3: 200-status delivery
pages and tens of thousands of 200/204 API sub-responses). What remains *inferred* is
higher-level success — whether harvested data was successfully exfiltrated to the actor,
whether browserless/urlquery accepted the authenticated/automated calls, and the operator's
ultimate purpose. README rightly warns a 200 does not prove a task succeeded; I treat data
retrieval as shown, and downstream use/exfiltration as probable but not proven.

## 7. Verification, limits, and selection effects

I verified: submitter and monthly distributions (direct counts over `scans.jsonl`); host
prevalence for both submitted and final URLs; decoding of 13,031 `/base64/` payloads with
tallies of `fetch()`/form targets; and the 1,065 CRLF-injected user-agents with their
target-host distribution and 58 bearer-token cases. I decoded representative payloads
(`96bedcf4-…` render-fetch; `3fd26e7f-…`/`5c1d264b-…` browserless form) to confirm mechanism.

A further automation signal is visible in encoding artefacts: the same `/base64/` payload
appears both with raw `+`/`/` characters and with their percent-encoded forms (`%2B`, `%2F`)
as near-equal duplicate submissions (e.g. the two `httpbin.org/base64/PGh0bWw…` variants at
756 and 697 occurrences). Re-submitting the identical logical payload under two encodings is
what a script does when it is unsure how the endpoint will parse the path — a human would not
hand-generate thousands of such pairs. Combined with the flat single user-agent and the tight
burst window, this is consistent throughout with programmatic generation.

Limits and honest uncertainty:

- The `resources.jsonl` layer partly corroborates retrieval: in a sample I saw 41,683
  `embedded` resources with ~29,570 `application/json` bodies carrying content hashes —
  consistent with harvested API responses being stored. But a large fraction is
  `not_in_download` (≈368k) or `not_available` (≈207k), which per README are acquisition gaps,
  not empty responses; so exhaustive per-scan reconstruction of *what data* was captured is not
  possible from the supplied files, only that JSON bodies were retrieved in bulk.
- Transaction verification used the first ~1.5M records of the 1.7 GB `http.jsonl`, not the
  whole file, so status tallies are large samples, not full totals. I did not read response
  *bodies* to confirm the harvested data's content, nor confirm exfiltration to the actor.
- Base64 decoding of truncated path segments can fail or mislead; I padded and replaced
  percent-encoding heuristically. Counts are lower bounds where truncation defeated decoding.
- Identity is inferred from submission metadata only. A single `submission_user_id` is
  consistent with one operator or one shared automation platform used by many; I cannot
  distinguish these from the data.
- **Selection effect:** this is a curated collection. The overwhelming April–June 2026 burst
  may reflect collection focus as much as real-world timing; prevalence figures describe the
  corpus, not the internet.
- Counterevidence exists (benign tags; developer-normal tool usage; unrelated tail scans) and
  is retained above rather than discarded.

## 7b. Implications for the scanning service

Independent of the operator's ultimate goal, the records expose two abuse primitives the
scanning platform itself enables. First, **the scanner is a confused deputy**: because it
renders submitted URLs in a real browser from its own IP space, any submitter can borrow its
network position and JavaScript engine to reach third-party APIs they could not (or did not
want to) reach directly. The echo-service trick weaponises this by controlling the rendered
page's content, not just its address. Second, **the user-agent (and likely other scanner
settings) is injectable**: CRLF sequences in that field became additional request headers on
the wire (`raw` request lines in `http.jsonl` show headers appended after the UA). That single
input-validation gap is what upgrades the scanner from a passive fetcher into an
attacker-controlled authenticated HTTP client. Both primitives are visible directly in the
evidence and are the most actionable takeaways for a defender: constrain outbound fetches
initiated by rendered content, and strictly validate/serialise scanner-setting fields so they
cannot inject headers.

The targets themselves — public statistical portals (UNCTAD, AIHW, Thai ONCB, dataforindia,
Thai NSO), a mapping API (Mapillary), and theme-park telemetry (thrill-data) — are mostly open
data. That lowers the likelihood of this being espionage against sensitive systems and raises
the likelihood of **bulk dataset assembly** (e.g. building a scraped corpus while dodging rate
limits, CORS, and per-key quotas). The webhook/exfil channel and account-minting subsystem are
the parts most suggestive of a commercial or resale motive, but motive here is inferred, not
observed.

## 8. Most consequential findings (ranked)

1. **Scanner-as-proxy data harvesting** via echo/`/base64/` HTML+JS payloads against UNCTAD,
   AIHW, thrill-data, Mapillary, and a Thai ONCB endpoint, with proxy rotation to bypass CORS
   and rate limits (thousands of scans; §3). Highest volume, clearest mechanism, and
   **demonstrated in transactions** (56k+ AIHW 200s, 8k+ UNCTAD 200s, apparent code
   enumeration via 9.5k 404s).
2. **HTTP header smuggling through the user-agent field** (1,065 scans; 58 with bearer
   tokens) to reach browserless.io GraphQL authenticated (§4). Demonstrates deliberate abuse
   beyond ordinary tooling.
3. **SaaS account-automation subsystem** — urlquery signup/login/apikey minting plus
   disposable email (mail.tm, boomlify) and webhook.site callbacks (§5).
4. **Single-account, single-burst concentration** (§2) binding 1–3 into one campaign; the
   `null`-user scans share the same target profile and are likely part of it, while only the
   pre-2026 phishing-triage tail is left unattributed.

## Appendix A: Key evidence pointers

- Submitter concentration: `[submission ID A]` 33,104 / 38,158 scans; monthly peak 2026-05
  (20,237), 2026-06 (13,164), 2026-04 (3,840). Source: `scans.jsonl`,
  `submission_user_id`, `scanned_at`.
- Render-fetch payload: scan `96bedcf4-445b-42de-a43e-333ad239298c`, `source_field`
  `submit.url.addr`/`url.addr`/`final.url.addr` (`decoded_text.jsonl`), Base64 body decodes to
  a `<script>fetch('https://dataapi.oncb.go.th/suppress/case_per/2557')…</script>` page.
- Browserless form + header smuggling: scans `3fd26e7f-6726-450b-be22-585da82e6aac` and
  `5c1d264b-9452-4450-a281-b5af8be24f26` (2026-06-20); user-agent contains injected
  `Apollo-Require-Preflight` and `Authorization: Bearer` lines; decoded payload is a form
  POSTing to `https://api.browserless.io/graphql`.
- Decoded target tallies (`decoded_text.jsonl`, `/base64/` bodies, n=13,031): UNCTAD form
  POST 2,855; AIHW `pp.aihw.gov.au/getmedia/ce13d423…` 1,965; browserless form 287;
  urlquery signup 285; allorigins/thrill-data 136; Mapillary 115; codetabs/UNCTAD 109;
  webhook.site 100; mail.tm token 80; boomlify 70; urlquery login 69; urlquery apikey 49;
  mail.tm accounts 50.
- CRLF-injected user-agents: 1,065 scans; top targets www.aihw.gov.au (571), eu.httpbin.org
  (156), pp.aihw.gov.au (111), httpbun.com (69); 58 carry an `Authorization: Bearer` token.
- Unattributed tail (not the campaign): `b0921af8-…` (2023 tracking-link redirect),
  `099a0846-…` / `95db645f-…` (MAX.gov CAS login pages, 2024).
- Recurring monitored target: `whssgr.com`/`mail.whssgr.com` `/history/` fetched repeatedly
  through many markdown/CORS proxies — markdown.new (623), pure.md (42), md.succ.ai (27),
  microlink variants, api.cors.lol, corsmirror, cors-anywhere.fly.dev, r.jina.ai. The heavy
  proxy fan-out on one URL suggests either content monitoring or proxy-viability testing.

## Appendix B: Method notes

All figures are `len`/`Counter` tallies computed locally over the JSONL files with Python; no
network access, no execution of supplied programs, no credential reuse. Base64 payloads were
decoded read-only to characterise mechanism. Where README distinguishes attempt from outcome
(status codes, missing content), I flagged claims accordingly and did not upgrade attempts to
outcomes without captured content.

Reproduction pointers for a checker: submitter/monthly counts come from iterating
`scans.jsonl` and grouping on `submission_user_id` and `scanned_at[:7]`; host prevalence from
`submitted_url.fqdn`/`final_url.fqdn`; payload target tallies from regex-extracting
`/base64/<seg>` across `decoded_text.jsonl`, Base64-decoding each segment, and counting
`fetch(...)` and form `action=...` targets; header injection from scanning
`scanner_settings.useragent` for embedded newline characters; and transaction outcomes from
grouping `http.jsonl` records on `url.addr` host and `response.status_code`, filtering
`is_navigation_request`. Every headline number in this report was produced by one of these
passes, and the specific scan IDs in Appendix A can be fetched directly for spot-checking.
Because `http.jsonl` was sampled rather than fully traversed, treat its status counts as
representative magnitudes rather than exact totals.
