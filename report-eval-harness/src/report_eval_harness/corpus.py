"""Corpus definitions, fetching and checksums.

A corpus is a directory under ``corpora/<name>/`` holding:

- ``ids.txt``: urlquery report IDs, one per line (committed);
- ``answer_key.jsonl``: the claims the report is graded against (committed);
- ``SHA256SUMS``: checksums of the fetched records (committed, written on first fetch).

The raw records themselves go to ``data/<name>/`` (gitignored: urlquery's terms
forbid redistribution, so we fetch at build time and commit only checksums).

What the agent sees at ``/work/data`` is built from them into ``build/data/<name>/``
(also gitignored): ``scans.jsonl``, one record per line in scan order, and
``README.txt``, the schema and citation format.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPORA_DIR = PROJECT_ROOT / "corpora"
DATA_DIR = PROJECT_ROOT / "data"
SANDBOX_DATA_DIR = PROJECT_ROOT / "build" / "data"
REPORT_JSON_URL = "https://urlquery.net/report/{id}/json"
USER_AGENT = "report-eval-harness/0.1 (research; corpus fetch)"

# Neutral on purpose: it describes the format, never what the records contain.
SANDBOX_README = """\
Scan records
============

scans.jsonl holds {n} scans from urlquery.net, a public service that opens a submitted URL
in a sandboxed browser and records what happened. There is one JSON object per line,
sorted by scan time ({first} to {last}). Each object is the scan as urlquery.net
published it.

Citing a scan
-------------
A scan's ID is its report_id. Cite it as a Markdown link:

    [scan](https://urlquery.net/report/<report_id>)

Only cite report_id values that appear in scans.jsonl.

Fields
------
report_id    scan ID (UUID)
date         when the scan ran (UTC, ISO 8601)
status       scan status; version is the record format version
tags         urlquery's tags for the scan
url          the submitted URL: schema, addr (host, path and query), fqdn, domain, tld
ip           the submitted host's IP address, ASN, AS name and country
final        the URL the browser ended on, and the page title
submit       submission details (url, ip, tags, meta); often empty
settings     scan settings: access (public or private), device_type, useragent, referer,
             cookies, exit_node, expires_at
stats        alert counts per sensor family (ids, urlquery, analyzer)
detection    detections per sensor family
summary      one entry per host contacted: fqdn, ip, domain_registered, domain_rank,
             first_seen, last_seen, alert_count, request_count, received_data,
             sent_data, tags, fingerprints
files        files the browser downloaded
artifacts    items extracted from the page (windows_shortcuts, files, telegram, pdfs,
             clipboard)
sensors      per-sensor results: ids (network IDS), analyzer (YARA and similar rules),
             urlquery (alert, verdict, severity, tags)
javascript   script: scripts the page loaded (url, hashes, size, is_inline, times_seen,
             alerts); eval and write: strings passed to eval() and document.write();
             console: console output
http         every request the browser made, in order: url, ip, date, timestamp
             (milliseconds since the epoch), is_navigation_request, resource_type,
             requested_by, request.raw (request line and headers), response.raw (status
             line and headers), response.data (body metadata: mime_type, size, hashes,
             times_seen; data holds the body when it was captured), timings, alerts

first_seen, last_seen and times_seen on scripts and bodies count sightings across all of
urlquery.net, not just these scans. Empty or null fields are common.
"""


@dataclass(frozen=True)
class Corpus:
    name: str

    @property
    def spec_dir(self) -> Path:
        return CORPORA_DIR / self.name

    @property
    def data_dir(self) -> Path:
        return DATA_DIR / self.name

    @property
    def sandbox_data_dir(self) -> Path:
        return SANDBOX_DATA_DIR / self.name

    @property
    def checksum_file(self) -> Path:
        return self.spec_dir / "SHA256SUMS"

    def ids(self) -> list[str]:
        lines = (self.spec_dir / "ids.txt").read_text().splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith("#")]

    def claims(self) -> list[dict]:
        path = self.spec_dir / "answer_key.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def records(self) -> list[Path]:
        return sorted(self.data_dir.glob("*.json"))


def list_corpora() -> list[str]:
    return sorted(p.name for p in CORPORA_DIR.iterdir() if (p / "ids.txt").exists())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch_one(report_id: str, dest: Path) -> str:
    req = urllib.request.Request(
        REPORT_JSON_URL.format(id=report_id), headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
    json.loads(body)  # fail loudly on an HTML error page
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_bytes(body)
    tmp.replace(dest)
    return report_id


def fetch(corpus: Corpus, force: bool = False, workers: int = 4) -> list[str]:
    """Fetch missing records into ``data/<name>/``. Returns the IDs fetched."""
    corpus.data_dir.mkdir(parents=True, exist_ok=True)
    todo = [i for i in corpus.ids() if force or not (corpus.data_dir / f"{i}.json").exists()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda i: _fetch_one(i, corpus.data_dir / f"{i}.json"), todo))


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)  # atomic, so a running sandbox never sees half a file


def build_sandbox_data(corpus: Corpus) -> Path:
    """Write ``scans.jsonl`` and ``README.txt`` for ``/work/data``; return their directory.

    Two passes (dates, then records) so a large corpus is never all in memory.
    """
    order = []
    for path in corpus.records():
        record = json.loads(path.read_bytes())
        if record.get("report_id") != path.stem:
            raise ValueError(f"{path}: report_id {record.get('report_id')!r} != file name")
        order.append((record.get("date") or "", path.stem, path))
    if not order:
        raise FileNotFoundError(f"no records in {corpus.data_dir}")
    order.sort()

    out = corpus.sandbox_data_dir
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "scans.jsonl.tmp"
    with tmp.open("w") as f:
        for _, _, path in order:
            f.write(json.dumps(json.loads(path.read_bytes()), separators=(",", ":")) + "\n")
    os.replace(tmp, out / "scans.jsonl")
    readme = SANDBOX_README.format(n=len(order), first=order[0][0], last=order[-1][0])
    _write(out / "README.txt", readme)
    return out


def verify(corpus: Corpus) -> list[str]:
    """Check records against the committed SHA256SUMS, writing it if absent.

    Returns human-readable problems (empty list = all good). urlquery records
    carry counters such as ``times_seen`` that can change on re-fetch, so a
    mismatch is worth reading, not necessarily fatal.
    """
    present = {p.stem: sha256(p) for p in corpus.records()}
    missing = [i for i in corpus.ids() if i not in present]
    problems = [f"missing record: {i}" for i in missing]
    if not corpus.checksum_file.exists():
        if not missing:
            lines = [f"{present[i]}  {i}.json" for i in corpus.ids()]
            corpus.checksum_file.write_text("\n".join(lines) + "\n")
        return problems
    for line in corpus.checksum_file.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        rid = name.removesuffix(".json")
        if rid in present and present[rid] != digest:
            problems.append(f"checksum mismatch: {name}")
    return problems
