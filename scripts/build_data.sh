#!/usr/bin/env bash
# Rebuild every data variant from the public download, deterministically.
#
#   scripts/build_data.sh            # build every incident corpus, then verify
#   scripts/build_data.sh --verify   # only check existing outputs against data/SHA256SUMS.variants
#
# Outputs: data/raw (download, checksums verified by fetch_data.sh),
#          data/raw_stripped (analysis fields removed; the primary benchmark input),
#          data/verbatim (raw_stripped plus what the report prints verbatim; see docs/verbatim-data.md),
#          data/verbatim_anthropic (verbatim with the maker re-attributed to Anthropic; see scripts/swap_provider.py).
#          data/mythos5 (the released transcript with its editorial metadata row removed).
#          data/rubyhack (redacted package diffs cited by the RubyHack investigation).
# data/SHA256SUMS.variants is committed; a rebuild must reproduce it exactly.
set -euo pipefail
# sha256sum is GNU-only; macOS ships `shasum -a 256`.
if command -v sha256sum >/dev/null 2>&1; then SHA256SUM=sha256sum; else SHA256SUM="shasum -a 256"; fi
cd "$(dirname "$0")/.."
SUMS=data/SHA256SUMS.variants

if [ "${1:-}" != "--verify" ]; then
  [ -f data/raw/revisions.jsonl ] || scripts/fetch_data.sh
  python3 scripts/strip_analysis_fields.py data/raw data/raw_stripped
  python3 scripts/fill_verbatim.py data/raw_stripped data/verbatim benchmark/human_report.txt
  python3 scripts/swap_provider.py data/verbatim data/verbatim_anthropic
  python3 scripts/build_mythos5_data.py
  python3 scripts/build_rubyhack_data.py
fi

if [ -f "$SUMS" ]; then
  $SHA256SUM -c "$SUMS" && echo "data variants match $SUMS"
else
  $SHA256SUM data/raw_stripped/*.jsonl data/verbatim/*.jsonl data/verbatim_anthropic/*.jsonl > "$SUMS"
  echo "wrote $SUMS (first build; commit it)"
fi
