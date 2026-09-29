"""Grade URLQuery reports against the findings, one judge call per headline finding.

    uv run python benchmarks/urlquery/judge/grade.py RUN_DIR [RUN_DIR ...] [--workers 8]
    uv run python benchmarks/urlquery/judge/grade.py --batch runs/urlquery/<batch-dir>
    uv run python benchmarks/urlquery/judge/grade.py --launch runs/urlquery/<final>/launch.json --omit-article
    uv run python benchmarks/urlquery/judge/grade.py --judge openrouter/openai/gpt-6-astra --launch ...
    uv run python benchmarks/urlquery/judge/grade.py --batch ... --plan   # calls to make, no API use

The resumable batch counterpart of the `urlquery_grade_reports` Inspect task: the prompt,
parsing and arithmetic are `messageboard_audit_bench.grading.findings`, shared with the
Inspect scorer. Two judge transports:

* ``anthropic/<model>`` (default ``anthropic/claude-opus-5-5``, effort xhigh, adaptive
  thinking): synchronous Messages API calls. The prompt is sent as three blocks so the
  cache does the work: rules + article (identical for every call), the report (identical
  for a report's calls), then the finding. The first call on each report runs alone so the
  others read its cache.
* ``openrouter/<model>`` (the final run used ``openrouter/openai/gpt-6-astra``, effort
  high): synchronous OpenRouter chat completions with a JSON response format.

A refusal, an unparseable answer or an API error leaves that finding unscored and says so;
it is never recorded as a zero, and there is no fallback to another model, so one file is
always one judge's work. With the Anthropic judge, a refusal on a report's first headline
skips its remaining headlines (it recurs on every one); OpenRouter refusals are retried on
the next run, as before. Grades land in reports/urlquery/graded/judge_<model>[_<effort>]/, which is
gitignored: they quote the reports, and URLQuery reports can quote recorded secrets.
Re-running skips findings already graded under the same judge, prompt, findings and article.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from messageboard_audit_bench.benchmarks import primary_root, urlquery_manifest  # noqa: E402
from messageboard_audit_bench.grading import findings as fj  # noqa: E402

load_dotenv(ROOT / ".env")

DEFAULT_JUDGE = urlquery_manifest()["grading"]["default_judge"]
EFFORTS = {"anthropic": "xhigh", "openrouter": "high"}
MAX_TOKENS = {"anthropic": 32000, "openrouter": 24000}
# $ per million tokens: input, output, cache read, 5-minute cache write
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0)}

# Kept importable for older callers.
sha = fj.sha
extract_json = fj.extract_json
validate = fj.validate
run_meta = fj.run_meta
SYSTEM = fj.SYSTEM


def split_blocks(prompt: str) -> list[dict]:
    """Three Anthropic content blocks, the first two cached. Their concatenation is `prompt`."""
    rules, report, finding = fj.split_prompt(prompt)
    return [
        {"type": "text", "text": rules, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": report, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": finding},
    ]


def provider_of(judge: str) -> tuple[str, str]:
    """('anthropic', 'claude-opus-5-5') from 'anthropic/claude-opus-5-5' or a bare Claude name."""
    if judge.startswith("openrouter/"):
        return "openrouter", judge.removeprefix("openrouter/")
    if judge.startswith("anthropic/"):
        return "anthropic", judge.removeprefix("anthropic/")
    if judge.startswith("claude"):
        return "anthropic", judge
    raise SystemExit(f"judge must be anthropic/<model> or openrouter/<model>, not {judge!r}")


class Judge:
    def __init__(self, judge: str, effort: str | None = None):
        self.provider, self.model = provider_of(judge)
        self.effort = effort or EFFORTS[self.provider]
        self.lock = threading.Lock()
        self.spend = 0.0
        if self.provider == "anthropic":
            import anthropic

            self.client = anthropic.Anthropic()
            self.errors = (anthropic.APIError,)
        else:
            from openai import OpenAI

            key_file = primary_root() / "runs" / f".openrouter_key.{self.model.replace('/', '_')}"
            key = os.environ.get("OPENROUTER_API_KEY") or (key_file.read_text().strip() if key_file.is_file() else "")
            if not key:
                raise SystemExit("OpenRouter API key is missing")
            self.client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", timeout=600.0, max_retries=2)
            self.errors = (Exception,)

    def cost(self, usage) -> float:
        p_in, p_out, p_read, p_write = PRICES.get(self.model, (0, 0, 0, 0))
        return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
                + usage.get("cache_read_input_tokens", 0) * p_read
                + usage.get("cache_creation_input_tokens", 0) * p_write) / 1e6

    def _anthropic(self, prompt: str, suffix: str) -> tuple[str, dict, str, dict | None]:
        blocks = split_blocks(prompt)
        blocks[-1] = {"type": "text", "text": blocks[-1]["text"] + suffix}
        with self.client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS["anthropic"],
            system=fj.SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": blocks}],
        ) as stream:
            msg = stream.get_final_message()
        usage = {k: getattr(msg.usage, k, 0) or 0 for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        refusal = None
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            refusal = {"category": getattr(details, "category", None), "explanation": getattr(details, "explanation", None)}
        text = "".join(b.text for b in msg.content if b.type == "text")
        stop = {"refusal": "refused", "max_tokens": "truncated"}.get(msg.stop_reason)
        return text, usage, stop, refusal

    def _openrouter(self, prompt: str) -> tuple[str, dict, str | None, str | None]:
        response = self.client.chat.completions.create(
            model=self.model,
            reasoning_effort=self.effort,
            response_format={"type": "json_object"},
            max_completion_tokens=MAX_TOKENS["openrouter"],
            messages=[{"role": "system", "content": fj.SYSTEM}, {"role": "user", "content": prompt}],
        )
        choice = response.choices[0]
        usage = response.usage.model_dump() if response.usage else {}
        text = choice.message.content or ""
        if choice.message.refusal or choice.finish_reason == "content_filter":
            return text, usage, "refused", choice.message.refusal or choice.finish_reason
        return text, usage, "truncated" if choice.finish_reason == "length" else None, None

    def grade(self, headline: str, subs: list[str], prompt: str) -> dict:
        started = time.time()
        usage_all, raws = [], []
        # Anthropic gets one retry asking for bare JSON; OpenRouter's response format already asks.
        for attempt in range(2 if self.provider == "anthropic" else 1):
            if self.provider == "anthropic":
                text, usage, stop, refusal = self._anthropic(prompt, fj.JSON_ONLY if attempt else "")
            else:
                text, usage, stop, refusal = self._openrouter(prompt)
            usage_all.append(usage)
            raws.append(text)
            with self.lock:
                self.spend += self.cost(usage)
            if stop == "refused":
                return {"status": "refused", "refusal": refusal, "usage": usage_all, "raw": raws}
            if stop == "truncated":
                return {"status": "truncated", "usage": usage_all, "raw": raws}
            data = fj.extract_json(text)
            if data is not None:
                try:
                    result, notes = fj.validate(data, headline, subs)
                except (TypeError, ValueError) as exc:
                    return {"status": "invalid", "error": repr(exc), "usage": usage_all, "raw": raws}
                return {"status": "ok", **result, "validation": notes, "usage": usage_all,
                        "raw": raws, "seconds": round(time.time() - started, 1)}
        return {"status": "unparseable", "usage": usage_all, "raw": raws}


def parser(defaults: dict | None = None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--batch", type=Path, help="a batch directory whose *.result.json name the run dirs")
    ap.add_argument("--launch", type=Path, help="launch.json; use completed reports from all referenced plans")
    ap.add_argument("--article", choices=fj.ARTICLE_CONTEXTS,
                    help="article context; default omitted for Anthropic judges, full for OpenRouter")
    ap.add_argument("--omit-article", action="store_const", const="omitted", dest="article",
                    help="same as --article omitted")
    ap.add_argument("--judge", default=DEFAULT_JUDGE, help="anthropic/<model> or openrouter/<model>")
    ap.add_argument("--effort", help="default xhigh for Anthropic, high for OpenRouter")
    ap.add_argument("--output", type=Path, help="grade directory (default reports/urlquery/graded/judge_<model>...)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--findings", nargs="*", help="only these headline ids")
    ap.add_argument("--plan", action="store_true", help="print the calls to make and stop")
    ap.set_defaults(**(defaults or {}))
    return ap


def main(argv: list[str] | None = None, defaults: dict | None = None) -> None:
    args = parser(defaults).parse_args(argv)
    run_dirs = fj.reports_from(runs=args.runs, batches=[args.batch] if args.batch else [], launch=args.launch)
    if not run_dirs:
        sys.exit("no run directories with a report.md")

    context = args.article or fj.default_article_context(args.judge)
    article = fj.article_text(context)
    findings = fj.load_findings()
    heads = fj.headlines(findings)
    if args.findings:
        heads = [h for h in heads if h in args.findings]
    subs_of = {h: fj.sub_ids(h, findings) for h in heads}
    provider, model = provider_of(args.judge)
    effort = args.effort or EFFORTS[provider]
    # Opus grades have always been filed without an effort suffix; OpenRouter's with one.
    out_dir = args.output or fj.output_root() / fj.judge_dir(model, effort if provider == "openrouter" else None)
    print(f"{len(run_dirs)} reports x {len(heads)} findings = {len(run_dirs) * len(heads)} calls "
          f"({args.judge}, effort {effort}, article {context}) -> {out_dir}", flush=True)
    if args.plan:
        return

    judge = Judge(args.judge, effort)
    # Recorded without the transport prefix, as the existing grade files record it.
    stamp = fj.stamp(model, effort, article)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    reports: dict[str, str] = {}
    todo: list[tuple[Path, str]] = []
    # Anthropic refusals recur on every finding of a report; skip rather than repay them.
    skip_refused = provider == "anthropic"
    for d in run_dirs:
        report = (d / "report.md").read_text()
        reports[d.name] = report
        path = out_dir / f"{d.name}.json"
        prev = json.loads(path.read_text()) if path.exists() else {}
        if prev.get("article_sha256") not in (None, stamp["article_sha256"]):
            sys.exit(f"{path} was graded with a different article context; use another --output")
        same = all(prev.get(k) == v for k, v in stamp.items()) and prev.get("report_sha256") == fj.sha(report)
        # A matching file keeps every field it has (e.g. rubric_provenance on combined grades).
        body = ({**prev, "article_context": prev.get("article_context", context)} if same else
                {**fj.run_meta(d), **stamp, "article_context": context, "report_sha256": fj.sha(report),
                 "findings": {}})
        files[d.name] = body
        done_statuses = ("ok", "refused") if skip_refused else ("ok",)
        if skip_refused and body["findings"].get(heads[0], {}).get("status") == "refused":
            continue
        todo += [(d, h) for h in heads if body["findings"].get(h, {}).get("status") not in done_statuses]
    print(f"{len(todo)} calls to make", flush=True)

    write_lock = threading.Lock()

    def write(name: str) -> None:
        body = fj.summarize(files[name], heads, reports[name])
        if judge.model in PRICES:  # no price table for OpenRouter judges; record nothing rather than $0
            body["cost_usd"] = round(sum(judge.cost(u) for f in body["findings"].values() for u in f.get("usage", [])), 4)
        tmp = out_dir / f".{name}.json.tmp"
        tmp.write_text(json.dumps(body, indent=1, ensure_ascii=False))
        tmp.replace(out_dir / f"{name}.json")

    def do(item: tuple[Path, str]) -> None:
        d, h = item
        prompt = fj.render(h, article, reports[d.name])
        try:
            result = judge.grade(h, subs_of[h], prompt)
        except judge.errors as exc:
            result = {"status": "api_error", "error": f"{type(exc).__name__}: {exc}"[:500]}
        with write_lock:
            prev = files[d.name]["findings"].get(h)
            if prev and prev.get("status") != "ok":  # keep the history of failed attempts
                earlier = prev.pop("previous_attempts", [])
                result["previous_attempts"] = earlier + [{k: v for k, v in prev.items() if k != "raw"}]
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
        rest = [(d, h) for d, h in rest
                if not skip_refused or files[d.name]["findings"].get(heads[0], {}).get("status") != "refused"]
        list(pool.map(do, rest))

    print(f"done: spend ${judge.spend:.2f}")
    # Rewrite only the files this run graded; untouched grade files stay byte-for-byte.
    for name in {d.name for d, _ in todo}:
        write(name)
    for name, body in files.items():
        print(f"  {name[17:70]:54} mean {body.get('score_mean')} (unweighted {body.get('score_mean_unweighted')})"
              f"  scored {body.get('n_scored')}/{body.get('n_findings')}  unscored {body.get('unscored')}")


if __name__ == "__main__":
    main()
