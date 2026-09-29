# Can the Transluce report support a new investigation benchmark?

Assessment · 26 September 2026 · No model trials run

**Yes, conditionally: keep the investigation-and-report methodology, but acquire the evidence before running a pilot.** The released ZIP is an annotated catalog, not a usable blind investigation dataset. I verified its contents and fetched two cited scans as JSON. Those scans contain useful evidence, so this is a tractable data-preparation problem, not a reason to abandon the benchmark.

I recommend a separate URLQuery benchmark on the existing infrastructure, initially using only archived URLQuery evidence. Extract the findings manually with the existing report UI, then validate them against the exact frozen input. My planning estimate is **15–20 candidate findings, with perhaps 12–18 surviving feasibility review**. That is enough for an exploratory pilot, although neither the count nor the difficulty has been validated yet. Do not force the new rubric to match the old benchmark's 38 findings.

| Your question | Assessment | What must happen before a scored pilot |
|---|---|---|
| Is the data suitable? | The underlying scans look suitable; the ZIP alone is not. | Freeze raw scans, remove investigator annotations, and establish evidence coverage. |
| Does the methodology need an overhaul? | No. Preserve blind investigation, manual findings, feasibility review, and report grading. | Define what the input can establish; grade uncertainty and unsupported assertions explicitly. |
| Which settings change? | Dataset, prompt, rubric, report ceiling, file validation, and output destinations. | Use a separate benchmark identity throughout the pipeline. |
| Are there enough findings? | Probably for a pilot; uncertain for a stable model ranking. | Approve at least 12 nonredundant, supported findings spanning at least five families. This is a proposed gate, not an established statistical threshold. |

## The download is an answer-bearing catalog

The [public release](https://transluce.org/data/urlquery-agent-activity-2026-09-23.zip) contains 16 files and no individual scan JSONs. I checked all 15 file hashes listed in its manifest; all matched. The union catalog contains 38,160 unique report IDs: 38,078 main rows and 82 supplemental rows, with no overlap. These are measurements from the downloaded files, reproduced in [the evidence record](evidence.json).

The catalog has nine columns: `report_id`, `report_url`, `report_date_utc`, `timestamp_precision`, `disposition`, `confidence`, `broad_class`, `why_included`, and `caveat`. Its URLs point to scan reports, not to the originally submitted target URLs. Removing the last five columns therefore leaves identifiers, report links, and timestamps—not the requests needed to investigate the incident.

The remaining files include source assignments, daily counts, collection rules, and review decisions. Keep them on the evaluator side. They reveal what investigators selected and concluded. In particular, `raw_json_preserved: 38160` in the collection summary describes an upstream private archive; the release's README explicitly says those raw files are not included.

The catalog classifies 37,649 reports as included, 79 as background, and 432 as requiring review. These are researcher decisions, not verified actor identities. Stripping the labels also does not undo the selection: the input remains a collection assembled around suspected activity. Frame the task as investigating a selected collection; do not score population-wide prevalence or treat an empty day as proof that all agent activity stopped. The earliest catalog timestamp is in 2023, which is likewise not evidence that agents were active then.

### Public scan JSONs provide a plausible acquisition route

I downloaded two report-linked scans, selected deliberately to test different evidence types. This is a spot check, not a random availability sample.

| Public scan | What I independently observed | What remains unsupported by this check |
|---|---|---|
| [AIHW probe](https://urlquery.net/report/52e02785-083a-4bca-915c-28e1c7bfce01/json) | Submitted probe URL, Cloudflare page title, five HTTP transactions including two 403 responses. | Complete surrounding sequence, all response contents, and a universal claim that exploitation failed. |
| [March 6 ONCB retrieval](https://urlquery.net/report/81699969-91c3-4454-913e-1a015b3fde47/json) | Encoded program in the submitted URL; four transactions; a recorded output URL containing returned data fields. | Every step in the reported escalation sequence and completeness of the returned dataset. |

Across these two JSONs, all nine response-body fields and both final DOM-body fields are null; all seven script-body entries are empty. The submitted URL can still contain a program that can be decoded as text. A `resource_available` flag sometimes indicates a separately retrievable resource, but I did not verify those downloads. Do not equate an available JSON endpoint with a complete evidence archive.

Use frozen URLs, timestamps, request methods, response statuses, headers, and any actually available content. Preserve raw bytes privately and record missing resources explicitly. Decode payloads offline without executing them. Do not visit the submitted target URLs or replay the historical probes. A small neutral schema guide can explain where scan fields live without explaining the incident.

Before bulk acquisition or redistribution, resolve the release route with the data owners. [URLQuery's current terms](https://urlquery.net/terms-and-conditions) restrict reproduction/distribution and commercial use, and describe automatic deletion. A fetch-at-build-time script does not by itself settle permission or long-term reproducibility. A permitted bulk export from Transluce or URLQuery would be preferable to relying on thousands of live links. No outreach or bulk crawl was performed for this assessment.

## Keep the method, make the evidence boundary explicit

The [existing benchmark](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/README.md) already has the right structure: give agents a fixed corpus, withhold the human report, let them investigate, and grade against manually selected findings that the corpus can support. Here the work shifts toward decoding requests and reconstructing sequences. That adds a useful capability test while preserving the core task.

Start with **URLQuery-only evidence**. A later, separately named condition can add the existing wiki logs and frozen external reference material. That condition would test joining sources, but it would overlap more strongly with MessageBoardAuditBench. Separate storage prevents accidental mixing; it does not make the incidents or their evidence statistically independent.

Three grading changes matter:

1. **Credit the strongest conclusion supported by the available evidence.** A submitted probe, a returned page, a successful retrieval, and a compromised server are different claims. A 200 response is not proof of exploitation; an absent body is not proof of failure. A sequence consistent with an agent adapting to errors does not authenticate its operator or reveal its training objective.
2. **Restrict the answer key as well as the findings.** Giving the summary judge the full published narrative can penalize an appropriately cautious URLQuery-only report for omitting outside attribution. Retain the original human report as provenance, but give the judge a scope-matched reference and explicit exclusions. Audit unsupported assertions separately from finding coverage; a report should not benefit merely by repeating the expected story.
3. **Validate the judge on this domain.** Manually score a spread of pilot reports before viewing judge scores, include attempted-versus-successful cases, and inspect disagreements. The [blog post](https://www.lesswrong.com/posts/wt4kk6vFPEhkXvF8Q/how-good-are-slop-vestigators) describes both coverage and summary grading, but its calibration does not establish reliability on URL traces. Keep the existing 70/30 composite as a provisional secondary view; show its components and unsupported-claim counts. Incomplete grading should not silently shrink the denominator.

Public release also creates a contamination risk. An offline agent may already know the report from training. Record model/version dates, require citations to the supplied records, and avoid interpreting report agreement alone as proof of fresh discovery. This assessment does not measure contamination.

## There is enough candidate material to justify extraction

The following is a compact inventory of candidate targets from the [Transluce report](https://transluce.org/agent-activity), not a completed rubric. The target descriptions below summarize the report; the evidence requirements and inclusion decisions are my recommendations. Only the two spot checks above were independently inspected in raw form in this assessment.

| Candidate target | Evidence needed in the frozen input | Proposed treatment |
|---|---|---|
| 1. Remote-browser relay use | Submitted URLs and outgoing transactions | Core; establish behavior before inferring restrictions. |
| 2. Encoded programs and output relays | Recoverable code and recorded outputs | Core; partial spot check. |
| 3. ONCB escalation | Complete chronological sequence | Core if earlier attempts can be evidenced. |
| 4. UNM retrieval-to-probe sequence | Related requests, timing, error evidence | Core; one incident-level finding. |
| 5. UNM request burst | Decoded loop and/or observed transactions | Distinguish programmed count from executed count. |
| 6. Data USA retrieval-to-probe sequence | Related requests and outcomes | Core; do not create one point per payload. |
| 7. AIHW blocked probe | Probe and outcome records | Core; partial spot check. |
| 8. AIHW alternate-host retrieval | Requests, content identity, chunk evidence | Conditional on outcome evidence. |
| 9. Task-driven escalation | Multiple supported incident sequences | Synthesis point; avoid double-weighting details. |
| 10. Collection timeline | Frozen timestamps and documented coverage | Describe this collection only. |
| 11. Disposable inbox/account attempts | Linked programs and observed responses | Score attempts separately from completed signup. |
| 12. Browserless account sequence | Linked requests and success evidence | Completion requires more than submitted code. |
| 13. September energy-data retrieval | Requests, decoded program, output trace | Exclude benchmark-question attribution initially. |
| 14. Crypto-platform activity | Related requests and recorded outcomes | Bound claims about executed trades. |
| 15. Earlier ambiguous retrieval | Earlier records and comparison cases | Reward calibrated uncertainty. |
| 16. Limits of public visibility | Collection metadata and service facts | Methodological synthesis; no invented private activity. |

These 16 provisional targets are correlated. Several share the same incident or express a generalization over earlier rows. Group results by mechanism, retrieval/probes, account acquisition, later activity, chronology, and uncertainty; inspect both family coverage and item coverage. A rubric with 16 items is not 16 independent experimental tasks, and one omitted item moves an equally weighted score by 6.25 percentage points.

Four additional candidate groups require a broader input: wiki timing/target matches, operator attribution, the DeepSearchQA match, and the external paste comparison. Keep them outside the first score unless their supporting sources are explicitly frozen and supplied. Exclude claims of learned behavior across training runs, authenticated identities, or universal exploit failure unless independently supportable; these are not mandatory conclusions simply because the source discusses them. Official statements and disclosure history belong in a separate context condition.

For manual extraction, retain the published passage and its anchor, write the smallest meaningful claim, and assign a family. Then validate against only the agent-visible files. Each feasibility record should contain `dataset_hash`, record IDs, an exact local query, its result, supported wording, missing evidence, and a verdict of derivable/partial/not derivable. Narrow partial claims before approval. Validate on the eventual pilot input, not on a larger archive or the live web.

## Settings for the first ten-minute runs

Treat “10 min report” as ten minutes of investigation **including writing**. My recommendation is six exploratory runs: three available model/harness combinations, two independent runs each. This tests feasibility and operational failure modes; it is too small for strong ranking claims. Use the existing harnesses if the objective is testing the whole stack, and record that harness and model vary together. Use a common harness if isolating model differences becomes the objective.

| Setting | Proposed pilot value | Reason |
|---|---|---|
| Benchmark identity | `urlquery`; own dataset and rubric versions | Never overload `data_variant` to mean a different benchmark. |
| Time | `time_limit_minutes=10`; 15-minute outer guard | Preserve ten minutes of agent work; the guard is for cleanup. |
| Minimum runtime | `min_runtime_fraction=0.75` | Preserve the current continuation policy. |
| Report target | `report_min_words=2500`, `report_max_words=5000` | Give room for evidence and uncertainty; provisional until a human reference is compressed to fit. |
| Acceptance | `report_accept_min_words=0`, `report_accept_max_words=5100` | Short nonempty reports remain valid; record any overrun. |
| Summary | Suggest 200–300 words in the new prompt | Concentrate prioritization in the summary; not currently a separate enforced config field. |
| Network/backend | `backend=inspect`; no web or subagents | Freeze the input and preserve the existing isolation boundary. |
| Reasoning | Same supported high-effort policy across runs | Record actual provider settings; do not assume `xhigh` is available or equivalent everywhere. |
| Data | One immutable, unannotated snapshot | All repetitions must see the same files. |
| Grading | URLQuery-specific findings and scoped summary reference | Explicit judge/version; no implicit old rubric fallback. |

The [blog's length follow-up](https://www.lesswrong.com/posts/wt4kk6vFPEhkXvF8Q/how-good-are-slop-vestigators) found that a longer report changed coverage; its comments also explain that the original cap came from an incomplete prose count. That makes copying the old 3,000-word ceiling a poor default. The proposed 5,000 ceiling is a design choice, not an empirically optimal length. Check whether pilot reports hit the cap; if they do, run a separately labelled length diagnostic before freezing the benchmark.

Keep the current whitespace-based counter initially, which counts headings, citations, code, and appendices. Request short record-ID citations rather than long encoded URLs. The current TOML acceptance ceiling is **3,200**, whereas the README says **3,100**; carry resolved configuration values and prompt hashes into metadata rather than relying on prose defaults. See [config](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/configs/blind-10.toml) and [length policy](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/messageboard_audit_bench/report_length.py).

Do not silently take only high-confidence rows to make ten minutes easier: that selects on an investigator's conclusions. Prefer the full permitted catalog after freezing, or a documented subset chosen by neutral time/source rules with complete sequences. If an incident-enriched subset is needed for an engineering smoke test, label it as such and exclude broad timeline claims. Low coverage may reflect search burden, missing evidence, refusal, or writing time; inspect traces before lengthening the budget.

## Refactor around a benchmark definition, preserve the infrastructure

Use one repository and shared runners, with two explicit benchmark definitions. Leave the legacy benchmark's paths and outputs intact behind its definition; a wholesale directory migration would add risk without helping the pilot. A proposed `BenchmarkSpec` should resolve the dataset manifest, prompt, human reference, finding set, rubric sheets, scoring policy, and every output location together. Unknown or mismatched identities should fail before any trial or grade is written.

| Existing coupling verified in code | Recommended change |
|---|---|
| [`paths.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/paths.py) has one global answer-key/rubric tree. | Pass resolved benchmark paths. New evaluator artifacts under `benchmarks/urlquery/`; preserve the current `benchmark/` mapping for MessageBoardAuditBench. |
| [`task.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/messageboard_audit_bench/task.py) allowlists three config names and three data variants. | Add an explicit benchmark selector/entry point. A new TOML file alone cannot launch this task. |
| [`isolation_preflight.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/sandbox/isolation_preflight.py) requires four wiki JSONL files and rejects extras. | Validate a benchmark-specific file manifest, preserving hashes, read-only mounts, and no-network checks. Do not weaken preflight globally. |
| [`grading/core.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/messageboard_audit_bench/grading/core.py) fixes sheet counts and maps unknown data variants to the default rubric. | Resolve sheets dynamically from the benchmark; require matching dataset/rubric identities. Preserve old prompt bytes and arithmetic. |
| [`build_combined_coverage.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/viewers/build_combined_coverage.py) expects a rendered wiki bundle and recognizes `collusion.wiki` exports. | Reuse its selection, comment, and claim workflow with a supplied article, report hash, anchors, and benchmark ID. Render Transluce text inertly; do not execute its embedded scripts. |
| [`build_new_claims_ui.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/viewers/build_new_claims_ui.py) uses a fixed local-storage key; feasibility UI hardcodes the old dataset label. | Namespace browser state, save paths, imports, and exports by benchmark and report/rubric version. Keep the familiar interaction. |
| [`collect_reports.py`](https://github.com/hamzah2304/messageboardauditbench/blob/b7ecf93ddc8c0bc71747860d0a98dd9c373a8538/scripts/collect_reports.py) groups by condition, variant, effort, and prompt hash. | Add benchmark/dataset identity to collection, grading, replay, exports, and result filtering. Require explicit cross-benchmark aggregation. |

Give the new benchmark separate roots for `data/urlquery/<version>/`, `runs/urlquery/`, `logs/urlquery/`, `reports/urlquery/`, grades, graded inputs, UI state, and caches. Under evaluator-only `benchmarks/urlquery/`, keep source report, annotations, findings, feasibility records, and rubric versions. Every run should carry `benchmark_id`, dataset hash, prompt hash, rubric version/hash, time/length policy, requested and served model, harness/version, and parent run identity where applicable. Cache and resume keys need the same distinction.

The worktree helper currently links only known wiki data variants. Extend it to resolve the new dataset from the primary checkout; do not build another copy under a worktree. Also update collectors before using nested run directories: the current collector scans only immediate children. Keep web payloads inert in previews, redact usable credentials while preserving stable linkage tokens where necessary, and retain a private transformation manifest.

Implement in three reviewable steps: (1) freeze and validate inputs plus findings; (2) introduce benchmark definitions and isolate the manual UI; (3) connect runners, graders, and exporters. Add meaningful regression checks for old prompt/grade parity, cross-benchmark save/import rejection, wrong-rubric rejection, and preflight isolation. This is a focused refactor, not a new experiment platform. The assessment does not implement it.

## The next decision is about evidence acquisition

Proceed with manual extraction and a bounded acquisition check. Resolve a permitted snapshot route, then verify the three probe episodes, the ONCB sequence, and one account sequence end to end, alongside a neutral availability sample. The report-linked examples are for feasibility diagnosis, not the final sampling rule. Record which resource types survive and how often requests fail; those measurements determine corpus size and acquisition cost. At one request per second, 38,160 JSON requests alone take about 10.6 hours, before retries or additional resources—an arithmetic illustration, not a recommended crawl rate.

Launch the six ten-minute runs only after the scope-matched rubric has at least 12 approved findings across five families, the input has no investigator labels, and the same evidence is available offline to every model. If the central episode outcomes cannot be recovered, narrow the claims or obtain more evidence; extra model time will not fix absent data. Record refusals, model fallbacks, incomplete reports, grading failures, and time spent locating versus interpreting evidence separately.

## Evidence and limits of this assessment

This assessment builds on the [September 24 repository note](../../transluce-urlquery-assessment.md). That note describes a 20-scan check, but its raw scratch files are not in the repository; I have not treated that as a freshly reproduced availability result. This assessment independently verifies the ZIP and two cited scans, and inspects the current code at `b7ecf93ddc8c0bc71747860d0a98dd9c373a8538`. It makes feasibility wording stricter and recommends a standalone initial condition, with a joint-source condition later.

The checks are reproducible with [inspect_dataset.py](inspect_dataset.py):

```sh
python docs/assessments/transluce/inspect_dataset.py \
  /private/tmp/urlquery-agent-activity-2026-09-23.zip \
  /private/tmp/urlquery-aihw.json /private/tmp/urlquery-oncb.json \
  --output docs/assessments/transluce/evidence.json
```

Download sources are linked above; snapshot hashes and schemas are in [evidence.json](evidence.json). The ZIP SHA-256 is `969a13fbd7d80d7e1556eef58a347f52ecdd85661c541f6c0d1d6f5e2a86570d`. Raw samples are temporary local inspection files, not redistributed benchmark inputs. No complete corpus, approved findings, calibrated judge, paid model results, or implemented refactor exists from this assessment.
