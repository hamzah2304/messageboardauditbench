"""Read-only checks for the public catalog and two purposively selected scans.

Usage: python inspect_dataset.py ARCHIVE [SCAN_JSON ...]
Prints aggregate/schema evidence, never raw payloads or credentials.
"""

import argparse
import collections
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path


def schema(value, prefix="", depth=0):
    if depth > 3:
        return {}
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            path = f"{prefix}.{key}".lstrip(".")
            out[path] = type(child).__name__
            if isinstance(child, (dict, list)):
                out.update(schema(child, path, depth + 1))
        return out
    if isinstance(value, list) and value:
        return schema(value[0], prefix + "[]", depth + 1)
    return {}


def inspect(archive, samples):
    with zipfile.ZipFile(archive) as z:
        base = z.namelist()[0].split("/")[0] + "/"

        def read(name):
            return z.read(base + name)

        manifest = json.loads(read("manifest.json"))
        mismatches = []
        for name, expected in manifest["files"].items():
            content = read(name)
            if len(content) != expected["bytes"] or hashlib.sha256(content).hexdigest() != expected["sha256"]:
                mismatches.append(name)

        def rows(name):
            return list(csv.DictReader(io.StringIO(read(name).decode("utf-8-sig"))))

        all_rows = rows("all-reports.csv")
        main = rows("reports.csv")
        extra = rows("additional-cited-reports.csv")
        keys = list(all_rows[0])
        ids = {r["report_id"] for r in all_rows}
        sources = rows("report-sources.csv")
        out = {
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "archive_bytes": archive.stat().st_size,
            "uncompressed_bytes": sum(f.file_size for f in z.infolist()),
            "members": [n.removeprefix(base) for n in z.namelist()],
            "manifest_files_checked": len(manifest["files"]),
            "manifest_mismatches": mismatches,
            "catalog_columns": keys,
            "catalog_rows": len(all_rows),
            "unique_report_ids": len(ids),
            "main_rows": len(main),
            "supplement_rows": len(extra),
            "component_overlap": len({r["report_id"] for r in main} & {r["report_id"] for r in extra}),
            "disposition": dict(collections.Counter(r["disposition"] for r in all_rows)),
            "confidence": dict(collections.Counter(r["confidence"] for r in all_rows)),
            "broad_class": dict(collections.Counter(r["broad_class"] for r in all_rows)),
            "date_min": min(r["report_date_utc"] for r in all_rows),
            "date_max": max(r["report_date_utc"] for r in all_rows),
            "nonempty_cells": {k: sum(bool(r[k]) for r in all_rows) for k in keys},
            "source_rows": len(sources),
            "source_columns": list(sources[0]),
            "samples": [],
        }
        for path in samples:
            payload = json.loads(path.read_text())
            rid = payload.get("report_id")
            sample = {
                "report_id": rid,
                "source": f"https://urlquery.net/report/{rid}/json",
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "in_catalog": rid in ids,
                "status": payload.get("status"),
                "date": payload.get("date"),
                "schema": schema(payload),
                "top_level_counts": {k: len(v) for k, v in payload.items() if isinstance(v, (dict, list))},
                "http_transactions": len(payload.get("http") or []),
                "http_status_counts": dict(collections.Counter(x["response"]["status_code"] for x in payload.get("http") or [])),
                "nonempty_response_bodies": sum(bool(x["response"].get("data", {}).get("data")) for x in payload.get("http") or []),
                "script_entries": len(payload.get("javascript", {}).get("script") or []),
                "nonempty_script_bodies": sum(bool(x.get("data")) for x in payload.get("javascript", {}).get("script") or []),
                "dom_body_present": bool(payload.get("final", {}).get("dom", {}).get("data")),
            }
            out["samples"].append(sample)
        return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("samples", type=Path, nargs="*")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(inspect(args.archive, args.samples), indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
        print(f"Wrote {args.output}")
    else:
        print(result, end="")
