"""Summarize frozen input coverage without emitting payloads or credentials.

Article-linked scans are a purposive feasibility check, not the sampling rule.
Section groups can overlap. Presence and mechanical decoding do not certify a
finding's derivability; outcome and attribution claims still need manual review.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from messageboard_audit_bench.dataset_manifest import file_sha256, validate_dataset


def article_groups(source: Path) -> dict[str, set[str]]:
    article = BeautifulSoup(source.read_bytes(), "html.parser").select_one("article")
    if article is None:
        raise ValueError("source article missing")
    groups = collections.defaultdict(set)
    heading = "Introduction"
    pattern = re.compile(r"https://urlquery\.net/report/([a-f0-9-]{36})(?:[/#?]|$)")
    for element in article.descendants:
        if getattr(element, "name", None) in ("h2", "h3", "summary"):
            heading = element.get_text(" ", strip=True)
        if getattr(element, "name", None) == "a":
            match = pattern.match(element.get("href", ""))
            if match:
                groups[heading].add(match[1])
    if not groups:
        raise ValueError("no article scan links found")
    return dict(groups)


def summarize(dataset: Path, source: Path) -> dict:
    manifest = validate_dataset(dataset)
    groups = article_groups(source)
    cited = set().union(*groups.values())
    per_scan = {scan_id: {"present": False, "transactions": 0,
                         "http_error": False, "decoded": False,
                         "response_bodies": 0, "dom_bodies": 0}
                for scan_id in cited}
    statuses, decoding, availability = (collections.Counter() for _ in range(3))
    observed_counts = {}
    for name in ("scans", "http", "decoded_text", "resources"):
        count = 0
        with (dataset / f"{name}.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                count += 1
                selected = per_scan.get(row["scan_id"])
                if name == "scans" and selected is not None:
                    selected["present"] = True
                elif name == "http":
                    status = str(row["response"]["status_code"])
                    statuses[status] += 1
                    if selected is not None:
                        selected["transactions"] += 1
                        selected["http_error"] |= status.isdigit() and int(status) >= 400
                elif name == "decoded_text":
                    decoding[row["parse_status"]] += 1
                    if selected is not None:
                        selected["decoded"] |= row["parse_status"] == "ok"
                elif name == "resources" and "availability" in row:
                    availability[row["availability"]] += 1
                    if selected is not None and row["availability"] == "embedded":
                        pointer = row["source_field"]
                        selected["response_bodies"] += bool(re.fullmatch(r"http\[\d+\]\.response\.data", pointer))
                        selected["dom_bodies"] += pointer == "final.dom"
        if count != manifest["files"][f"{name}.jsonl"]["records"]:
            raise ValueError(f"record count changed during summary: {name}")
        observed_counts[name] = count

    def coverage(ids):
        records = [per_scan[scan_id] for scan_id in ids]
        return {"cited_scan_count": len(ids),
                "present_scan_count": sum(r["present"] for r in records),
                "missing_scan_ids": sorted(i for i in ids if not per_scan[i]["present"]),
                "http_transactions": sum(r["transactions"] for r in records),
                "scans_with_http_error": sum(r["http_error"] for r in records),
                "scans_with_any_successful_text_decoding": sum(r["decoded"] for r in records),
                "embedded_nonempty_response_bodies": sum(r["response_bodies"] for r in records),
                "embedded_nonempty_final_dom_bodies": sum(r["dom_bodies"] for r in records)}

    files = manifest["files"]
    return {"benchmark_id": "urlquery", "dataset_sha256": manifest["dataset_sha256"],
            "manifest_sha256": file_sha256(dataset / "manifest.json"),
            "source_html_sha256": file_sha256(source),
            "summary_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "catalog_count": manifest["catalog_count"],
            "downloaded_count": manifest["downloaded_count"],
            "missing_count": manifest["missing_count"],
            "acquisition_closed": manifest["acquisition_closed"],
            "file_bytes": {k: v["bytes"] for k, v in files.items() if not k.startswith("content/")},
            "content_files": sum(k.startswith("content/") for k in files),
            "content_bytes": sum(v["bytes"] for k, v in files.items() if k.startswith("content/")),
            "total_listed_file_bytes": sum(v["bytes"] for v in files.values()),
            "records": observed_counts, "http_status_counts": dict(statuses),
            "decoding_status_counts": dict(decoding), "resource_availability": dict(availability),
            "article_citation_coverage": coverage(cited),
            "overlapping_article_sections": {heading: {**coverage(ids), "scan_ids": sorted(ids)}
                                             for heading, ids in groups.items()},
            "interpretation": __doc__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.dataset, args.source)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["article_citation_coverage"], indent=2))


if __name__ == "__main__":
    main()
