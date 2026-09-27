#!/usr/bin/env python3
"""Reuse the original selection/comment UI with inert source text and scoped state.

No finding is automatically generated or approved. Import only exports for this
exact benchmark/source/rendered article; arbitrary original-benchmark exports
are rejected. The original UI template is read as an AST literal, never executed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent


def template_literal(path: Path, name: str) -> str:
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = node.value
            while isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "replace":
                value = value.func.value
            return ast.literal_eval(value)
    raise ValueError(f"template {name} missing")


class InertArticle(HTMLParser):
    allowed = {"p", "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "pre", "code", "strong", "em", "br", "table", "thead", "tbody", "tr", "td", "th", "summary", "details"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.skipped = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.active = True
        if not self.active:
            return
        if tag in {"script", "style", "svg"}:
            self.skipped += 1
        if not self.skipped and tag in self.allowed:
            self.parts.append("<details open>" if tag == "details" else f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg"} and self.skipped:
            self.skipped -= 1
            return
        if self.active and not self.skipped and tag in self.allowed and tag != "br":
            self.parts.append(f"</{tag}>")
        if tag == "article":
            self.active = False

    def handle_data(self, data):
        if self.active and not self.skipped:
            self.parts.append(html.escape(data))


def build(source: Path, output: Path, imports: list[Path]):
    raw = source.read_bytes()
    parser = InertArticle()
    parser.feed(raw.decode("utf-8"))
    article = "".join(parser.parts)
    if len(article) < 1000:
        raise ValueError("source article not found; refusing empty extraction UI")
    scope = {"benchmark_id": "urlquery", "report_sha256": hashlib.sha256(raw).hexdigest(),
             "article_sha256": hashlib.sha256(article.encode()).hexdigest()}
    comments, statuses = [], {}
    for path in imports:
        data = json.loads(path.read_text())
        if any(data.get(key) != value for key, value in scope.items()):
            raise ValueError(f"wrong benchmark/source/anchor version: {path}")
        comments.extend(data.get("comments", []))
        statuses.update(data.get("claim_status", {}))
    ids = [c["id"] for c in comments]
    for comment in comments:
        if not re.fullmatch(r"[a-z0-9_-]{1,60}", comment.get("author", "me")):
            raise ValueError("author must use 1–60 lowercase letters, digits, underscores or hyphens")
        if comment.get("type") not in {"gap", "note", "covered"} or comment.get("status") not in {None, "approved", "rejected"}:
            raise ValueError("invalid comment type/status")
        if comment.get("claim"):
            raise ValueError("no approved claim IDs exist in the initial extraction view")
        for reply in comment.get("replies", []):
            if not re.fullmatch(r"[a-z0-9_-]{1,60}", reply.get("author", "me")):
                raise ValueError("invalid reply author")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate comment IDs; pass only the latest export")
    authors = sorted({c.get("author", "me") for c in comments})
    seed_hash = hashlib.sha256(json.dumps(comments, sort_keys=True).encode()).hexdigest()[:12]
    def js(value):
        return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    embed = "\n".join(f"var {key}={js(value)};" for key, value in {
        "CDATA": {"claims": []}, "SEED": comments, "AUTHORS": authors,
        "ASLOT": {a: i % 6 for i, a in enumerate(authors)}, "SEEDHASH": seed_hash,
        "SCOPE": scope, "IMPORTED_STATUSES": statuses}.items())
    original = HERE / "build_combined_coverage.py"
    css = template_literal(original, "INJECT_CSS").replace("__HLCSS__", "::highlight(cmt-0){background:#CDE9DD}").replace("__AUBADGE__", "")
    interface = template_literal(original, "INJECT_HTML").replace("__EMBED__", embed)
    interface = interface.replace('"coverage_combined_"+SEEDHASH', '"coverage_urlquery_"+SCOPE.article_sha256+"_"+SEEDHASH')
    interface = interface.replace("'cov_author'", "'urlquery_cov_author'")
    interface = interface.replace(".trim().toLowerCase(); localStorage", ".trim().toLowerCase().replace(/[^a-z0-9_-]/g,'_').slice(0,60)||'me'; localStorage")
    interface = interface.replace("C.claimStatus={};", "C.claimStatus=IMPORTED_STATUSES;")
    interface = interface.replace('report:"human collusion.wiki report",', 'report:"URLQuery source report",benchmark_id:SCOPE.benchmark_id,report_sha256:SCOPE.report_sha256,article_sha256:SCOPE.article_sha256,')
    interface = interface.replace('a.download="coverage_combined.json"', 'a.download="urlquery_findings_"+SCOPE.article_sha256.slice(0,12)+".json"')
    interface = interface.replace("Coverage &mdash; combined", "URLQuery findings")
    body = '<!doctype html><html><head><meta charset="utf-8"><title>URLQuery findings extraction</title><style>body{font:16px/1.65 system-ui;background:#faf9f6;color:#222}article{max-width:850px;padding:25px;margin:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}aside{padding:18px;background:#fff2d8}h1,h2,h3{line-height:1.25}summary{font-weight:600}</style>' + css + '</head><body><aside>Same selection/comment workflow as the original benchmark. Select a passage and add a candidate finding in the note. These are not approved rubric claims. Scope: offline scan observations only; external attribution and cross-source matches need separate evidence. Export JSON before rebuilding or changing browsers.</aside><article class="essay">' + article + '</article>' + interface + '</body></html>'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    return scope


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=HERE / "urlquery_findings.html")
    ap.add_argument("--import-review", type=Path, action="append", default=[])
    args = ap.parse_args()
    print(json.dumps(build(args.source, args.output, args.import_review), indent=2))
