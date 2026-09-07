from messageboard_audit_bench.provenance import host_provenance


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
