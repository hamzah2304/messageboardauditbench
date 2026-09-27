"""Dependency-free frozen-input validation, shared by host and Docker canary."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = {"README.txt", "scans.jsonl", "http.jsonl", "decoded_text.jsonl", "resources.jsonl"}


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(manifest: dict) -> str:
    body = {key: value for key, value in manifest.items() if key != "dataset_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_dataset(root: Path, *, benchmark_id: str = "urlquery", expected_sha256: str | None = None) -> dict:
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("manifest must not be a symlink")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("benchmark_id") != benchmark_id or manifest.get("schema_version") != 1:
        raise ValueError("benchmark/schema mismatch")
    if manifest.get("dataset_sha256") != identity(manifest):
        raise ValueError("dataset identity mismatch")
    if expected_sha256 and manifest["dataset_sha256"] != expected_sha256:
        raise ValueError("pinned dataset identity mismatch")
    if manifest["downloaded_count"] + manifest["missing_count"] != manifest["catalog_count"]:
        raise ValueError("inconsistent acquisition counts")
    files = manifest["files"]
    if files.get("scans.jsonl", {}).get("records") != manifest["downloaded_count"]:
        raise ValueError("scan count does not match acquisition")
    if not REQUIRED <= files.keys():
        raise ValueError("required dataset files missing")
    for name in files:
        if name not in REQUIRED and not re.fullmatch(r"content/[a-f0-9]{64}\.txt", name):
            raise ValueError(f"unexpected manifest path: {name}")
    visible = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"dataset symlink rejected: {path.name}")
        if path.is_file():
            visible.add(path.relative_to(root).as_posix())
        elif path.is_dir() and path.relative_to(root).as_posix() != "content":
            raise ValueError("unexpected dataset directory")
        elif not path.is_dir():
            raise ValueError("dataset contains a non-regular entry")
    if visible != set(files) | {"manifest.json"}:
        raise ValueError("dataset contains unlisted or missing files")
    for name, expected in files.items():
        path = root / name
        if path.stat().st_size != expected["bytes"] or file_sha256(path) != expected["sha256"]:
            raise ValueError(f"file integrity mismatch: {name}")
        if name.endswith(".jsonl"):
            rows = 0
            with path.open() as stream:
                for line in stream:
                    if not isinstance(json.loads(line), dict):
                        raise ValueError(f"non-object JSONL record: {name}")
                    rows += 1
            if rows != expected["records"]:
                raise ValueError(f"record count mismatch: {name}")
    if manifest.get("unavailable_scan_count", 0) > manifest["missing_count"]:
        raise ValueError("unavailable count exceeds missing count")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    result = validate_dataset(args.root, expected_sha256=args.expected_sha256)
    print(json.dumps({"benchmark_id": result["benchmark_id"], "dataset_sha256": result["dataset_sha256"],
                      "files": len(result["files"]), "ok": True}))
