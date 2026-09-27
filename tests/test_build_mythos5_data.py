from __future__ import annotations

import hashlib
import json

import pytest

from scripts import build_mythos5_data


def source(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row) + "\n").encode() for row in rows)


def test_build_strips_editorial_metadata_and_keeps_messages(monkeypatch) -> None:
    raw = source(
        [
            {"record": "metadata", "about": ["answer-leaking summary"]},
            {"record": "message", "index": 0, "content": "system"},
            {"record": "message", "index": 82, "content": "thinking"},
        ]
    )
    monkeypatch.setattr(build_mythos5_data, "SOURCE_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(build_mythos5_data, "EXPECTED_MESSAGE_COUNT", 2)

    built = build_mythos5_data.build(raw)
    rows = [json.loads(line) for line in built.splitlines()]

    assert [row["index"] for row in rows] == [0, 82]
    assert all(row["record"] == "message" for row in rows)
    assert b"answer-leaking" not in built


def test_build_rejects_unpinned_source() -> None:
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        build_mythos5_data.build(b"changed upstream")
