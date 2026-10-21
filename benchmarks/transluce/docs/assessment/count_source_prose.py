"""Count saved Transluce HTML without quotes, excerpts, or site chrome.

All eight collapsed sections are included. Main prose, appendix, footnotes,
and the six March 6 timeline descriptions are reported separately. Headings,
captions, chart labels, overview graphic, URL margin notes, quoted spans,
and code excerpts are excluded. Inline domain names are retained.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import bs4
from bs4 import BeautifulSoup

QUOTES = re.compile(r'“[^”]*”|"[^"\n]*"')
DOMAIN = re.compile(r"[A-Za-z0-9*.-]+\.[A-Za-z]{2,}")


def clean(node):
    for el in list(node.select(".margin-note, button, script, style, svg, sup, blockquote, pre")):
        if el.parent is not None:
            el.decompose()
    for el in list(node.find_all("code")):
        text = el.get_text(" ", strip=True)
        if DOMAIN.fullmatch(text):
            el.replace_with(text)
        else:
            el.decompose()
    for el in list(node.find_all("a")):
        label = el.get_text(strip=True)
        if label.isdigit() or label in {"↩", "View entry ↗"} or label.startswith(("http://", "https://")):
            el.decompose()


def words(text):
    text = QUOTES.sub("", text)
    return sum(any(c.isalnum() for c in w) for w in text.split())


def count_prose(path):
    raw = path.read_bytes()
    soup = BeautifulSoup(raw, "html.parser")
    content = soup.select_one("article .article-content")
    assert content is not None, "Article selector changed; review extraction."
    body = content.find_all("div", recursive=False)[-1]
    assert body.find("h2", id="appendix"), "Appendix missing; do not count a truncated article."
    assert len(body.find_all("details")) == 8, "Collapsed sections changed; review extraction."
    timeline = body.select('p[class*="March6Sequence_description"]')
    assert len(timeline) == 6
    timeline_words = 0
    for el in timeline:
        clean(el)
        timeline_words += words(el.get_text(" ", strip=True))
    for el in list(body.select('figure, div[class*="articleFigure"], div[class*="March6Sequence_figure"]')):
        el.decompose()
    clean(body)
    section = "Introduction"
    counts = defaultdict(int)
    blocks = []
    for el in body.find_all(["h2", "p", "li"]):
        if el.name == "h2":
            section = el.get_text(" ", strip=True)
            continue
        if el.find_parent(["p", "li"]):
            continue
        text = el.get_text(" ", strip=True)
        n = words(text)
        counts[section] += n
        blocks.append({"section": section, "words": n, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    main = sum(n for section, n in counts.items() if section not in {"Appendix", "Footnotes"})
    return {
        "source": "https://transluce.org/agent-activity",
        "html_sha256": hashlib.sha256(raw).hexdigest(),
        "beautifulsoup_version": bs4.__version__,
        "method": __doc__,
        "all_eight_collapsed_sections_included": True,
        "main_prose_words": main,
        "appendix_prose_words": counts["Appendix"],
        "footnote_prose_words": counts["Footnotes"],
        "body_prose_words": sum(counts.values()),
        "timeline_description_words": timeline_words,
        "body_and_timeline_prose_words": sum(counts.values()) + timeline_words,
        "section_words": dict(counts),
        "blocks": blocks,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = count_prose(args.html)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "blocks"}, indent=2))
