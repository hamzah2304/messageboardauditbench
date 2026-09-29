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
                      '[scan](https://urlquery.net/report/596d7f21-9030-404e-a432-f6810151dbef) '
                      '[wrong](https://urlquery.net.evil.test/report/596d7f21-9030-404e-a432-f6810151dbef) '
                      '[query](https://urlquery.net/report/596d7f21-9030-404e-a432-f6810151dbef?x=1) '
                      '[typo](https://urlquery.net/report/84997b9-5831-4910-be69-b7ec86da828a) '
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
    assert set(parsed.hrefs) == {"index.html", "overview.txt", "overview.html", "#p-2",
                                 "https://urlquery.net/report/596d7f21-9030-404e-a432-f6810151dbef"}
    assert 'target="_blank" rel="noopener noreferrer"' in page
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


def test_excluded_report_exports_only_a_pinned_redacted_copy(tmp_path):
    config = fixture_config(tmp_path)
    archive = tmp_path / "runs/urlquery/trial"
    archive.mkdir(parents=True)
    original = b"# AI report\nCredential: private-test-value\nSafe finding\n"
    (archive / "report.md").write_bytes(original)
    (archive / "prompt.txt").write_bytes(b"Prompt")
    digest = hashlib.sha256(original).hexdigest()
    prompt_digest = hashlib.sha256(b"Prompt").hexdigest()
    row = {"run_id": "abc", "run_name": "trial", "preview_name": "model_run",
           "report_label": "Opus", "replicate": 1, "report_path": None,
           "report_exists": True, "report_sha256": digest,
           "publication_exclusion": {"matches": [{"line": 2, "category": "credential"}]},
           "report_finalization": "not_confirmed", "prompt_sha256": prompt_digest,
           "dataset_sha256": "data", "model_fallback": None}
    (tmp_path / "runs.json").write_text(json.dumps({"benchmark_id": "urlquery", "attempts": [row]}))
    config["run_indexes"] = ["runs.json"]
    config["prompt_groups"] = [{"slug": "prompt_one", "title": "Prompt one", "description": "Test",
                                "source_run": "trial", "sha256": prompt_digest}]
    config["redacted_runs"] = [{"run_id": "abc", "sha256": digest, "lines": [2]}]
    output = tmp_path / "dist"
    MODULE["build"](tmp_path, config, output)
    shared = (output / "model_run.txt").read_bytes()
    assert b"private-test-value" not in shared
    assert b"Safe finding" in shared and b"source line 2" in shared
    assert (archive / "report.md").read_bytes() == original
    page = (output / "model_run.html").read_text()
    assert "redacted shared copy" in page and "partial report" in page
    manifest = json.loads((output / "manifest.json").read_text())["reports"][-1]
    assert manifest["source_sha256"] == digest
    assert manifest["sha256"] == hashlib.sha256(shared).hexdigest()
    assert manifest["redaction_lines"] == [2]
    del config["redacted_runs"]
    config["original_runs"] = [{"run_id": "abc", "sha256": digest}]
    MODULE["build"](tmp_path, config, output)
    assert (output / "model_run.txt").read_bytes() == original
    full = json.loads((output / "manifest.json").read_text())["reports"][-1]
    assert full["sha256"] == full["source_sha256"] == digest
    config["original_runs"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="disagrees"):
        MODULE["collect"](tmp_path, config)
    del config["original_runs"]
    config["redacted_runs"] = [{"run_id": "abc", "sha256": digest, "lines": [2]}]
    config["redacted_runs"][0]["lines"] = [1]
    with pytest.raises(ValueError, match="disagrees"):
        MODULE["collect"](tmp_path, config)
    config["redacted_runs"][0]["lines"] = [2]
    config["redacted_runs"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="disagrees"):
        MODULE["collect"](tmp_path, config)


def test_successful_run_export_crosslinks_approval_and_portable_archive(tmp_path):
    config = fixture_config(tmp_path)
    other = tmp_path / "other.md"
    other.write_text("# Other\n\n[overview](overview.md) [AI](http://localhost:8792/model_run.html) "
                     "[missing](http://localhost:8792/not_included.html)")
    config["documents"].append({"source": "other.md", "slug": "other", "title": "Other"})
    archive = tmp_path / "runs/urlquery/trial"
    archive.mkdir(parents=True)
    (archive / "report.md").write_text("# AI report\n")
    prompt = b"Exact task prompt\n<script>inert</script>\n"
    (archive / "prompt.txt").write_bytes(prompt)
    prompt_digest = hashlib.sha256(prompt).hexdigest()
    config["prompt_groups"] = [{"slug": "prompt_one", "title": "Prompt one", "description": "First cohort",
                                "source_run": "trial", "sha256": prompt_digest}]
    digest = hashlib.sha256((archive / "report.md").read_bytes()).hexdigest()
    row = {"report_path": "/former/worktree/reports/urlquery/group/model.md",
           "run_name": "trial", "preview_name": "model_run", "report_label": "Opus fallback",
           "replicate": 1, "report_sha256": digest, "run_id": "abc",
           "prompt_sha256": prompt_digest, "dataset_sha256": "data", "requested_model": "opus",
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
    assert manifest["prompt_sha256"] == prompt_digest and manifest["dataset_sha256"] == "data"
    assert (output / "prompt_one.txt").read_bytes() == prompt
    prompt_page = (output / "prompt_one.html").read_text()
    assert "&lt;script&gt;inert&lt;/script&gt;" in prompt_page
    homepage = (output / "index.html").read_text()
    assert '<h2>AI reports by prompt</h2>' in homepage and '<h2>Writeups</h2>' in homepage
    assert 'href="prompt_one.html"' in homepage and 'href="model_run.html"' in homepage
    assert 'id="export-all-comments"' in homepage
    assert 'urlquery-report-abc' in homepage
    assert json.loads((output / "manifest.json").read_text())["prompts"][0]["sha256"] == prompt_digest
    config["redacted_runs"] = [{"run_id": "abc", "sha256": digest, "lines": [1]}]
    MODULE["build"](tmp_path, config, output)
    assert (output / "model_run.txt").read_bytes() != (archive / "report.md").read_bytes()
    assert "redacted shared copy" in (output / "model_run.html").read_text()
    del config["redacted_runs"]
    (archive / "prompt.txt").write_text("Changed prompt")
    with pytest.raises(ValueError, match="Archived prompt"):
        MODULE["build"](tmp_path, config, output)
    (archive / "prompt.txt").write_bytes(prompt)
    row["prompt_sha256"] = "f" * 64
    index_path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="disagrees"):
        MODULE["collect"](tmp_path, config)
    row["prompt_sha256"] = prompt_digest
    row["report_path"] = "/outside/secret.md"
    index_path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="reports/urlquery"):
        MODULE["collect"](tmp_path, config)
    index["benchmark_id"] = "original"
    index_path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="Wrong benchmark"):
        MODULE["collect"](tmp_path, config)


def test_prompt_groups_cover_each_report_exactly_once(tmp_path):
    archive = tmp_path / "runs/urlquery/trial"
    archive.mkdir(parents=True)
    (archive / "prompt.txt").write_text("Prompt")
    digest = hashlib.sha256(b"Prompt").hexdigest()
    group = {"slug": "prompt_one", "sha256": digest, "source_run": "trial"}
    entries = [{"slug": "report_one", "kind": "AI report", "prompt_sha256": digest}]
    with pytest.raises(ValueError, match="exactly one"):
        MODULE["collect_prompts"](tmp_path, {}, entries)
    with pytest.raises(ValueError, match="duplicate"):
        MODULE["collect_prompts"](tmp_path, {"prompt_groups": [group, group]}, entries)
    with pytest.raises(ValueError, match="exactly one"):
        MODULE["collect_prompts"](tmp_path, {"prompt_groups": [group]}, [])
    group["slug"] = "report_one"
    with pytest.raises(ValueError, match="duplicate"):
        MODULE["collect_prompts"](tmp_path, {"prompt_groups": [group]}, entries)


@pytest.mark.parametrize(("key", "value"), [
    ("source_run", ".."), ("source_run", "."), ("source_run", "a/b"),
    ("slug", "index"), ("slug", "manifest"), ("slug", "Bad-Slug"),
    ("sha256", "A" * 64), ("sha256", "abc"),
])
def test_prompt_groups_reject_unsafe_config(tmp_path, key, value):
    group = {"slug": "prompt_one", "sha256": "a" * 64, "source_run": "trial", key: value}
    with pytest.raises(ValueError, match="Invalid"):
        MODULE["collect_prompts"](tmp_path, {"prompt_groups": [group]}, [])


def test_prompt_groups_reject_escaped_symlink(tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("Not an archived prompt")
    archive = tmp_path / "runs/urlquery/trial"
    archive.mkdir(parents=True)
    (archive / "prompt.txt").symlink_to(secret)
    group = {"slug": "prompt_one", "sha256": "a" * 64, "source_run": "trial"}
    with pytest.raises(ValueError, match="inside"):
        MODULE["collect_prompts"](tmp_path, {"prompt_groups": [group]}, [])


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


def test_collects_comments_across_reports_and_earlier_versions():
    source = MODULE["COLLECTION_EXPORT"].split("const reportIds=")[0] + """
const hash1='a'.repeat(64),hash2='b'.repeat(64),hash3='c'.repeat(64);
const values={
 ['report-one:'+hash1]:JSON.stringify({report_id:'report-one',report_sha256:hash1,comments:[{note:'First'}]}),
 ['report-one:'+hash2]:JSON.stringify({report_id:'report-one',report_sha256:hash2,comments:[{note:'Earlier'}]}),
 ['report-two:'+hash3]:JSON.stringify({report_id:'report-two',report_sha256:hash3,comments:[{note:'Second'}]}),
 ['other:'+hash1]:JSON.stringify({report_id:'other',report_sha256:hash1,comments:[{note:'Unrelated'}]}),
 ['report-two:'+hash1]:'invalid JSON'
};
const storage={length:Object.keys(values).length,key:i=>Object.keys(values)[i],getItem:k=>values[k]};
const bundle=collectComments(storage,new Set(['report-one','report-two']));
if(bundle.comment_count!==3||bundle.reports.length!==3||bundle.format!=='urlquery-comments-bundle-v1')process.exit(1);
if(!bundle.reports.some(r=>r.comments[0].note==='Earlier'))process.exit(1);
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
    additions = tmp_path / "additions.toml"
    additions.write_text("run_indexes=[]\nprompt_groups=[]\napproved_runs=[]\n")
    monkeypatch.setattr(sys, "argv", ["build_share_site.py", "--config", str(config),
                                    "--additions", str(additions)])
    main()
    additions.write_text("run_indexes=[]\n")
    with pytest.raises(SystemExit, match="2"):
        main()
