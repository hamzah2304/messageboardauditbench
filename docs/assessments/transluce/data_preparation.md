# What data will the agents receive?

Follow-up to your assessment comments · 26 September 2026 · Proposed design, not a built dataset

**We can download the public data and remove Transluce's annotations. Removing the annotations is easy; obtaining the underlying evidence is the additional step.** Transluce's ZIP contains a list of scan IDs and research labels. We use those IDs to download the corresponding public URLQuery records, then give agents a consistent, searchable version of those records. We do not give agents the ZIP's explanations of what they mean.

The proposed agent input is a read-only folder containing a scan index, HTTP transactions, mechanically decoded text, any available response content, and a short file-format guide. It contains no human report, findings, analyst labels, incident summaries, or wiki logs. This follow-up explains that folder, the transformations that produce it, and which findings are worth your time to extract.

Your other decisions are carried forward: **medium effort**, reuse the **same findings-extraction UI**, and call MessageBoardAuditBench the **original benchmark**. I counted the source report instead of retaining the earlier 5,000-word recommendation: it has **3,135 prose words including its six timeline descriptions**, under the exclusion rules below. I propose a **3,000–3,500-word report target**, with the existing short-report acceptance policy retained. None of these settings has been applied.

## Downloading the ZIP is the beginning of the transformation

| Stage | What exists at that stage | What we do | What the agent sees |
|---|---|---|---|
| 1. Transluce download | 38,160 scan IDs, timestamps, links, and investigator annotations | Read the union catalog once; deduplicate by scan ID | None of the annotated catalog |
| 2. URLQuery download | One public JSON record per available scan ID | Cache successful downloads; record errors and missing resources | Only fields admitted into the clean files below |
| 3. Deterministic cleanup | URLs, timestamps, request traces, metadata, sometimes retrievable resources | Keep observations; remove classifications; redact secrets consistently | Original observations and explicit missing-data indicators |
| 4. Mechanical text decoding | Percent-encoded URLs and programs embedded in URLs | Decode recognized encodings as text, keeping the original | Searchable text with links back to its source field |
| 5. Freeze the input | Clean files plus hashes and a completeness manifest | Check every retained record and pin one version | The same offline folder in every run |

The [Transluce ZIP](https://transluce.org/data/urlquery-agent-activity-2026-09-23.zip) has no scan JSONs, submitted target URLs, response bodies, or screenshots. Its `report_url` is a link such as `https://urlquery.net/report/<id>`, not the URL that an agent submitted for scanning. Removing its labels alone therefore cannot produce the intended benchmark input. The raw record is separately available at `https://urlquery.net/report/<id>/json`; the [earlier checks](evidence.json) verified two examples.

I recommend downloading the public records identified by the full catalog, caching them once, and doing all subsequent work offline. Retain all catalog dispositions for acquisition: do not download only records the investigators called significant. Freeze the list of missing records as well as the successful files. A failed download is an acquisition gap, not evidence of historical inactivity. A complete public JSON set may still lack bodies and screenshots; completeness must be tracked by resource type.

There is already a separate explorer/download effort in the workspace. Its subset includes report-cited scans, nearby scans chosen using source labels, and confidence-stratified samples. It is useful for inspecting examples. Its selection deliberately uses the investigators' conclusions, so hiding the labels in that explorer would not turn its subset into a blind benchmark. I inspected its existing files and selection code; I did not modify or restart it. We can reuse its cache when constructing the final input, with the final selection rule recorded separately.

## What to remove, and what must survive

The implementation should construct clean records from an explicit list of allowed fields. Merely deleting a few known keys from a large JSON risks carrying through another source of annotations. Keep untouched downloads and transformation records outside the agent's mount for reproducibility.

| Source field or file | Agent input | Reason |
|---|---|---|
| Catalog `report_id`, `report_url`, timestamp, timestamp precision | Keep as neutral identifiers/provenance; prefer the raw scan's event timestamp when present and record disagreements outside the input | These locate observations. |
| Catalog `disposition`, `confidence`, `broad_class`, `why_included`, `caveat` | Remove | These are Transluce's classifications and explanations. |
| `report-sources.csv`, daily counts, methods, selection provenance, supplemental classifications and confidence overrides | Keep outside the agent input | They reveal investigator grouping, search strategy, and decisions. Recompute neutral counts from retained records when needed. |
| Submitted URL, visited URL, final URL, page title, scan time | Keep | These record what was requested and returned. Preserve distinctions between the three URLs. |
| HTTP transaction time/order, URL, method, status, raw headers, recorded data sizes | Keep, subject to secret redaction | These support reconstruction of a sequence and its outcomes. |
| Original text inside URLs, programs, titles, or returned content | Keep | This is evidence, including self-descriptions, task values, and failures. |
| URLQuery detector results, alert classifications, analyst comments, service-generated tags/fingerprints | Exclude from the initial clean view | These add another analyst's interpretation. Their absence must not remove the underlying requests. |
| `submit.tags` | Hold out initially unless original-submitter provenance is established | A field called “tag” is not enough to establish who wrote it or when. Document the choice; do not use it for a required finding. |
| IPs and account-like IDs | Preserve needed raw observations with cautious field names; pseudonymize private identifiers consistently | A destination, scanner, shared account bucket, or relay is not an authenticated agent identity. Do not rename ambiguous metadata to “agent IP.” |
| Cookies, authorization values, passwords, one-time codes | Replace secret values with stable placeholders across occurrences | Preserve evidence that a credential was requested or used, and preserve joins, without handing agents usable secrets. |
| Absent response bodies, absent script bodies, unavailable resources | Explicit `not_in_download` / `fetch_failed` / `not_available` states | Missing content must not look like a successful empty response. |

**“Remove their tagging” must not become a text search that deletes every identity-like string.** In two inspected [May 13 scans](https://urlquery.net/report/1368e4a9-bae5-4120-ac25-aeab21a44ee5), [the recorded requests](https://urlquery.net/report/850d1c01-cbbf-4ca2-ad41-fb5de7bf7898) contain `CHATGPT…` markers in their submitted URLs and encoded content. The JSON's top-level tag arrays are empty and `submit.tags` is null. The proposed cleanup keeps these request strings because they are original observations. They may support a hypothesis; they do not authenticate an operator.

Redaction needs consistency across representations: a secret can occur in a URL, its Base64 payload, and a later HTTP request. Record a private mapping, preserve the nonsecret program structure and matching tokens, and check the decoded and encoded copies agree after transformation. Public target domains, dates, and task parameters should not be removed just because they are distinctive. Missing bodies cannot be reconstructed by copying the report's explanation into the input.

## The folder the agent opens

Use JSON Lines—one JSON object per line—so ordinary Python and text search work without a new tool. Store large content separately, with stable references. The following is a proposed layout, not files already generated for a trial:

```text
/work/data/
  README.txt                 File meanings, time units, citation format
  manifest.json              Dataset version, hashes, counts, missing-file counts
  scans.jsonl                One row per downloaded scan
  http.jsonl                 One row per recorded HTTP transaction
  decoded_text.jsonl         Generic text decodings with source-field references
  resources.jsonl            Content availability and file references
  content/<hash>.txt         Available content stored as inert text
```

The guide explains how to read these files, not what to find in them. It should not contain named incidents, a task-source taxonomy, a hand-selected list of interesting IDs, or the Transluce report URL. The manifest records this collection's coverage and missingness; it does not reproduce the investigators' confidence breakdown. The evaluator keeps the original catalog, source report, private downloads, full acquisition logs, redaction map, findings, and grades elsewhere.

| Clean file | Example fields | Why split it out? |
|---|---|---|
| `scans.jsonl` | `scan_id`, `scanned_at`, `submitted_url`, `visited_url`, `final_url`, `title`, transaction count | A compact index for searching and chronology. It should be usable without reading all headers or bodies. |
| `http.jsonl` | `scan_id`, `transaction_index`, `at`, `url`, `method`, `status`, headers, size, content reference | Agents can trace requests within a scan and compare scans. |
| `decoded_text.jsonl` | `scan_id`, `source_field`, `transforms`, `text`, parse status | Makes embedded text searchable without classifying it. |
| `resources.jsonl` | `scan_id`, source-field reference, resource hash, availability, local path | Distinguishes recorded metadata from content actually supplied. |

Sort scan rows by timestamp and ID, and preserve the original transaction order with its timestamps. Deduplicate catalog references by scan ID, not by submitted URL: repeated requests are often the evidence. Do not collapse near-duplicates or delete failed requests. For unusually large bodies, reference a content file instead of silently truncating the evidence.

### A real example of what this enables

For the [March 6 ONCB scan](https://urlquery.net/report/81699969-91c3-4454-913e-1a015b3fde47/json), the clean index would retain scan ID `81699969-91c3-4454-913e-1a015b3fde47` and time `2026-03-06T20:07:41Z`. The observed trace contains four HTTP transactions. The submitted URL embeds a program; another recorded URL includes returned data fields. A model can connect those observations without being told that this is the report's ONCB case.

This is the proposed *shape* of a decoded record; placeholders below are explanatory, not evidence:

```json
{
  "scan_id": "81699969-91c3-4454-913e-1a015b3fde47",
  "source_field": "submit.url.addr",
  "transforms": ["extract_base64_path", "base64_decode_utf8"],
  "text": "<the original decoded HTML/JavaScript, stored without execution>",
  "parse_status": "ok"
}
```

The agent receives the actual program text, not a generated summary saying it bypassed restrictions. The distinction matters: decoding is a reproducible format transformation; explaining the program's purpose is part of the investigation. In the earlier two-scan check, all nine response-body fields were null. The ONCB output is nevertheless partly visible in a recorded URL. That is why “body unavailable” does not imply “no recoverable outcome evidence.”

I recommend supplying generic percent-decoded URL text and supported Base64 text decodings for the first ten-minute runs. Apply the same rules to every record, preserve the original representation, cap decoding depth/expanded size with an explicit status, and leave unsupported formats available in their original form. Do not execute JavaScript, replay a request, infer a target inside arbitrary code, or generate incident labels. This makes the benchmark focus more on investigation than decoding syntax; record that choice as part of the dataset version. A later raw-only condition can measure the effect of the convenience view.

## Which findings should you extract, narrow, or skip?

Your manual workflow should stay the same: select a passage in the human report, write a candidate finding, then review its feasibility. Before you do that, use the following distinctions. They apply to the proposed URLQuery-only input; they are not final certifications of every cited sequence.

| Action during extraction | Kinds of finding | What the data can establish |
|---|---|---|
| **Extract** | Request mechanisms; encoded programs; targeted resources; probe categories; observed chronology | Directly recoverable when the relevant records and text are in the frozen input. These are the strongest starting points. |
| **Extract, then narrow** | Retrieval failure followed by a probe; alternate-host retrieval; account creation; trading attempts | Keep the observed actions separate from claimed completion, intent, and inferred common actor. Full sequences may need more than a single cited scan. |
| **Extract only with bounded wording** | No visible successful exploitation; concentration or decline in activity | Bound success claims to the available observations and counts to the selected collection. Do not claim universal failure or the end of all agent activity. |
| **Skip in the initial rubric** | Matches to wiki posts; shared wiki/URLQuery operator; an exact match to a DeepSearchQA question; equality with an external paste | These compare against another corpus. They need those sources supplied too. Occasional self-descriptions in raw URLs do not substitute for the missing comparison. |
| **Skip as required conclusions** | Provider acknowledgement; official announcements; private disclosure dates; authenticated operator attribution | The URLQuery collection alone does not establish these external facts. An attribution hypothesis can still be discussed and assessed for calibration. |
| **Skip as established facts** | Learning across training runs; private activity totals; all agents sharing an operator; real intent or training objective | Observed requests can motivate hypotheses, not establish those hidden facts. |

For example, split “created an account to hide further activity” into (a) evidence of signup attempts, (b) evidence the signup completed, and (c) the proposed purpose. The first may be directly visible, the second needs an outcome, and the third remains an interpretation unless separately evidenced. This avoids spending time polishing a claim the chosen input cannot support.

Before opening the extraction UI, produce a short coverage checklist for the main incident sequences: required IDs present, code decodable, errors visible, outcomes visible, and outside sources required. This is a preparation check, not automatic extraction. In the existing UI, show the checklist and add a scope note to each candidate; retain the familiar selection/comment/approval flow. Keep its report anchors, exports, browser state, and saved decisions separate from the original benchmark. The new data explorer can help inspect records; it should not replace your findings-extraction UI.

## Report length, counted rather than guessed

I counted the saved [Transluce report](https://transluce.org/agent-activity), including all eight collapsed sections. The [reproducible count](source_word_count.json) excludes quotes and code/data excerpts, full-URL margin notes, citation markers, title/headings, author information, site controls, captions, chart labels, and the overview graphic. Inline domain names in prose remain. The six timeline descriptions are counted separately because they repeat some of the surrounding narrative. Standalone punctuation does not count as a word.

| Counted material | Prose words |
|---|---:|
| Main article, including introduction, key findings, summary, and all incident sections | 2,456 |
| Appendix | 421 |
| Footnote prose after excluding quoted material and URL citations | 81 |
| Body prose subtotal | **2,958** |
| Six March 6 timeline descriptions | 177 |
| Body plus timeline prose | **3,135** |

These are counts under an explicit extraction rule, not a claim that every possible word counter agrees. The report also contains graphic labels and an overview graphic, which are not counted as running prose. Both saved HTML copies in the workspace have the same SHA-256; the count uses that pinned snapshot, not a newly changing page.

Based on the 3,135-word count, propose `report_min_words=3000`, `report_max_words=3500`, `report_accept_min_words=0`, and `report_accept_max_words=3600`. That gives room for short ID citations and headings while staying close to the human report's prose length. The existing agent counter includes those elements; the human-source count deliberately excludes excerpts. This is an approximate length match, not identical counting rules. Keep nonempty shorter reports valid, and set `effort="medium"`. The ten-minute budget still includes report writing. These supersede my earlier high-effort and 5,000-word suggestions.

## What is easy, and what the build must verify

Deleting researcher labels, reshaping JSON, sorting records, and producing generic decodings are ordinary deterministic scripting work. The main uncertainties are missing public resources, consistent secret redaction across encodings, and whether enough complete sequences survive. The two-scan evidence check and the additional marker checks show this design is technically plausible; they do not establish full-corpus availability.

Before a trial, verify that every clean record traces back to a cached file; scan IDs, timestamps, transaction ordering, and nonredacted evidence survive; annotations and source-report text are absent from the mount; decoding errors and unavailable bodies are explicit; and every required finding can be supported using only the exact frozen input. No hand-authored episode clusters or analyst-selected “important records” should enter the agent folder. Test the mount and preflight against the new manifest without changing the original benchmark's accepted files.

Downloading and local cleanup are the intended acquisition route. Public redistribution remains a separate question under [URLQuery's terms](https://urlquery.net/terms-and-conditions); this write-up does not make outreach a prerequisite for explaining or designing the transformation. The existing explorer's data, including its labels, must remain outside the trial mount.

The proposed next sequence is: review this design; build and verify the clean snapshot plus the short finding-coverage checklist; reuse the original findings UI for your manual extraction; validate and freeze the rubric; then run the ten-minute, medium-effort pilot. This turn produced the write-up and the word-count audit. It did not build the agent dataset, modify the parallel download, refactor the benchmark, or launch model runs.

## Sources and reproduction

The [initial assessment](assessment.md) and [its evidence audit](evidence.json) document the catalog and two raw scans. Your [six comments, with replies](review_replies.json) are retained separately. The proposed data layout and transformation rules here are recommendations, not an existing API contract.

Run the count with the existing environment:

```sh
.venv/bin/python docs/assessments/transluce/count_source_prose.py \
  /private/tmp/transluce-agent-activity.html \
  --output docs/assessments/transluce/source_word_count.json
```

The script uses the already-installed BeautifulSoup 4.15.0. Source HTML SHA-256: `5825b43741d51705e52c5f25c18e81dc3726851926bfb8048197546842e0fbc5`. The additional marker checks read the existing local cache for `1368e4a9-bae5-4120-ac25-aeab21a44ee5` (SHA-256 `027e00946e8e51e438843419a8985ac8e95b123fec831fca3f78eb0a87db0321`) and `850d1c01-cbbf-4ca2-ad41-fb5de7bf7898` (SHA-256 `6162bb3ab9b8c37dd28e489754a335a999938ce5d0c14c18f1d1d34e82b39940`). Explorer selection logic was read from `scripts/fetch_transluce.py` at commit `4a780ef` on the separate explorer branch. No full-corpus availability rate is inferred from those checks.
