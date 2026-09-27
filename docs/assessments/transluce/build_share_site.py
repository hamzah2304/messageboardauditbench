"""Export an explicit, private report collection using the existing viewer template.

No publishing or access changes here. Output is sensitive even though links and
active report content are neutralized. Sites must gate ALL assets, including txt.
"""

import argparse
import hashlib
import html
import json
import re
import runpy
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = runpy.run_path(str(HERE / "build_preview.py"))["SHELL"]
FALLBACK_NOTICE = runpy.run_path(str(HERE / "summarize_pilot.py"))["fallback_notice"]
NOTICE = (
    "Restricted research reports; unscored and not verified findings. Recorded URLs, "
    "programs and credential-like strings are evidence only: do not visit, execute or use them. "
    "Links within this collection and to cited URLQuery scans are active; other recorded URLs "
    "remain disabled. Comments stay in your browser; "
    "export JSON to send them to Oscar. They are not shared automatically."
)
PREVIOUS_COMMENTS = """
function previousComments(storage,meta){
 const found=[];
 for(let i=0;i<storage.length;i++){
  const key=storage.key(i);if(!key||!key.startsWith(meta.report_id+':'))continue;
  try{const d=JSON.parse(storage.getItem(key));
   if(d.report_id===meta.report_id&&d.report_sha256!==meta.report_sha256&&Array.isArray(d.comments)&&d.comments.length)found.push(d);
  }catch(e){}
 }
 return found;
}
"""


def inside(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Source must be an existing file inside the repository")
    return path


def redact_report(raw, line_numbers):
    """Replace reviewed source lines without changing the archived report."""
    lines = raw.decode("utf-8").splitlines(keepends=True)
    if not line_numbers or len(line_numbers) != len(set(line_numbers)):
        raise ValueError("Redaction lines must be unique and nonempty")
    for number in line_numbers:
        if type(number) is not int or number < 1 or number > len(lines):
            raise ValueError("Invalid redaction line")
        ending = "\n" if lines[number - 1].endswith("\n") else ""
        lines[number - 1] = (
            f"[Shared-copy redaction: source line {number} contained a credential "
            f"or personal identifier.]" + ending
        )
    return "".join(lines).encode("utf-8")


def collect(root, config):
    entries = []
    for document in config["documents"]:
        entries.append({**document, "path": inside(root, document["source"]), "kind": "overview"})
    approved = {r["run_id"]: r["sha256"] for r in config.get("approved_runs", [])}
    if len(approved) != len(config.get("approved_runs", [])):
        raise ValueError("Duplicate sharing approval")
    redactions = {r["run_id"]: r for r in config.get("redacted_runs", [])}
    if len(redactions) != len(config.get("redacted_runs", [])):
        raise ValueError("Duplicate redaction approval")
    originals = {r["run_id"]: r["sha256"] for r in config.get("original_runs", [])}
    if len(originals) != len(config.get("original_runs", [])) or set(originals) & set(redactions):
        raise ValueError("Duplicate or conflicting original report approval")
    used_redactions = set()
    used_originals = set()
    for name in config["run_indexes"]:
        data = json.loads(inside(root, name).read_text())
        if data["benchmark_id"] != "urlquery":
            raise ValueError("Wrong benchmark in publication index")
        for row in data["attempts"]:
            redaction = redactions.get(row.get("run_id"))
            original = originals.get(row.get("run_id"))
            if not row.get("report_path") and redaction is None and original is None:
                continue
            if redaction is None and original is None and approved.get(row["run_id"]) != row["report_sha256"]:
                raise ValueError("AI report lacks an explicit matching sharing approval")
            if original is not None:
                excluded = row.get("publication_exclusion") or {}
                if (row.get("report_path") or not row.get("report_exists")
                        or not excluded.get("matches") or original != row["report_sha256"]):
                    raise ValueError("Original report approval disagrees with excluded source")
                used_originals.add(row["run_id"])
            if redaction is not None:
                if (redaction["sha256"] != row["report_sha256"]
                        or not redaction["lines"]):
                    raise ValueError("Redaction approval disagrees with excluded source")
                if row.get("report_path"):
                    if approved.get(row["run_id"]) != row["report_sha256"]:
                        raise ValueError("Redacted report lacks matching sharing approval")
                else:
                    if not row.get("report_exists"):
                        raise ValueError("Redaction approval disagrees with excluded source")
                    excluded = row.get("publication_exclusion") or {}
                    flagged = sorted({m["line"] for m in excluded.get("matches", [])})
                    if sorted(redaction["lines"]) != flagged or not flagged:
                        raise ValueError("Redaction approval disagrees with excluded source")
                used_redactions.add(row["run_id"])
            # Indexes retain original absolute paths. Resolve their report-root
            # suffix here, or the immutable run archive after worktree removal.
            if row.get("report_path"):
                parts = Path(row["report_path"]).parts
                markers = [i for i in range(len(parts)-1) if parts[i:i+2] == ("reports", "urlquery")]
                if len(markers) != 1 or ".." in parts:
                    raise ValueError("AI report must be in reports/urlquery")
                report_root = (root / "reports/urlquery").resolve()
                relative = Path(*parts[markers[0]+2:])
                path = report_root / relative
                if path.is_file():
                    path = inside(report_root, relative)
                else:
                    run_name = row.get("run_name", "")
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_name) or run_name in {".", ".."}:
                        raise ValueError("Report missing and no valid archived run")
                    path = inside((root / "runs/urlquery").resolve(), run_name + "/report.md")
            else:
                run_name = row.get("run_name", "")
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_name) or run_name in {".", ".."}:
                    raise ValueError("Report missing and no valid archived run")
                path = inside((root / "runs/urlquery").resolve(), run_name + "/report.md")
            title = f"{row['report_label']} · run {row['replicate']}"
            if redaction is not None:
                title += " · redacted shared copy"
                if row.get("report_finalization") not in {None, "cli_finished"}:
                    title += " (partial report)"
            entries.append({"path": path, "slug": row["preview_name"], "kind": "AI report",
                            "report_id": "urlquery-report-" + row["run_id"],
                            "title": title,
                            "expected_sha256": row["report_sha256"],
                            "notice": FALLBACK_NOTICE(row),
                            "redaction_lines": redaction["lines"] if redaction else [],
                            "run_name": row.get("run_name", ""),
                            "prompt_sha256": row["prompt_sha256"],
                            "dataset_sha256": row["dataset_sha256"]})
    if used_redactions != set(redactions):
        raise ValueError("Redaction approval has no matching excluded report")
    if used_originals != set(originals):
        raise ValueError("Original report approval has no matching excluded report")
    slugs = set()
    for entry in entries:
        slug = entry["slug"]
        if not re.fullmatch(r"[a-z][a-z0-9_]+", slug) or slug in slugs or slug == "index":
            raise ValueError("Invalid or duplicate report slug")
        slugs.add(slug)
        source = entry["path"].read_bytes()
        entry["source_sha256"] = hashlib.sha256(source).hexdigest()
        if entry.get("expected_sha256", entry["source_sha256"]) != entry["source_sha256"]:
            raise ValueError("Report hash changed since the run index was generated")
        entry["raw"] = redact_report(source, entry["redaction_lines"]) if entry.get("redaction_lines") else source
        entry["sha256"] = hashlib.sha256(entry["raw"]).hexdigest()
        if entry["kind"] == "AI report":
            run = entry["run_name"]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", run) or run in {".", ".."}:
                raise ValueError("AI report needs its archived run to verify the actual prompt")
            prompt = inside((root / "runs/urlquery").resolve(), run + "/prompt.txt")
            if hashlib.sha256(prompt.read_bytes()).hexdigest() != entry["prompt_sha256"]:
                raise ValueError("Archived prompt for this report disagrees with its run index")
    return entries


def render_body(entry, entries):
    paths = {e["path"]: e["slug"] for e in entries}
    slugs = {e["slug"] for e in entries}
    md = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")

    def link_open(tokens, idx, options, env):
        token = tokens[idx]
        href = token.attrGet("href") or ""
        url = urlsplit(href)
        target = None
        if not url.scheme and not url.netloc and not url.path and url.fragment:
            target = "#" + url.fragment
        elif (url.scheme == "https" and url.netloc == "urlquery.net"
              and not url.query and not url.fragment
              and re.fullmatch(r"/report/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", url.path)):
            target = href
        elif (url.hostname in {"localhost", "127.0.0.1"}
              and url.scheme in {"http", "https"} and not url.query):
            slug = Path(url.path).stem
            if slug in slugs and url.path == f"/{slug}.html":
                target = slug + ".html"
        elif not url.scheme and not url.netloc and not url.query:
            path = (entry["path"].parent / unquote(url.path)).resolve()
            if path in paths:
                target = paths[path] + ".html"
        if target is None:
            return '<a aria-disabled="true" title="Not included in this collection; link disabled">'
        attributes = ' target="_blank" rel="noopener noreferrer"' if target == href and url.scheme else ""
        return '<a href="' + html.escape(target, quote=True) + '"' + attributes + '>'

    md.renderer.rules["link_open"] = link_open
    return md.render(entry["raw"].decode("utf-8"))


def render_page(entry, entries):
    def replace(shell, old, new):
        if old not in shell:
            raise ValueError("Viewer template changed; review the hosted adaptation")
        return shell.replace(old, new)

    shell = replace(SHELL, "Research assessment", "Benchmark reports")
    shell = replace(shell, '<a href="__SOURCE__">Markdown source</a>',
                          '<div><a href="index.html">All reports</a> · <a href="__SOURCE__">Markdown source</a></div>')
    shell = replace(shell, "In this assessment", "In this report")
    shell = replace(shell, "Select text in the assessment, then add a note. Comments save locally to this worktree.",
                          "Select text to add a note. Comments stay in this browser; export JSON to share them.")
    shell = replace(replace(shell, 'value="Oscar"', 'value=""'), "||'Oscar'", "||'Reader'")
    shell = replace(shell, '<div id="comments">', '<div id="previous"></div><div id="comments">')
    shell = replace(shell, "(async()=>{", PREVIOUS_COMMENTS + """
(async()=>{
 try{for(const d of previousComments(localStorage,M)){
  const p=document.createElement('p');p.textContent='Comments on an earlier version ('+d.report_sha256.slice(0,12)+'). Anchors may be stale.';
  const b=document.createElement('button');b.textContent='Export earlier comments ('+d.comments.length+')';
  b.onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=M.report_id+'-'+d.report_sha256.slice(0,12)+'-comments.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
  p.append(b);$('previous').append(p);
 }}catch(e){}
""")
    shell = re.sub(r"async function persist\(\)\{.*?\n\}", """async function persist(){
 try{localStorage.setItem(KEY,JSON.stringify(payload()));$('status').textContent='Saved in this browser only; export JSON to share.';}
 catch(e){$('status').textContent='Could not save; export JSON before closing.';}
}""", shell, flags=re.S)
    shell = re.sub(r" try\{const r=await fetch\('/file\?p='.*?catch\(e\)\{\}", "", shell)
    if "fetch(" in shell:
        raise ValueError("Hosted viewer must not call the local file server")
    toc = []
    counter = 0

    def block(match):
        nonlocal counter
        counter += 1
        tag, content = match.groups()
        anchor = f"p-{counter}"
        if tag == "h2":
            toc.append(f'<a href="#{anchor}">{content}</a>')
        return f'<{tag} id="{anchor}" data-block="1">{content}</{tag}>'

    body = re.sub(r"<(h[123]|p|li|td)>(.*?)</\1>", block, render_body(entry, entries), flags=re.S)
    body = body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
    notice = NOTICE + entry.get("notice", "")
    if entry.get("redaction_lines"):
        notice += (" This shared copy replaces " + str(len(entry["redaction_lines"])) +
                   " source line(s) containing credentials or personal identifiers. "
                   "The archived original is unchanged.")
        if "(partial report)" in entry["title"]:
            notice += " This report was unfinished when the trial reached its time limit."
    substitutions = {
        "BODY": body, "TOC": "".join(toc), "TITLE": html.escape(entry["title"]),
        "SOURCE": entry["slug"] + ".txt", "SEED": "null",
        "META": json.dumps({"report_id": entry.get("report_id", entry["slug"]), "report_sha256": entry["sha256"]}).replace("<", "\\u003c"),
        "NOTICE": '<div class="notice">' + html.escape(notice) + '</div>',
    }
    return re.sub(r"__([A-Z]+)__", lambda m: substitutions[m[1]], shell)


def collect_prompts(root, config, entries):
    prompts, hashes, slugs = [], set(), {e["slug"] for e in entries} | {"index", "manifest"}
    for group in config.get("prompt_groups", []):
        slug, digest, run = group["slug"], group["sha256"], group["source_run"]
        if (not re.fullmatch(r"[a-z][a-z0-9_]+", slug) or slug in slugs
                or not re.fullmatch(r"[0-9a-f]{64}", digest) or digest in hashes
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", run) or run in {".", ".."}):
            raise ValueError("Invalid or duplicate prompt group")
        path = inside((root / "runs/urlquery").resolve(), run + "/prompt.txt")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Archived prompt does not match the configured hash")
        prompts.append({**group, "raw": raw})
        slugs.add(slug)
        hashes.add(digest)
    used = {e["prompt_sha256"] for e in entries if e["kind"] == "AI report"}
    if used != hashes:
        raise ValueError("Every AI report must belong to exactly one nonempty prompt group")
    return prompts


def static_page(title, body, extra_style=""):
    style = re.search(r"<style>(.*?)</style>", SHELL, re.S)[1]
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + html.escape(title) + '</title><style>' + style + extra_style +
            '</style></head><body><main class="collection">' + body + '</main></body></html>').encode()


COLLECTION_STYLE = """
.collection{max-width:1100px;margin:auto;padding:40px 24px 60px}
.collection h1{font-size:36px}.collection h2{margin-top:36px}
.collection .intro{color:var(--muted);max-width:78ch}
.collection .jump{display:flex;gap:24px;flex-wrap:wrap;margin:20px 0}
.collection .groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.collection .group{padding:22px;border:1px solid var(--line);border-radius:10px;background:var(--paper)}
.collection h3{margin:0 0 12px;font:600 23px/1.25 Georgia,serif}
.collection .group p{margin:12px 0;color:var(--muted)}
.collection ul{padding-left:22px;margin-bottom:0}.collection li{margin-bottom:10px}
.collection .writeups{grid-template-columns:repeat(3,minmax(0,1fr))}
.collection .writeups h3{font-size:21px}.collection footer{margin-top:32px;border-top:1px solid var(--line);padding-top:18px;font-size:14px;color:var(--muted)}
.collection pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:15px;line-height:1.65}
@media(max-width:760px){.collection .groups{grid-template-columns:1fr}.collection{padding:24px 18px}.collection h1{font-size:30px}}
"""


def render_index(config, entries, prompts):
    def links(rows):
        return '<ul>' + ''.join('<li><a href="' + e["slug"] + '.html">' + html.escape(e["title"]) + '</a></li>' for e in rows) + '</ul>'

    sections = []
    for prompt in prompts:
        rows = [e for e in entries if e.get("prompt_sha256") == prompt["sha256"]]
        sections.append('<section class="group"><h3>' + html.escape(prompt["title"]) +
                        '</h3><p>' + html.escape(prompt["description"]) + '</p><p><a href="' +
                        prompt["slug"] + '.html">Read the exact prompt</a> · ' + str(len(rows)) +
                        ' reports</p>' + links(rows) + '</section>')
    writeups = {}
    for entry in entries:
        if entry["kind"] == "overview":
            writeups.setdefault(entry.get("group", "Other writeups"), []).append(entry)
    writeup_sections = ''.join('<section class="group"><h3>' + html.escape(group) + '</h3>' + links(rows) + '</section>' for group, rows in writeups.items())
    return static_page(config["title"], '<h1>' + html.escape(config["title"]) +
                       '</h1><p class="intro">' + str(sum(e["kind"] == "AI report" for e in entries)) + ' AI investigations, grouped by the prompt they received. '
                       'Reports are unscored; different prompts mean this is not a controlled model comparison.</p>'
                       '<nav class="jump" aria-label="Page sections"><a href="#ai-reports">AI reports by prompt</a><a href="#writeups">Writeups</a></nav>'
                       '<section id="ai-reports"><h2>AI reports by prompt</h2><div class="groups">' + ''.join(sections) + '</div></section>'
                       '<section id="writeups"><h2>Writeups</h2><div class="groups writeups">' + writeup_sections + '</div></section>'
                       '<footer><p>' + html.escape(NOTICE) + '</p><a href="manifest.json">Publication hashes</a></footer>', COLLECTION_STYLE)


def build(root, config, output):
    entries = collect(root, config)
    prompts = collect_prompts(root, config, entries)
    files = {}
    manifest = []
    for entry in entries:
        files[entry["slug"] + ".html"] = render_page(entry, entries).encode()
        files[entry["slug"] + ".txt"] = entry["raw"]
        manifest.append({k: entry[k] for k in ("slug", "title", "kind", "sha256", "source_sha256",
                                             "redaction_lines", "prompt_sha256", "dataset_sha256")
                         if k in entry and (k != "redaction_lines" or entry[k])})
    for prompt in prompts:
        files[prompt["slug"] + ".txt"] = prompt["raw"]
        files[prompt["slug"] + ".html"] = static_page(prompt["title"],
            '<a href="index.html#ai-reports">All reports by prompt</a><h1>' + html.escape(prompt["title"]) +
            '</h1><p>This is the exact archived task prompt supplied to the agents, including the rendered runtime instructions; not the provider system prompt.</p>'
            '<p><a href="' + prompt["slug"] + '.txt">Download exact text</a></p><p>SHA-256: <code>' + prompt["sha256"] +
            '</code></p><pre>' + html.escape(prompt["raw"].decode("utf-8")) + '</pre>', COLLECTION_STYLE)
    files["index.html"] = render_index(config, entries, prompts)
    files["manifest.json"] = (json.dumps({"reports": manifest, "prompts": [
        {k: p[k] for k in ("slug", "title", "sha256")} for p in prompts]}, indent=2) + "\n").encode()
    # Fail closed on stale files or symlinks; never sweep/delete arbitrary output.
    output.mkdir(parents=True, exist_ok=True)
    for path in output.iterdir():
        if path.is_symlink() or not path.is_file() or path.name not in files:
            raise ValueError("Unexpected output file; use a new empty output directory")
    for name, content in files.items():
        (output / name).write_bytes(content)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/urlquery-sharing.toml")
    parser.add_argument("--redactions", type=Path)
    parser.add_argument("--originals", type=Path,
                        help="Explicit hash-pinned approval to export archived reports without redaction")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        args.output = primary_root() / "reports/share-site/dist"
    if not (args.output.parent / ".openai/hosting.json").is_file():
        parser.error("Missing existing Sites binding; restore .openai/hosting.json before rebuilding")
    config = tomllib.loads(args.config.read_text())
    if args.originals is not None and args.redactions is not None:
        parser.error("Choose either original or redacted report copies")
    redactions = args.redactions
    if (redactions is None and args.originals is None
            and args.config.resolve() == (ROOT / "configs/urlquery-sharing.toml").resolve()):
        redactions = ROOT / "configs/urlquery-sharing-redactions.toml"
    if redactions is not None and redactions.is_file():
        overlay = tomllib.loads(redactions.read_text())
        if set(overlay) != {"redacted_runs"}:
            parser.error("Redaction overlay must contain only redacted_runs")
        config["redacted_runs"] = overlay["redacted_runs"]
    if args.originals is not None:
        overlay = tomllib.loads(args.originals.read_text())
        if set(overlay) != {"original_runs"}:
            parser.error("Original overlay must contain only original_runs")
        config["original_runs"] = overlay["original_runs"]
    manifest = build(ROOT, config, args.output)
    print(f"Built {len(manifest)} private reports. Publish only behind verified named-viewer access.")


def primary_root():
    common = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True
    ).strip()
    return Path(common).parent


if __name__ == "__main__":
    main()
