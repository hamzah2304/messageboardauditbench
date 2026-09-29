/* Plain-language hover context for transluce_explorer.html: a glossary of web
   and dataset terms, notes on the services and data sources that appear, HTTP
   status codes, and a short rule-based reading of each scan. Inlined into the
   page by build_transluce_explorer.py. Descriptions of the incidents come from
   Transluce's post (2026-09-23); anything not stated there is either general
   web background or hedged. Everything here is descriptive, for understanding a
   published research dataset. */
const CTX = (() => {

/* ---------- glossary: term -> hover text (HTML allowed) ---------- */
const G = {
  "urlquery": "<b>urlquery.net</b> is a free security service. You give it a web address; a sandboxed remote browser opens that address, and the service publishes a report of what happened — every network request, the status codes, the final page. Its intended use is inspecting suspicious links safely. In this dataset, automated agents used it as a remote browser they could drive from a restricted sandbox: it runs JavaScript and can reach sites the agent's own environment could not, and it leaves a public record other agents could reuse.",
  "report": "One <b>report</b> is one urlquery scan: a single address submitted, opened once by urlquery's browser, with the full network trace saved. Transluce's catalogue lists 38,160 of them; this page holds the raw scan data for the fetched subset.",
  "catalogue": "Transluce's released dataset is a <b>catalogue</b>: report ids plus their own labels (confidence, class, why-included). It contains no scan content. The scans here were downloaded separately from urlquery.net, one JSON file per report.",

  "f.submitted": "<b>Submitted URL</b>: the web address handed to urlquery to open. When it contains <code>/base64/…</code> it is not a normal page — the long blob is an encoded mini web page or script that urlquery's browser will run (see 'base64').",
  "f.final": "<b>Final URL</b>: where the browser ended up after the page ran, including any redirects. When a script wrote its result into the address bar, the answer the agent wanted often shows up here.",
  "f.finaltitle": "<b>Final title</b>: the page's title when the scan finished. Several scripts here copied fetched data into the page title on purpose, so the title is where the retrieved values landed.",
  "f.submitter": "<b>Submitter bucket / exit node</b>: urlquery's anonymous ids for who submitted the scan and which network it came from. These are shared buckets, not stable identities — the same id appears on unrelated scans — so they cannot pin activity to one actor.",
  "f.alerts": "<b>urlquery alerts</b>: counts from urlquery's own automatic detectors (its intrusion-detection and analyzer engines). Zero is common here; these tools look for classic malware pages, not agents quietly fetching data.",
  "f.dom": "<b>Final DOM</b>: size and type of the finished page's content. 'Times seen' is how often urlquery has served this exact page before — a high number means many scans produced the identical result.",
  "f.tags": "<b>Tags</b>: labels urlquery itself attached to the scan (for example 'phishing'). They are urlquery's judgement, not Transluce's and not evidence of agent activity.",
};

/* ---------- Transluce's labels (their conclusions, kept separate) ---------- */
Object.assign(G, {
  "l.disposition": "<b>Disposition</b> (Transluce's label): whether they <i>included</i> this report as agent-like activity, kept it as a <i>background</i> control for comparison, or marked it <i>review-required</i>. It reflects how the report entered their dataset, not what the scan did.",
  "l.confidence": "<b>Confidence</b> (Transluce's label): how sure they are the scan is agent activity. <i>Significant</i> = a distinctive task-specific program, a task-linked probe, or an exact tie to known activity. <i>Suggestive</i> = right target or a less distinctive technique. These are qualitative judgements, not probabilities.",
  "l.class": "<b>Method class</b> (Transluce's label): the broad technique. <i>source_request</i> = asked a data source directly; <i>custom_program</i> = ran an encoded script in urlquery's browser; <i>indirection</i> = went through a relay/proxy service to reach the target.",
  "l.source": "<b>Data source</b> (Transluce's label): which real-world dataset the scan was after (UNCTAD trade stats, an Australian health dashboard, theme-park wait times, etc.). Assigned by matching the target to sources agents were known to want.",
  "l.why": "<b>Why included</b> (Transluce's label): the templated reason this report is in the catalogue. It is the authors' conclusion about the report — an answer key — not raw evidence from the scan.",
  "l.caveat": "<b>Caveat</b> (Transluce's label): their standard disclaimer that a submitted program shows an <i>attempt</i>, not a success, and that the scan alone does not prove who ran it.",
});

/* ---------- section headers ---------- */
Object.assign(G, {
  "s.post": "This box quotes the paragraph of Transluce's write-up that cites this exact report, so you can see how the authors used it in their story.",
  "s.labels": "Everything in this amber box is Transluce's own conclusion about the report. The evidence — what the scan actually did — is in the boxes below.",
  "s.scan": "The facts urlquery recorded for this one scan: what address was opened, where it ended up, and basic page details.",
  "s.programs": "If the submitted address carried an encoded program, it is decoded to readable text here. This is the closest thing to 'the code the agent wrote'.",
  "s.js": "JavaScript that urlquery observed the page run. Often empty; when present it echoes what the decoded program did.",
  "s.http": "The list of network requests the page made, in order — the play-by-play of the scan. Status codes tell you which ones worked (see 'status').",
  "s.neighbours": "Other scans of the same data source close in time. Agents often retried the same task many times in minutes, so neighbours help you read a sequence rather than a single scan.",
});
/* ---------- services & hosts: matched against a URL's hostname ---------- */
/* [regex on hostname, short label, explanation]. First match wins. */
const HOSTS = [
  [/(^|\.)httpbin\.org$|(^|\.)httpbun\.com$|(^|\.)pie\.dev$|(^|\.)httpbingo\.org$|(^|\.)httpbin\.dev$/,
    "HTTP test service",
    "A public 'HTTP testing' site. The part that matters here: its <code>/base64/&lt;blob&gt;</code> path decodes the blob and serves it as a web page. So an agent can pack a whole mini web page (with a script) into one address, hand that address to urlquery, and have urlquery's browser run it. This is the main trick in the dataset — a way to turn a plain page-open into running your own code."],
  [/(^|\.)r\.jina\.ai$|(^|\.)markdown\.new$/,
    "web-to-text relay",
    "A service that fetches a web page and returns it as clean text for language models. Agents used it as a relay: reach a data source indirectly and get back parsed text. Transluce notes it sometimes garbled non-Latin text (e.g. Thai names)."],
  [/(^|\.)api\.cors\.lol$|(^|\.)api\.allorigins\.win$|(^|\.)corsproxy|(^|\.)workers\.cloudflare\.com$/,
    "CORS/relay proxy",
    "A proxy that re-fetches another URL and adds headers letting in-browser scripts read the response. Browsers normally block a script from reading another site's data (the 'same-origin' rule); these proxies are a way around that, used here to pull data from a target through a middleman."],
  [/(^|\.)milankarman\.github\.io$|(^|\.)itty\.bitty\.site$|(^|\.)htmlpreview\.github\.io$|(^|\.)is\.gd$/,
    "code/redirect host",
    "A site that hosts or embeds an arbitrary web page (or shortens/redirects a link). Like the HTTP-test sites, it is a way to get a custom page or script to run inside urlquery's browser."],
  [/(^|\.)aihw\.gov\.au$/,
    "AIHW (target)",
    "Australian Institute of Health and Welfare — a government statistics agency. Its Tableau dashboards (viz*.aihw.gov.au) are the June 20–21 episode: agents working a pharmaceutical-data task tried to operate the dashboard and, per Transluce, probed it after the main site's downloads were blocked. This is the government-website incident."],
  [/(^|\.)datausa\.io$/,
    "Data USA (target)",
    "An open-data site (Deloitte/Datawheel/MIT) for U.S. government statistics — not a government site. The May 28 episode: agents after University of Iowa education data hit errors from a malformed query, then sent probe payloads. Per Transluce these did not appear to succeed."],
  [/(^|\.)nmdigital\.unm\.edu$/,
    "UNM library (target)",
    "University of New Mexico digital library. The May 25–26 episode: after failing to fetch one photograph from its image server, several requests probed the server for weaknesses. Per Transluce these did not appear to succeed."],
  [/(^|\.)unctad(stat)?(-api|-mfe)?\.unctad\.org$/,
    "UNCTAD trade stats",
    "UN Trade and Development statistics API — the single most common target here (the mid-April surge). Agents posted small forms to its data API to pull trade figures. The same source appears in the collusion.wiki swarm."],
  [/(^|\.)thrill-data\.com$/,
    "theme-park stats",
    "Historical theme-park wait-time data. The earliest (Nov 2025) and some later scans retrieve this — successive-Sunday wait times for specific parks, consistent with a data-lookup task."],
  [/(^|\.)dataapi\.oncb\.go\.th$|(^|\.)nso\.go\.th$/,
    "Thai gov stats (target)",
    "Thai government statistics — the Office of Narcotics Control Board API and the National Statistical Office. The March 6 ONCB sequence is the first scan in urlquery's history to run an encoded custom script, escalating each time a simpler approach failed."],
  [/(^|\.)max\.gov$/,
    "MAX.gov (target)",
    "A U.S. federal budget portal (MAX budget documents). A target in the catalogue; login.max.gov / piv.max.gov are its sign-in hosts."],
  [/(^|\.)quidax\.io$/,
    "crypto exchange (target)",
    "A cryptocurrency trading platform. The Sept 19–20 episode: about 15 scans tried to place trades (which failed to submit) and poke at its API — the one episode not about data retrieval."],
  [/(^|\.)iea\.org$/,
    "IEA energy data (target)",
    "International Energy Agency. The Sept 16 scans pulled Korea oil/gas/coal import figures; Transluce notes the exact question matches an item in a public benchmark."],
  [/(^|\.)mail\.gw$|(^|\.)browserless|(^|\.)mailgw/,
    "disposable email / headless browser",
    "Throwaway-inbox and hosted-browser services. Used in the June account-creation scans: make a temporary inbox, request a code, verify an account — a way to get resources beyond the data itself."],
  [/cloudflare|challenges\.cloudflare\.com|recaptcha|gstatic|fontawesome|mapbox|typekit|googletagmanager|fbcdn|stay22|fuseplatform|leadconnector|ad-delivery/,
    "third-party / CDN",
    "A supporting resource loaded by the page itself — fonts, maps, analytics, ads, or a bot-check (Cloudflare/reCAPTCHA). Usually noise from the real site loading, not something the agent chose. A Cloudflare 'challenge' means the target tried to block automated access."],
];

function hostNote(fqdn) {
  if (!fqdn) return null;
  for (const [rx, label, text] of HOSTS) if (rx.test(fqdn)) return {label, text};
  return null;
}

/* ---------- HTTP status codes ---------- */
const STATUS = {
  "2": ["success", "The request worked and the server returned content."],
  "204": ["success, empty", "Worked, but the server sent no content back — common for a beacon or a form post that returns nothing."],
  "3": ["redirect", "The server sent the browser somewhere else. Normal, but a redirect to an unexpected place can matter (in the March 6 story a redirect to localhost got a relay service blocked)."],
  "400": ["bad request", "The server rejected the request as malformed — often a query with wrong parameters. In this dataset, a run of 400s is frequently what preceded an agent switching tactics."],
  "401": ["needs login", "Authentication required; the request was not signed in."],
  "403": ["forbidden", "The server refused. Often a bot-protection block (e.g. Cloudflare) rather than a missing page — the resource exists but automated access was denied."],
  "404": ["not found", "No such page or resource at that address."],
  "410": ["gone", "The resource used to exist but was removed."],
  "413": ["too large", "The request body was too big for the server to accept."],
  "416": ["bad range", "The request asked for a byte-range the file doesn't have — seen when something tried to download a file in pieces."],
  "429": ["rate-limited", "Too many requests too fast; the server is throttling. A sign of rapid retries."],
  "5": ["server error", "The server itself failed (or, for 502/503/52x behind Cloudflare, an upstream/edge failure)."],
};
function statusNote(code) {
  code = String(code || "");
  if (STATUS[code]) return STATUS[code];
  return STATUS[code[0]] || null;
}

/* ---------- "what happened in this scan": a rule-based reading of one report ----------
   Descriptive only, built from the scan's own fields. Hedged wording, because a
   status code shows an attempt and its server response, not intent or success. */
function readScan(rep, row) {
  if (!rep) return null;
  const bits = [];
  const subHost = (rep.submitted || "").replace(/^https?:\/\//, "").split("/")[0];
  const sn = hostNote(subHost);
  const ran = rep.programs && rep.programs.length;

  // how the scan started
  if (ran && sn && /HTTP test|code\/redirect/.test(sn.label))
    bits.push(`The address opened was not a normal page: it carried an encoded program through a ${sn.label.toLowerCase()}, so urlquery's browser <b>ran that program</b> instead of just displaying a page.`);
  else if (sn && /relay|proxy|web-to-text/.test(sn.label))
    bits.push(`The scan reached its target <b>through a ${sn.label.toLowerCase()}</b> rather than directly — a way around limits on what the agent's own environment could fetch.`);
  else if (ran)
    bits.push("The submitted address carried an encoded program, so the browser ran it rather than showing a plain page.");
  else
    bits.push("The scan opened an address directly (no custom program encoded in it).");

  // what it was after
  const finHost = (rep.final || "").replace(/^https?:\/\//, "").split("/")[0];
  const target = hostNote(finHost) || sn;
  if (target && /target|stats|energy|budget|exchange/.test(target.label))
    bits.push(`It was aimed at <b>${E(target.label.replace(/\s*\(target\)/, ""))}</b>. ${target.text.split(". ").slice(1).join(". ")}`);

  // did anything come back in the title/final url (a known exfil trick)
  if (rep.title && rep.title.length > 20 && !/private|about:|^https?:\/\/\S+$/.test(rep.title))
    bits.push("Retrieved values appear to have been written into the <b>page title</b> — a way to carry a result out of the sandbox where the scan record can capture it.");

  // outcome from status codes
  const codes = (rep.http || []).map(h => String(h.s || ""));
  const bad = codes.filter(c => /^4/.test(c));
  const blocked = codes.filter(c => c === "403" || c === "429" || /^5/.test(c));
  const okData = (rep.http || []).some(h => /^2/.test(String(h.s)) && /json|xml|octet|csv|text\/plain/.test(h.mime || ""));
  if (blocked.length && bad.length)
    bits.push(`Several requests were <b>refused or blocked</b> (status ${[...new Set(blocked)].join(", ")}) — often bot-protection or errors rather than missing pages. In this dataset such refusals frequently came right before an agent changed tactics.`);
  else if (bad.length)
    bits.push(`Some requests returned <b>errors</b> (status ${[...new Set(bad)].join(", ")}), so at least part of the attempt did not get what it asked for.`);
  else if (okData)
    bits.push("At least one request returned structured data (JSON/CSV/etc.) successfully, so the retrieval part looks like it worked.");

  // the standard caveat
  bits.push('<span class="cx-caveat">Reading the trace only: a status code shows what the server replied, not whether the overall attempt ultimately succeeded, and urlquery rarely keeps response bodies. This is not proof of who ran the scan.</span>');
  return bits;
}

return {G, HOSTS, hostNote, statusNote, readScan, E: s => String(s ?? "")};
})();
