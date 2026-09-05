#!/usr/bin/env python3
"""Make the 'raw' variant of the collusion.wiki dump.

Drops every field that encodes the report authors' own analysis (page-family
classification, event-source bookkeeping, probe classification) and keeps what
the wiki itself would have recorded: page, revision text, name, IP prefix, time.

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
    "labels.jsonl": set(),
}

# The authors named the moderator "[Admin1]" in delete events; keep the fact
# that a human deleted the page, not the analysts' actor id.
RENAME_ACTOR = {"[Admin1]": "moderator"}


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
                    # event ids embed the analysts' source file names
                    if row["event_type"] == "probe":
                        row["event_id"] = f"probe:{n}"
                    if row.get("actor_label") in RENAME_ACTOR:
                        row["actor_label"] = RENAME_ACTOR[row["actor_label"]]
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
        print(f"{fname}: {n} rows, dropped {sorted(drop)}")
    # manifest.json describes populations like 'dse_admin_deletions'; omit it.
    print("manifest.json: omitted (describes the analysts' export pipeline)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
