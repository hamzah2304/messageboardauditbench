import base64

from viewers import build_transluce_explorer as tx

PROGRAM = '<html><body><form id=f method=POST action="https://example.org/api?x=1"></form></body></html>'


def test_urlsafe_base64_program_decodes_cleanly():
    blob = base64.urlsafe_b64encode(PROGRAM.encode()).decode().rstrip("=")
    assert "-" in blob or "_" in blob
    progs = tx.decode_programs(("submitted URL", f"https://httpbin.org/base64/{blob}"))
    assert [p["text"] for p in progs] == [PROGRAM]


def test_standard_base64_and_non_base64_paths():
    blob = base64.b64encode(PROGRAM.encode()).decode()
    assert tx.decode_programs(("u", f"https://pie.dev/base64/{blob}"))[0]["text"] == PROGRAM
    assert tx.decode_programs(("u", "https://example.org/base64/not-really-base64-at-all!!")) == []


def test_post_parser_records_citation_context_and_drops_margin_notes():
    html = (
        '<html><body><nav>menu</nav><main><h2>Probes</h2><p>Agents probed '
        '<a href="https://urlquery.net/report/76ddbb5e-c40e-46b5-b487-7853ea2d4314">1</a>'
        '<span class="margin-note report-url-note"><button>i</button><span>Full URL: <code>https://x.test/a</code></span></span>'
        " the library.</p></main><footer>f</footer></body></html>"
    )
    p = tx.PostParser()
    p.feed(html)
    out = "".join(p.out)
    rid = "76ddbb5e-c40e-46b5-b487-7853ea2d4314"
    assert 'data-rid="' + rid in out and "menu" not in out and "Full URL" not in out
    assert p.cites[rid]["section"] == "Probes"
    assert p.cites[rid]["context"] == "Agents probed 1 the library."
    assert p.notes[rid] == "https://x.test/a"


def test_headers_drops_cookies_and_keeps_status():
    raw = "HTTP/2 403 Forbidden\r\nset-cookie: a=" + "x" * 500 + "\r\ncontent-type: text/html\r\nserver: cloudflare"
    h = tx.headers(raw, 700)
    assert h.startswith("HTTP/2 403 Forbidden") and "set-cookie" not in h and "server: cloudflare" in h
