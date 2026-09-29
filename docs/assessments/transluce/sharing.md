# Sharing reports

The restricted report collection is separate from the public CommentBench site.
Use Sites named-viewer access; never change this collection to public. Raw report
text can contain recorded credential-like evidence. Do not copy it into a public
repository, dashboard-data bundle or unauthenticated file host.

## Refresh the collection

`configs/urlquery-sharing.toml` is the explicit document/index allowlist. The
exporter requires a separate `approved_runs` entry pinning each AI report's run ID
and SHA-256 hash. It refuses new or changed unapproved reports, preserves source
bytes as `.txt`, and records publication hashes. Regenerate the run indexes through
`summarize_pilot.py` after new trials, review the reports for the intended audience,
then explicitly update the sharing approvals and run:

```sh
.venv/bin/python docs/assessments/transluce/build_share_site.py
```

The homepage groups AI reports by their full rendered `prompt_sha256`.
`prompt_groups` names each cohort and pins the hash and an archived `source_run`.
The exporter verifies that run's `prompt.txt` before publishing readable and
byte-identical text versions. These are the task prompts actually supplied,
including rendered runtime instructions, not provider system prompts or current
templates. Every AI report must match one configured, nonempty prompt group.
Document `group` fields organize the writeups independently. Existing report
URLs, source bytes and comment anchors do not change when the index is regrouped.
Each report's own archived `prompt.txt` is also checked against its run-index
hash, preventing a mislabelled index from assigning it to a different cohort.

The private static source is the **primary checkout's** `reports/share-site/`,
not a task worktree's directory, with public-output directory `dist/`. The builder
defaults to that shared location and refuses a missing Sites binding. It remains
safe when a task worktree is removed. Both are gitignored in the benchmark
repository. Preserve its
`.openai/hosting.json` and reuse the same Sites project; do not register a new site
for every update. The collection URL is
<https://urlquery-benchmark-reports.oscar-mats999.chatgpt.site>.

Use the Sites building/hosting skills to validate, commit and push only this
separate static site's source, package it, save a version and publish. Read its
current access before every deployment and preserve all authorized viewers.
Once shared, deployment follows the shared-audience approval path. Verify both
HTML and direct `.txt`/manifest URLs require sign-in without credentials.
Do not push this private static source to the benchmark's GitHub remote.

## Reading and comments

The site reuses the local viewer's layout and comment anchors. Only links between
included documents are active. Other source links are disabled to prevent
accidentally following recorded attack or credential-bearing URLs; their original
text remains in the downloadable source. No raw datasets, transcripts, runtime
credentials or evaluator finding-extraction state are included.

Comments persist in the reader's browser, not a shared database. Readers must
export JSON and send it to Oscar. Exports retain the original report identity and
source hash so they can be matched to local review workflows. Existing local
comments/replies are not copied into this publication. Original report bytes and
benchmark inputs are unchanged.

After a document changes, the viewer offers exports of browser-local comments on
older versions. It does not silently attach old anchors to the new text. Report
lookup uses the collected report-root suffix or the archived run's exact report
bytes, so an old absolute worktree prefix does not prevent rebuilding elsewhere.

## Sharing review

Subscription-backed Opus 5.5 was requested through Claude Companion. Review
`5cfc51c7-9281-4751-afa0-fd062e2e569d` raised five accepted issues: explicit report
approval pins, portable source lookup, earlier-comment recovery, template drift,
and coverage of successful exports/cross-report links. Follow-up
`de627df4-99cd-4ddb-9d2c-8e4ea37664c7` verified those fixes and identified one
remaining lifecycle issue: ignored private site state must outlive its worktree.
The source repository and hosting binding were moved to the primary checkout;
the exporter now uses that shared location and requires the existing binding.
Final bounded review `d2f6103f-a94f-4311-b390-f91c7534721c` found two low-severity
follow-ups, both accepted: resolve the primary checkout relative to the script,
not the caller's current directory; and keep a local `.git/info/exclude` safety
rule until the tracked ignore change is integrated. Both are fixed. Three review
rounds completed; the final small fixes were tested without a fourth review.

The first publication is Sites version 2, static-source commit
`9abe2f89e8e7f19734c1f8191dd6809697646a5a`. Deployment succeeded, and unauthenticated
requests to the index, report HTML, raw `.txt` and manifest returned HTTP 401.
Sites access was then restricted to the owner plus Adam's email-bound viewer
grant. An access read-back confirmed the grant; Adam's own sign-in was not tested.

Homepage regrouping is published as Sites version 3, static-source commit
`6c2d0ba7783b12838e5a2a2dd9085e3a7b1e2b91`. It adds two exact task-prompt pages,
groups the eight reports by prompt hash, and separates six writeups into three
categories. All 1,425 tests pass. The initial Opus review
`074ca36e-bdc0-4f89-8d67-3171f2a508d3` raised three accepted robustness issues:
fixed budget prose, per-report prompt verification and unsafe-config test gaps.
All were fixed; the follow-up found no actionable issues. The user approved
publication to the existing owner-plus-Adam audience. Deployment succeeded on
2026-09-27 at 01:30 UTC without changing access. Signed-out checks of the homepage
and the new exact-prompt download returned HTTP 401.

The six additional `weird-v2`/`swarm-v2` reports are indexed in
`v2_prompt_runs.json`, with the original experiment-manifest hash and per-report
and per-prompt hashes. This is a publication selection, not a replacement for
the launch histories: those runs used a parallel handoff and a results schema
that the older `summarize_pilot.py` does not accept. The original plans were not
edited, and its finished-plan guard was not relaxed. Collected report bytes,
archived prompt bytes, metadata and model-identity observations were checked
against all six archived runs before adding their explicit sharing approvals.
The collection now has 14 AI reports across four prompt groups and six writeups.
The Opus runs in the two new groups observed Opus 4.8 without fallback; the older
Opus 5.5-to-4.8 reports retain their fallback labels.

This addition was published as Sites version 4, static-source commit
`636098b9f70ab4a9454dcb94391c39e5ea21f571`, on 2026-09-27 at 01:46 UTC.
The requested Opus review `a28fcf37-0cf6-4a39-9fe1-ce5f74ee3db6` found no
actionable issues; all 1,425 tests passed. Access remained restricted to the
owner and the two previously invited viewers, Adam and ilykxar@gmail.com.

The five focused-swarm reports are indexed in `v3_focus_runs.json` from the
finished five-model pilot. Their report and archived prompt hashes are pinned
in `urlquery-sharing.toml` as a fifth prompt group. The collection now has 19
AI reports; existing report files are byte-for-byte unchanged. Sites version 5
was published from static-source commit `688dd256cc98275d65dba97f59d7ac09c8a04e26`.
Access remains limited to Oscar, Adam and ilykxar@gmail.com. Signed-out
requests to the homepage, new prompt, report HTML and text, and manifest
returned HTTP 403.
