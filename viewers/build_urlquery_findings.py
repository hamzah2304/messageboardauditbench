#!/usr/bin/env python3
"""Build the manual findings-extraction page for Transluce's urlquery article.

The page shows the article as published (Transluce's own stylesheet and the
static SVG/PNG figures) with every script, event handler, form and remote embed
removed, plus a sidebar where people write findings in their own words, add
sub-findings under them, and attach quotes from the article to either level.

No finding is generated or approved automatically. Imports are accepted only
for this exact benchmark/source/rendered article.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = "https://transluce.org"
DEFAULT_ASSETS = ROOT / "data/transluce/site_assets"
SCHEMA = "urlquery-findings-v2"
DERIVABLE = {"yes", "partly", "no", None}
KINDS = {"finding", "conclusion", "context"}

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# Whole subtrees that never reach the page: executable, remote, or site chrome.
DROP = {"script", "noscript", "iframe", "object", "embed", "form", "input", "textarea", "select",
        "template", "foreignobject", "animate", "set", "animatemotion", "animatetransform",
        "header", "footer", "meta", "link", "base", "style", "title", "head"}
URL_ATTRS = {"href", "src", "xlink:href", "action", "formaction", "poster", "srcset"}


class InertPage(HTMLParser):
    """Re-serialise the page body without anything that can run or fetch."""

    def __init__(self, images: dict[str, str]):
        super().__init__(convert_charrefs=False)
        self.images, self.parts, self.stack, self.drop_depth = images, [], [], 0
        self.in_body = False

    def _attrs(self, tag, attrs):
        out = []
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on") or name in {"srcdoc", "ping", "download", "formaction", "action"}:
                continue
            value = value or ""
            if name in URL_ATTRS:
                if re.match(r"\s*(javascript|data|vbscript):", value, re.I):
                    continue
                if tag == "img" and name == "src":
                    if value not in self.images:
                        continue  # never load a remote image
                    value = self.images[value]
                elif name == "srcset":
                    continue
                elif value.startswith("/"):
                    value = SITE + value
            out.append(f' {name}="{html.escape(value, quote=True)}"')
        if tag == "a" and any(n == "href" for n, _ in attrs):
            href = dict(attrs).get("href") or ""
            if not href.startswith("#"):
                out.append(' target="_blank" rel="noopener noreferrer"')
        return "".join(out)

    def _skip_chrome(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        return tag == "div" and cls.startswith("sticky top-0")  # the site's nav bar

    def handle_starttag(self, tag, attrs, closed=False):
        if tag == "body":
            self.in_body = True
            return
        if not self.in_body:
            return
        if self.drop_depth or tag in DROP or self._skip_chrome(tag, attrs):
            if tag not in VOID and not closed:
                self.drop_depth += 1
            return
        self.parts.append(f"<{tag}{self._attrs(tag, attrs)}{' /' if closed else ''}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, closed=True)

    def handle_endtag(self, tag):
        if tag == "body":
            self.in_body = False
            return
        if not self.in_body or tag in VOID:
            return
        if self.drop_depth:
            self.drop_depth -= 1
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.in_body and not self.drop_depth:
            self.parts.append(data)  # convert_charrefs=False: already-escaped source text stays escaped

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def fetch_assets(source_html: str, assets: Path) -> tuple[str, dict[str, str]]:
    """Transluce's CSS and article images, cached beside the article (fetched once)."""
    assets.mkdir(parents=True, exist_ok=True)
    css_paths = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="(/_next/static/css/[^"]+)"', source_html)
    css_paths += re.findall(r'<link[^>]+href="(/_next/static/css/[^"]+)"[^>]*rel="stylesheet"', source_html)
    img_paths = sorted(set(re.findall(r'<img[^>]+src="(/images/[^"]+)"', source_html)))

    def cached(path: str) -> bytes:
        local = assets / Path(path).name
        if not local.exists():
            with urllib.request.urlopen(SITE + path, timeout=30) as resp:
                local.write_bytes(resp.read())
        return local.read_bytes()

    css = "\n".join(cached(p).decode("utf-8") for p in dict.fromkeys(css_paths))
    css = re.sub(r"@import[^;]+;", "", css)
    css = re.sub(r"url\((?!['\"]?data:)[^)]*\)", "none", css)  # no remote fonts/images from CSS
    css = css.replace("100vw", "var(--fx-vw,100vw)")  # full-bleed figures must stop at the sidebar
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml"}
    images = {}
    for p in img_paths:
        kind = mime.get(Path(p).suffix.lower())
        if kind and kind != "image/svg+xml":
            images[p] = f"data:{kind};base64," + base64.b64encode(cached(p)).decode()
    return css, images


def validate_import(data: dict, scope: dict) -> tuple[list[dict], list[dict]]:
    """Split a v2 export into finding and quote records, rejecting anything off-scope."""
    if any(data.get(key) != value for key, value in scope.items()):
        raise ValueError("wrong benchmark/source/anchor version")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"expected schema {SCHEMA}")
    findings, quotes = [], []
    ids = {f.get("id") for f in data.get("findings", [])}
    for f in data.get("findings", []):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(f.get("id", ""))):
            raise ValueError("invalid finding id")
        if f.get("derivable") not in DERIVABLE or f.get("kind", "finding") not in KINDS:
            raise ValueError("invalid derivable/kind")
        if f.get("status", "draft") not in {"draft", "rejected"}:
            raise ValueError("invalid status")
        if f.get("parent") not in ids | {None}:
            raise ValueError("sub-finding points at a missing parent")
        quotes.extend({**{k: q.get(k) for k in ("id", "s", "e", "raw", "quote", "section", "author", "created")},
                       "finding": f["id"]} for q in f.get("quotes", []))
        findings.append({k: f.get(k) for k in ("id", "parent", "text", "note", "kind", "derivable", "status",
                                               "author", "created", "updated")})
    return findings, quotes


def artifact_fragment(page: str) -> str:
    """claude.ai wraps a published page in its own skeleton, so drop ours."""
    page = re.sub(r"^<!doctype html>\s*<html[^>]*><head><meta[^>]*><meta[^>]*>\s*", "", page, count=1)
    page = page.replace("</head><body>", "", 1)
    return re.sub(r"</body></html>\s*$", "", page)


def build(source: Path, output: Path, imports: list[Path], assets: Path = DEFAULT_ASSETS,
          artifact_out: Path | None = None):
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    css, images = fetch_assets(text, assets)
    parser = InertPage(images)
    parser.feed(text if "<body" in text else f"<body>{text}</body>")
    page = "".join(parser.parts)
    article = re.search(r"<article\b.*?</article>", page, re.S)
    if not article or len(article.group(0)) < 1000:
        raise ValueError("source article not found; refusing empty extraction UI")
    scope = {"benchmark_id": "urlquery", "report_sha256": hashlib.sha256(raw).hexdigest(),
             "article_sha256": hashlib.sha256(article.group(0).encode()).hexdigest()}
    seed = {"findings": [], "quotes": []}
    for path in imports:
        try:
            findings, quotes = validate_import(json.loads(path.read_text()), scope)
        except ValueError as exc:
            raise ValueError(f"{exc}: {path}") from None
        seed["findings"] += findings
        seed["quotes"] += quotes
    ids = [f["id"] for f in seed["findings"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate finding IDs; pass only the latest export")

    def js(value):
        return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    embed = f"var SCOPE={js(scope)};var SEED={js(seed)};var SEEDHASH={js(hashlib.sha256(json.dumps(seed, sort_keys=True).encode()).hexdigest()[:12])};var SCHEMA={js(SCHEMA)};"
    shell = (HERE / "urlquery_findings.template.html").read_text()
    for key, value in {"__SITE_CSS__": css.replace("</style", "<\\/style"), "__EMBED__": embed,
                       "__LIMITS__": (HERE / "urlquery_findings.limits.html").read_text(), "__PAGE__": page}.items():
        shell = shell.replace(key, value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(shell, encoding="utf-8")
    if artifact_out:
        artifact_out.parent.mkdir(parents=True, exist_ok=True)
        artifact_out.write_text(artifact_fragment(shell), encoding="utf-8")
    return scope


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=ROOT / "data/transluce/agent-activity.html")
    ap.add_argument("--output", type=Path, default=HERE / "urlquery_findings.html")
    ap.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    ap.add_argument("--import-review", type=Path, action="append", default=[])
    ap.add_argument("--artifact-out", type=Path, help="also write a copy for publishing as a claude.ai artifact")
    args = ap.parse_args()
    print(json.dumps(build(args.source, args.output, args.import_review, args.assets, args.artifact_out), indent=2))
