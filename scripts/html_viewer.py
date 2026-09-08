#!/usr/bin/env python3
"""Serve viewers/*.html with the two endpoints the audit/rubric pages expect.

  GET  /                  -> index of viewers/*.html
  GET  /<name>.html       -> viewers/<name>.html
  GET  /file?p=<abs path> -> that file (must live under the repo root)
  POST /save?p=<abs path> -> write the request body to that file (repo root only)

Usage: python3 scripts/html_viewer.py [port]   (default 8765)
"""
import http.server, mimetypes, os, pathlib, sys, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIEWERS = ROOT / "viewers"


def _inside_root(p):
    p = pathlib.Path(p).resolve()
    return p if ROOT in p.parents else None


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path):
        if not path or not path.is_file():
            return self._send(404, b"not found")
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/json":
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/file":
            return self._serve_file(_inside_root(q.get("p", [""])[0]))
        if u.path == "/":
            pages = sorted(p.name for p in VIEWERS.glob("*.html"))
            body = "<h3>viewers</h3>" + "".join(f'<p><a href="/{n}">{n}</a></p>' for n in pages)
            return self._send(200, body.encode(), "text/html; charset=utf-8")
        rel = u.path.lstrip("/")
        return self._serve_file(_inside_root(VIEWERS / rel))

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path != "/save":
            return self._send(404, b"not found")
        path = _inside_root(q.get("p", [""])[0])
        if not path:
            return self._send(403, b"path must be inside the repo")
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(body)
        os.replace(tmp, path)
        self._send(200, b'{"ok":true}', "application/json")

    def log_message(self, fmt, *a):
        if "/file?" not in (a[0] if a else ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"serving {VIEWERS} on http://localhost:{port}/  (audit: /audit.html)", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
