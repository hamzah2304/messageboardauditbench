"""Grade reports against a benchmark's answer key, one judge call per headline finding.

    uv run python scripts/grade_answer_key.py --benchmark aivillage RUN_DIR [RUN_DIR ...] [--workers 8]
    uv run python scripts/grade_answer_key.py --benchmark german-wiki --batch runs/<batch-dir>
    uv run python scripts/grade_answer_key.py --launch runs/urlquery/<final>/launch.json --omit-article
    uv run python scripts/grade_answer_key.py --judge openrouter/openai/gpt-6-astra --launch ...
    uv run python scripts/grade_answer_key.py --benchmark aivillage --batch ... --plan   # resume-aware call count, no API use

The resumable batch counterpart of the ``*_report_grade`` Inspect tasks: the prompt, parsing and
arithmetic are `slopvestigator_bench.grading.answer_key_judge`, shared with the Inspect scorers, so
every benchmark is graded the same way. ``--benchmark`` defaults to transluce, whose old command
(benchmarks/transluce/judge/grade.py) still runs this. The judge defaults to the standard judge
(configs/standard.toml: openrouter/openai/gpt-6.1-sol at high effort). Three judge transports:

* ``anthropic/<model>`` (effort xhigh unless given, adaptive thinking): synchronous Messages
  API calls. The prompt is sent as three blocks so the
  cache does the work: rules + source (identical for every call), the report (identical
  for a report's calls), then the finding. The first call on each report runs alone so the
  others read its cache.
* ``openrouter/<model>`` (the standard judge; the Transluce final run used
  ``openrouter/openai/gpt-6-astra``, effort high): synchronous OpenRouter chat completions with a
  JSON response format, no fallback provider, and OpenRouter's reported cost recorded.
* ``openai/<model>``: the same chat completions, from OpenAI directly.
* ``codex/<model>`` (e.g. ``codex/gpt-6.1-sol``): the Codex CLI on the ChatGPT subscription, stripped
  to the grader's system prompt and the judge prompt (`grading.codex_judge`). Its grades file under
  judge_codex_<model>_<effort>/, apart from the API judge's. The batch stops when the subscription
  window passes ``--codex-stop-at`` percent (default 90), so it never spends Codex credits.

A refusal, an unparseable answer or an API error leaves that finding unscored and says so;
it is never recorded as a zero, and there is no fallback to another model, so one file is
always one judge's work. With the Anthropic judge, a refusal on a report's first headline
skips its remaining headlines (it recurs on every one); OpenRouter refusals are retried on
the next run, as before. Grades land in judge_<model>[_<effort>]/ under
benchmarks/transluce/reports/graded/ for Transluce and benchmarks/<benchmark>/graded-answer-key/
otherwise; both are gitignored, because reports can quote recorded secrets. German wiki reports
written from verbatim_anthropic data are skipped: the key names OpenAI. Re-running skips findings
already graded under the same judge, prompt, findings and source.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopvestigator_bench import standard  # noqa: E402
from slopvestigator_bench.benchmarks import primary_root  # noqa: E402
from slopvestigator_bench.grading import answer_key_judge as akj  # noqa: E402
from slopvestigator_bench.grading import codex_judge  # noqa: E402
from slopvestigator_bench.grading import findings as fj  # noqa: E402
from slopvestigator_bench.grading.core import variant_for_data  # noqa: E402
from slopvestigator_bench.grading.judge import OPENROUTER_ROUTE  # noqa: E402

load_dotenv(ROOT / ".env")

DEFAULT_JUDGE, DEFAULT_EFFORT = standard.judge()
TRANSPORTS = fj.TRANSPORTS  # effort, max_tokens, attempts, refusal skip per transport
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
    if judge.startswith("codex/"):
        return "codex", judge.removeprefix("codex/")
    if judge.startswith("anthropic/"):
        return "anthropic", judge.removeprefix("anthropic/")
    if judge.startswith("claude"):
        return "anthropic", judge
    if judge.startswith("openai/"):
        return "openai", judge.removeprefix("openai/")
    raise SystemExit(f"judge must be anthropic/<model>, openai/<model>, openrouter/<model> or codex/<model>, not {judge!r}")


def transport_of(provider: str) -> dict:
    """The call settings for a provider: OpenAI directly is called as OpenRouter is."""
    return TRANSPORTS["openrouter" if provider in ("openai", "codex") else provider]


class Judge:
    def __init__(self, judge: str, effort: str | None = None, codex_stop_at: float = 90.0):
        self.provider, self.model = provider_of(judge)
        self.effort = effort or transport_of(self.provider)["effort"]
        self.lock = threading.Lock()
        self.spend = 0.0
        self.codex = None
        if self.provider == "codex":
            self.codex = codex_judge.CodexJudge(self.model, self.effort, fj.SYSTEM,
                                                primary_root() / "runs" / ".codex-judge-home", codex_stop_at)
            self.errors = (Exception,)
        elif self.provider == "anthropic":
            import anthropic

            self.client = anthropic.Anthropic()
            self.errors = (anthropic.APIError,)
        elif self.provider == "openai":
            from openai import OpenAI

            self.client = OpenAI(timeout=600.0, max_retries=2)
            self.errors = (Exception,)
        else:
            from openai import OpenAI

            key_file = primary_root() / "runs" / f".openrouter_key.{self.model.replace('/', '_')}"
            key = os.environ.get("OPENROUTER_API_KEY") or (key_file.read_text().strip() if key_file.is_file() else "")
            if not key:
                raise SystemExit("OpenRouter API key is missing")
            self.client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", timeout=600.0, max_retries=2)
            self.errors = (Exception,)

    def cost(self, usage) -> float:
        if "cost" in usage:  # OpenRouter reports what it charged
            return usage["cost"] or 0.0
        p_in, p_out, p_read, p_write = PRICES.get(self.model, (0, 0, 0, 0))
        return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
                + usage.get("cache_read_input_tokens", 0) * p_read
                + usage.get("cache_creation_input_tokens", 0) * p_write) / 1e6

    def _anthropic(self, prompt: str, suffix: str) -> tuple[str, dict, str, dict | None]:
        blocks = split_blocks(prompt)
        blocks[-1] = {"type": "text", "text": blocks[-1]["text"] + suffix}
        with self.client.messages.stream(
            model=self.model,
            max_tokens=TRANSPORTS["anthropic"]["max_tokens"],
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
            max_completion_tokens=transport_of(self.provider)["max_tokens"],
            messages=[{"role": "system", "content": fj.SYSTEM}, {"role": "user", "content": prompt}],
            **({"extra_body": {**OPENROUTER_ROUTE, "usage": {"include": True}}} if self.provider == "openrouter" else {}),
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
        for attempt in range(transport_of(self.provider)["attempts"]):
            if self.provider == "anthropic":
                text, usage, stop, refusal = self._anthropic(prompt, fj.JSON_ONLY if attempt else "")
            elif self.codex:
                text, usage, stop, refusal = self.codex.call(prompt)
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
                if reason := fj.incomplete(data, result, headline):
                    return {"status": "invalid", "error": reason, **result, "validation": notes,
                            "usage": usage_all, "raw": raws}
                return {"status": "ok", **result, "validation": notes, "usage": usage_all,
                        "raw": raws, "seconds": round(time.time() - started, 1)}
        return {"status": "unparseable", "usage": usage_all, "raw": raws}


def parser(defaults: dict | None = None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--benchmark", choices=sorted(akj.SPECS), default="transluce")
    ap.add_argument("--batch", type=Path, help="a batch directory whose *.result.json name the run dirs")
    ap.add_argument("--launch", type=Path, help="launch.json; use completed reports from all referenced plans")
    ap.add_argument("--article", choices=fj.ARTICLE_CONTEXTS,
                    help="Transluce's article context; default omitted for Anthropic judges, full otherwise")
    ap.add_argument("--omit-article", action="store_const", const="omitted", dest="article",
                    help="same as --article omitted")
    ap.add_argument("--judge", default=DEFAULT_JUDGE,
                    help="anthropic/<model>, openai/<model> or openrouter/<model> (default: the standard judge)")
    ap.add_argument("--effort", help="default: the standard judge's effort for it; else xhigh for Anthropic, high otherwise")
    ap.add_argument("--output", type=Path, help="grade directory (default: see above, then judge_<model>...)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--codex-stop-at", type=float, default=90.0,
                    help="codex judge: stop when the subscription window is this percent used")
    ap.add_argument("--findings", nargs="*", help="only these headline ids")
    ap.add_argument("--plan", action="store_true", help="print the calls a run would make (after resume) and stop")
    ap.set_defaults(**(defaults or {}))
    return ap


def output_root(benchmark: str) -> Path:
    if benchmark == "transluce":
        return fj.output_root()
    return primary_root() / "benchmarks" / benchmark / "graded-answer-key"


def report_setup(benchmark: str, run_dir: Path) -> dict[str, str] | None:
    """The report's prompt values, or None when the key cannot grade it."""
    meta = run_dir / "meta.json"
    variant = json.loads(meta.read_text()).get("data_variant") if meta.is_file() else None
    if benchmark == "german-wiki" and variant_for_data(variant):
        return None
    return akj.report_variables(benchmark, variant)


def main(argv: list[str] | None = None, defaults: dict | None = None) -> None:
    args = parser(defaults).parse_args(argv)
    run_dirs = fj.reports_from(runs=args.runs, batches=[args.batch] if args.batch else [], launch=args.launch)
    if not run_dirs:
        sys.exit("no run directories with a report.md")

    bench = args.benchmark
    spec = akj.SPECS[bench]
    context = (args.article or fj.default_article_context(args.judge)) if spec.source == "article" else None
    source = akj.source_text(bench, context)
    key = akj.load_key(bench)
    all_findings = akj.graded_findings(key)
    by_id = {f["id"]: f for f in all_findings}
    all_heads = list(by_id)
    heads = [h for h in all_heads if h in args.findings] if args.findings else all_heads
    weights = akj.headline_weights(all_findings)
    provider, model = provider_of(args.judge)
    effort = args.effort or (DEFAULT_EFFORT if args.judge == DEFAULT_JUDGE else transport_of(provider)["effort"])
    # Opus grades have always been filed without an effort suffix; OpenRouter's and OpenAI's with one.
    out_dir = args.output or output_root(bench) / fj.judge_dir(f"codex_{model}" if provider == "codex" else model,
                                                              effort if provider != "anthropic" else None)
    variables: dict[str, dict[str, str]] = {}
    for d in list(run_dirs):
        found = report_setup(bench, d)
        if found is None:
            print(f"  skipped {d.name}: the answer key has no variant for its data", flush=True)
            run_dirs.remove(d)
        else:
            variables[d.name] = found
    print(f"{len(run_dirs)} reports x {len(heads)} findings "
          f"({bench}, {args.judge}, effort {effort}{f', article {context}' if context else ''}) -> {out_dir}", flush=True)

    # Recorded without the transport prefix, as the existing grade files record it.
    stamp = akj.stamp(bench, args.judge if provider == "codex" else model, effort, source, key)
    files: dict[str, dict] = {}
    reports: dict[str, str] = {}
    todo: list[tuple[Path, str]] = []
    # Anthropic refusals recur on every finding of a report; skip rather than repay them.
    skip_refused = transport_of(provider)["skip_after_first_refusal"]
    for d in run_dirs:
        report = (d / "report.md").read_text()
        reports[d.name] = report
        path = out_dir / f"{d.name}.json"
        prev = json.loads(path.read_text()) if path.exists() else {}
        if spec.source == "article" and prev.get("article_sha256") not in (None, stamp["article_sha256"]):
            sys.exit(f"{path} was graded with a different article context; use another --output")
        same = (all(prev.get(k) == v for k, v in stamp.items()) and prev.get("report_sha256") == fj.sha(report)
                and prev.get("prompt_variables", {}) == variables[d.name])
        # A matching file keeps every field it has (e.g. rubric_provenance on combined grades).
        extra = {"article_context": prev.get("article_context", context) if same else context} if context else {}
        body = ({**prev, **extra} if same else
                {**fj.run_meta(d), **stamp, **extra, "report_sha256": fj.sha(report),
                 **({"prompt_variables": variables[d.name]} if variables[d.name] else {}), "findings": {}})
        files[d.name] = body
        if skip_refused and body["findings"].get(heads[0], {}).get("status") == "refused":
            continue

        def done(result: dict) -> bool:
            # A stored "ok" with an unscored sub-finding predates the stricter check: grade it again.
            return fj.usable(result) or (skip_refused and result.get("status") == "refused")

        todo += [(d, h) for h in heads if not done(body["findings"].get(h, {}))]
    # With --plan this is the resume-aware count a real run would pay for.
    print(f"{len(todo)} calls to make", flush=True)
    if judge.codex and todo:
        judge.codex.refresh_limits(force=True)
        if reason := judge.codex.limit_reason():
            raise SystemExit(f"not starting: {reason}")
        print(judge.codex.window(), flush=True)
    if args.plan:
        return

    judge = Judge(args.judge, effort, args.codex_stop_at)
    stop = threading.Event()
    out_dir.mkdir(parents=True, exist_ok=True)

    write_lock = threading.Lock()

    def write(name: str) -> None:
        body = akj.summarize(bench, files[name], all_heads, weights, reports[name])
        usages = [u for f in body["findings"].values() for u in f.get("usage", [])]
        # Anthropic from the price table, OpenRouter from its reported cost; OpenAI direct records nothing rather than $0.
        if judge.model in PRICES or any("cost" in u for u in usages):
            body["cost_usd"] = round(sum(judge.cost(u) for u in usages), 4)
        tmp = out_dir / f".{name}.json.tmp"
        tmp.write_text(json.dumps(body, indent=1, ensure_ascii=False))
        tmp.replace(out_dir / f"{name}.json")

    def do(item: tuple[Path, str]) -> None:
        if stop.is_set():
            return
        d, h = item
        prompt = akj.render(bench, by_id[h], reports[d.name], source, variables[d.name])
        try:
            result = judge.grade(h, [s["id"] for s in by_id[h]["subfindings"]], prompt)
        except codex_judge.UsageLimit as exc:
            stop.set()
            print(f"stopping: subscription usage limit: {exc}", flush=True)
            return
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
        cost = judge.codex.window() if judge.codex else f"spend ${judge.spend:.2f}"
        print(f"  {d.name[17:60]:44} {h:4} {tag:10} {cost}", flush=True)
        if judge.codex and (reason := judge.codex.limit_reason()) and not stop.is_set():
            stop.set()
            print(f"stopping: {reason}; rerun to resume", flush=True)

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
        print(f"  {name[17:70]:54} score {body.get('score')} (unweighted mean {body.get('score_mean_unweighted')})"
              f"  scored {body.get('n_scored')}/{body.get('n_findings')}  unscored {body.get('unscored')}")


if __name__ == "__main__":
    main()
