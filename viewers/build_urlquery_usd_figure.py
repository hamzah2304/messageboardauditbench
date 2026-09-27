#!/usr/bin/env python3
"""Build the URLQuery v6 performance-vs-USD figure from the final run archive.

Performance is deliberately null until URLQuery grades are approved. Existing
per-run performance entries in the output JSON survive a rebuild, keyed by run
directory name. The HTML also works while the batch is still running.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "urlquery"
OUT = ROOT / "viewers" / "figures" / "urlquery_usd_figure.json"
HTML = OUT.with_suffix(".html")
CONDITIONS = {10: "urlquery-agents-v6-10", 30: "urlquery-agents-v6-30"}
MODELS = [
    ("codex", "gpt-6-astra", "GPT-6 Astra", "openai"),
    ("codex", "gpt-6-sol", "GPT-6 Sol", "openai"),
    ("codex", "gpt-6-luna", "GPT-6 Luna", "openai"),
    ("claude", "claude-opus-5", "Opus 5", "anthropic"),
    ("claude", "claude-opus-4-8", "Opus 4.8", "anthropic"),
    ("claude", "claude-opus-4-6", "Opus 4.6", "anthropic"),
    ("claude", "claude-sonnet-5", "Sonnet 5", "anthropic"),
    ("react", "google/gemini-3.8-flash", "Gemini 3.8 Flash", "google"),
    ("react", "meta/muse-spark-1.3", "Muse Spark 1.3", "meta"),
    ("react", "moonshotai/kimi-k3", "Kimi K3", "moonshot"),
    ("react", "z-ai/glm-5.3", "GLM 5.3", "zai"),
    ("react", "deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", "deepseek"),
]
# Standard, short-context list prices per million tokens, checked 2026-09-27.
# Codex subscription use is shown as a token-equivalent API estimate.
OPENAI_PRICES = {
    "gpt-6-astra": (10.0, 1.0, 12.5, 50.0),
    "gpt-6-sol": (2.0, 0.2, 2.5, 10.0),
    "gpt-6-luna": (0.1, 0.01, 0.125, 0.5),
}
PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def cost_of(model: str, usage: dict) -> tuple[float | None, str | None]:
    if model in OPENAI_PRICES:
        keys = ("input_tokens_uncached", "cache_read_tokens", "cache_write_tokens", "output_tokens")
        if any(not isinstance(usage.get(k), (int, float)) for k in keys):
            return None, None
        prices = OPENAI_PRICES[model]
        return round(sum(usage[k] * price for k, price in zip(keys, prices)) / 1e6, 6), "estimated_api_list"
    cost = usage.get("cost_usd")
    if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
        return round(cost, 6), "recorded_usage"
    return None, None


def main() -> None:
    old = read_json(OUT) if OUT.exists() else {}
    previous = {r["run_dir"]: r.get("performance") for r in old.get("runs", []) if r.get("run_dir")}
    found = {}
    for path in RUNS.glob("*/meta.json"):
        try:
            meta = read_json(path)
        except (OSError, ValueError):
            continue  # a running trial can still be writing its metadata
        if meta.get("condition") not in CONDITIONS.values():
            continue
        key = (meta.get("condition"), meta.get("agent"), meta.get("model"), meta.get("replicate"))
        if key in found:
            raise ValueError(f"duplicate final run for {key}: {found[key]} and {path.parent}")
        found[key] = path.parent

    rows = []
    for budget, condition in CONDITIONS.items():
        for agent, model, label, provider in MODELS:
            for replicate in (1, 2):
                path = found.get((condition, agent, model, replicate))
                usage_path = path / "usage.json" if path else None
                report = bool(path and (path / "report.md").exists())
                usage = read_json(usage_path) if report and usage_path and usage_path.exists() else {}
                cost, source = cost_of(model, usage) if report else (None, None)
                name = path.name if path else None
                performance = previous.get(name)
                if performance is not None and (not isinstance(performance, (int, float)) or
                                                not math.isfinite(performance) or not 0 <= performance <= 1):
                    raise ValueError(f"invalid performance for {name}: {performance}")
                rows.append({"run_dir": name, "model": model, "label": label, "provider": provider,
                             "harness": agent, "budget_min": budget, "replicate": replicate,
                             "status": "complete" if report else "running" if path else "not_started",
                             "cost_usd": cost, "cost_source": source, "performance": performance})

    payload = {"benchmark": "urlquery", "version": "agents-v6", "measure": "finding_score_mean",
               "measure_note": "0–1 mean of approved URLQuery headline-finding grades; null means ungraded",
               "cost_note": "USD per run. Codex values estimate Standard short-context API list-price token equivalents; other values come from usage.json cost_usd. Subscription charges and judge costs are excluded.",
               "openai_price_source": PRICE_SOURCE, "runs": rows}
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    template = (ROOT / "viewers" / "templates" / "urlquery_usd_figure.html").read_text()
    HTML.write_text(template.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
    print(f"{HTML}: {sum(r['status'] == 'complete' for r in rows)}/{len(rows)} reports, "
          f"{sum(r['cost_usd'] is not None for r in rows)} costs, "
          f"{sum(r['performance'] is not None for r in rows)} performance values")


if __name__ == "__main__":
    main()
