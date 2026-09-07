#!/usr/bin/env bash
# Download the collusion.wiki dump (4.2 MB zip, 57 MB unpacked) into data/raw and verify checksums.
set -euo pipefail
# sha256sum is GNU-only; macOS ships `shasum -a 256`.
if command -v sha256sum >/dev/null 2>&1; then SHA256SUM=sha256sum; else SHA256SUM="shasum -a 256"; fi
cd "$(dirname "$0")/.."
mkdir -p data/raw && cd data/raw
ARCHIVE=full-wiki-logs.zip
ARCHIVE_SHA256=eb68aa12d26bf189d8bfc4ce47f4d8af66ae5ba7ebbadd429738297a3cbb25ae
curl -fsSL https://collusion.wiki/explorer/download/full-wiki-logs.zip -o "$ARCHIVE"
printf '%s  %s\n' "$ARCHIVE_SHA256" "$ARCHIVE" | $SHA256SUM -c -
unzip -o -q "$ARCHIVE"
$SHA256SUM -c SHA256SUMS
