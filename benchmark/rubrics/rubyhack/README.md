# RubyHack transfer incident

This incident uses 23 preserved Diffend pages cited by the 11 September 2026
[RubyHack investigation](https://www.rubyhack.ai/). They cover 22 distinct
Ruby packages and two consecutive comparisons for one package.

`scripts/build_rubyhack_data.py` verifies a canonicalized SHA256 for every
source page, extracts only package paths and diff lines into
`data/rubyhack/packages.jsonl`, and redacts embedded RubyGems API keys with
stable hash-labelled placeholders. The generated corpus contains 134 file
records and 1,992 diff lines. The report page, its labels, and its conclusions
are not included.

The source pages contain a changing CSRF token. The builder replaces only that
token before checking each pinned digest. Any change to the preserved package
content or page structure still fails the build.

The corpus boundary is narrower than the investigators' working set. It can
establish the YARD/RubyDoc execution mechanism, council-data collection, gem
and webhook return paths, API-key probes, and the self-removing package
progression. It cannot independently establish:

- the campaign-wide upload count or complete chronology;
- RubyGems' operational response;
- whether a third-party API key was successfully stolen;
- OpenAI or model attribution; or
- a relationship to the wiki, Hugging Face, or Artifactory incidents.

Those exclusions are deliberate. `claims_rh.json` contains 12 corpus-derivable
points, including calibrated points for execution, coordination, credential
outcome, and attribution limits. `build_rubrics_rh.py` generates three finding
sheets plus the incident-specific TL;DR sheet from the shared grading scale.

Build and run:

```bash
scripts/build_data.sh
uv run inspect eval messageboard_audit_bench/messageboard_audit_bench \
  -T agent=react -T config=rubyhack -T time_limit_minutes=10 \
  --model openai/gpt-5.6-sol --model-role grader=anthropic/claude-fable-5-1
```

Use a non-OpenAI judge for claims involving OpenAI attribution. A score should
not be presented alongside the headline wiki results until the new sheets have
been manually reviewed and judge independence has been recorded.
