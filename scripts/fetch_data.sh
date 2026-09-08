#!/usr/bin/env bash
# Download the collusion.wiki dump (4.2 MB zip, 57 MB unpacked) into data/raw and verify checksums.
#
# The dump is fetched from a single upstream host. If that host is unreachable or
# has moved, the benchmark can still be built from any copy of the archive: the
# SHA256 below is what makes a copy trustworthy, not where it came from.
#
#   MBAB_DUMP_ARCHIVE=/path/to/full-wiki-logs.zip scripts/fetch_data.sh   # use a local copy
#   MBAB_DUMP_URL=https://example.org/full-wiki-logs.zip scripts/fetch_data.sh  # use a mirror
#
# Either way the archive must match ARCHIVE_SHA256 or the script stops.
set -euo pipefail
# sha256sum is GNU-only; macOS ships `shasum -a 256`.
if command -v sha256sum >/dev/null 2>&1; then SHA256SUM=sha256sum; else SHA256SUM="shasum -a 256"; fi
cd "$(dirname "$0")/.."
mkdir -p data/raw && cd data/raw
ARCHIVE=full-wiki-logs.zip
ARCHIVE_SHA256=eb68aa12d26bf189d8bfc4ce47f4d8af66ae5ba7ebbadd429738297a3cbb25ae
ARCHIVE_URL=${MBAB_DUMP_URL:-https://collusion.wiki/explorer/download/full-wiki-logs.zip}

if [ -n "${MBAB_DUMP_ARCHIVE:-}" ]; then
  if [ ! -f "$MBAB_DUMP_ARCHIVE" ]; then
    echo "MBAB_DUMP_ARCHIVE is set but not a file: $MBAB_DUMP_ARCHIVE" >&2
    exit 1
  fi
  cp "$MBAB_DUMP_ARCHIVE" "$ARCHIVE"
elif ! curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE"; then
  cat >&2 <<MSG
Could not download the dump from:
  $ARCHIVE_URL

The benchmark does not depend on that host staying up, only on the archive
contents. If you have a copy of full-wiki-logs.zip from anywhere, use it:

  MBAB_DUMP_ARCHIVE=/path/to/full-wiki-logs.zip scripts/fetch_data.sh

or point at a mirror with MBAB_DUMP_URL. Either is verified against:

  sha256  $ARCHIVE_SHA256

A copy that does not match that digest is not the benchmark's dataset and
will not reproduce the committed grades.
MSG
  exit 1
fi

printf '%s  %s\n' "$ARCHIVE_SHA256" "$ARCHIVE" | $SHA256SUM -c -
unzip -o -q "$ARCHIVE"
$SHA256SUM -c SHA256SUMS
