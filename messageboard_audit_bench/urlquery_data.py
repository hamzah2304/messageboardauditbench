"""Reproducible acquisition of public scan records; never visit scanned URLs.

Raw cache and acquisition logs are evaluator-only. Config pins the union catalog,
not an investigator-enriched subset. Existing explorer downloads are reused.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
import shutil
import threading
import time
import tomllib
import urllib.error
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def primary_root() -> Path:
    from messageboard_audit_bench.benchmarks import primary_root as shared_primary_root

    return shared_primary_root()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_config(path: Path) -> dict:
    cfg = tomllib.loads(path.read_text())
    if cfg["benchmark_id"] != "urlquery" or cfg["selection"] != "all_catalog_ids":
        raise ValueError("unsupported benchmark or selection")
    if cfg["credential_policy"] != "retain_recorded_values" or cfg["submit_tags"] != "retain":
        raise ValueError("unsupported evidence policy")
    if cfg["fetch_external_resources"]:
        raise ValueError("resource retrieval is not implemented; no target URLs may be fetched")
    if not 1 <= cfg["workers"] <= 4 or cfg["request_interval_seconds"] < 0.25:
        raise ValueError("collector supports at most four workers and four starts/second")
    if cfg["attempts"] < 1 or cfg["minimum_free_gib"] < 1:
        raise ValueError("invalid acquisition bounds")
    return cfg


def atomic_bytes(path: Path, value: bytes) -> None:
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("download redirect refused")


def public_get(url: str, timeout: int, maximum: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "URLQueryResearchBenchmark/1.0"})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("download exceeds configured byte limit")
    return data


def catalog(cfg: dict, cache: Path) -> list[dict]:
    path = cache / "urlquery-agent-activity-2026-09-23.zip"
    if not path.exists():
        downloaded = public_get(cfg["catalog_zip_url"], 60, 16 * 1024**2)
        if digest(downloaded) != cfg["catalog_zip_sha256"]:
            raise ValueError("downloaded catalog ZIP digest mismatch")
        atomic_bytes(path, downloaded)
    blob = path.read_bytes()
    if digest(blob) != cfg["catalog_zip_sha256"]:
        raise ValueError("catalog ZIP digest mismatch")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read(cfg["catalog_member"]).decode())))
    ids = [row["report_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scan IDs in catalog")
    for scan_id in ids:
        if str(uuid.UUID(scan_id)) != scan_id:
            raise ValueError("invalid scan ID")
    return sorted(rows, key=lambda row: (row["report_date_utc"], row["report_id"]))


def validate_raw(blob: bytes, scan_id: str) -> dict:
    raw = json.loads(blob)
    if not isinstance(raw, dict) or raw.get("report_id") != scan_id:
        raise ValueError("raw report identity mismatch")
    if not isinstance(raw.get("http"), list) or not isinstance(raw.get("url"), dict):
        raise ValueError("unrecognized raw report schema")
    return raw


class RateGate:
    def __init__(self, interval: float):
        self.interval = interval
        self.next = 0.0
        self.lock = threading.Lock()

    def wait(self):
        while True:
            with self.lock:
                delay = self.next - time.monotonic()
                if delay <= 0:
                    self.next = time.monotonic() + self.interval
                    return
            time.sleep(min(delay, 1))

    def backoff(self, seconds: float):
        with self.lock:
            self.next = max(self.next, time.monotonic() + seconds)


def collect(cfg: dict, cache: Path, *, limit: int | None = None) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    reports = cache / "reports"
    reports.mkdir(exist_ok=True)
    gate = RateGate(cfg["request_interval_seconds"])
    stop = threading.Event()
    with (cache / "full-collection.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = catalog(cfg, cache)
        pending, cached = [], 0
        run_id = uuid.uuid4().hex
        config_sha256 = digest(json.dumps(cfg, sort_keys=True).encode())
        cache_manifest = []
        for row in rows:
            scan_id = row["report_id"]
            path = reports / f"{scan_id}.json"
            if path.exists():
                blob = path.read_bytes()
                # Fail closed rather than mutate another downloader's cache.
                # A corrupt file needs explicit recovery; nothing is overwritten.
                validate_raw(blob, scan_id)
                cache_manifest.append({"scan_id": scan_id, "sha256": digest(blob),
                                       "bytes": len(blob), "origin": "reused_cache",
                                       "mtime_ns": path.stat().st_mtime_ns})
                cached += 1
            else:
                pending.append(scan_id)
        unscheduled = max(0, len(pending) - limit) if limit is not None else 0
        if limit is not None:
            pending = pending[:limit]
        atomic_bytes(cache / f"cache-manifest-{run_id}.json", json.dumps(cache_manifest).encode())
        print(json.dumps({"catalog": len(rows), "cached": cached, "pending": len(pending)}), flush=True)

        def fetch(scan_id):
            last_error = None
            for attempt in range(1, cfg["attempts"] + 1):
                if stop.is_set():
                    return {"scan_id": scan_id, "status": "deferred"}
                if shutil.disk_usage(cache).free < cfg["minimum_free_gib"] * 1024**3:
                    stop.set()
                    return {"scan_id": scan_id, "status": "disk_guard"}
                gate.wait()
                try:
                    blob = public_get(f"https://urlquery.net/report/{scan_id}/json",
                                      cfg["request_timeout_seconds"], cfg["max_report_bytes"])
                    validate_raw(blob, scan_id)
                    atomic_bytes(reports / f"{scan_id}.json", blob)
                    return {"scan_id": scan_id, "status": "downloaded", "bytes": len(blob),
                            "sha256": digest(blob), "attempts": attempt}
                except urllib.error.HTTPError as exc:
                    last_error = f"HTTP {exc.code}"
                    if exc.code in (401, 403):
                        stop.set()  # do not work around access restrictions
                        return {"scan_id": scan_id, "status": "access_denied", "http_code": exc.code}
                    if exc.code in (404, 410):
                        return {"scan_id": scan_id, "status": "not_available", "http_code": exc.code}
                    if exc.code not in (429, 500, 502, 503, 504):
                        break
                    retry = exc.headers.get("Retry-After", "")
                    gate.backoff(max(30, float(retry) if retry.isdigit() else 30 * attempt))
                except Exception as exc:
                    last_error = type(exc).__name__ + ": " + str(exc)[:160]
                    gate.backoff(2**attempt)
            return {"scan_id": scan_id, "status": "failed", "error": last_error}

        counts = {"downloaded": 0, "failed": 0, "deferred": 0, "disk_guard": 0,
                  "not_available": 0, "access_denied": 0}
        interrupted = False
        context = {"run_id": run_id, "config_sha256": config_sha256, "limit": limit}
        with (cache / "full-acquisition.jsonl").open("a") as audit:
            with ThreadPoolExecutor(max_workers=cfg["workers"]) as pool:
                futures = [pool.submit(fetch, scan_id) for scan_id in pending]
                handled = set()
                try:
                    for number, future in enumerate(as_completed(futures), 1):
                        result = future.result()
                        handled.add(future)
                        counts[result["status"]] += 1
                        audit.write(json.dumps({**context, **result, "collected_at": time.time()}) + "\n")
                        audit.flush()
                        if number % 100 == 0 or number == len(pending):
                            print(json.dumps({"processed": number, "scheduled": len(pending), **counts}), flush=True)
                except BaseException:
                    interrupted = True
                    stop.set()
                    for future in futures:
                        future.cancel()
                    pool.shutdown(wait=True, cancel_futures=True)
                    for future in futures:
                        if future not in handled and not future.cancelled():
                            result = future.result()
                            counts[result["status"]] += 1
                            audit.write(json.dumps({**context, **result, "collected_at": time.time()}) + "\n")
        result = {"catalog": len(rows), "previously_cached": cached, **counts,
                  **context, "scheduled": len(pending), "not_scheduled": unscheduled,
                  "interrupted": interrupted,
                  "complete": cached + counts["downloaded"] == len(rows),
                  "available": cached + counts["downloaded"], "finished_at": time.time()}
        summary_name = "smoke-acquisition-summary.json" if limit is not None else "full-acquisition-summary.json"
        atomic_bytes(cache / summary_name, json.dumps(result, indent=2).encode())
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/urlquery-data.toml"))
    parser.add_argument("--limit", type=int, help="acquisition smoke check only; never changes catalog")
    args = parser.parse_args()
    result = collect(load_config(args.config), primary_root() / "data/transluce", limit=args.limit)
    print(json.dumps(result), flush=True)
    return int(bool(result["failed"] or result["disk_guard"] or result["deferred"] or result["access_denied"] or result["interrupted"]))


if __name__ == "__main__":
    raise SystemExit(main())
