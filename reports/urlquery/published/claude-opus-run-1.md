> Published copy of the archived agent report. Credential and personal-identifier spans were redacted; the analysis was not edited.
> Archived report SHA-256: `d7e9ce07a1c81469543ca56c531b3e8e89a8cfc9dec2966a1d0992a08925079c`.

# Investigation of recorded web scans (/work/data)

## TL;DR

This collection of 38,158 recorded scans is not a random census of web
traffic; it is overwhelmingly the activity of a single submitting account,
`[submission ID A]` (33,104 scans, ~87%), concentrated in April–June 2026. The
dominant, best-supported story is **instrumental abuse of the scanning service
itself as a free, IP-diverse headless browser and CORS-bypass proxy** to pull
data from public statistical APIs and dashboards (UNCTADstat, Australia's AIHW
Tableau servers, Thrill Data, SEC, Mapillary, US max.gov). The recurring
mechanism is Base64-smuggled HTML/JavaScript delivered through echo endpoints
(`httpbin.org/base64/…`, `httpbun.com`, `eu.httpbin.org`, `pie.dev`,
`httpbingo.org`) whose rendered `fetch()` calls exfiltrate API responses into
the DOM, plus reader/relay services (`r.jina.ai`, `markdown.new`, `cors.lol`,
`allorigins.win`, `cors.bwa.workers.dev`, Google's redirector, Wayback CDX). A
distinct and more aggressive sub-episode targets the analysis platform
`urlquery.net` itself, smuggling auto-submitting forms and a VNC-control script
to create API keys and drive an operator session. A small, older, separate
stratum contains genuine phishing and ordinary page loads. Motives and single
authorship are inferred, not proven; timestamps sit in 2026 and cannot be
independently corroborated offline.

## Data and method

I worked only from the offline files described in `README.txt`. I parsed
`scans.jsonl` (38,158 rows) for submission metadata, URLs and titles;
cross-referenced `decoded_text.jsonl` (211,607 rows of bounded percent/Base64
decodings) and `http.jsonl` for per-transaction detail; and decoded a sample of
Base64 payloads independently to confirm the convenience views. All URLs,
scripts, tokens and credentials are treated as inert evidence. Counts below come
from full passes over `scans.jsonl`; payload contents are quoted from
`decoded_text.jsonl` and verified against the raw `submitted_url`/`initial_url`
fields. I cite `scan_id` and, where relevant, `source_field` or
`transaction_index`.

Two structural caveats frame everything. First, `README.txt` states the
collection is *selected*, not a census, and that missing scans are acquisition
gaps — so absence of a pattern is weak evidence. Second, `submission_user_id`
and `submission_tags` are unauthenticated submission metadata, not proven
identities; grouping by them shows correlated *submissions*, not necessarily one
human.

## Finding 1 — One account dominates; the corpus is a workload, not a census

Grouping `scans.jsonl` by `submission_user_id` gives `[submission ID A]` = 33,104
scans and `null` = 5,054. By month of `scanned_at`, volume is negligible before
2026 (single-digit counts scattered across 2023–2025) then rises sharply:
2026-04 = 3,840, 2026-05 = 20,237, 2026-06 = 13,164, then collapses (2026-07 =
39). This is the shape of a bounded automated campaign, not organic reputation
checking. The final-URL domain histogram is likewise concentrated on data
sources, not typical phishing/malware fare: `unctad.org` (14,793),
`thrill-data.com` (3,746), `aihw.gov.au` (1,992), `httpbin.org` (2,655),
`maryland.gov` (543), `jina.ai` (542), `mapillary.com` (498), `sec.gov` (319),
`max.gov` (343). The large empty-domain bucket (6,376) corresponds to failed/
private-tab/`Problem loading page` results (title `Problem loading page` =
4,138; `about:privatebrowsing` / `New Private Tab` ≈ 2,200), i.e. scans that did
not resolve to content.

**Interpretation.** The operator is systematically harvesting numbered API
resources. UNCTADstat titles show enumerated dataset IDs, e.g.
`US.PCI/2005/Facts`, `US.PortCalls/1064/Facts`,
`US.TradeFoodProcByCat/1677/Facts`, many carrying an inline
`subscription-key=[REDACTED]` in the title/URL. The same
key string recurs in **9,333 scans** (a quarter of the entire corpus),
consistent with one workflow iterating a catalogue under a single API
credential. **Uncertainty:** shared tags/user-id and a shared subscription key
are consistent with one actor but do not exclude a shared tool or team.

## Finding 2 — Echo endpoints used to smuggle and execute attacker HTML/JS

8,373 scans have `/base64/` in their submitted/initial URL. These endpoints
(`httpbin.org/base64/<b64>` and siblings) decode arbitrary Base64 and serve it
back with a content type the scanner renders as a page. The decoded payloads are
not documents to be *read* — they are programs to be *run by the scanner*. A
representative payload (scan `8e1afe36-ee38-44de-8f2f-de01ecc9ac17`,
`source_field submit.url.addr`) decodes to:

```
<html><body>loading<script>fetch('https://dataapi.oncb.go.th/suppress/case_per/2557')
.then(r=>r.text()).then(t=>{document.body.textContent=t})
.catch(e=>{document.body.textContent='ERR '+e})</script></body></html>
```

The pattern is uniform across the family: a tiny HTML shell whose script
`fetch()`es a *third-party* API (Thai ONCB, UNCTADstat, AIHW, SEC, Mapillary)
and writes the response into the DOM, where the scanner captures it as page
content. This is a deliberate **CORS/origin-laundering technique**: the target
API refuses cross-origin browser reads, but code executing from an
`httpbin.org` origin (or via a permissive relay) obtains and materialises the
body. Titles like `e898-keyed-start` (seen in later payloads) show the operator
tagging runs. The choice of many interchangeable echo hosts
(`httpbin.org`, `httpbun.com`, `eu.httpbin.org`, `pie.dev`, `httpbingo.org`) and
relays spreads load and evades any single-host rate limit or block — the same
target (e.g. Thrill Data ride-wait graphs) appears via `r.jina.ai`,
`api.cors.lol`, `api.allorigins.win` and `www.google.com/url?q=view-source:…`
almost interchangeably.

**Observed vs. inferred.** Observed: the payloads exist, are executable, and
name specific data endpoints. Whether each `fetch` *succeeded* is not
established by the smuggling URL alone — README warns status codes do not prove
higher-level success, and thousands of scans ended in `Problem loading page`.
The *attempt* and *technique* are demonstrated; per-target *exfiltration
outcomes* would need the stored response bodies in `content/` to confirm
case-by-case.

I tested one case directly. For the ONCB exemplar
(`8e1afe36-…`), `resources.jsonl` shows `final.dom` is only 90 bytes and marked
`not_available`, and both HTTP response bodies are `not_in_download`
(`size_decoded=0`). So for this scan the captured DOM is too small to contain a
harvested dataset, and the response content simply was not retained upstream.
This cuts two ways: it confirms README's warning that a smuggling URL does not
prove a successful read, and it means my success claims must stay at the level
of *attempted technique*. A full pass joining `local_path`/`sha256` for all
8,373 echo scans — filtering to DOMs whose size and MIME indicate a real JSON/
CSV payload — is the way to quantify how often exfiltration actually landed; I
scoped that as follow-up rather than assert it.

Extending the check across the whole family sharpens this into a firm result: of
all 8,373 echo scans, **every one has its `final.dom` marked `not_available`** in
`resources.jsonl` (0 available). The rendered DOMs for this entire technique are
absent from the collection — a systematic acquisition gap, not evidence of
failure. The consequence is important and I state it plainly: for the echo-
smuggling campaign I can prove the *inputs* (the executable payloads and their
targets) in detail, but I have **no captured output** to confirm or refute any
individual exfiltration. Anyone extending this work cannot recover those
outcomes from these files; they would need the upstream response store. A spot check of `http.jsonl`
confirms this: for a 4,000-scan sample of echo scans the transaction-0
`response.status` is `null` in every case, so neither the HTTP status nor the
body was retained for the smuggling requests.

## Finding 3 — A targeted attack on the scanning/analysis platform (`urlquery.net`)

A distinct, more serious sub-episode turns the tooling against the analysis
platform itself. Decoded rows reference `urlquery.net/api/htmx/apikey/new` (119
rows), `urlquery.net/api/htmx/user/login` (211 rows),
`urlquery.net/user/email/validate` and a VNC console path
`urlquery.net/static/vnc/core/rfb.js` + `wss://urlquery.net/queue/…/vnc`.

Two concrete payloads show intent:

1. **API-key minting via auto-targeted form** (scan
   `b7addfa5-bd63-4791-bc93-7057c764578d`, `submit.url.addr`). The Base64 body
   builds a hidden `<iframe name=i0>` and a `<form target=i0 method=POST
   action="https://urlquery.net/api/htmx/apikey/new?token=<JWT>">` with
   `apikey-name=[REDACTED]`. The embedded `token` is a JWT whose payload decodes
   to `{"collectionId":"[REDACTED]","exp":1781561368,"id":"[REDACTED]",
   "refreshable":true,"type":"auth"}` — a PocketBase user auth token. So the
   operator carries an authenticated session and uses the scanner to POST it,
   creating a persistent API key from within a scan.
2. **Operator-session hijack via VNC keystroke injection** (scan
   `d8baa8ef-f233-47ad-aecb-1d925bb5a914`, `submit.url.addr`, HTTP transaction 0
   loads it from `httpbun.com/base64/…`). The decoded module imports urlquery's
   own `rfb.js`, opens `wss://urlquery.net/queue/<id>/vnc`, then after a delay
   sends F6 and *types a `javascript:` URL* into the remote browser:
   `location='/backend/companies/61065761-…/publications?limit=100&offset=0'`,
   finishing with Enter. This scripts the platform's *interactive* analysis VM
   to navigate to an internal backend endpoint and read company publications.

This is a repeated sub-campaign, not a one-off: **97 distinct scans** carry
`urlquery.net` inside their decoded payloads, spanning login (172 decoded rows),
API-key creation (70), email request/validate (7) and VNC control (4). The login
payloads are auto-submitting credential forms, e.g.
`<form action="https://urlquery.net/api/htmx/user/login?…"> username=
[REDACTED EMAIL], password=[REDACTED] <script>forms[0].submit()`
— using a disposable `sharklasers.com` mailbox. Together the four payload types
sketch a full account lifecycle driven *through the scanner*: register/validate a
throwaway account, log it in, mint an API key, and remote-drive the operator VNC.
(Credentials/tokens are quoted only as inert evidence; they are not used.)
Crucially, the 36 scans whose payloads carry the login/apikey/VNC actions all
belong to the *same* dominant account `[submission ID A]` (0 from any other user
or from `null`), tying the platform-attack sub-episode directly to the bulk
scraping operation rather than to a separate actor.

**Why this matters.** These are not data-scraping payloads aimed outward; they
manipulate the scanning service's own authenticated surfaces (API-key creation,
a backend `/backend/companies/.../publications` route, and remote-control of the
VNC session). This is the most consequential activity in the corpus: an attempt
to escalate from "submit a URL" to "act as an authenticated operator / drive the
analyst's browser." **Uncertainty:** success is not shown — `http.jsonl` records
the payload being fetched (status fields null in the sampled rows), not the
platform's response to the forged POST or the injected keystrokes. Treat as a
demonstrated *technique and attempt*; outcome unproven.

## Finding 4 — Broad, methodical scraping of public statistical/dashboard sources

Beyond the echo trick, the account directly and via relays pulls large public
datasets. Evidence:

- **AIHW (Australia).** Tableau workbook views (`viz.aihw.gov.au/t/Public/views/
  AGE115_MentalhealthinAgedCare…`, `vizprod.aihw.gov.au/…/PBSdashboardallATC1-
  ATC2medicines-Agegroup`), plus report pages fetched repeatedly with a
  cache-busting `?rescan=NNNNN` query (tags `test`, scans around
  2026-06-18T11:21Z). Also `httpbingo.org/redirect-to?url=…viz.aihw.gov.au/…`
  and `www.google.com/url?q=…pp.aihw.gov.au/getmedia/…/a.zip` — using open
  redirectors to reach the dashboards.
- **UNCTADstat.** Hundreds of `datamart-api` `Facts` endpoints and CSV report
  files, plus Wayback `web.archive.org/cdx/search/cdx?url=unctadstat…pci-all.csv`
  to enumerate historical copies (`7803e891-…`).
- **Thrill Data** ride-wait graphs via `r.jina.ai` and `api.cors.lol`
  (`ridell?id=1580&dateStart=…`); **Mapillary** `graph.mapillary.com/images?
  bbox=…` via `allorigins.win`; **SEC** `sec.gov/files/county.json` via
  `cors.lol` and `markdown.new`; **max.gov / login.max.gov** SF-133 budget
  documents via `markdown.new`; **healthdata.org** `vizhub…/lbd/api` via
  `cors.bwa.workers.dev`; **UNM** IIIF image tiles via `cors.lol`.

Quantifying the routing: at least **10,777 scans** (~28% of the corpus) go
through an echo endpoint or a proxy/relay — `markdown.new` (1,001), `r.jina.ai`
(564), `web.archive.org` (449), `api.cors.lol` (233), `httpbingo.org` (150),
`allorigins.win` (124), `cors.bwa.workers.dev` (113), plus Google's `/url`
redirector — the rest hitting targets directly. That is a large, deliberate
fraction relying on intermediaries whose main function is to strip origin/CORS
controls or convert gated pages to plain text.

The consistent signature — numbered/enumerated resource IDs, cache-busting,
Wayback fallback, multiple interchangeable CORS relays for the same target — is
characteristic of **bulk data collection that routes around origin
restrictions**, using the scan service as disposable, geographically varied
egress. The `markdown.new/whssgr.com/history/` cluster (≈500 scans) and
`datastudio/lookerstudio.google.com/reporting/beb9619f…` (≈650 scans) fit the
same "render a gated view through a converter" pattern.

## Finding 5 — Submission tags reveal iterative tooling development

Only a few hundred scans carry `submission_tags`, but they are informative
because they are the operator's own labels. The most common are versioned:
`v0`–`v9` (57, 55, 46, 40, 37… down to 6), almost all dated 2026-06-20 and
pointed at throwaway targets `example.com`, `pie.dev`, `httpbin.org` and
`httpbingo.org`. This is the signature of someone **iterating payload versions
against sacrificial endpoints** — building and regression-testing the smuggling
technique, not collecting data. Other tags name concrete jobs:
`pbschunk` (56) and `pbsjob` (7) both point at `aihw.gov.au`/`httpbun.com` and
correspond to chunked harvesting of Australia's PBS (Pharmaceutical Benefits
Scheme) dashboards; `test`/`research`/`mel2`/`melbourne`/`csvhorsham` (Victoria/
Australia placenames) also cluster on AIHW; `cfbulk` (24, from 2026-06-16)
targets `workers.cloudflare.com/playground` with an identical encoded snippet,
suggesting the operator was also prototyping a Cloudflare Worker as an
alternative relay. The `openphish` tag (Finding 6) stands apart from all of
these. The tag chronology (cfbulk 06-16 → test/research 06-18/19 → version
sweep 06-20/21) reads like a short, intense build-and-run push in mid-June 2026,
consistent with the overall volume curve. **Caveat:** tagged scans are a tiny,
self-selected slice (<2%), so this is suggestive of workflow, not a measured
breakdown of the whole campaign.

## Finding 6 — A separate, older phishing/benign stratum (do not over-merge)

Not everything shares the scraping actor. The earliest rows are ordinary:
`b0921af8-…` (2023-09) is a marketing click-tracker redirect
(`is-tracking-link-api-prod.appspot.com` → `smartenergydecisions.com`) with
normal Google Analytics `collect` beacons in `http[18]` — benign. `9e4a9857-…`
(2023-10) is a plain load of `hummeldumm.com`.

There is also at least one **genuine credential-phishing** record with the
`openphish` tag: scan `7a5f32b3-59d3-49a0-88f6-219f1962fde8` (2026-05-28),
initial URL `saraghrar.scholarlumni.info/ga/click/…` redirecting to
`hallfieldschoolpta.info/PL-1466-160526/?u=[REDACTED]&e=[REDACTED]…`,
title `Oferta specjalna: 90–95% taniej`. Notably the pre-filled victim address
`[REDACTED EMAIL]` ties the lure to a UNCTAD mailbox — the same
organisation whose public API the bulk-scraping account harvests. This could be
coincidence (UNCTAD is a large target) or a faint thematic link; the evidence
does not support asserting a shared operator — and this phishing scan carries
`submission_user_id=null`, not the dominant account, so on the recorded metadata
it is a *different* submission origin. I flag it as a **counterpoint to
single-actor framing**: the corpus mixes an automated data-harvesting/platform-
abuse campaign with conventional phishing submissions and mundane loads.

## Mechanisms in plain terms

It is worth stating how the pieces fit, because the individual services are
benign and only the *composition* is abusive. A URL-scanning service exists to
visit a submitted URL in a real browser from the service's own infrastructure
and record what happens. Three properties make it attractive to misuse: it runs
untrusted pages for you, it egresses from the service's IP addresses (not the
submitter's), and it will render whatever a URL returns. The operator exploits
each property.

*Property one — arbitrary code execution.* Echo endpoints such as
`httpbin.org/base64/<b64>` will decode any Base64 and return it as a page. By
encoding a small HTML+`<script>` document, the submitter gets the scanner to
execute code of their choosing. The script does the real work: it `fetch()`es a
data API and copies the response into `document.body`, converting a network read
into visible page content the scanner records.

*Property two — origin laundering.* Browsers block cross-origin reads (CORS), so
a page on `evil.example` cannot normally read `unctadstat-api.unctad.org`. But
running from an `httpbin.org` origin, or funnelling the request through a relay
that adds permissive CORS headers (`api.cors.lol`, `api.allorigins.win`,
`cors.bwa.workers.dev`) or a text-extractor (`r.jina.ai`, `markdown.new`),
sidesteps the restriction. Wayback (`web.archive.org/…id_/…`) and Google's
`/url?q=view-source:…` redirector serve the same purpose for cached or
view-source fetches.

*Property three — trusted, disposable egress.* Because requests leave from the
scanner's addresses and rotate across many echo/relay hosts, target sites see
diffuse, reputable-looking traffic rather than one hammering client — useful for
staying under rate limits and blocklists.

The `urlquery.net` sub-episode (Finding 3) is the same three properties turned
inward: the executed script targets the *scanning platform's own* authenticated
routes, so the scanner is tricked into acting as a logged-in operator against
its host. That is why I rank it the most serious activity even though its
outcome is unconfirmed.

## Alternative explanations weighed

1. **"Legitimate researcher/journalist doing open-data collection."** Plausible
   for Finding 4 in isolation — the sources are public statistics. But the
   Finding 2 origin-laundering and especially the Finding 3 attacks on
   `urlquery.net`'s own auth/API/VNC surfaces are not what benign scraping
   requires. The platform-abuse payloads push the interpretation toward
   deliberate misuse of the service, at minimum ToS-violating and
   access-escalating.
2. **"Security analyst detonating hostile samples."** The `test`/`research`
   tags and the deliberate, hand-crafted payloads could be an analyst studying
   these techniques. This cannot be excluded. However, the industrial *volume*
   (20k+ scans/month), enumeration of real dataset IDs, real embedded auth JWT,
   and cache-busting argue for live collection/operation rather than sandbox
   study. I hold this as a real alternative for the smuggling subset.
3. **"Many unrelated users, artifact of grouping."** README warns
   `submission_user_id` is unauthenticated. The tight temporal clustering,
   shared subscription key, shared payload templates and shared target list are
   strong internal-consistency evidence for a small number of coordinated
   workflows — but "one person" remains an inference. I attribute *coordinated
   activity*, not an identity.
4. **"Timestamps/records fabricated."** Times are 2026-dated and cannot be
   checked offline; the collection is explicitly selected. Selection effects
   could over-represent the dominant account (e.g. if the corpus was built
   *around* it). I therefore avoid population-level claims ("X% of the web").

## What is demonstrated vs. inferred

- **Demonstrated (from data):** the account concentration and time profile
  (Finding 1); existence and executable content of Base64 payloads that `fetch`
  named third-party APIs (Finding 2); the urlquery API-key form with a real
  PocketBase JWT and the VNC keystroke-injection module (Finding 3); direct/
  relayed requests to specific public datasets (Finding 4); at least one phishing
  and several benign records (Finding 6).
- **Inferred (motive/identity/outcome):** that one actor drives the bulk of it;
  that the aim is data collection and platform escalation; and that any given
  `fetch`/POST/keystroke *succeeded*. Success requires the response bodies in
  `content/`, which I did not exhaustively join per target within budget — a
  clear next step.

## Missing data, selection effects, counterevidence

Thousands of scans resolved to `Problem loading page`, `503`, `404`, or private-
tab placeholders — many attempts failed or were not captured, so exfiltration
counts would be upper bounds on *attempts*, not confirmed reads. README notes
`not_in_download`/`not_available` distinctions and that empty script data with
positive size is *missing*, not observed-empty; I did not treat missing content
as evidence of failure. The pre-2026 benign records and the `openphish` phish
are genuine counterevidence against a monolithic-campaign reading and are
reported as such.

## Overall assessment

Weighing the evidence, the most important and best-supported story is a single,
mid-2026, high-volume workflow (account `[submission ID A]`) that used a public
URL-scanning service as programmable, origin-laundering egress — first to
prototype payloads against sacrificial hosts, then to harvest numbered public
statistical resources at scale, and, most seriously, to drive authenticated
actions against the scanning platform's own account, API-key and VNC surfaces.
This is an operational-abuse story, not a malware-detonation or reputation-check
story, and it should not be conflated with the small, older benign loads or the
one genuine phishing submission that also sit in the corpus. The strongest
claims rest on directly decoded payloads and full-corpus counts; the weakest —
identity, ultimate motive, and whether any exfiltration or platform action
actually succeeded — remain open, chiefly because the collection systematically
lacks the response/DOM bodies that would settle them.

## Recommended verification (offline)

1. Join `content/<sha256>.txt` to the Finding-2 scans to confirm which target
   API bodies were actually materialised (look for JSON/CSV payloads inside
   pages served from echo origins).
2. In `http.jsonl`, inspect response status/headers for the urlquery
   `apikey/new` POST and `queue/…/vnc` transactions to test whether the platform
   accepted the forged actions.
3. Cluster payload templates (hash the decoded script skeletons) to quantify how
   many distinct "programs" the operator used and their time order.

## Appendix — key evidence pointers

- Account/volume: `scans.jsonl`, group by `submission_user_id`
  (`[submission ID A]`=33,104) and `scanned_at[:7]`.
- Echo-smuggling exemplar: scan `8e1afe36-ee38-44de-8f2f-de01ecc9ac17`,
  `decoded_text.jsonl source_field=submit.url.addr` (ONCB `fetch`).
- urlquery API-key form + JWT: scan `b7addfa5-bd63-4791-bc93-7057c764578d`,
  `submit.url.addr`; JWT payload `id=[REDACTED]`, `exp=1781561368`.
- urlquery VNC keystroke injection: scan
  `d8baa8ef-f233-47ad-aecb-1d925bb5a914`, `submit.url.addr`; loaded at
  `http.jsonl` transaction_index 0 from `httpbun.com/base64/…`.
- Data scraping: AIHW `?rescan=` scans ~2026-06-18T11:21Z (e.g.
  `7ccdb393-046b-4cf3-8de1-b98f2df81ce7`); Wayback CDX `7803e891-4d77-…`;
  Thrill Data via `r.jina.ai` (`c9721695-9456-…`).
- Phishing: scan `7a5f32b3-59d3-49a0-88f6-219f1962fde8`, tag `openphish`, lure
  address `[REDACTED EMAIL]`.
- Benign baseline: `b0921af8-4f6a-4557-b9d8-604ee8b6e87c` (2023, analytics),
  `9e4a9857-526d-4808-9bd1-5dff5960473d`.
EOF
