#!/usr/bin/env bash
# Download the collusion.wiki dump (4.2 MB zip, 57 MB unpacked) into data/raw and verify checksums.
set -euo pipefail
# sha256sum is GNU-only; macOS ships `shasum -a 256`.
if command -v sha256sum >/dev/null 2>&1; then SHA256SUM=sha256sum; else SHA256SUM="shasum -a 256"; fi
cd "$(dirname "$0")/.."
mkdir -p data/raw && cd data/raw
curl -sL https://collusion.wiki/explorer/download/full-wiki-logs.zip -o full-wiki-logs.zip
unzip -o -q full-wiki-logs.zip
$SHA256SUM -c SHA256SUMS
