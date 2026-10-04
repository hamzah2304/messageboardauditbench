"""Build the three-post source/findings review for ui-kit (stdlib only)."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

POSTS = [
    ("truth", "what-do-we-tell-the-humans"),
    ("gemini", "saving-gemini"),
    ("leader", "ais-finetune-their-own-leader-a-barking"),
]
ALLOWED = set(
    "p span a img blockquote h1 h2 h3 h4 h5 h6 ul ol li figure figcaption strong em b i code pre br div table tr td th thead tbody hr sup sub".split()
)
VOID = {"img", "br", "hr"}


def safe_url(value: str) -> bool:
    return urlsplit(value).scheme in {"https", "http"}


class Article(HTMLParser):
    """Keep article structure, images and links, but no scripts or controls."""

    def __init__(self, key: str):
        super().__init__(convert_charrefs=True)
        self.key = key
        self.parts: list[str] = []
        self.images: dict[str, str] = {}
        self.skip = 0
        self.number = 0
        self.image_number = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "button", "form"}:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED:
            return
        attrs = dict(attrs)
        if tag == "div" and "twitter-embed" in attrs.get("class", ""):
            try:
                tweet = json.loads(attrs.get("data-attrs", "{}"))
            except (ValueError, TypeError):
                tweet = {}
            self.number += 1
            self.parts.append(
                f'<blockquote class="embedded-post" data-uikit-section="{self.key}-source-{self.number}">'
            )
            self.parts.append("<p>" + html.escape(tweet.get("full_text", "")) + "</p>")
            url = tweet.get("url", "")
            if safe_url(url):
                self.parts.append(
                    '<p><a href="'
                    + html.escape(url, quote=True)
                    + '" target="_blank" rel="noopener noreferrer">'
                    + html.escape(
                        "@"
                        + tweet.get("username", "unknown")
                        + " · "
                        + tweet.get("date", "")
                        + " · "
                        + url
                    )
                    + "</a></p>"
                )
            for photo in tweet.get("photos", []):
                self.handle_starttag("img", [("src", photo.get("img_url", ""))])
            quoted = tweet.get("quoted_tweet") or {}
            if quoted.get("full_text"):
                self.parts.append(
                    "<p>Quoted post: " + html.escape(quoted["full_text"]) + "</p>"
                )
            self.parts.append("</blockquote>")
        output = []
        if tag in {"p", "blockquote", "figure", "h1", "h2", "h3", "h4"}:
            self.number += 1
            output.append(("data-uikit-section", f"{self.key}-source-{self.number}"))
        if tag == "a" and safe_url(attrs.get("href", "")):
            output += [
                ("href", attrs["href"]),
                ("target", "_blank"),
                ("rel", "noopener noreferrer"),
            ]
        if tag == "img":
            self.image_number += 1
            output.append(("data-source-image", self.image_number))
            src = attrs.get("src", "")
            try:
                src = json.loads(attrs.get("data-attrs", "{}")).get("src") or src
            except (ValueError, TypeError):
                pass
            if not safe_url(src):
                return
            name = "images/" + hashlib.sha256(src.encode()).hexdigest()[:20] + ".img"
            self.images[src] = name
            output += [
                ("src", name),
                (
                    "alt",
                    attrs.get("alt")
                    or "Source screenshot; open the image for a larger view",
                ),
                ("loading", "lazy"),
            ]
        self.parts.append(
            "<"
            + tag
            + "".join(f' {k}="{html.escape(str(v), quote=True)}"' for k, v in output)
            + ">"
        )

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "button", "form"}:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in ALLOWED and tag not in VOID:
            self.parts.append(f"</{tag}>")

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(html.escape(value))


def download_image(item, output):
    url, name = item
    path = output / name
    if path.exists() and path.stat().st_size:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            path.write_bytes(response.read())
        return None
    except OSError as exc:
        return {"url": url, "path": name, "error": str(exc)}


def copy_generated(source: Path, destination: Path):
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extraction-suffix", default="")
    parser.add_argument("--prompt-file", default="extraction-prompt-v2.md")
    parser.add_argument("--previous-extraction-suffix")
    parser.add_argument("--all-posts", action="store_true")
    parser.add_argument("--extractions", type=Path)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "images").mkdir(exist_ok=True)
    articles = []
    images = {}
    posts = POSTS
    if args.all_posts:
        posts = [
            (p["slug"], p["slug"])
            for p in json.loads((args.input / "screening-v2.json").read_text())["posts"]
            if p["decision"] == "keep"
        ]
    for key, slug in posts:
        source = json.loads((args.input / f"{slug}.json").read_text())
        extraction_base = (
            (args.extractions / slug)
            if args.extractions
            else (args.input / f"trial-{key}{args.extraction_suffix}")
        )
        if extraction_base.with_suffix(".json").exists():
            extraction = json.loads(extraction_base.with_suffix(".json").read_text())
        elif args.allow_pending:
            extraction = {
                "status": "pending",
                "findings": [],
                "excluded_source_claims": [],
                "source_limits": [
                    "Extraction is still running. Refresh to see the result."
                ],
            }
        else:
            raise FileNotFoundError(extraction_base.with_suffix(".json"))
        if args.extractions and extraction.get("status") != "pending":
            run = extraction["run"]
            if run["model"] != "gpt-6.1-sol" or run["reasoning"]["effort"] != "high":
                raise ValueError("Batch review requires GPT-6.1 Sol with high reasoning")
        if args.previous_extraction_suffix is not None:
            previous = json.loads(
                (
                    args.input / f"trial-{key}{args.previous_extraction_suffix}.json"
                ).read_text()
            )
            claims = {
                sf["id"]: sf["claim"]
                for finding in previous["findings"]
                for sf in finding["subfindings"]
            }
            for finding in extraction["findings"]:
                for sf in finding["subfindings"]:
                    old = claims.get(sf["id"])
                    if old and old != sf["claim"]:
                        sf["previous_claim"] = old
        sanitized = Article(key)
        sanitized.feed(source["body_html"])
        images.update(sanitized.images)
        articles.append(
            {
                "key": key,
                "title": source["title"],
                "url": source["canonical_url"],
                "html": "".join(sanitized.parts),
                "extraction": extraction,
            }
        )
        if extraction_base.with_suffix(".md").exists():
            shutil.copyfile(
                extraction_base.with_suffix(".md"), args.output / f"trial-{key}.md"
            )
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = [
            result
            for result in pool.map(
                lambda item: download_image(item, args.output), images.items()
            )
            if result
        ]
    if errors:
        # Remote fallback keeps the source visible even if a cache request fails.
        for article in articles:
            for error in errors:
                article["html"] = article["html"].replace(
                    error["path"], html.escape(error["url"], quote=True)
                )
    data = {
        "model": "GPT-6.1 Sol",
        "reasoning_effort": "high" if args.extractions else None,
        "prompt_url": "https://docs.google.com/document/d/18990mApAhiePaBvboLdEJNPudffXaLdGaIVNUH58xSE/edit?tab=t.b4p0fddg1zx8",
        "articles": articles,
        "image_cache_errors": errors,
    }
    temporary = args.output / "review.json.tmp"
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temporary.replace(args.output / "review.json")
    if args.all_posts:
        export = {
            "model": data["model"],
            "reasoning_effort": data["reasoning_effort"],
            "articles": [
                {k: v for k, v in article.items() if k != "html"}
                for article in articles
            ],
        }
        export_temporary = args.output / "batch-findings.json.tmp"
        export_temporary.write_text(json.dumps(export, ensure_ascii=False, indent=2))
        export_temporary.replace(args.output / "batch-findings.json")
    copy_generated(
        Path(__file__).with_name("aivillage_findings_review.template.html"),
        args.output / "index.html",
    )
    copy_generated(
        (args.extractions or args.input) / args.prompt_file,
        args.output / "extraction-prompt-v2.md",
    )
    print(
        json.dumps(
            {
                "articles": len(articles),
                "findings": sum(len(a["extraction"]["findings"]) for a in articles),
                "images": len(images),
                "image_errors": len(errors),
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
