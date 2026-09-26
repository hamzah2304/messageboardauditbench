#!/usr/bin/env python3
"""Build viewers/transluce_explorer.html: browse Transluce's urlquery.net
agent-activity catalogue, read the raw urlquery evidence for the fetched subset,
and leave comments (questions) on reports, sections, selected text or the page.

    uv run scripts/fetch_transluce.py          # catalogue + raw JSON subset
    uv run viewers/build_transluce_explorer.py
    python3 scripts/html_viewer.py             # then open /transluce_explorer.html

Inputs are the primary checkout's gitignored data/transluce/. The page embeds
urlquery content, which may not be redistributed, so it is written to the
primary checkout's viewers/ (gitignored) and never committed.

Comments: always kept in browser localStorage; when the page is served by
scripts/html_viewer.py they are also written to data/transluce/comments.json,
which is the file to hand back to an agent. Export/Import JSON covers file://.
"""
import base64
import binascii
import csv
import json
import re
import subprocess
import sys
import urllib.parse
from html import escape
from html.parser import HTMLParser
from pathlib import Path


def primary_root():
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


ROOT = primary_root()
SRC = ROOT / "data" / "transluce"
OUT = ROOT / "viewers" / "transluce_explorer.html"
COMMENTS = SRC / "comments.json"
TEMPLATE = Path(__file__).with_name("transluce_explorer.template.html")


# ---- the blog post --------------------------------------------------------------
KEEP = {"h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "a", "code", "em", "strong", "b", "i",
        "blockquote", "table", "thead", "tbody", "tr", "th", "td", "pre", "sup", "br", "figcaption"}
SKIP = {"script", "style", "svg", "button", "nav", "footer", "noscript", "img", "picture", "iframe",
        "form", "input", "select", "canvas", "video", "header"}
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr", "area", "col", "embed"}
BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "blockquote", "td", "th", "figcaption", "pre"}
RID = re.compile(r"urlquery\.net/report/([0-9a-f-]{36})")


class PostParser(HTMLParser):
    """Reduce the article to plain semantic HTML; record where each report is cited."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0
        self.inside = False
        self.section = ""
        self.cites = {}          # rid -> {section, context, block}
        self.notes = {}          # rid -> full scanned URL from the margin note
        self.block_n = 0
        self.block_text, self.block_rids, self.block_id = [], [], None
        self.heading = None
        self.last_rid = None
        self.note_depth = None
        self.note_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "main":
            self.inside = True
        if not self.inside:
            return
        if self.note_depth is not None:
            if tag not in VOID:
                self.note_depth += 1
            return
        if self.skip:
            if tag not in VOID:
                self.skip += 1
            return
        if "margin-note" in cls and "report-url-note" in cls:
            self.note_depth, self.note_text = 1, []
            return
        if tag in SKIP or "margin-note" in cls:
            if tag not in VOID:
                self.skip = 1
            return
        if tag == "details":
            tag = "section"
        if tag == "summary":
            tag = "h3"
        if tag not in KEEP and tag != "section":
            return
        if tag in BLOCK:
            self.block_n += 1
            self.block_id = f"pb{self.block_n}"
            self.block_text, self.block_rids = [], []
            if tag in ("h2", "h3"):
                self.heading = []
        if tag == "a":
            href = a.get("href", "")
            m = RID.search(href)
            if m:
                rid = m.group(1)
                self.block_rids.append(rid)
                self.last_rid = rid
                self.out.append(f'<a class="rep" data-rid="{rid}" href="#r={rid}">')
            else:
                self.out.append(f'<a href="{escape(href)}" target="_blank" rel="noopener">')
            self.stack.append("a")
            return
        attr = f' id="{self.block_id}"' if tag in BLOCK else ""
        self.out.append(f"<{tag}{attr}>")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.inside:
            return
        if tag == "main":
            self.inside = False
            return
        if self.note_depth is not None:
            self.note_depth -= 1
            if self.note_depth == 0:
                self.note_depth = None
                t = "".join(self.note_text)
                for u in re.findall(r"(?:Full URL:\s*|\d+\.\s*)(\S+)", t):
                    if self.last_rid and self.last_rid not in self.notes:
                        self.notes[self.last_rid] = u
            return
        if self.skip:
            self.skip -= 1
            return
        tag = {"details": "section", "summary": "h3"}.get(tag, tag)
        if tag not in KEEP and tag != "section":
            return
        if tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break
        if tag in BLOCK:
            text = re.sub(r"\s+", " ", "".join(self.block_text)).strip()
            if tag in ("h2", "h3") and self.heading is not None:
                self.section = text
                self.heading = None
            for rid in self.block_rids:
                self.cites.setdefault(rid, {"section": self.section, "context": text[:900],
                                            "block": self.block_id})
            self.block_text, self.block_rids = [], []

    def handle_data(self, data):
        if not self.inside:
            return
        if self.note_depth is not None:
            self.note_text.append(data)
            return
        if self.skip:
            return
        self.block_text.append(data)
        self.out.append(escape(data))


def parse_post():
    p = PostParser()
    p.feed((SRC / "agent-activity.html").read_text(errors="replace"))
    html = "".join(p.out)
    html = re.sub(r"<(p|li|h[1-4]|section)[^>]*>\s*</\1>", "", html)
    return html, p.cites, p.notes


# ---- raw urlquery reports ----------------------------------------------------------
B64 = re.compile(r"/base64/([A-Za-z0-9+/=_%\-]{16,})")
DATAURI = re.compile(r"data:[a-z/+-]+;base64,([A-Za-z0-9+/=%]{16,})")


def b64text(blob):
    blob = urllib.parse.unquote(blob).strip("=")
    alphabets = [b"-_", b"+/"] if re.search(r"[-_]", blob) else [b"+/", b"-_"]
    for alt in alphabets:
        try:
            raw = base64.b64decode(blob + "=" * (-len(blob) % 4), altchars=alt, validate=True)
        except (binascii.Error, ValueError):
            continue
        text = raw.decode("utf-8", errors="replace")
        ok = sum((c.isprintable() and c != "\ufffd") or c in "\n\r\t" for c in text)
        if text and ok / len(text) > 0.95:
            return text
    return None


def decode_programs(*urls):
    """Base64 payloads embedded in URLs (httpbin /base64/, data: URIs), one level nested."""
    seen, out = set(), []

    def walk(s, where, depth):
        for rx in (B64, DATAURI):
            for m in rx.finditer(s):
                blob = m.group(1)
                if blob in seen:
                    continue
                seen.add(blob)
                t = b64text(blob)
                if t:
                    out.append({"where": where, "text": t[:20000]})
                    if depth < 1:
                        walk(t, where + " → nested", depth + 1)

    for where, u in urls:
        if u:
            walk(u, where, 0)
    return out


def trim(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n… [{len(s) - n} more chars]"


NOISY = re.compile(r"^((?:set-)?cookie|user-agent|accept(?:-language|-encoding)?|sec-[\w-]+|"
                   r"x-amz[\w-]*|report-to|nel|content-security-policy[\w-]*|strict-transport-security|"
                   r"permissions-policy|alt-svc|cf-ray|etag|expect-ct|vary|x-served-by|x-cache[\w-]*|x-timer):",
                   re.I)


def headers(raw, n):
    """Raw HTTP head with the first line of request URLs cut and bulky, uninformative headers dropped."""
    lines = (raw or "").replace("\r\n", "\n").split("\n")
    if lines and len(lines[0]) > 200:
        lines[0] = lines[0][:200] + " …"
    keep = [ln for ln in lines if ln and not NOISY.match(ln)]
    dropped = sum(1 for ln in lines if ln and NOISY.match(ln))
    return trim("\n".join(keep) + (f"\n[{dropped} cookie/UA/cache headers omitted]" if dropped else ""), n)


def url_of(u):
    if not u:
        return ""
    return f'{u.get("schema") or "http"}://{u.get("addr") or ""}'


def slim(d):
    http, prev_by = [], None
    for h in d.get("http") or []:
        rq, rs = h.get("request") or {}, h.get("response") or {}
        data = rs.get("data") or {}
        status = str(rs.get("status_code") or "")
        # headers only where they carry signal: navigations, non-GET, XHR/fetch, non-2xx
        telling = (h.get("is_navigation_request") or rq.get("method") not in (None, "GET")
                   or h.get("resource_type") in ("xhr", "fetch") or not status.startswith("2"))
        req_head = "\n".join((rq.get("raw") or "").replace("\r\n", "\n").split("\n")[1:])  # request line = method + URL
        by = h.get("requested_by") or ""
        http.append({
            "t": h.get("date"), "m": rq.get("method"), "s": status,
            "st": rs.get("status_text"), "rt": h.get("resource_type"),
            "nav": h.get("is_navigation_request"), "u": url_of(h.get("url")),
            "by": "" if by == prev_by else trim(by, 200), "mime": data.get("mime_type"), "size": data.get("size"),
            "req": headers(req_head, 450) if telling else "", "res": headers(rs.get("raw"), 550) if telling else "",
        })
        prev_by = by
    fin = d.get("final") or {}
    sub = d.get("submit") or {}
    js = d.get("javascript") or {}
    stats = (d.get("stats") or {}).get("alert_count") or {}
    det = d.get("detection") or {}
    alerts = []
    for k in ("ids", "analyzer", "urlquery"):
        for a in det.get(k) or []:
            alerts.append(f'{k}: {a.get("alert") or a.get("name") or a.get("signature") or json.dumps(a)[:160]}'
                          if isinstance(a, dict) else f"{k}: {str(a)[:160]}")
    submitted = url_of(sub.get("url")) or url_of(d.get("url"))
    return {
        "date": d.get("date"), "status": d.get("status"), "tags": d.get("tags") or [],
        "submitted": submitted, "final": url_of(fin.get("url")), "title": fin.get("title") or "",
        "dom": {k: (fin.get("dom") or {}).get(k) for k in ("size", "mime_type", "times_seen", "first_seen")},
        "user": (sub.get("user") or {}).get("user_id"), "exit": (d.get("settings") or {}).get("exit_node"),
        "ua": (d.get("settings") or {}).get("useragent"),
        "alerts": {"counts": stats, "items": alerts[:30]},
        "programs": decode_programs(("submitted URL", submitted), ("final URL", url_of(fin.get("url"))),
                                    *(("request " + str(i + 1), x["u"]) for i, x in enumerate(http))),
        "js": {k: [trim(json.dumps(x) if not isinstance(x, str) else x, 1500) for x in (js.get(k) or [])[:20]]
               for k in ("console", "write", "eval")},
        "http": http[:40], "http_total": len(http),
        "hosts": [{"fqdn": s.get("fqdn"), "n": s.get("request_count")} for s in d.get("summary") or []],
    }


# ---- catalogue -------------------------------------------------------------------
def build():
    cat = sorted(SRC.glob("urlquery-agent-activity-*/all-reports.csv"))
    if not cat:
        sys.exit(f"no catalogue in {SRC}; run scripts/fetch_transluce.py first")
    cat = cat[0].parent
    subset = json.loads((SRC / "subset.json").read_text())
    reasons = subset["reasons"]
    src = {r["report_id"]: r for r in csv.DictReader(open(cat / "report-sources.csv"))}

    tables = {k: [] for k in ("disp", "conf", "cls", "why", "cav", "src", "basis")}
    index = {k: {} for k in tables}

    def ix(k, v):
        v = v or ""
        if v not in index[k]:
            index[k][v] = len(tables[k])
            tables[k].append(v)
        return index[k][v]

    rows = []
    for r in csv.DictReader(open(cat / "all-reports.csv")):
        s = src.get(r["report_id"], {})
        rows.append([r["report_id"], r["report_date_utc"], ix("disp", r["disposition"]),
                     ix("conf", r["confidence"]), ix("cls", r["broad_class"]), ix("why", r["why_included"]),
                     ix("cav", r["caveat"]), ix("src", s.get("data_source")), ix("basis", s.get("source_basis"))])
    rows.sort(key=lambda x: x[1])

    reports, missing = {}, []
    for rid in reasons:
        f = SRC / "reports" / f"{rid}.json"
        if f.exists():
            try:
                reports[rid] = slim(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                missing.append((rid, str(e)[:80]))
        else:
            missing.append((rid, "not fetched"))

    post_html, cites, notes = parse_post()
    data = {
        "catalogue": cat.name, "tables": tables, "rows": rows, "reports": reports, "reasons": reasons,
        "cites": cites, "notes": notes, "post": post_html,
        "comments_path": str(COMMENTS), "comments_rel": str(COMMENTS.relative_to(ROOT)),
        "overrides": json.loads((cat / "classification-overrides.json").read_text()),
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text().replace("__DATA__", blob)
    OUT.write_text(page)
    print(f"{OUT}: {len(page) / 1e6:.1f} MB | {len(rows)} catalogue rows | {len(reports)} raw reports "
          f"({len(missing)} of subset missing) | {len(cites)} cited in post")


if __name__ == "__main__":
    build()
