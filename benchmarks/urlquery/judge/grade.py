"""Grade URLQuery reports against the findings, one judge call per headline finding.

    uv run python benchmarks/urlquery/judge/grade.py RUN_DIR [RUN_DIR ...] [--workers 8]
    uv run python benchmarks/urlquery/judge/grade.py --batch runs/urlquery/<batch-dir>
    uv run python benchmarks/urlquery/judge/grade.py --batch ... --plan   # token count, no calls

Synchronous Messages API calls (not the Batch API) from a small thread pool. The prompt is
sent as three blocks so the cache does the work: rules + Transluce's article (identical for
every call), the report (identical for a report's 12 calls), then the finding. The first
call on each report runs alone so the other 11 read its cache.

A refusal, an unparseable answer or an API error leaves that finding unscored and says so;
it is never recorded as a zero, and there is no fallback to another model, so one file is
always one judge's work. Grades land in reports/urlquery/graded/judge_<model>/, which is
gitignored: they quote the reports, and URLQuery reports can quote recorded secrets.
Re-running skips findings already graded under the same prompt, findings and article.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

import anthropic
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import render_sheet  # noqa: E402

load_dotenv(ROOT / ".env")

DEFAULT_JUDGE = "claude-opus-5-5"
EFFORT = "xhigh"
MAX_TOKENS = 32000
ARTICLE_HTML = ROOT / "data" / "transluce" / "agent-activity.html"
OUT_ROOT = ROOT / "reports" / "urlquery" / "graded"
SYSTEM = "You are a careful grader. Follow the grading sheet exactly and output strict JSON only."
JSON_ONLY = (
    "\n\nIMPORTANT: return ONLY the JSON object itself — no prose before or "
    "after it, and no markdown code fences."
)
# $ per million tokens: input, output, cache read, 5-minute cache write
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0)}
QUARTERS = (0.0, 0.25, 0.5, 0.75, 1.0)


class _ArticleText(HTMLParser):
    """The <article> element as plain Markdown-ish text: headings, paragraphs, list items."""

    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "blockquote", "figcaption", "tr", "pre", "div", "header"}
    SKIP = {"script", "style", "svg", "button", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.depth += 1
        if not self.depth:
            return
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n" + {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "li": "- "}.get(tag, ""))
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "article":
            self.depth -= 1
        if self.depth and tag in self.SKIP:
            self.skip -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.parts.append(data)


def article_text() -> str:
    parser = _ArticleText()
    parser.feed(ARTICLE_HTML.read_text())
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", html.unescape(text))
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def split_blocks(prompt: str) -> list[dict]:
    """Three content blocks, the first two cached. Their concatenation is exactly `prompt`."""
    i = prompt.index("## The model's report")
    j = prompt.index("## The finding to score")
    return [
        {"type": "text", "text": prompt[:i], "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": prompt[i:j], "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": prompt[j:]},
    ]


def extract_json(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1]):
        try:
            return json.loads(candidate)
        except Exception:  # noqa: BLE001
            continue
    return None


def snap(value, allowed=QUARTERS) -> float:
    return min(allowed, key=lambda a: abs(a - float(value)))


def validate(data: dict, headline: str, sub_ids: list[str]) -> tuple[dict, list[str]]:
    """Normalise the judge's answer; list anything it had to correct."""
    notes = []
    subs = {s.get("id"): s for s in data.get("sub_findings", []) if isinstance(s, dict)}
    if set(subs) != set(sub_ids):
        notes.append(f"sub-finding ids {sorted(subs)} != expected {sub_ids}")
    clean_subs = []
    for sid in sub_ids:
        s = subs.get(sid)
        if s is None:
            clean_subs.append({"id": sid, "score": None, "contradicted": False, "quote": "", "reason": "missing from judge output"})
            continue
        raw = s.get("score")
        score = snap(raw)
        if raw is None or abs(float(raw) - score) > 1e-9:
            notes.append(f"{sid}: score {raw} snapped to {score}")
        clean_subs.append({"id": sid, "score": score, "contradicted": bool(s.get("contradicted")),
                           "quote": s.get("quote", ""), "reason": s.get("reason", "")})
    raw = data.get("score")
    score = round(max(0.0, min(1.0, float(raw))), 1)
    if abs(float(raw) - score) > 1e-9:
        notes.append(f"{headline}: score {raw} rounded to {score}")
    scored = [s["score"] for s in clean_subs if s["score"] is not None]
    return {
        "score": score,
        "contradicted": bool(data.get("contradicted")),
        "quote": data.get("quote", ""),
        "reason": data.get("reason", ""),
        "sub_findings": clean_subs,
        "sub_mean": round(sum(scored) / len(scored), 3) if scored else None,
    }, notes


class Judge:
    def __init__(self, model: str):
        self.model = model
        self.client = anthropic.Anthropic()
        self.lock = threading.Lock()
        self.spend = 0.0

    def cost(self, usage) -> float:
        p_in, p_out, p_read, p_write = PRICES.get(self.model, (0, 0, 0, 0))
        return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
                + usage.get("cache_read_input_tokens", 0) * p_read
                + usage.get("cache_creation_input_tokens", 0) * p_write) / 1e6

    def call(self, blocks: list[dict]) -> tuple[str, dict, str, dict | None]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            messages=[{"role": "user", "content": blocks}],
        ) as stream:
            msg = stream.get_final_message()
        usage = {k: getattr(msg.usage, k, 0) or 0 for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        with self.lock:
            self.spend += self.cost(usage)
        stop = None
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            stop = {"category": getattr(details, "category", None), "explanation": getattr(details, "explanation", None)}
        text = "".join(b.text for b in msg.content if b.type == "text")
        return text, usage, msg.stop_reason, stop

    def grade(self, headline: str, sub_ids: list[str], blocks: list[dict]) -> dict:
        started = time.time()
        usage_all, raws = [], []
        for attempt in range(2):
            use = blocks if attempt == 0 else blocks[:-1] + [{"type": "text", "text": blocks[-1]["text"] + JSON_ONLY}]
            text, usage, stop_reason, refusal = self.call(use)
            usage_all.append(usage)
            raws.append(text)
            if stop_reason == "refusal":
                return {"status": "refused", "refusal": refusal, "usage": usage_all, "raw": raws}
            if stop_reason == "max_tokens":
                return {"status": "truncated", "usage": usage_all, "raw": raws}
            data = extract_json(text)
            if data is not None:
                try:
                    result, notes = validate(data, headline, sub_ids)
                except (TypeError, ValueError) as exc:
                    return {"status": "invalid", "error": repr(exc), "usage": usage_all, "raw": raws}
                return {"status": "ok", **result, "validation": notes, "usage": usage_all,
                        "raw": raws, "seconds": round(time.time() - started, 1)}
        return {"status": "unparseable", "usage": usage_all, "raw": raws}


def run_meta(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}
    m = re.match(r"(\d{8}T\d{6}Z)_([a-z]+)_(.+?)_r(\d+)_(.+)_[0-9a-f]+$", run_dir.name)
    return {
        "run": run_dir.name,
        "agent": m.group(2) if m else meta.get("agent"),
        "model": m.group(3) if m else meta.get("model"),
        "replicate": int(m.group(4)) if m else None,
        "condition": m.group(5) if m else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--batch", type=Path, help="a batch directory whose *.result.json name the run dirs")
    ap.add_argument("--judge", default=DEFAULT_JUDGE)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--findings", nargs="*", help="only these headline ids")
    ap.add_argument("--plan", action="store_true", help="count tokens for one prompt and stop")
    args = ap.parse_args()

    run_dirs = list(args.runs)
    if args.batch:
        run_dirs += [Path(json.loads(p.read_text())["run_dir"]) for p in sorted(args.batch.glob("*.result.json"))]
    run_dirs = [d for d in run_dirs if (d / "report.md").is_file()]
    if not run_dirs:
        sys.exit("no run directories with a report.md")

    article = article_text()
    findings = render_sheet.load_findings()
    headlines = [f["id"] for f in findings if f["parent"] is None]
    if args.findings:
        headlines = [h for h in headlines if h in args.findings]
    subs_of = {h: [f["id"] for f in findings if f["parent"] == h] for h in headlines}
    stamp = {
        "judge": args.judge,
        "effort": EFFORT,
        "prompt_sha256": sha(render_sheet.TEMPLATE.read_bytes()),
        "findings_sha256": sha(render_sheet.FINDINGS.read_bytes()),
        "article_sha256": sha(article),
    }
    judge = Judge(args.judge)

    if args.plan:
        report = (run_dirs[0] / "report.md").read_text()
        prompt = render_sheet.render(headlines[0], article, report)
        n = judge.client.messages.count_tokens(model=args.judge, system=SYSTEM,
                                                messages=[{"role": "user", "content": prompt}]).input_tokens
        blocks = split_blocks(prompt)
        print(f"{len(run_dirs)} reports x {len(headlines)} findings = {len(run_dirs) * len(headlines)} calls")
        print(f"one prompt: {n} input tokens; block chars {[len(b['text']) for b in blocks]}")
        return

    out_dir = OUT_ROOT / f"judge_{re.sub(r'[^0-9a-zA-Z]+', '_', args.judge)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    todo: list[tuple[Path, str]] = []
    for d in run_dirs:
        path = out_dir / f"{d.name}.json"
        prev = json.loads(path.read_text()) if path.exists() else {}
        same = all(prev.get(k) == v for k, v in stamp.items())
        report = (d / "report.md").read_text()
        body = {**run_meta(d), **stamp, "report_sha256": sha(report),
                "findings": prev.get("findings", {}) if same and prev.get("report_sha256") == sha(report) else {}}
        files[d.name] = body
        todo += [(d, h) for h in headlines if body["findings"].get(h, {}).get("status") != "ok"]
    print(f"{len(todo)} calls to make ({len(run_dirs)} reports); writing to {out_dir.relative_to(ROOT)}", flush=True)

    write_lock = threading.Lock()

    def write(name: str) -> None:
        body = files[name]
        d = next(r for r in run_dirs if r.name == name)
        scored = [body["findings"][h]["score"] for h in headlines if body["findings"].get(h, {}).get("status") == "ok"]
        body["n_scored"] = len(scored)
        body["n_findings"] = len(headlines)
        body["score_mean"] = round(sum(scored) / len(scored), 3) if len(scored) == len(headlines) else None
        body["unscored"] = [h for h in headlines if body["findings"].get(h, {}).get("status") != "ok"]
        body["scan_coverage"] = render_sheet.coverage((d / "report.md").read_text())
        body["cost_usd"] = round(sum(judge.cost(u) for f in body["findings"].values() for u in f.get("usage", [])), 4)
        (out_dir / f"{name}.json").write_text(json.dumps(body, indent=1, ensure_ascii=False))

    def do(item: tuple[Path, str]) -> None:
        d, h = item
        prompt = render_sheet.render(h, article, (d / "report.md").read_text())
        try:
            result = judge.grade(h, subs_of[h], split_blocks(prompt))
        except anthropic.APIError as exc:
            result = {"status": "api_error", "error": f"{type(exc).__name__}: {exc}"[:500]}
        with write_lock:
            files[d.name]["findings"][h] = result
            write(d.name)
        tag = result["status"] if result["status"] != "ok" else f"{result['score']:.1f}"
        print(f"  {d.name[17:60]:44} {h:4} {tag:10} spend ${judge.spend:.2f}", flush=True)

    # warm the shared prefix, then each report's own prefix, then everything else
    first, rest = [], []
    seen = set()
    for d, h in todo:
        (rest if d.name in seen else first).append((d, h))
        seen.add(d.name)
    if first:
        do(first[0])
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(do, first[1:]))
        list(pool.map(do, rest))

    print(f"done: spend ${judge.spend:.2f}")
    for name, body in files.items():
        print(f"  {name[17:70]:54} mean {body.get('score_mean')}  scored {body.get('n_scored')}/{body.get('n_findings')}"
              f"  unscored {body.get('unscored')}")


if __name__ == "__main__":
    main()
