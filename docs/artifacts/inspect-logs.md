# Inspect log archive

The [8 September 2026 log archive](https://github.com/hamzah2304/messageboardauditbench/releases/tag/inspect-logs-2026-09-08)
preserves the native Inspect `.eval` files for round 4, the provider-swap
ablation, and both followup cohorts. This is an experiment archive, not a
software release or a claim that every included run enters the headline results.

Download and verify from a fresh checkout:

```bash
gh release download inspect-logs-2026-09-08 \
  --repo hamzah2304/messageboardauditbench --dir downloaded-logs
cd downloaded-logs
shasum -a 256 -c SHA256SUMS
for archive in *.tar; do tar -xf "$archive"; done
uv run inspect view --log-dir .
```

Each archive contains a separate batch directory. `manifest.json` records each
log's SHA-256, status, sample IDs and epochs, scoring availability, and available
fallback metadata. Report-index entries map published reports to source log
basenames and epochs. Existing indexes can contain obsolete absolute local paths;
use the basename to locate the corresponding downloaded log.

Finalized error and cancelled logs are retained for transparency. Logs still
marked `started` at packaging time are excluded and listed in the manifest.
Do not average every archived sample: use the tracked report indexes, grades,
and figure builders to reproduce the published selection. Historical runs often
used `--no-score`; their grades are stored separately under `benchmark/graded/`.
The current task runs both graders by default.

The archives do not include `.env`, account credentials, the complete legacy
`runs/` directory, or reconstructed datasets. Keep a private backup of local
state before deleting a working checkout. Build the public data using the setup
instructions in the repository README.
