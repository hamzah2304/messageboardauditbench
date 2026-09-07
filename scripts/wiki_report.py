#!/usr/bin/env python3
"""The human report as the site publishes it: corpus/wiki_index.html.

`article_html()` returns the <article class="essay"> subtree with scripts removed —
what the audit UI shows in an iframe alongside the site's own stylesheets.
`article_text()` returns that subtree's text the way a browser's textContent would,
whitespace collapsed, so an anchor validated here is findable in the rendered page.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import CORPUS

INDEX = CORPUS / "wiki_index.html"
CSS = ["wiki_tokens.css", "wiki_styles.css", "wiki_chrome.css", "wiki_figures.css"]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

# Text that is not part of the reading flow: margin notes the page sets beside the
# column, and the labels that open and close a collapsed post. Their words sit inside
# a sentence in textContent, so an anchor computed over them splices a sidenote into
# the middle of a claim. The browser-side highlighter skips the same classes, so a
# span validated here is findable in the rendered page.
SKIP_CLASSES = {"sidenote", "marginnote", "margin-toggle", "ex-more", "ex-open",
                "more", "less"}


class _Article(HTMLParser):
    """Capture the first <article class="essay"> subtree, dropping <script>/<style>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0          # nesting depth inside the article, 0 = not started
        self.skip = 0           # inside script/style
        self.done = False
        self.mute: list[int] = []   # depths at which a skipped-class element opened
        self.html: list[str] = []
        self.text: list[str] = []

    @property
    def muted(self):
        return bool(self.mute)

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        d = dict(attrs)
        if not self.depth:
            if tag == "article" and "essay" in (d.get("class") or ""):
                self.depth = 1
                self.html.append(self._tag(tag, attrs))
            return
        if tag in ("script", "style"):
            self.skip += 1
            return
        classes = set((d.get("class") or "").split())
        if tag not in VOID:
            self.depth += 1
            if classes & SKIP_CLASSES:
                self.mute.append(self.depth)
        self.html.append(self._tag(tag, attrs))

    def handle_startendtag(self, tag, attrs):
        if self.depth and not self.skip and not self.done:
            self.html.append(self._tag(tag, attrs, self_close=True))

    def handle_endtag(self, tag):
        if not self.depth or self.done:
            return
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in VOID:
            return
        self.html.append(f"</{tag}>")
        if self.mute and self.mute[-1] == self.depth:
            self.mute.pop()
        self.depth -= 1
        if self.depth == 0:
            self.done = True

    def handle_data(self, data):
        if self.depth and not self.skip and not self.done:
            self.html.append(_escape_text(data))
            if not self.muted:
                self.text.append(data)

    @staticmethod
    def _tag(tag, attrs, self_close=False):
        out = "<" + tag
        for k, v in attrs:
            if k.lower().startswith("on"):     # no inline handlers in the embedded copy
                continue
            out += f' {k}="{_escape_attr(v)}"' if v is not None else f" {k}"
        return out + ("/>" if self_close else ">")


def _escape_text(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(s):
    return _escape_text(s).replace('"', "&quot;")


def _parse():
    p = _Article()
    p.feed(INDEX.read_text())
    if not p.html:
        raise SystemExit(f"no <article class=\"essay\"> in {INDEX}")
    return p


def article_html() -> str:
    return "".join(_parse().html)


def article_text() -> str:
    return re.sub(r"\s+", " ", "".join(_parse().text)).strip()


def css() -> str:
    return "\n".join((CORPUS / c).read_text() for c in CSS)


def skip_classes() -> list[str]:
    """Classes the browser-side highlighter must skip so its text matches article_text()."""
    return sorted(SKIP_CLASSES)


if __name__ == "__main__":
    h, t = article_html(), article_text()
    print(f"article html {len(h)/1000:.0f} KB, text {len(t)/1000:.0f} KB, css {len(css())/1000:.0f} KB")
    print(t[:400])
