"""Local browser for the Transluce urlquery catalogue and raw urlquery records.

    python3 report-browser/server.py              # serve on http://127.0.0.1:8765
    python3 report-browser/server.py fetch --all  # bulk-fetch every raw record (polite, resumable)

Stdlib only. The catalogue CSVs are indexed into ``data/browser.sqlite``. Raw
records, script sources and urlquery's domain-graph GIFs are fetched on demand
and cached under ``data/raw/`` (gitignored: urlquery forbids redistribution).
Golden findings live in ``report-browser/golden/findings.json`` (IDs and claims
only, safe to commit).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).parent))
import decode  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CATALOG_DIR = ROOT / "data" / "urlquery-agent-activity-2026-09-22-v5"
RAW_DIR = ROOT / "data" / "raw"
EXTRA_RAW_GLOBS = [ROOT / "report-eval-harness" / "data"]
DB_PATH = ROOT / "data" / "browser.sqlite"
GOLDEN_PATH = HERE / "golden" / "findings.json"
CORPORA_DIR = ROOT / "report-eval-harness" / "corpora"
STATIC = HERE / "static"
UA = "transluce-report-browser/0.1 (research; local cache)"
UQ = "https://urlquery.net"
SCHEMA_VERSION = "3"

_db_lock = threading.RLock()
_local = threading.local()


# ---------------------------------------------------------------- database

def db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS reports(
  report_id TEXT PRIMARY KEY, url TEXT, ts TEXT, day TEXT, week TEXT, month TEXT,
  hour INT, dow INT, precision TEXT, disposition TEXT, confidence TEXT,
  broad_class TEXT, why_included TEXT, caveat TEXT, source TEXT, source_basis TEXT,
  matched_sources TEXT, fetched INT DEFAULT 0, fetch_error TEXT);
CREATE INDEX IF NOT EXISTS ix_reports_ts ON reports(ts);
CREATE TABLE IF NOT EXISTS raw(
  report_id TEXT PRIMARY KEY, submitted_url TEXT, submitted_fqdn TEXT, final_url TEXT,
  final_fqdn TEXT, title TEXT, n_http INT, n_domains INT, n_scripts INT, n_eval INT,
  n_write INT, n_console INT, verdict TEXT, alert TEXT, tags TEXT, useragent TEXT,
  country TEXT, asn TEXT, payload_kinds TEXT, payload_sig TEXT, n_targets INT);
CREATE TABLE IF NOT EXISTS domains(report_id TEXT, fqdn TEXT, kind TEXT, n INT);
CREATE INDEX IF NOT EXISTS ix_domains_fqdn ON domains(fqdn);
CREATE INDEX IF NOT EXISTS ix_domains_rid ON domains(report_id);
CREATE TABLE IF NOT EXISTS scripts(report_id TEXT, section TEXT, md5 TEXT, url TEXT,
  size INT, inline INT, intro TEXT, times_seen INT);
CREATE INDEX IF NOT EXISTS ix_scripts_md5 ON scripts(md5);
CREATE INDEX IF NOT EXISTS ix_scripts_rid ON scripts(report_id);
"""


def _time_parts(ts: str) -> dict:
    try:
        t = dt.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return {"day": ts[:10], "week": ts[:10], "month": ts[:7], "hour": None, "dow": None}
    wk = (t.date() - dt.timedelta(days=t.weekday())).isoformat()
    return {"day": t.date().isoformat(), "week": wk, "month": ts[:7], "hour": t.hour, "dow": t.weekday()}


def build_index(force: bool = False) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db()
    conn.executescript(SCHEMA)
    csv_path = CATALOG_DIR / "all-reports.csv"
    stamp = f"{SCHEMA_VERSION}:{csv_path.stat().st_mtime_ns}"
    row = conn.execute("SELECT v FROM meta WHERE k='catalog_stamp'").fetchone()
    if row and row[0] == stamp and not force:
        return
    print("indexing catalogue…", flush=True)
    sources = {}
    with open(CATALOG_DIR / "report-sources.csv", newline="") as f:
        for r in csv.DictReader(f):
            sources[r["report_id"]] = r
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            s = sources.get(r["report_id"], {})
            tp = _time_parts(r["report_date_utc"])
            rows.append((
                r["report_id"], r["report_url"], r["report_date_utc"], tp["day"], tp["week"], tp["month"],
                tp["hour"], tp["dow"], r["timestamp_precision"], r["disposition"], r["confidence"] or None,
                r["broad_class"], r["why_included"], r["caveat"],
                s.get("data_source") or ("(background)" if r["disposition"] == "background" else "(review required)" if r["disposition"] == "review_required" else "Source not identified"),
                s.get("source_basis"), s.get("matched_sources"),
            ))
    with _db_lock:
        conn.execute("DELETE FROM reports")
        conn.executemany(
            "INSERT OR REPLACE INTO reports(report_id,url,ts,day,week,month,hour,dow,precision,disposition,"
            "confidence,broad_class,why_included,caveat,source,source_basis,matched_sources) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.execute("DELETE FROM raw"); conn.execute("DELETE FROM domains"); conn.execute("DELETE FROM scripts")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('catalog_stamp',?)", (stamp,))
        conn.commit()
    n = 0
    for path in iter_raw_files():
        try:
            ingest_raw(json.loads(path.read_text()), corpus=corpus_of(path))
            n += 1
        except (ValueError, KeyError) as e:
            print(f"skip {path}: {e}")
    with _db_lock:
        conn.commit()
    print(f"indexed {len(rows)} catalogue rows, {n} cached raw records", flush=True)


def iter_raw_files():
    if RAW_DIR.exists():
        yield from RAW_DIR.glob("*.json")
    for base in EXTRA_RAW_GLOBS:
        if base.exists():
            yield from base.glob("*/*.json")


def corpus_of(path: Path) -> str | None:
    return None if path.parent == RAW_DIR else path.parent.name


def raw_path(rid: str) -> Path | None:
    p = RAW_DIR / f"{rid}.json"
    if p.exists():
        return p
    for base in EXTRA_RAW_GLOBS:
        for c in base.glob(f"*/{rid}.json"):
            return c
    return None


def _url(u: dict | None) -> str:
    if not u or not u.get("addr"):
        return ""
    return (u.get("schema") + "://" if u.get("schema") else "") + u["addr"]


def ingest_raw(d: dict, corpus: str | None = None) -> None:
    rid = d["report_id"]
    conn = db()
    http = d.get("http") or []
    per_host = Counter((h.get("url") or {}).get("fqdn", "").lower() for h in http)
    per_host.pop("", None)
    js = d.get("javascript") or {}
    script_rows = []
    for section in ("script", "eval", "write"):
        for s in js.get(section) or []:
            script_rows.append((rid, section, s.get("md5"), _url(s.get("url")), s.get("size"),
                                int(bool(s.get("is_inline"))), s.get("introduction_type"), s.get("times_seen")))
    uq = ((d.get("sensors") or {}).get("urlquery") or [])
    verdicts = sorted({a.get("verdict") for a in uq if a.get("verdict")})
    alerts = sorted({a.get("alert") for a in uq if a.get("alert")})
    submitted = _url(d.get("url"))
    final = _url((d.get("final") or {}).get("url"))
    pa = decode.analyze(submitted)
    carrier = (d.get("url") or {}).get("fqdn", "").lower()
    ip = d.get("ip") or {}
    tags = d.get("tags") or []
    with _db_lock:
        exists = conn.execute("SELECT 1 FROM reports WHERE report_id=?", (rid,)).fetchone()
        if not exists:
            ts = d.get("date", "")
            tp = _time_parts(ts)
            conn.execute(
                "INSERT INTO reports(report_id,url,ts,day,week,month,hour,dow,precision,disposition,broad_class,"
                "why_included,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, f"{UQ}/report/{rid}", ts, tp["day"], tp["week"], tp["month"], tp["hour"], tp["dow"],
                 "second", "uncatalogued", "(none)", "Not in the Transluce catalogue; raw record cached locally.",
                 f"corpus:{corpus}" if corpus else "(uncatalogued)"))
        conn.execute("UPDATE reports SET fetched=1, fetch_error=NULL WHERE report_id=?", (rid,))
        conn.execute("DELETE FROM domains WHERE report_id=?", (rid,))
        conn.execute("DELETE FROM scripts WHERE report_id=?", (rid,))
        conn.execute(
            "INSERT OR REPLACE INTO raw VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, submitted, carrier, final, ((d.get("final") or {}).get("url") or {}).get("fqdn", "").lower(),
             (d.get("final") or {}).get("title"), len(http), len(per_host),
             len(js.get("script") or []), len(js.get("eval") or []), len(js.get("write") or []),
             len(js.get("console") or []), ",".join(verdicts) or None, " | ".join(alerts) or None,
             ",".join(t if isinstance(t, str) else json.dumps(t) for t in tags) or None,
             (d.get("settings") or {}).get("useragent"), ip.get("country_code"), ip.get("as"),
             ",".join(pa["kinds"]) or None, pa["sig"], len(pa["targets"])))
        conn.executemany("INSERT INTO domains VALUES(?,?,?,?)", [(rid, h, "http", n) for h, n in per_host.items()])
        conn.executemany("INSERT INTO domains VALUES(?,?,?,?)", [(rid, t, "payload", 1) for t in pa["targets"]])
        conn.executemany("INSERT INTO scripts VALUES(?,?,?,?,?,?,?,?)", script_rows)


# ---------------------------------------------------------------- fetching

def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_raw(rid: str) -> dict:
    p = raw_path(rid)
    if p:
        return json.loads(p.read_text())
    body = _get(f"{UQ}/report/{rid}/json")
    d = json.loads(body)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RAW_DIR / f"{rid}.json.tmp"
    tmp.write_bytes(body)
    tmp.replace(RAW_DIR / f"{rid}.json")
    ingest_raw(d)
    with _db_lock:
        db().commit()
    return d


class FetchJob:
    def __init__(self, ids: list[str], workers: int):
        self.id = uuid.uuid4().hex[:8]
        self.ids, self.workers = ids, workers
        self.done = self.errors = 0
        self.last_error = None
        self.cancel = False
        self.started = time.time()
        self.finished = None
        threading.Thread(target=self.run, daemon=True).start()

    def one(self, rid: str) -> None:
        if self.cancel:
            return
        try:
            fetch_raw(rid)
        except Exception as e:  # noqa: BLE001 — one bad record must not stop the job
            self.errors += 1
            self.last_error = f"{rid}: {e}"
            try:
                with _db_lock:
                    db().execute("UPDATE reports SET fetch_error=? WHERE report_id=?", (str(e)[:200], rid))
                    db().commit()
            except sqlite3.Error:
                pass
        self.done += 1

    def run(self) -> None:
        try:
            with ThreadPoolExecutor(self.workers) as pool:
                list(pool.map(self.one, self.ids))
        finally:
            self.finished = time.time()

    def status(self) -> dict:
        el = (self.finished or time.time()) - self.started
        return {"id": self.id, "total": len(self.ids), "done": self.done, "errors": self.errors,
                "last_error": self.last_error, "running": self.finished is None and not self.cancel,
                "rate": round(self.done / el, 2) if el else 0}


JOBS: dict[str, FetchJob] = {}


def js_source(rid: str, md5: str, section: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", md5) or section not in ("script", "eval", "write"):
        raise ValueError("bad script ref")
    cache = RAW_DIR / "js" / f"{md5}.txt"
    if cache.exists():
        return cache.read_text()
    page = _get(f"{UQ}/api/htmx/report/{rid}/javascript/{md5}?section={section}").decode("utf-8", "replace")
    m = re.search(r"<code[^>]*>(.*)</code>", page, re.S)
    text = html.unescape(m.group(1)) if m else ""
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text)
    return text


def domain_graph(rid: str) -> bytes:
    cache = RAW_DIR / "graph" / f"{rid}.gif"
    if cache.exists():
        return cache.read_bytes()
    body = _get(f"{UQ}/report/{rid}/domain_graph")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return body


# ---------------------------------------------------------------- golden findings

_golden_lock = threading.Lock()


def load_golden() -> dict:
    if GOLDEN_PATH.exists():
        return json.loads(GOLDEN_PATH.read_text())
    return {"version": 1, "incidents": [], "findings": []}


def save_golden(g: dict) -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GOLDEN_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(GOLDEN_PATH)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def golden_op(op: str, body: dict) -> dict:
    with _golden_lock:
        g = load_golden()
        if op == "incident":
            inc = next((i for i in g["incidents"] if i["id"] == body.get("id")), None)
            if inc is None:
                key = re.sub(r"[^A-Z0-9]", "", (body.get("key") or body.get("name", "INC")).upper())[:6] or "INC"
                inc = {"id": uuid.uuid4().hex[:10], "key": key, "created": _now()}
                g["incidents"].append(inc)
            for k in ("name", "key", "description", "start", "end", "status"):
                if k in body:
                    inc[k] = body[k]
            inc["updated"] = _now()
        elif op == "delete_incident":
            g["incidents"] = [i for i in g["incidents"] if i["id"] != body["id"]]
            g["findings"] = [f for f in g["findings"] if f["incident_id"] != body["id"]]
        elif op == "finding":
            f = next((x for x in g["findings"] if x["id"] == body.get("id")), None)
            if f is None:
                inc = next(i for i in g["incidents"] if i["id"] == body["incident_id"])
                used = [x["id"] for x in g["findings"] if x["incident_id"] == inc["id"]]
                n = 1
                while f"{inc['key']}{n:02d}" in used:
                    n += 1
                f = {"id": f"{inc['key']}{n:02d}", "incident_id": inc["id"], "evidence": [],
                     "section": "", "claim": "", "grading_mode": "recall_accuracy", "note": "",
                     "confidence": "medium", "created": _now()}
                g["findings"].append(f)
            for k in ("section", "claim", "grading_mode", "note", "confidence", "order"):
                if k in body:
                    f[k] = body[k]
            for rid in body.get("add_evidence") or []:
                if rid not in [e["report_id"] for e in f["evidence"]]:
                    f["evidence"].append({"report_id": rid, "note": body.get("evidence_note", ""), "added": _now()})
            if body.get("remove_evidence"):
                f["evidence"] = [e for e in f["evidence"] if e["report_id"] not in body["remove_evidence"]]
            if "evidence_notes" in body:
                for e in f["evidence"]:
                    if e["report_id"] in body["evidence_notes"]:
                        e["note"] = body["evidence_notes"][e["report_id"]]
            f["updated"] = _now()
        elif op == "delete_finding":
            g["findings"] = [f for f in g["findings"] if f["id"] != body["id"]]
        else:
            raise ValueError(op)
        save_golden(g)
        return g


def export_incident(inc_id: str, write: bool) -> dict:
    g = load_golden()
    inc = next(i for i in g["incidents"] if i["id"] == inc_id)
    fs = [f for f in g["findings"] if f["incident_id"] == inc_id]
    lines = [json.dumps({"id": f["id"], "section": f["section"], "claim": f["claim"],
                         "grading_mode": f["grading_mode"], "note": f["note"]}, ensure_ascii=False) for f in fs]
    ids = sorted({e["report_id"] for f in fs for e in f["evidence"]})
    slug = re.sub(r"[^a-z0-9]+", "-", (inc.get("name") or inc["key"]).lower()).strip("-")
    out = {"slug": slug, "answer_key": "\n".join(lines) + "\n", "ids": "\n".join(ids) + "\n"}
    if write:
        d = CORPORA_DIR / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "answer_key.jsonl").write_text(out["answer_key"])
        (d / "ids.txt").write_text(f"# {inc.get('name')} — exported from report-browser golden findings\n" + out["ids"])
        out["written"] = str(d.relative_to(ROOT))
    return out


# ---------------------------------------------------------------- queries

DIMS = {
    "source": "c.source", "broad_class": "c.broad_class",
    "confidence": "COALESCE(c.confidence,'(none)')", "disposition": "c.disposition",
    "day": "c.day", "week": "c.week", "month": "c.month", "hour": "c.hour", "weekday": "c.dow",
    "submitted_fqdn": "r.submitted_fqdn", "final_fqdn": "r.final_fqdn", "verdict": "r.verdict",
    "payload_sig": "r.payload_sig", "payload_kinds": "r.payload_kinds", "useragent": "r.useragent",
    "fetched": "CASE WHEN c.fetched=1 THEN 'fetched' ELSE 'not fetched' END",
}
JOIN_DIMS = {  # dimension -> (join clause, expr)
    "target": ("JOIN domains dj ON dj.report_id=c.report_id AND dj.kind='payload'", "dj.fqdn"),
    "contacted": ("JOIN domains dj ON dj.report_id=c.report_id AND dj.kind='http'", "dj.fqdn"),
    "script": ("JOIN scripts sj ON sj.report_id=c.report_id", "sj.md5"),
}
BINS = {"hour": "substr(c.ts,1,13)", "day": "c.day", "week": "c.week", "month": "c.month"}
MULTI = {"disposition": "c.disposition", "confidence": "COALESCE(c.confidence,'(none)')",
         "broad_class": "c.broad_class", "source": "c.source", "submitted_fqdn": "r.submitted_fqdn",
         "final_fqdn": "r.final_fqdn", "payload_sig": "r.payload_sig", "verdict": "r.verdict",
         "week": "c.week", "day": "c.day", "month": "c.month", "useragent": "r.useragent"}


def where(q: dict) -> tuple[str, list]:
    cl, ps = ["1=1"], []

    def one(k):
        v = q.get(k)
        return v[0] if isinstance(v, list) else v

    for k, expr in MULTI.items():
        v = one(k)
        if v:
            vals = json.loads(v) if v.startswith("[") else [v]
            cl.append(f"{expr} IN ({','.join('?' * len(vals))})")
            ps += vals
    for k, op in (("from", ">="), ("to", "<=")):
        if one(k):
            cl.append(f"c.ts {op} ?"); ps.append(one(k))
    if one("hour"):
        cl.append("c.hour = ?"); ps.append(int(one("hour")))
    if one("weekday"):
        cl.append("c.dow = ?"); ps.append(int(one("weekday")))
    if one("fetched") in ("1", "fetched"):
        cl.append("c.fetched=1")
    elif one("fetched") in ("0", "not fetched"):
        cl.append("c.fetched=0")
    if one("q"):
        like = f"%{one('q')}%"
        cl.append("(c.report_id LIKE ? OR c.why_included LIKE ? OR r.submitted_url LIKE ? OR r.final_url LIKE ? OR r.title LIKE ? OR c.matched_sources LIKE ?)")
        ps += [like] * 6
    for k, kind in (("contacted", "http"), ("target", "payload")):
        if one(k):
            vals = json.loads(one(k)) if one(k).startswith("[") else [one(k)]
            cl.append(f"EXISTS(SELECT 1 FROM domains d WHERE d.report_id=c.report_id AND d.kind='{kind}' AND d.fqdn IN ({','.join('?' * len(vals))}))")
            ps += vals
    if one("host"):
        cl.append("EXISTS(SELECT 1 FROM domains d WHERE d.report_id=c.report_id AND d.fqdn=?)"); ps.append(one("host"))
    if one("script"):
        cl.append("EXISTS(SELECT 1 FROM scripts s WHERE s.report_id=c.report_id AND s.md5=?)"); ps.append(one("script"))
    if one("ids"):
        ids = json.loads(one("ids"))
        cl.append(f"c.report_id IN ({','.join('?' * len(ids))})"); ps += ids
    if one("incident") or one("finding"):
        g = load_golden()
        fs = [f for f in g["findings"] if (one("finding") and f["id"] == one("finding"))
              or (not one("finding") and f["incident_id"] == one("incident"))]
        ids = sorted({e["report_id"] for f in fs for e in f["evidence"]}) or ["-"]
        cl.append(f"c.report_id IN ({','.join('?' * len(ids))})"); ps += ids
    return " AND ".join(cl), ps


BASE = "FROM reports c LEFT JOIN raw r ON r.report_id=c.report_id"


def q_rows(q: dict) -> dict:
    w, p = where(q)
    sort = {"ts": "c.ts", "-ts": "c.ts DESC", "n_http": "r.n_http DESC", "source": "c.source, c.ts"}.get(q.get("sort", ["ts"])[0], "c.ts")
    limit = min(int(q.get("limit", ["200"])[0]), 5000)
    offset = int(q.get("offset", ["0"])[0])
    conn = db()
    total = conn.execute(f"SELECT count(*) {BASE} WHERE {w}", p).fetchone()[0]
    rows = conn.execute(
        f"SELECT c.report_id, c.ts, c.disposition, c.confidence, c.broad_class, c.source, c.why_included, c.fetched, c.fetch_error,"
        f" r.submitted_url, r.submitted_fqdn, r.final_fqdn, r.title, r.n_http, r.n_domains, r.n_scripts, r.n_eval,"
        f" r.verdict, r.payload_kinds, r.payload_sig, r.n_targets {BASE} WHERE {w} ORDER BY {sort} LIMIT ? OFFSET ?",
        p + [limit, offset]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["submitted_url"] and len(d["submitted_url"]) > 300:
            d["submitted_url"] = d["submitted_url"][:300] + "…"
        out.append(d)
    return {"total": total, "rows": out}


def q_summary(q: dict) -> dict:
    w, p = where(q)
    conn = db()
    r = conn.execute(f"SELECT count(*) n, sum(c.fetched) f, min(c.ts) a, max(c.ts) b, count(DISTINCT c.source) s {BASE} WHERE {w}", p).fetchone()
    facets = {}
    for dim in ("disposition", "confidence", "broad_class", "source", "fetched"):
        facets[dim] = [dict(x) for x in conn.execute(
            f"SELECT {DIMS[dim]} v, count(*) n {BASE} WHERE {w} GROUP BY v ORDER BY n DESC", p)]
    return {"n": r["n"], "fetched": r["f"] or 0, "first": r["a"], "last": r["b"], "sources": r["s"], "facets": facets}


def _fill_bins(bins: list[str], unit: str) -> list[str]:
    if not bins:
        return []
    lo, hi = min(bins), max(bins)
    out = []
    if unit == "month":
        y, m = int(lo[:4]), int(lo[5:7])
        while f"{y:04d}-{m:02d}" <= hi:
            out.append(f"{y:04d}-{m:02d}"); m += 1
            if m > 12:
                y, m = y + 1, 1
        return out
    if unit == "hour":
        t = dt.datetime.strptime(lo, "%Y-%m-%dT%H"); end = dt.datetime.strptime(hi, "%Y-%m-%dT%H")
        if (end - t).total_seconds() / 3600 > 20000:
            return sorted(set(bins))
        while t <= end:
            out.append(t.strftime("%Y-%m-%dT%H")); t += dt.timedelta(hours=1)
        return out
    step = 7 if unit == "week" else 1
    t = dt.date.fromisoformat(lo); end = dt.date.fromisoformat(hi)
    while t <= end:
        out.append(t.isoformat()); t += dt.timedelta(days=step)
    return out


def _dim_sql(dim: str) -> tuple[str, str]:
    if dim in JOIN_DIMS:
        return JOIN_DIMS[dim]
    if dim in DIMS:
        return "", DIMS[dim]
    raise ValueError(f"unknown dimension {dim}")


def q_timeseries(q: dict) -> dict:
    w, p = where(q)
    unit = q.get("bin", ["day"])[0]
    stack = q.get("stack", ["confidence"])[0]
    topk = int(q.get("top", ["8"])[0])
    join, expr = _dim_sql(stack)
    conn = db()
    rows = conn.execute(
        f"SELECT {BINS[unit]} b, {expr} s, count(DISTINCT c.report_id) n {BASE} {join} WHERE {w} AND c.ts <> '' GROUP BY b, s", p).fetchall()
    tot = Counter()
    for r in rows:
        tot[r["s"]] += r["n"]
    keep = [k for k, _ in tot.most_common(topk)]
    series = defaultdict(Counter)
    for r in rows:
        series[r["s"] if r["s"] in keep else "Other"][r["b"]] += r["n"]
    bins = _fill_bins([r["b"] for r in rows if r["b"]], unit)
    names = [str(k) for k in keep] + (["Other"] if "Other" in series else [])
    return {"bins": bins, "series": [{"name": str(k), "data": [series[k][b] for b in bins]}
                                     for k in keep + (["Other"] if "Other" in series else [])], "names": names,
            "totals": {str(k): v for k, v in tot.items()}}


def q_groups(q: dict) -> dict:
    w, p = where(q)
    by = q.get("by", ["source"])[0]
    join, expr = _dim_sql(by)
    by2 = q.get("by2", [""])[0]
    conn = db()
    rows = conn.execute(
        f"SELECT {expr} v, count(DISTINCT c.report_id) n, min(c.ts) first, max(c.ts) last,"
        f" sum(CASE WHEN c.confidence='significant' THEN 1 ELSE 0 END) sig, count(DISTINCT c.day) days,"
        f" sum(c.fetched) fetched {BASE} {join} WHERE {w} GROUP BY v ORDER BY n DESC LIMIT 500", p).fetchall()
    out = [dict(r) for r in rows]
    if by2 and out:
        j2, e2 = _dim_sql(by2)
        if j2 and join:
            j2 = j2.replace("dj", "dk").replace("sj", "sk"); e2 = e2.replace("dj", "dk").replace("sj", "sk")
        sub = defaultdict(list)
        for r in conn.execute(
                f"SELECT {expr} v, {e2} v2, count(DISTINCT c.report_id) n {BASE} {join} {j2} WHERE {w} GROUP BY v, v2 ORDER BY n DESC", p):
            if len(sub[r["v"]]) < 12:
                sub[r["v"]].append({"v": r["v2"], "n": r["n"]})
        for r in out:
            r["sub"] = sub.get(r["v"], [])
    if by == "script":
        info = {r["md5"]: dict(r) for r in conn.execute(
            "SELECT md5, max(url) url, max(size) size, max(inline) inline, max(section) section, max(times_seen) times_seen FROM scripts GROUP BY md5")}
        for r in out:
            r["info"] = info.get(r["v"])
    return {"by": by, "groups": out}


def q_bursts(q: dict) -> dict:
    w, p = where(q)
    gap = float(q.get("gap", ["30"])[0]) * 60
    min_size = int(q.get("min", ["2"])[0])
    rows = db().execute(
        f"SELECT c.report_id, c.ts, c.source, c.confidence, r.submitted_fqdn, r.payload_sig {BASE} WHERE {w} AND c.ts <> '' ORDER BY c.ts", p).fetchall()
    bursts, cur, last = [], [], None
    for r in rows:
        try:
            t = dt.datetime.strptime(r["ts"][:19], "%Y-%m-%dT%H:%M:%S").timestamp()
        except ValueError:
            continue
        if last is not None and t - last > gap:
            bursts.append(cur); cur = []
        cur.append((t, r)); last = t
    if cur:
        bursts.append(cur)
    out = []
    for b in bursts:
        if len(b) < min_size:
            continue
        rs = [r for _, r in b]
        out.append({
            "start": rs[0]["ts"], "end": rs[-1]["ts"], "n": len(rs),
            "minutes": round((b[-1][0] - b[0][0]) / 60, 1),
            "sources": Counter(r["source"] for r in rs).most_common(4),
            "carriers": Counter(r["submitted_fqdn"] for r in rs if r["submitted_fqdn"]).most_common(4),
            "sigs": len({r["payload_sig"] for r in rs if r["payload_sig"]}),
            "significant": sum(r["confidence"] == "significant" for r in rs),
            "first_id": rs[0]["report_id"],
        })
    order = q.get("order", ["n"])[0]
    out.sort(key=(lambda x: -x["n"]) if order == "n" else (lambda x: x["start"]))
    return {"count": len(out), "bursts": out[:1000], "reports": len(rows)}


def q_sites(q: dict) -> dict:
    w, p = where(q)
    kinds = q.get("kinds", ["payload"])[0].split(",")
    max_edges = int(q.get("max", ["250"])[0])
    min_n = int(q.get("minn", ["1"])[0])
    exclude = [x.strip() for x in q.get("exclude", [""])[0].split(",") if x.strip()]
    conn = db()
    kin = ",".join("?" * len(kinds))
    rows = conn.execute(
        f"SELECT r.submitted_fqdn a, d.fqdn b, d.kind k, count(DISTINCT c.report_id) n, min(c.ts) first, max(c.ts) last,"
        f" group_concat(DISTINCT c.source) srcs {BASE} JOIN domains d ON d.report_id=c.report_id AND d.kind IN ({kin})"
        f" WHERE {w} AND r.submitted_fqdn IS NOT NULL GROUP BY a, b, k HAVING n >= ? ORDER BY n DESC",
        kinds + p + [min_n]).fetchall()
    edges = []
    for r in rows:
        if any(x in (r["a"] or "") or x in (r["b"] or "") for x in exclude):
            continue
        if r["a"] == r["b"]:
            continue
        edges.append({"a": r["a"], "b": r["b"], "kind": r["k"], "n": r["n"], "first": r["first"], "last": r["last"],
                      "sources": (r["srcs"] or "").split(",")[:5]})
        if len(edges) >= max_edges:
            break
    nodes = {}
    for e in edges:
        for side, role in ((e["a"], "carrier"), (e["b"], "target" if e["kind"] == "payload" else "contacted")):
            n = nodes.setdefault(side, {"id": side, "n": 0, "roles": set(), "first": e["first"], "last": e["last"]})
            n["n"] += e["n"]; n["roles"].add(role)
            n["first"] = min(n["first"], e["first"]); n["last"] = max(n["last"], e["last"])
    for n in nodes.values():
        n["roles"] = sorted(n["roles"])
    # time-grouped heatmap: top hosts × bin
    unit = q.get("bin", ["week"])[0]
    hosts = Counter()
    for e in edges:
        hosts[e["b"]] += e["n"]
    top = [h for h, _ in hosts.most_common(int(q.get("heat", ["30"])[0]))]
    heat = []
    bins = []
    if top:
        hin = ",".join("?" * len(top))
        hr = conn.execute(
            f"SELECT {BINS[unit]} bn, d.fqdn h, count(DISTINCT c.report_id) n {BASE} JOIN domains d ON d.report_id=c.report_id"
            f" AND d.kind IN ({kin}) WHERE {w} AND d.fqdn IN ({hin}) GROUP BY bn, h", kinds + p + top).fetchall()
        bins = _fill_bins([r["bn"] for r in hr], unit)
        heat = [[r["bn"], r["h"], r["n"]] for r in hr]
    return {"nodes": list(nodes.values()), "edges": edges, "heat": {"hosts": top, "bins": bins, "cells": heat}}


def q_clock(q: dict) -> dict:
    w, p = where(q)
    rows = db().execute(f"SELECT c.dow d, c.hour h, count(*) n {BASE} WHERE {w} AND c.hour IS NOT NULL GROUP BY d, h", p).fetchall()
    return {"cells": [[r["h"], r["d"], r["n"]] for r in rows]}


def q_report(rid: str, do_fetch: bool) -> dict:
    conn = db()
    cat = conn.execute("SELECT * FROM reports WHERE report_id=?", (rid,)).fetchone()
    if not cat:
        raise KeyError(rid)
    out = {"catalog": dict(cat), "raw": None}
    d = None
    p = raw_path(rid)
    if p:
        d = json.loads(p.read_text())
    elif do_fetch:
        d = fetch_raw(rid)
    if d:
        http = []
        for h in d.get("http") or []:
            req = (h.get("request") or {}).get("raw") or ""
            resp = (h.get("response") or {}).get("raw") or ""
            first = req.split("\r\n", 1)[0]
            rdata = (h.get("response") or {}).get("data") or {}
            http.append({
                "url": _url(h.get("url")), "fqdn": (h.get("url") or {}).get("fqdn"),
                "ip": (h.get("ip") or {}).get("addr"), "asn": (h.get("ip") or {}).get("as"),
                "country": (h.get("ip") or {}).get("country_code"),
                "method": first.split(" ", 1)[0] if first else "",
                "status": (resp.split("\r\n", 1)[0].split(" ", 2)[1:2] or [""])[0] if resp else "",
                "ts": h.get("timestamp"), "date": h.get("date"), "nav": h.get("is_navigation_request"),
                "type": h.get("resource_type"), "by": h.get("requested_by"),
                "mime": rdata.get("mime_type") or rdata.get("magic"), "size": rdata.get("size"),
                "sha256": rdata.get("sha256"), "times_seen": rdata.get("times_seen"),
                "req_raw": req[:20000], "resp_raw": resp[:8000],
            })
        js = d.get("javascript") or {}
        scripts = []
        for section in ("script", "eval", "write"):
            for s in js.get(section) or []:
                scripts.append({"section": section, "md5": s.get("md5"), "url": _url(s.get("url")),
                                "size": s.get("size"), "inline": s.get("is_inline"), "intro": s.get("introduction_type"),
                                "times_seen": s.get("times_seen"), "first_seen": s.get("first_seen"),
                                "data": s.get("data") or None, "alerts": s.get("alerts")})
        sub = _url(d.get("url"))
        out["raw"] = {
            "submitted": sub, "final": _url((d.get("final") or {}).get("url")),
            "title": (d.get("final") or {}).get("title"), "date": d.get("date"), "tags": d.get("tags"),
            "ip": d.get("ip"), "settings": d.get("settings"), "stats": d.get("stats"),
            "urlquery_alerts": (d.get("sensors") or {}).get("urlquery"),
            "summary": d.get("summary"), "http": http, "scripts": scripts,
            "console": js.get("console"), "artifacts": d.get("artifacts"),
            "payload": decode.analyze(sub),
        }
        out["full"] = d if do_fetch or p else None
    g = load_golden()
    out["findings"] = [{"id": f["id"], "incident_id": f["incident_id"], "claim": f["claim"]}
                       for f in g["findings"] if rid in [e["report_id"] for e in f["evidence"]]]
    return out


def q_ids(q: dict) -> list[str]:
    w, p = where(q)
    extra = " AND c.fetched=0" if q.get("only_missing", ["1"])[0] == "1" else ""
    limit = int(q.get("limit", ["500"])[0])
    return [r[0] for r in db().execute(f"SELECT c.report_id {BASE} WHERE {w}{extra} ORDER BY c.ts LIMIT ?", p + [limit])]


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            return
        super().log_message(fmt, *args)

    def send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, default=str).encode(), "application/json")

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        path = u.path
        try:
            if path in ("/", "/index.html"):
                return self.static("index.html")
            if path.startswith("/static/"):
                return self.static(path[len("/static/"):])
            routes = {"/api/rows": q_rows, "/api/summary": q_summary, "/api/timeseries": q_timeseries,
                      "/api/groups": q_groups, "/api/bursts": q_bursts, "/api/sites": q_sites, "/api/clock": q_clock}
            if path in routes:
                return self.json(routes[path](q))
            if path == "/api/golden":
                return self.json(load_golden())
            if path.startswith("/api/report/"):
                rid = path.split("/")[3]
                if path.endswith("/graph.gif"):
                    return self.send(200, domain_graph(rid), "image/gif")
                return self.json(q_report(rid, q.get("fetch", ["0"])[0] == "1"))
            if path == "/api/js":
                return self.send(200, js_source(q["report"][0], q["md5"][0], q["section"][0]).encode(), "text/plain; charset=utf-8")
            if path == "/api/fetch/status":
                return self.json([j.status() for j in JOBS.values()])
            if path.startswith("/api/golden/export/"):
                return self.json(export_incident(path.rsplit("/", 1)[1], False))
            return self.json({"error": "not found"}, 404)
        except urllib.error.HTTPError as e:
            return self.json({"error": f"urlquery returned {e.code}"}, 502)
        except (urllib.error.URLError, TimeoutError) as e:
            return self.json({"error": f"urlquery unreachable: {e}"}, 502)
        except (KeyError, ValueError, StopIteration) as e:
            return self.json({"error": f"{type(e).__name__}: {e}"}, 400)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            b = self.body()
            if path == "/api/fetch":
                q = {k: [v] if not isinstance(v, list) else v for k, v in (b.get("filters") or {}).items()}
                q["limit"] = [str(b.get("limit", 500))]
                ids = b.get("ids") or q_ids(q)
                job = FetchJob(ids, int(b.get("workers", 4)))
                JOBS[job.id] = job
                return self.json(job.status())
            if path == "/api/fetch/cancel":
                for j in JOBS.values():
                    j.cancel = True
                return self.json({"ok": True})
            if path.startswith("/api/golden/"):
                op = path.rsplit("/", 1)[1]
                if op == "write_corpus":
                    return self.json(export_incident(b["id"], True))
                return self.json(golden_op(op, b))
            return self.json({"error": "not found"}, 404)
        except (KeyError, ValueError, StopIteration) as e:
            return self.json({"error": f"{type(e).__name__}: {e}"}, 400)

    def static(self, name: str):
        p = (STATIC / name).resolve()
        if STATIC not in p.parents or not p.exists():
            return self.json({"error": "not found"}, 404)
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}.get(p.suffix, "application/octet-stream")
        self.send(200, p.read_bytes(), ctype)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="serve", choices=["serve", "fetch", "reindex"])
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    ap.add_argument("--all", action="store_true", help="fetch: every catalogue report")
    ap.add_argument("--source", help="fetch: only this data source")
    ap.add_argument("--confidence", help="fetch: only this confidence (significant/suggestive)")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    build_index(force=a.cmd == "reindex")
    if a.cmd == "reindex":
        return
    if a.cmd == "fetch":
        q = {"limit": [str(10**9 if a.all else a.limit)]}
        if a.source:
            q["source"] = [a.source]
        if a.confidence:
            q["confidence"] = [a.confidence]
        ids = q_ids(q)
        print(f"fetching {len(ids)} records with {a.workers} workers…")
        job = FetchJob(ids, a.workers)
        while job.finished is None:
            time.sleep(5)
            s = job.status()
            print(f"\r{s['done']}/{s['total']}  errors={s['errors']}  {s['rate']}/s", end="", flush=True)
        print()
        if job.last_error:
            print("last error:", job.last_error)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"report browser on http://127.0.0.1:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
