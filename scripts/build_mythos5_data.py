#!/usr/bin/env python3
"""Fetch, verify, and strip the released Mythos 5 incident transcript.

The upstream JSONL begins with an editorial metadata record that names the
incident and summarizes its conclusion. That row is useful on the release page
and leaks the answer in a blind investigation, so the benchmark input retains
only the 2,064 raw message records.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import DATA  # noqa: E402

SOURCE_URL = (
    "https://raw.githubusercontent.com/anthropics/"
    "mythos-5-incident-transcript/"
    "62858fcf2725fe7b38872d538e973f38846ea744/transcript.jsonl"
)
SOURCE_SHA256 = "6f2a5a50b53640bd779a198cef8a620f2d6e2bbaaf4a0dea9edac87a69fc3e4b"
EXPECTED_MESSAGE_COUNT = 2064


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes() -> bytes:
    local = os.environ.get("MBAB_MYTHOS5_TRANSCRIPT")
    if local:
        return Path(local).read_bytes()
    url = os.environ.get("MBAB_MYTHOS5_URL", SOURCE_URL)
    with urllib.request.urlopen(url) as response:  # noqa: S310 — configured download, hash pinned below
        return response.read()


def build(raw: bytes) -> bytes:
    if digest(raw) != SOURCE_SHA256:
        raise ValueError(
            "Mythos 5 source SHA256 mismatch: "
            f"expected {SOURCE_SHA256}, got {digest(raw)}"
        )
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    messages = [row for row in rows if row.get("record") == "message"]
    if len(rows) != EXPECTED_MESSAGE_COUNT + 1 or len(messages) != EXPECTED_MESSAGE_COUNT:
        raise ValueError(
            f"unexpected Mythos 5 shape: {len(rows)} rows, {len(messages)} messages"
        )
    if [row.get("record") for row in rows if row.get("record") != "message"] != ["metadata"]:
        raise ValueError("the only removable Mythos 5 row must be metadata")
    return b"".join(
        (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        for row in messages
    )


def output_dir() -> Path:
    candidate = DATA / "mythos5"
    if candidate.exists():
        return candidate.resolve()
    try:
        common_git = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=DATA.parent,
                text=True,
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return candidate
    shared = common_git.parent / "data" / "mythos5"
    shared.mkdir(parents=True, exist_ok=True)
    if shared != candidate:
        candidate.symlink_to(shared, target_is_directory=True)
    return shared


def main() -> None:
    output = output_dir() / "transcript.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    content = build(source_bytes())
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    temporary.replace(output)
    print(
        f"wrote {output}: {EXPECTED_MESSAGE_COUNT} messages, "
        f"sha256 {digest(content)}"
    )


if __name__ == "__main__":
    main()
