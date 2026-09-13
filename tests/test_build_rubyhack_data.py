from __future__ import annotations

import hashlib
import json

import pytest

from scripts import build_rubyhack_data


def page(token: str = "dynamic") -> bytes:
    return f'''<html><head><meta name="csrf-token" content="{token}" /></head><body>
<div class="d2h-file-wrapper"><span class="d2h-file-name">data/evil.rb</span>
<table><tr><td class="d2h-code-linenumber d2h-ins"></td><td class="d2h-ins">
<span class="d2h-code-line-ctn">KEY='rubygems_abcdefghijklmnopqrstuvwxyz012345'</span>
</td></tr></table></div></body></html>'''.encode()


def canonical(data: bytes) -> bytes:
    return build_rubyhack_data.CSRF_RE.sub(br"\1<REDACTED>\2", data)


def one_source(monkeypatch, expected_sha256: str) -> None:
    monkeypatch.setattr(
        build_rubyhack_data,
        "SOURCES",
        (("https://my.diffend.io/gems/testpkg/1.0.0", expected_sha256),),
    )
    monkeypatch.setattr(build_rubyhack_data, "EXPECTED_PACKAGES", 1)
    monkeypatch.setattr(build_rubyhack_data, "EXPECTED_FILE_RECORDS", 1)
    monkeypatch.setattr(build_rubyhack_data, "EXPECTED_DIFF_LINES", 1)


def test_build_extracts_diff_and_redacts_keys(tmp_path, monkeypatch) -> None:
    raw = page()
    source = tmp_path / "gems__testpkg__1.0.0.html"
    source.write_bytes(raw)
    one_source(monkeypatch, hashlib.sha256(canonical(raw)).hexdigest())

    built = build_rubyhack_data.build(tmp_path)
    [record] = [json.loads(line) for line in built.splitlines()]

    assert record["package"] == "testpkg"
    assert record["record_id"] == "testpkg:1.0.0:data/evil.rb"
    assert record["path"] == "data/evil.rb"
    assert record["lines"][0]["kind"] == "added"
    assert "rubygems_<REDACTED_" in record["lines"][0]["text"]
    assert b"abcdefghijklmnopqrstuvwxyz012345" not in built


def test_build_ignores_changing_csrf_token(tmp_path, monkeypatch) -> None:
    original = page("first")
    changed = page("second")
    (tmp_path / "gems__testpkg__1.0.0.html").write_bytes(changed)
    one_source(monkeypatch, hashlib.sha256(canonical(original)).hexdigest())

    assert build_rubyhack_data.build(tmp_path)


def test_build_rejects_changed_package_content(tmp_path, monkeypatch) -> None:
    (tmp_path / "gems__testpkg__1.0.0.html").write_bytes(page() + b"changed")
    one_source(monkeypatch, "0" * 64)

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        build_rubyhack_data.build(tmp_path)
