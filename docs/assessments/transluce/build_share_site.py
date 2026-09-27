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
    "Only links within this published collection are active. Comments stay in your browser; "
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


def collect(root, config):
    entries = []
    for document in config["documents"]:
        entries.append({**document, "path": inside(root, document["source"]), "kind": "overview"})
    approved = {r["run_id"]: r["sha256"] for r in config.get("approved_runs", [])}
    if len(approved) != len(config.get("approved_runs", [])):
        raise ValueError("Duplicate sharing approval")
    for name in config["run_indexes"]:
        data = json.loads(inside(root, name).read_text())
        if data["benchmark_id"] != "urlquery":
            raise ValueError("Wrong benchmark in publication index")
        for row in data["attempts"]:
            if not row.get("report_path"):
                continue
            if approved.get(row["run_id"]) != row["report_sha256"]:
                raise ValueError("AI report lacks an explicit matching sharing approval")
            # Indexes retain original absolute paths. Resolve their report-root
            # suffix here, or the immutable run archive after worktree removal.
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
            entries.append({"path": path, "slug": row["preview_name"], "kind": "AI report",
                            "report_id": "urlquery-report-" + row["run_id"],
                            "title": f"{row['report_label']} · run {row['replicate']}",
                            "expected_sha256": row["report_sha256"],
                            "notice": FALLBACK_NOTICE(row),
                            "prompt_sha256": row["prompt_sha256"],
                            "dataset_sha256": row["dataset_sha256"]})
    slugs = set()
    for entry in entries:
        slug = entry["slug"]
        if not re.fullmatch(r"[a-z][a-z0-9_]+", slug) or slug in slugs or slug == "index":
            raise ValueError("Invalid or duplicate report slug")
        slugs.add(slug)
        entry["raw"] = entry["path"].read_bytes()
        entry["sha256"] = hashlib.sha256(entry["raw"]).hexdigest()
        if entry.get("expected_sha256", entry["sha256"]) != entry["sha256"]:
            raise ValueError("Report hash changed since the run index was generated")
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
        return '<a href="' + html.escape(target, quote=True) + '">'

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
    substitutions = {
        "BODY": body, "TOC": "".join(toc), "TITLE": html.escape(entry["title"]),
        "SOURCE": entry["slug"] + ".txt", "SEED": "null",
        "META": json.dumps({"report_id": entry.get("report_id", entry["slug"]), "report_sha256": entry["sha256"]}).replace("<", "\\u003c"),
        "NOTICE": '<div class="notice">' + html.escape(NOTICE + entry.get("notice", "")) + '</div>',
    }
    return re.sub(r"__([A-Z]+)__", lambda m: substitutions[m[1]], shell)


def build(root, config, output):
    entries = collect(root, config)
    files = {}
    manifest = []
    for entry in entries:
        files[entry["slug"] + ".html"] = render_page(entry, entries).encode()
        files[entry["slug"] + ".txt"] = entry["raw"]
        manifest.append({k: entry[k] for k in ("slug", "title", "kind", "sha256", "prompt_sha256", "dataset_sha256") if k in entry})
    links = "".join('<li><a href="' + e["slug"] + '.html">' + html.escape(e["title"]) + '</a></li>' for e in entries)
    style = re.search(r"<style>(.*?)</style>", SHELL, re.S)[1]
    files["index.html"] = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                           '<meta name="viewport" content="width=device-width,initial-scale=1">'
                           '<title>' + html.escape(config["title"]) + '</title><style>' + style +
                           '</style><main style="max-width:900px;margin:auto;padding:40px 24px">'
                           '<h1>' + html.escape(config["title"]) + '</h1><p>' + html.escape(NOTICE) +
                           '</p><p>The two pilot batches used different prompts; these are not scored model comparisons.</p>'
                           '<ul>' + links + '</ul><p><a href="manifest.json">Publication hashes</a></p></main></html>').encode()
    files["manifest.json"] = (json.dumps({"reports": manifest}, indent=2) + "\n").encode()
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        args.output = primary_root() / "reports/share-site/dist"
    if not (args.output.parent / ".openai/hosting.json").is_file():
        parser.error("Missing existing Sites binding; restore .openai/hosting.json before rebuilding")
    manifest = build(ROOT, tomllib.loads(args.config.read_text()), args.output)
    print(f"Built {len(manifest)} private reports. Publish only behind verified named-viewer access.")


def primary_root():
    common = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True
    ).strip()
    return Path(common).parent


if __name__ == "__main__":
    main()
