"""Post-hoc, selected report checks; emit no recorded credential values.

These are not a rubric, exhaustive factual verification, or model scores.
The status sample reproduces Opus run 1's exact first-4000 selection.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from urllib.parse import unquote

from messageboard_audit_bench.dataset_manifest import file_sha256, validate_dataset


def check(dataset: Path) -> dict:
    manifest = validate_dataset(dataset)
    selected = {
        "2fedcab0-5d3a-47ae-b5e6-e97750e4b2a0",
        "4f27ea2f-0865-4ab2-b7bd-be4d794ae2d1",
        "51a8b104-6337-4a13-8ff5-96bace96eac0",
        "595ea88a-07a4-445b-8a5e-288c5f9b8453",
        "3d4b0181-3d32-413a-853d-b2a7a40604c0",
        "6125f779-b94e-40cd-b544-3eb7914c4b0e",
        "e6b5c7bc-41c9-4937-a941-cdaa7019fd2e",
    }
    wrong, correct = collections.Counter(), collections.Counter()
    rows, n = [], 0
    for line in (dataset / "http.jsonl").open():
        row = json.loads(line)
        response = row["response"]
        if n < 4000 and "base64" in line and row["transaction_index"] == 0:
            n += 1
            wrong[str(response.get("status"))] += 1
            correct[str(response.get("status_code"))] += 1
        if row["scan_id"] not in selected:
            continue
        address = unquote(row["url"]["addr"])
        rows.append({
            "scan_id": row["scan_id"], "transaction_index": row["transaction_index"],
            "method": row["request"]["method"], "status_code": response["status_code"],
            # Host and fixed booleans only: never emit query strings or payloads.
            "fqdn": row["url"]["fqdn"],
            "url_contains_account_json_marker": '"address"' in address,
            "url_contains_token_marker": "TOKEN" in address,
            "url_contains_empty_mail_members": '"hydra:member":[]' in address,
            "url_contains_atc2_marker": "Atc2" in address,
        })
    bodies = collections.Counter()
    for line in (dataset / "resources.jsonl").open():
        row = json.loads(line)
        if row.get("availability") == "embedded":
            field = row["source_field"]
            category = "request_body" if ".request." in field else "response_body" if ".response." in field else field.split("[")[0]
            bodies[category] += 1
    return {"interpretation": __doc__, "dataset_sha256": manifest["dataset_sha256"],
            "script_sha256": file_sha256(Path(__file__)),
            "embedded_content_by_source": dict(bodies),
            "opus1_status_sample": {"n": n, "wrong_status_field": dict(wrong),
                                    "correct_status_code_field": dict(correct)},
            "selected_http_rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.dataset), indent=2, sort_keys=True) + "\n")
