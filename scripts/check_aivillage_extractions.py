"""Check extracted article-text quotes against the original saved articles."""

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewers"))
from build_aivillage_findings_review import Article


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "h1", "h2", "h3", "blockquote", "li", "figure", "br"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--sources", type=Path)
    args = parser.parse_args()
    source_directory = args.sources or args.directory.parent / "aivillage-substack-screen"
    checks = []
    for packet_path in sorted(args.directory.glob("*.packet.json")):
        slug = packet_path.name.removesuffix(".packet.json")
        result_path = args.directory / f"{slug}.json"
        if not result_path.exists():
            continue
        data = json.loads(result_path.read_text())
        packet = json.loads(packet_path.read_text())
        source = json.loads((source_directory / f"{slug}.json").read_text())
        article = Article(slug)
        article.feed(source["body_html"])
        plain = PlainText()
        plain.feed("".join(article.parts))
        text = normalize("".join(plain.parts))
        unmatched = []
        text_quotes = image_quotes = 0
        for finding in data["findings"]:
            for subfinding in finding["subfindings"]:
                for support in subfinding["source_support"]:
                    if support.get("image_number") is not None:
                        image_quotes += 1
                        continue
                    text_quotes += 1
                    if normalize(support["quote"]) not in text:
                        unmatched.append(
                            {
                                "id": subfinding["id"],
                                "quote": support["quote"],
                                "location": support["location"],
                            }
                        )
        check = {
            "slug": slug,
            "article_text_quotes": text_quotes,
            "image_quotes_requiring_visual_verification": image_quotes,
            "unmatched_text_quotes": unmatched,
            "images_submitted": len(packet["images"]),
            "image_inspection_entries": len(data["image_review"]["images"]),
        }
        (args.directory / f"{slug}.checks.json").write_text(
            json.dumps(check, ensure_ascii=False, indent=2)
        )
        checks.append(check)
    summary = {
        "articles_checked": len(checks),
        "article_text_quotes": sum(c["article_text_quotes"] for c in checks),
        "unmatched_text_quotes": sum(len(c["unmatched_text_quotes"]) for c in checks),
        "checks": checks,
    }
    (args.directory / "quote-checks.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "checks"}))
    if summary["unmatched_text_quotes"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
