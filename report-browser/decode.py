"""Unpack the programs agents smuggle through submitted URLs.

Agent submissions often wrap an HTML/JS program in the URL itself: a
``httpbin.org/base64/<b64>`` echo path, a ``data:`` URL, a base64 query value,
or a nested ``?url=https://...`` relay. ``analyze`` walks those layers
recursively and returns a flat list of decoded nodes plus every URL the decoded
content points at (the "intended targets").

Nothing here executes anything: decoding is pure string work, and the UI shows
the results as escaped text.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from urllib.parse import parse_qsl, unquote, unquote_plus, urlsplit

MAX_DEPTH = 5
MAX_TEXT = 200_000

B64_CHARS = re.compile(r"^[A-Za-z0-9+/=_-]+$")
URL_RE = re.compile(r"""(?:https?|wss?)://[^\s"'<>`\\)\]}]+""", re.I)
SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.I | re.S)
B64_PATH_RE = re.compile(r"/base64/([^/?#]+)", re.I)
DATA_URL_RE = re.compile(r"^data:([^,;]*)((?:;[^,;]*)*?)(;base64)?,(.*)$", re.I | re.S)


def _b64decode(s: str) -> str | None:
    s = unquote(s).strip()
    if len(s) < 8 or not B64_CHARS.match(s):
        return None
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        raw = base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
    if not text or printable / len(text) < 0.95:
        return None
    return text


def classify(text: str) -> str:
    t = text.lstrip()[:500].lower()
    if t.startswith(("<!doctype", "<html", "<body", "<head", "<script", "<form", "<meta", "<div", "<pre", "<h1")):
        return "html"
    if t.startswith(("{", "[")):
        return "json"
    if re.search(r"\b(fetch|XMLHttpRequest|function|const|let|var|await|document\.)\b", text[:4000]):
        return "js"
    return "text"


def signature(text: str) -> str:
    """Hash of a program with literals abstracted away, to bunch near-identical payloads."""
    t = URL_RE.sub("URL", text)
    t = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", "S", t)
    t = re.sub(r"\d+", "0", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()[:12]


def _fqdn(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def analyze(url: str) -> dict:
    """Return {"nodes": [...], "targets": [fqdn...], "kinds": [...], "sig": str|None}."""
    nodes: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, via: str, text: str, depth: int, parent: int | None) -> int:
        idx = len(nodes)
        ctype = classify(text)
        urls = sorted(set(u.rstrip(".,;") for u in URL_RE.findall(text)))[:200]
        nodes.append({
            "i": idx, "parent": parent, "depth": depth, "kind": kind, "via": via,
            "ctype": ctype, "size": len(text), "text": text[:MAX_TEXT], "urls": urls,
        })
        if ctype == "html":
            for body in SCRIPT_RE.findall(text):
                if body.strip():
                    add("inline-script", "<script>", body, depth + 1, idx)
        for u in urls:
            walk_url(u, depth + 1, idx)
        return idx

    def walk_url(u: str, depth: int, parent: int | None) -> None:
        if depth > MAX_DEPTH or u in seen:
            return
        seen.add(u)
        if u[:5].lower() == "data:":
            m = DATA_URL_RE.match(u)
            if m:
                body = m.group(4)
                text = _b64decode(body) if m.group(3) else unquote(body)
                if text:
                    add("data-url", f"data:{m.group(1)}", text, depth, parent)
            return
        for m in B64_PATH_RE.finditer(u):
            text = _b64decode(m.group(1))
            if text:
                add("base64-path", _fqdn(u) + "/base64/", text, depth, parent)
        try:
            query = urlsplit(u).query
        except ValueError:
            query = ""
        for key, val in parse_qsl(query, keep_blank_values=False):
            if re.match(r"^(?:https?|data):", val, re.I):
                nodes_before = len(nodes)
                walk_url(val, depth + 1, parent)
                if len(nodes) == nodes_before:
                    nodes.append({
                        "i": len(nodes), "parent": parent, "depth": depth, "kind": "url-param",
                        "via": f"?{key}=", "ctype": "url", "size": len(val), "text": val,
                        "urls": [val],
                    })
            elif len(val) >= 24:
                text = _b64decode(val)
                if text:
                    add("base64-param", f"?{key}=", text, depth, parent)

    walk_url(url, 0, None)
    if not nodes and "%3C" in url.upper():
        text = unquote_plus(url)
        add("urlencoded", "percent-encoding", text, 0, None)

    carrier = _fqdn(url)
    targets: list[str] = []
    for n in nodes:
        for u in n["urls"]:
            f = _fqdn(u)
            if f and "." in f and f != carrier and f not in targets:
                targets.append(f)
    programs = [n for n in nodes if n["ctype"] in ("html", "js")]
    sig = signature(programs[0]["text"]) if programs else None
    return {
        "nodes": nodes,
        "targets": targets,
        "kinds": sorted({n["kind"] for n in nodes}),
        "sig": sig,
    }
