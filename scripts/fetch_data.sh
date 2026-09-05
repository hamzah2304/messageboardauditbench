#!/usr/bin/env bash
# Download the collusion.wiki dump (4.2 MB zip, 57 MB unpacked) into data/raw and verify checksums.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw && cd data/raw
curl -sL https://collusion.wiki/explorer/download/full-wiki-logs.zip -o full-wiki-logs.zip
unzip -o -q full-wiki-logs.zip
sha256sum -c SHA256SUMS
