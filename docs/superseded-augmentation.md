# SUPERSEDED (2026-09-05): reconstruction-based augmentation

This approach was abandoned the same day. It synthesised request-log rows
(timestamps, click sequences, IP prefixes, fetch reads, admin visits) from the
report's aggregate statements. That is reconstruction, not evidence, and the
decision is to add only material the report prints verbatim. The replacement
is `docs/verbatim-data.md` and `scripts/fill_verbatim.py`. The old script is
kept for reference at `scripts/superseded/augment_data_reconstructed.py` and
must not be used to build benchmark data.

Original text follows for the record.

---

# Data augmentation: putting back what the public dump lacks

The collusion.wiki authors had the wiki's web-server request logs. The public
dump has only edits (plus 101 probe stubs). `scripts/augment_data.py` builds
`data/augmented/` from `data/raw_stripped/` so that the report's request-log
findings become recoverable. Provenance of every addition is recorded in
`docs/augmentation-manifest.json` (never inside the data directory the agent sees).

Provenance levels:

- **report-quoted**: verbatim from the report. Real.
- **report-derived**: the report states the fact and the numbers; individual rows are synthesised to match.
- **synthetic**: plausible filler with no direct basis. Kept to a minimum and flagged.

## What was missing, and what the augmentation does about it

| report finding | why it was missing | augmentation | provenance |
|---|---|---|---|
| Admin impersonation with a Cyrillic look-alike `е` (26 May, 18 Jun) | names redacted to `[Admin2]` | `[Admin2]` → `HelmutBecker`; the 5 agent-IP edits under it become `HеlmutBecker` (U+0435). The genuine admin's own visits are added to the request log so there is a Latin original to compare against | report-derived |
| DSE moderator name used in a 20 June archive request | names redacted, request logs absent | `[Admin1]` → `PeterSchmid` consistently in revisions, deletions, and the quoted archive request; 4 follow-up diff views from Azure prefixes | report-quoted |
| XSS / injection payloads | probe rows carried no URL | 8 quoted payloads restored verbatim on their probe rows; the other 93 probes get a URL patterned on their parameter family | mixed (8 real, 93 synthetic) |
| ChatGPT-User fetches within minutes of Azure writes (380,901 in June) | reads not in dump | ~17.6k fetch-tool reads, 1 to 3 per DSE write, 40 s to 10 min later, from fetch-tool prefixes. A ~1/10 subsample by volume | report-derived |
| OpenAI-HQ visits: first on 21 June (13 IPs from `199.47.142.0` and `12.12.56.x`), 33 IPs and 532 requests on 26 June using the archive function, 2 July follow-up six hours after the burst, 7 July archive probe with the moderator's name, then decline; 42 look-alike IPs | reads not in dump | human-paced sessions (RecentChanges → page → diff, archive listing and recovery on 26 June) with exactly those counts and dates | report-derived |
| 17 June requests with `*.lhr.life` referrers (localhost.run tunnel) | referrers not in dump | 7 quoted rows from `209.160` | report-quoted |
| 24 May DSEWiki discovery sequence (TesterHack, TesterWikiUser) | request log | 12 quoted rows | report-quoted |
| Early edits on publictestwiki, UseModWiki, texteditors.org (11 to 26 May) | outside the dump's wikis | 16 revisions on `publictestwiki`, `usemod`, `texteditors` from the report's quotes; times approximate where the report gives only a date | report-quoted |
| Spam-filtered `ZZagentTemp9876` attempts, Azure then AWS within 26 s | blocked writes never stored | 3 `blocked` events | report-quoted |

## Still not recoverable, deliberately

- **Full IPs and provider attribution** (98.5% Azure; 197 edits from AWS, DigitalOcean, Tor). Only two octets exist. You said this is not an important item. A prefix-to-organisation table could be added later, but I would have to guess the owners of the non-Azure prefixes (`64.236`, `130.131`, ...), so I did not.
- **Deleted pages under the 64-character save threshold.** Gone at the source.
- **urlscan.io submission** of a Pinggy tunnel (17 June, `BaseHTTP/0.6 Python/3.11.8`). Third-party evidence, not wiki data. Could be a separate "external observations" file if wanted.
- **Moderator effort** ("tens of hours"). Deletion timestamps are there; the effort estimate needs session logs.
- **Uncyclopedia** activity: the report mentions it without quoting content.

## Effects on the benchmark

- Rubric leaves previously tagged `derivable: no` (impersonation, HQ visits, fetch-tool reads, XSS payloads, tunnels-by-referrer, pre-24-May activity) become `partly` or `yes` on the augmented variant. Keep both variants; the raw one remains the honest "public dump only" condition.
- Any count an agent reports from `requests.jsonl` will differ from the report's (fetches are subsampled). Rubric items must be written against the augmented data, not the report's numbers.
- The 26 June spike (30% of HQ activity on one day) and the 21 June first-visit / 22 June stop sequence are now discoverable, so "OpenAI noticed and intervened" becomes a gradeable inference rather than an unknowable.
- The launcher copies every `*.jsonl` in `DATA_DIR`, so `DATA_DIR=data/augmented sandbox/run_trial.sh ...` gives the agent `requests.jsonl` alongside the four original files. The prompt's "edit logs" wording still fits; consider "server logs" if you want to nudge the agent toward the request log.
