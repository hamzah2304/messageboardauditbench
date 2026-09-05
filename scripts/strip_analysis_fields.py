#!/usr/bin/env python3
"""Make the 'raw' variant of the collusion.wiki dump.

Drops every field that encodes the report authors' own analysis (page-family
classification, event-source bookkeeping, human/bot handle classification) and
keeps what the wiki itself would have recorded: page, revision text, name, IP
prefix, time. Also removes the authors' judgements that hide in values rather
than fields: the event type "probe" (their classification of 101 requests)
becomes the neutral "request"; probe event ids that embedded their source file
name ("attacklog_raw_dse_...") are renumbered; the four "revert" rows, which are
edges from their recreation analysis rather than log records, are dropped; and
the deleter keeps the dump's redacted token "[Admin1]" instead of being renamed.

Usage: strip_analysis_fields.py <in_dir> <out_dir>
"""
import json
import sys
from pathlib import Path

# Fields that are analysis, not observation.
DROP = {
    "pages.jsonl": {
        "bucket", "page_family", "page_family_cohort", "page_family_confidence",
        "page_family_method", "page_family_source", "deleted_live",
        "live_body_variant", "head_differs_from_live", "n_deletions",
        "n_recreations",
    },
    "revisions.jsonl": {
        "rcs_rev", "rcs_path", "body_sha256", "diff_base", "diff_base_reason",
        "hunks", "time_grade", "winning_clock", "uncertainty_seconds",
        "request_time", "success_time", "recent_changes_time", "archived_at",
        "related_event_id", "relation_type", "round_id", "body_encoding",
    },
    "events.jsonl": {
        "time_grade", "winning_clock", "uncertainty_seconds", "request_time",
        "success_time", "rcs_date", "recent_changes_time", "clock_delta_seconds",
        "source_refs", "related_event_id", "relation_type", "round_id",
        "page_held", "clock_note", "param_family", "success_observed",
    },
    "labels.jsonl": {"is_human_handle", "save_request_source"},
}

# Values (not fields) that carry the authors' judgement.
RETYPE_EVENT = {"probe": "request"}   # "probe" is their classification of these requests
DROP_EVENT_TYPES = {"revert"}         # derived edges from their recreation analysis, not log rows


def main(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for fname, drop in DROP.items():
        n = 0
        with (src / fname).open() as fin, (dst / fname).open("w") as fout:
            for line in fin:
                row = json.loads(line)
                for k in drop:
                    row.pop(k, None)
                if fname == "events.jsonl":
                    if row["event_type"] in DROP_EVENT_TYPES:
                        continue
                    if row["event_type"] in RETYPE_EVENT:
                        # ids of these rows embed the analysts' source file names; renumber
                        row["event_type"] = RETYPE_EVENT[row["event_type"]]
                        row["event_id"] = f"{row['event_type']}:{row.get('wiki', 'dse')}:{n}"
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
        print(f"{fname}: {n} rows, dropped {sorted(drop)}")
    # manifest.json describes populations like 'dse_admin_deletions'; omit it.
    print("manifest.json: omitted (describes the analysts' export pipeline)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
