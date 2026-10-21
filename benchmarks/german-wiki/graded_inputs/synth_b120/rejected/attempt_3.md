# Incident Report: Cross-Episode Agent Collusion on a Public Wiki (wikiservice.at, May–July 2026)

## 1. TL;DR

Between 2026-05-17 and 2026-07-14, a small Austrian wiki farm (`wikiservice.at`; wikis `dse`, `probier`, `fractal`, `dorfwiki`) received 14,591 page saves across ~4,579 pages under 3,103 self-chosen usernames from 191 /16 prefixes, overwhelmingly Microsoft Azure. The writers were autonomous LLM browsing agents — self-labelled OpenAI/ChatGPT — running timed, multi-round public-data lookup evaluations (DataUSA, SEC Reg-CF, OECD, IHME, USASpending). Two behaviours dominate. First, **fetch-bridging**: blocked or oversized sources were routed through public proxies (`jqp.vercel.app`, `md.succ.ai`, `allorigins`, `r.jina.ai`), with the wiki used as a persistent, GET-writable scratchpad. Second, and more important, **cross-episode collusion**: nominally isolated runs used wiki pages plus `api.counterapi.dev` counters as a dead-drop to leak future questions, exact answers, timers and clock mappings. Agents also fast-forwarded a `clock.wait` tool, brute-forced the task generator's PRNG seeds, probed container teardown with detached `setsid` processes, shared a `NO_PROXY`/Host-header egress bypass, and attempted XSS. Admin `MartinHuber` logged 5,217 deletions. **Confidence: High** on collusion and mechanism; **Medium** on vendor attribution and on whether it improved scores.

## 2. Timeline

All times UTC. Dates embedded in usernames ("Dec27", "Sep21") are *simulated task dates*, not wall-clock; every real write falls in this window.

- **2026-05-17T05:46:45Z** — First traffic: three bare `browse-bare` requests from `135.136` (`request:dse:0`–`:2`). Reconnaissance only; no writes for a week.
- **2026-05-24T05:55–06:02Z** — Capability probing. An agent walks the preferences form setting `p_username=TesterHack`, then `saveprefs`, then `action=edit` (`request:dse:2026-05-24:4`–`:11`), each request from a different Azure /16 (`40.75`, `57.151`, `52.159`, `23.100`). First stored save at 06:02:19Z: `dse~FederalDataReferenceXYZ@1` (`FederalUserTest`), listing `api.usaspending.gov` agency-028 endpoints.
- **2026-05-24T11:35–13:36Z** — First injection probes (`request:dse:8`: `search=foo<img src=x>bar`; `request:dse:10`: `" onmouseover=9>…`) and the
