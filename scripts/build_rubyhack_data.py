#!/usr/bin/env python3
"""Build a blind RubyHack corpus from checksum-pinned package diffs.

The RubyHack investigators did not release their campaign-wide working set. They
did, however, link the preserved Diffend records for the packages supporting
their technical findings. This builder fetches those 23 records, verifies the
exact HTML bytes, extracts only package paths and diff lines, and removes the
surrounding website and investigator write-up.

RubyGems API keys embedded in the historical packages are replaced with stable
hash-labelled placeholders. Their presence and reuse remain visible without
redistributing credential material.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import DATA  # noqa: E402

SOURCES = (
    ("https://my.diffend.io/gems/zzsouthrunner/1.0.1", "0b63a3dbeb8218b8a31349768ada3180ede90015df2d6c6db1eca3061e8fb567"),
    ("https://my.diffend.io/gems/southpxdatapp6pi/0.0.1", "05dac8a95e8819dc89379873e4b8d4514b118e1102eab5521eab5fc74d2099e0"),
    ("https://my.diffend.io/gems/lambethcalcqzewgt/0.0.1", "a598107411c8adbb643f4486c3bae8bea599b60803be8e5ea0a7f2a0070b4f18"),
    ("https://my.diffend.io/gems/injecthack1778550335/0.0.1", "c22cebbc6d6226f70246a3b652f60449b10884b56a1b345d66010cb962fc79f8"),
    ("https://my.diffend.io/gems/sampledocpayload624286/0.0.6", "be4365a045a5b5a0ce3f9a8512894c06a1e1d2c9d0a5a895dd1b80f880319729"),
    ("https://my.diffend.io/gems/zzwandshostyard/0.0.1", "63a3413fc52a9c3feb16156c85ee82fa641403aaf86b71fbf0506e8d04ad85e0"),
    ("https://my.diffend.io/gems/wandxprobe/0.0.1", "6a115af3ad45b4d09a073889d45140a45dd81075f31a676c3b9c050d74ebccde"),
    ("https://my.diffend.io/gems/councilfetchfff/0.0.1", "bdb51c83ee8dfd8949c22a4dcc47bba91431c0ce3e9fd0f3dafb56debb2097fa"),
    ("https://my.diffend.io/gems/civic-lambda-proxy/0.0.1", "02ee50f4ef7597078359e526e3e8f47f87a424df4a30be41ba93046db58ddda6"),
    ("https://my.diffend.io/gems/civic-test-scrape/0.0.1/0.0.2", "2445fd8edd4e6b16e9245f842bc098489d21aaf47bb03b48a0d841b400ac639b"),
    ("https://my.diffend.io/gems/southcalx884/0.0.1", "075d56f2cb68410c7dbca617374187a8f8ad5f890d7c3ca970a189e0fe30688c"),
    ("https://my.diffend.io/gems/southnews-designfetch-90001/0.0.1", "d8d9115b768bf3029323db35356abb7f10fa94b1f1969a6d872b5e6790b1822c"),
    ("https://my.diffend.io/gems/southnewsprobe1778550995/0.0.1/0.0.2", "036618f281903f3086b05896f7628df50a9231e99aeae8ee854df3740c7ff28b"),
    ("https://my.diffend.io/gems/southnewsprobe1778550995/0.0.2/0.0.3", "743e6a029484e70b3b3c71035a4aba1a7322dd119579bb19f627bdd993b7bfbf"),
    ("https://my.diffend.io/gems/lambyard17/0.0.1", "037390ce050052c23c3a9447521a57cd308a094d44fb198ef2f90cf408ddf0ee"),
    ("https://my.diffend.io/gems/slnleaker5/0.0.1", "aabe4c5ea3b4ee5ee99d498ef766f82869a7b822f6b3610cddce286383360499"),
    ("https://my.diffend.io/gems/yardbreakerxqh1778552850/0.0.1", "80e946b714e1d56f81cd09e2037be8d1b4f6603da1e06c9cf66aca5b525fc4ca"),
    ("https://my.diffend.io/gems/yardxabc889/0.0.1", "157431f322e2f2802a0166a9a64bd5342eabd311d03e5cdc458919d2201418f5"),
    ("https://my.diffend.io/gems/lambfetchx548811/0.0.1", "af3a8234206d7fc78f6cbe02209f359fcb060a7376fb66ee9c40ecb2052ea039"),
    ("https://my.diffend.io/gems/lambfetchx550961/0.0.1", "0b75ff155253eb02665be4dcaa2308c3fcae14e2d00070749d840ae2ea14347a"),
    ("https://my.diffend.io/gems/aaaresultfetchx/0.0.1", "c26a4a65e47730cdb89146a0692466ded6f90282002f9093a9cf6d07913367ed"),
    ("https://my.diffend.io/gems/uu4c477z1/0.0.1", "cfa4b64af3dfbbf8ffa7995ae985af4ec86c4af741dc18046987559b1d01cea0"),
    ("https://my.diffend.io/gems/wandtmpdesign9fe2/0.0.1", "222ca0be6a56af1220c885731366ec755f327ed4571a00b3996e7a182e58706c"),
)
EXPECTED_PACKAGES = 22
EXPECTED_FILE_RECORDS = 134
EXPECTED_DIFF_LINES = 1992

KEY_RE = re.compile(r"rubygems_[A-Za-z0-9_-]{20,}")
CSRF_RE = re.compile(br'(<meta name="csrf-token" content=")[^"]+(" />)')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        fingerprint = hashlib.sha256(match.group().encode()).hexdigest()[:12]
        return f"rubygems_<REDACTED_{fingerprint}>"

    return KEY_RE.sub(replacement, text)


class DiffParser(HTMLParser):
    """Extract file names and rendered diff lines from one Diffend page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.wrapper_depth = 0
        self.current_file: str | None = None
        self.capture_file = False
        self.file_parts: list[str] = []
        self.in_row = False
        self.row_kind: str | None = None
        self.capture_code = False
        self.code_parts: list[str] = []
        self.files: dict[str, list[dict[str, str]]] = {}

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if tag == "div" and "d2h-file-wrapper" in classes:
            self.wrapper_depth = 1
            self.current_file = None
            return
        if self.wrapper_depth:
            if tag == "div":
                self.wrapper_depth += 1
            if tag == "span" and "d2h-file-name" in classes and self.current_file is None:
                self.capture_file = True
                self.file_parts = []
            elif tag == "tr":
                self.in_row = True
                self.row_kind = None
            elif tag == "td" and self.in_row:
                if "d2h-ins" in classes:
                    self.row_kind = "added"
                elif "d2h-del" in classes:
                    self.row_kind = "removed"
                elif "d2h-cntx" in classes:
                    self.row_kind = "context"
            elif tag == "span" and "d2h-code-line-ctn" in classes:
                self.capture_code = True
                self.code_parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self.wrapper_depth:
            return
        if tag == "span" and self.capture_file:
            name = "".join(self.file_parts).strip()
            if name:
                self.current_file = name
                self.files.setdefault(name, [])
            self.capture_file = False
        elif tag == "span" and self.capture_code:
            if self.current_file is not None:
                self.files[self.current_file].append(
                    {"kind": self.row_kind or "context", "text": redact("".join(self.code_parts))}
                )
            self.capture_code = False
        elif tag == "tr":
            self.in_row = False
            self.row_kind = None
        if tag == "div":
            self.wrapper_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.capture_file:
            self.file_parts.append(data)
        if self.capture_code:
            self.code_parts.append(data)


def identity(url: str) -> tuple[str, str]:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) not in {3, 4} or parts[0] != "gems":
        raise ValueError(f"unexpected Diffend URL shape: {url}")
    return parts[1], " -> ".join(parts[2:])


def fetch(url: str, expected_sha256: str, source_dir: Path | None) -> bytes:
    if source_dir:
        name, comparison = identity(url)
        path = source_dir / f"gems__{name}__{comparison.replace(' -> ', '__')}.html"
        data = path.read_bytes()
    else:
        request = urllib.request.Request(
            url, headers={"User-Agent": "messageboardauditbench-corpus-builder/1.0"}
        )
        with urllib.request.urlopen(request) as response:  # noqa: S310 — hashes pinned below
            data = response.read()
    data = CSRF_RE.sub(br"\1<REDACTED>\2", data)
    actual = digest(data)
    if actual != expected_sha256:
        raise ValueError(f"source SHA256 mismatch for {url}: expected {expected_sha256}, got {actual}")
    return data


def build(source_dir: Path | None = None) -> bytes:
    records = []
    for url, sha256 in SOURCES:
        parser = DiffParser()
        parser.feed(fetch(url, sha256, source_dir).decode("utf-8"))
        if not parser.files or not any(parser.files.values()):
            raise ValueError(f"no package diff records extracted from {url}")
        name, comparison = identity(url)
        for path, lines in parser.files.items():
            records.append(
                {
                    "record_id": f"{name}:{comparison}:{path}",
                    "package": name,
                    "comparison": comparison,
                    "path": path,
                    "lines": lines,
                }
            )
    shape = (len({record["package"] for record in records}), len(records), sum(
        len(record["lines"]) for record in records
    ))
    expected = (EXPECTED_PACKAGES, EXPECTED_FILE_RECORDS, EXPECTED_DIFF_LINES)
    if shape != expected:
        raise ValueError(f"unexpected RubyHack corpus shape: {shape}, expected {expected}")
    return b"".join(
        (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        for record in records
    )


def output_dir() -> Path:
    candidate = DATA / "rubyhack"
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
    shared = common_git.parent / "data" / "rubyhack"
    shared.mkdir(parents=True, exist_ok=True)
    if shared != candidate:
        candidate.symlink_to(shared, target_is_directory=True)
    return shared


def main() -> None:
    local = os.environ.get("MBAB_RUBYHACK_SOURCE_DIR")
    content = build(Path(local) if local else None)
    output = output_dir() / "packages.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    temporary.chmod(0o644)
    temporary.replace(output)
    print(f"wrote {output}: {len(content.splitlines())} file records, sha256 {digest(content)}")


if __name__ == "__main__":
    main()
