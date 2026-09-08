import hashlib

from messageboard_audit_bench.provenance import data_provenance, host_provenance


def test_host_provenance_identifies_config_prompt_sources_and_unknown_image() -> None:
    result = host_provenance("blind")
    assert result["config_source_path"] == "configs/blind.toml"
    assert result["config_source_text"].startswith("# Named benchmark config")
    assert len(result["config_source_sha256"]) == 64
    assert len(result["prompt_template_sha256"]) == 64
    assert result["declared_cli_versions"]["codex"]
    assert result["docker_image_identity"] is None
    assert (
        result["docker_image_identity_status"]
        == "unknown_not_exposed_by_inspect_sandbox"
    )


def _fake_repo(tmp_path, variant="verbatim_anthropic", bodies=None):
    """A checkout-shaped tree: a variant directory plus the committed manifest."""
    bodies = bodies or {"revisions.jsonl": b'{"a":1}\n', "events.jsonl": b'{"b":2}\n'}
    data = tmp_path / "data" / variant
    data.mkdir(parents=True)
    lines = []
    for name, body in bodies.items():
        (data / name).write_bytes(body)
        lines.append(f"{hashlib.sha256(body).hexdigest()}  data/{variant}/{name}")
    (tmp_path / "data" / "SHA256SUMS.variants").write_text("\n".join(lines) + "\n")
    return tmp_path


def test_data_provenance_records_digests_and_confirms_the_manifest(tmp_path) -> None:
    root = _fake_repo(tmp_path)
    record = data_provenance("verbatim_anthropic", root=root)
    assert record["data_manifest_status"] == "matches_manifest"
    assert set(record["data_files_sha256"]) == {"revisions.jsonl", "events.jsonl"}
    assert all(len(d) == 64 for d in record["data_files_sha256"].values())


def test_data_provenance_catches_a_variant_built_by_different_rules(tmp_path) -> None:
    """The item this exists for: data on disk older than the code that built it."""
    root = _fake_repo(tmp_path)
    stale = root / "data" / "verbatim_anthropic" / "revisions.jsonl"
    stale.write_bytes(b'{"a":1,"shorthand":"Claude"}\n')  # an earlier swap revision
    record = data_provenance("verbatim_anthropic", root=root)
    assert record["data_manifest_status"] == "differs_from_manifest"
    assert record["data_manifest_mismatched"] == ["revisions.jsonl"]
    assert record["data_manifest_missing"] == []


def test_data_provenance_reports_a_file_the_manifest_expects_but_disk_lacks(tmp_path) -> None:
    root = _fake_repo(tmp_path)
    (root / "data" / "verbatim_anthropic" / "events.jsonl").unlink()
    record = data_provenance("verbatim_anthropic", root=root)
    assert record["data_manifest_status"] == "differs_from_manifest"
    assert record["data_manifest_missing"] == ["events.jsonl"]


def test_data_provenance_distinguishes_unbuilt_data_from_a_mismatch(tmp_path) -> None:
    root = _fake_repo(tmp_path)
    for f in (root / "data" / "verbatim_anthropic").glob("*.jsonl"):
        f.unlink()
    assert data_provenance("verbatim_anthropic", root=root)["data_manifest_status"] == "absent_not_built"


def test_data_provenance_follows_worktree_symlinks_to_the_mounted_directory(tmp_path) -> None:
    root = _fake_repo(tmp_path / "primary")
    worktree = tmp_path / "worktree"
    (worktree / "data" / "verbatim_anthropic").mkdir(parents=True)
    real = root / "data" / "verbatim_anthropic"
    for f in real.glob("*.jsonl"):
        (worktree / "data" / "verbatim_anthropic" / f.name).symlink_to(f)
    record = data_provenance("verbatim_anthropic", root=worktree)
    assert record["data_dir"] == str(real.resolve())
    assert set(record["data_files_sha256"]) == {"revisions.jsonl", "events.jsonl"}


def test_host_provenance_carries_the_dataset_identity_when_a_variant_is_given() -> None:
    assert host_provenance("blind")["provenance_schema"] == 2
    assert (
        host_provenance("blind")["data_manifest_status"]
        == "not_recorded_no_variant_supplied"
    )
    assert "data_files_sha256" in host_provenance("blind", data_variant="verbatim")
