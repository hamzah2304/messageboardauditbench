import hashlib
import json
import runpy
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).parents[1] / "docs/assessments/transluce/build_share_site.py"))


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.hrefs.extend(v for k, v in attrs if k == "href")


def fixture_config(tmp_path):
    source = tmp_path / "overview.md"
    source.write_text('# Overview\n\n## Section\n\n<script>alert(1)</script>\n\n'
                      '[bad](https://example.com/?credential=secret) '
                      '[bad](//example.com) [local](http://localhost:8792/overview.html) '
                      '[source](overview.md) ![bad](https://example.com/image)\n\n'
                      '`__META__ __SEED__ __SOURCE__`\n')
    return {"title": "Reports", "documents": [{"source": "overview.md", "slug": "overview",
                                                "title": "Overview", "report_id": "original-id"}],
            "run_indexes": []}


def test_static_export_inert_links_local_comments_and_original_bytes(tmp_path):
    config = fixture_config(tmp_path)
    output = tmp_path / "dist"
    MODULE["build"](tmp_path, config, output)
    source = (tmp_path / "overview.md").read_bytes()
    assert (output / "overview.txt").read_bytes() == source
    page = (output / "overview.html").read_text()
    parsed = Elements()
    parsed.feed(page)
    assert "img" not in parsed.tags
    # Only the three trusted template scripts (metadata, seed and viewer JS).
    assert parsed.tags.count("script") == 3
    assert set(parsed.hrefs) == {"index.html", "overview.txt", "overview.html", "#p-2"}
    assert "fetch(" not in page and "/file?p=" not in page and "/save?p=" not in page
    assert '"report_id": "original-id"' in page
    assert "__META__ __SEED__ __SOURCE__" in page
    assert "Comments stay in this browser" in page
    assert 'value="Oscar"' not in page and "||'Oscar'" not in page
    assert "Export earlier comments" in page
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["reports"][0]["sha256"] == hashlib.sha256(source).hexdigest()
    assert str(tmp_path) not in (output / "manifest.json").read_text()


def test_rejects_unexpected_files_and_symlinks(tmp_path):
    config = fixture_config(tmp_path)
    output = tmp_path / "dist"
    output.mkdir()
    (output / "overview.html").symlink_to(tmp_path / "overview.md")
    with pytest.raises(ValueError, match="Unexpected output"):
        MODULE["build"](tmp_path, config, output)
    assert (tmp_path / "overview.md").read_text().startswith("# Overview")


def test_rejects_path_escape_and_duplicate_slug(tmp_path):
    config = fixture_config(tmp_path)
    config["documents"].append(config["documents"][0])
    with pytest.raises(ValueError, match="duplicate"):
        MODULE["collect"](tmp_path, config)
    with pytest.raises(ValueError, match="inside"):
        MODULE["inside"](tmp_path, __file__)


def test_rejects_changed_ai_report(tmp_path):
    config = fixture_config(tmp_path)
    reports = tmp_path / "reports/urlquery"
    reports.mkdir(parents=True)
    report = reports / "report.md"
    report.write_text("Changed")
    row = {"report_path": str(report), "preview_name": "model_run", "report_label": "Model",
           "replicate": 1, "report_sha256": "0" * 64, "run_id": "abc",
           "prompt_sha256": "p", "dataset_sha256": "d", "model_fallback": None}
    (tmp_path / "runs.json").write_text(json.dumps({"benchmark_id": "urlquery", "attempts": [row]}))
    config["run_indexes"] = ["runs.json"]
    config["approved_runs"] = [{"run_id": "abc", "sha256": "0" * 64}]
    with pytest.raises(ValueError, match="hash changed"):
        MODULE["build"](tmp_path, config, tmp_path / "dist")


def test_successful_run_export_crosslinks_approval_and_portable_archive(tmp_path):
    config = fixture_config(tmp_path)
    other = tmp_path / "other.md"
    other.write_text("# Other\n\n[overview](overview.md) [AI](http://localhost:8792/model_run.html) "
                     "[missing](http://localhost:8792/not_included.html)")
    config["documents"].append({"source": "other.md", "slug": "other", "title": "Other"})
    archive = tmp_path / "runs/urlquery/trial"
    archive.mkdir(parents=True)
    (archive / "report.md").write_text("# AI report\n")
    digest = hashlib.sha256((archive / "report.md").read_bytes()).hexdigest()
    row = {"report_path": "/former/worktree/reports/urlquery/group/model.md",
           "run_name": "trial", "preview_name": "model_run", "report_label": "Opus fallback",
           "replicate": 1, "report_sha256": digest, "run_id": "abc",
           "prompt_sha256": "prompt", "dataset_sha256": "data", "requested_model": "opus",
           "model_fallback": {"models": ["opus", "older"], "trigger": "refusal", "category": "cyber"}}
    index = {"benchmark_id": "urlquery", "attempts": [{"report_exists": False}, row]}
    index_path = tmp_path / "runs.json"
    index_path.write_text(json.dumps(index))
    config["run_indexes"] = ["runs.json"]
    with pytest.raises(ValueError, match="sharing approval"):
        MODULE["collect"](tmp_path, config)
    config["approved_runs"] = [{"run_id": "abc", "sha256": digest}]
    output = tmp_path / "dist"
    MODULE["build"](tmp_path, config, output)
    parsed = Elements()
    parsed.feed((output / "other.html").read_text())
    assert "overview.html" in parsed.hrefs and "model_run.html" in parsed.hrefs
    assert not any("localhost" in h for h in parsed.hrefs)
    assert (output / "model_run.txt").read_bytes() == (archive / "report.md").read_bytes()
    assert "fallback" in (output / "model_run.html").read_text()
    manifest = json.loads((output / "manifest.json").read_text())["reports"][-1]
    assert manifest["prompt_sha256"] == "prompt" and manifest["dataset_sha256"] == "data"
    row["report_path"] = "/outside/secret.md"
    index_path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="reports/urlquery"):
        MODULE["collect"](tmp_path, config)
    index["benchmark_id"] = "original"
    index_path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="Wrong benchmark"):
        MODULE["collect"](tmp_path, config)


def test_earlier_comment_versions_can_be_recovered():
    source = MODULE["PREVIOUS_COMMENTS"] + """
const values={
 'report:old':JSON.stringify({report_id:'report',report_sha256:'old',comments:[{note:'Keep this'}]}),
 'report:new':JSON.stringify({report_id:'report',report_sha256:'new',comments:[{}]}),
 'other:old':JSON.stringify({report_id:'other',report_sha256:'old',comments:[{}]}),
 'report:broken':'invalid'
};
const storage={length:Object.keys(values).length,key:i=>Object.keys(values)[i],getItem:k=>values[k]};
const found=previousComments(storage,{report_id:'report',report_sha256:'new'});
if(found.length!==1||found[0].comments[0].note!=='Keep this')process.exit(1);
"""
    subprocess.run(["node", "--input-type=commonjs"], input=source, text=True, check=True)


def test_cli_uses_shared_site_and_requires_existing_binding(tmp_path, monkeypatch):
    main = MODULE["main"]
    monkeypatch.setitem(main.__globals__, "primary_root", lambda: tmp_path)
    config = tmp_path / "sharing.toml"
    config.write_text('title="Reports"\nrun_indexes=[]\ndocuments=[]\n')
    monkeypatch.setattr(sys, "argv", ["build_share_site.py", "--config", str(config)])
    with pytest.raises(SystemExit):
        main()
    binding = tmp_path / "reports/share-site/.openai/hosting.json"
    binding.parent.mkdir(parents=True)
    binding.write_text('{"project_id":"existing"}')
    main()
    assert (tmp_path / "reports/share-site/dist/index.html").is_file()
