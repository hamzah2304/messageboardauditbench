#!/usr/bin/env python3
"""Estimate what each graded AI Village run cost in USD, subagents included.

Every run gets a list-price estimate: its tokens times the vendor's standard
per-token price. Where the run also recorded a cost, the script shows it next
to the estimate and flags a disagreement, so neither number is taken on trust:

- Claude Code: the CLI's own `modelUsage.costUSD`, which covers subagents.
  The estimate prices the same `modelUsage` tokens.
- Codex: no recorded cost. Tokens are summed over every thread's rollout
  (parent and subagents) by `messageboard_audit_bench.usage`.
- OpenRouter (react): the per-call `cost` OpenRouter billed. The headline uses
  it because routing between providers makes the list price only approximate.

Usage:
  uv run python scripts/aivillage_run_costs.py \
      --manifest .worktrees/claude-aivillage-pilot/benchmark/incidents/aivillage/benchmark-2026-10-04-runs.md \
      --out runs/aivillage-costs-20261004
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from messageboard_audit_bench.usage import summarize

ROOT = Path(__file__).resolve().parents[1]

# USD per million tokens: (uncached input, cache read, cache write, output).
# OpenRouter /api/v1/models, retrieved 2026-10-04, standard short-context tier;
# for OpenAI and Anthropic these equal the vendors' own list prices. OpenAI
# charges no cache-write fee and Codex reports no cache writes.
PRICES = {
    "claude-opus-5": (5.0, 0.5, 6.25, 25.0),
    "claude-opus-4-8": (5.0, 0.5, 6.25, 25.0),
    "claude-sonnet-5-5": (2.0, 0.2, 2.5, 10.0),
    "gpt-6-astra": (10.0, 1.0, 10.0, 50.0),
    "gpt-6.1-sol": (2.0, 0.1, 2.0, 10.0),
    "gpt-6-luna": (0.1, 0.01, 0.1, 0.5),
    "google/gemini-3.8-flash": (0.75, 0.075, 0.0417, 3.75),
    "meta/muse-spark-1.3": (1.25, 0.15, 0.0, 4.25),
    "moonshotai/kimi-k3": (0.72, 0.7, 0.0, 14.0),
    "z-ai/glm-5.3": (1.4, 0.14, 0.0, 4.4),
    "deepseek/deepseek-v4-flash": (0.0224, 0.0224, 0.0, 1.28),
}
PRICE_SOURCE = "https://openrouter.ai/api/v1/models (retrieved 2026-10-04)"
# Anthropic charges 2x input for a 1-hour cache write and 1.25x for a
# 5-minute one. modelUsage does not split them: on 4 Oct, runs without
# subagents matched the 1-hour price exactly, and subagent runs fell between
# the two, so the CLI cost is checked against that range.
CLAUDE_CACHE_WRITE_MULTIPLIERS = (1.25, 2.0)
# Above this prompt size some vendors charge a long-context rate; flagged only.
LONG_CONTEXT = 200_000
DISAGREE = 0.05


def manifest_runs(path: Path) -> list[str]:
    text = path.read_text()
    section = text.split("## Grade these", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"`(\d{8}T\d{6}Z_[^`]+)`", section)


def parse_name(name: str) -> dict:
    stamp, agent, rest = name.split("_", 2)
    model, replicate, config, _ = rest.rsplit("_", 3)
    if agent == "react":
        model = model.replace("_", "/", 1)
    return {"agent": agent, "model": model, "replicate": replicate,
            "subagents": config.endswith("-subagents"), "config": config}


def price(model: str, uncached: int, read: int, write: int, out: int,
          write_multiplier: float | None = None) -> float:
    p_in, p_read, p_write, p_out = PRICES[model]
    if write_multiplier is not None:
        p_write = p_in * write_multiplier
    return (uncached * p_in + read * p_read + write * p_write + out * p_out) / 1e6


def claude_cost(run_dir: Path, model: str, usage: dict) -> dict:
    per_model = usage.get("per_model") or {}
    tokens = {"uncached": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    recorded = 0.0
    low = high = 0.0
    for name, u in per_model.items():
        if name not in PRICES:
            raise SystemExit(f"{run_dir.name}: no price for Claude model {name}")
        t = (u.get("inputTokens", 0), u.get("cacheReadInputTokens", 0),
             u.get("cacheCreationInputTokens", 0), u.get("outputTokens", 0))
        for key, value in zip(tokens, t):
            tokens[key] += value
        recorded += u.get("costUSD") or 0
        low += price(name, *t, write_multiplier=CLAUDE_CACHE_WRITE_MULTIPLIERS[0])
        high += price(name, *t, write_multiplier=CLAUDE_CACHE_WRITE_MULTIPLIERS[1])
    if not per_model:
        raise SystemExit(f"{run_dir.name}: Claude run has no modelUsage")
    return {**tokens, "models": sorted(per_model), "recorded_usd": recorded,
            "list_usd": high, "list_usd_range": [low, high], "usd": recorded,
            "usd_source": "claude_cli"}


def codex_cost(model: str, usage: dict) -> dict:
    tokens = {"uncached": usage["input_tokens_uncached"],
              "cache_read": usage["cache_read_tokens"],
              "cache_write": usage["cache_write_tokens"],
              "output": usage["output_tokens"]}
    estimate = price(model, *tokens.values())
    return {**tokens, "threads": usage.get("sessions"), "recorded_usd": None,
            "list_usd": estimate, "usd": estimate, "usd_source": "list_price"}


def react_cost(run_dir: Path, model: str) -> dict:
    tokens = {"uncached": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    billed, estimate, calls, unbilled = 0.0, 0.0, 0, 0
    providers: dict[str, int] = {}
    seen: set[str] = set()
    for line in (run_dir / "transcript.jsonl").open():
        event = json.loads(line)
        if event.get("type") != "assistant":
            continue
        message = event.get("message") or {}
        u = message.get("usage")
        if not u or message.get("id") in seen:
            continue
        seen.add(message.get("id"))
        calls += 1
        read = u.get("cache_read_input_tokens") or 0
        write = u.get("cache_creation_input_tokens") or 0
        # OpenRouter's prompt count includes cached tokens.
        uncached = max((u.get("input_tokens") or 0) - read - write, 0)
        out = u.get("output_tokens") or 0
        for key, value in zip(tokens, (uncached, read, write, out)):
            tokens[key] += value
        estimate += price(model, uncached, read, write, out)
        if isinstance(u.get("cost"), (int, float)):
            billed += u["cost"]
        else:
            unbilled += 1
        provider = (event.get("api") or {}).get("provider") or "unknown"
        providers[provider] = providers.get(provider, 0) + 1
    if unbilled:
        raise SystemExit(f"{run_dir.name}: {unbilled} of {calls} calls have no billed cost")
    return {**tokens, "calls": calls, "providers": providers, "recorded_usd": billed,
            "list_usd": estimate, "usd": billed, "usd_source": "openrouter_billed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=ROOT / "runs")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for name in manifest_runs(args.manifest):
        run_dir = args.runs_root / name
        info = parse_name(name)
        usage = summarize(run_dir, info["agent"])
        if info["agent"] == "claude":
            cost = claude_cost(run_dir, info["model"], usage)
        elif info["agent"] == "codex":
            cost = codex_cost(info["model"], usage)
        else:
            cost = react_cost(run_dir, info["model"])
        flags = []
        if "list_usd_range" in cost:
            low, high = cost["list_usd_range"]
            if not low * (1 - 1e-6) <= cost["recorded_usd"] <= high * (1 + 1e-6):
                flags.append(f"recorded cost outside list range {low:.2f} to {high:.2f}")
        elif cost["recorded_usd"] and abs(cost["list_usd"] / cost["recorded_usd"] - 1) > DISAGREE:
            flags.append(f"list estimate differs from recorded by "
                         f"{cost['list_usd'] / cost['recorded_usd'] - 1:+.0%}")
        if (usage.get("peak_context_tokens") or 0) > LONG_CONTEXT:
            flags.append(f"peak context {usage['peak_context_tokens']:,} tokens")
        rows.append({"run": name, **info, **cost,
                     "peak_context_tokens": usage.get("peak_context_tokens"),
                     "flags": flags})

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "costs.json").write_text(json.dumps(
        {"price_source": PRICE_SOURCE, "prices_per_million": PRICES,
         "claude_cache_write_multipliers": CLAUDE_CACHE_WRITE_MULTIPLIERS,
         "runs": rows}, indent=1) + "\n")
    columns = ["run", "agent", "model", "replicate", "subagents", "usd", "usd_source",
               "recorded_usd", "list_usd", "uncached", "cache_read", "cache_write",
               "output", "peak_context_tokens", "flags"]
    with (args.out / "costs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "flags": "; ".join(row["flags"])})

    for row in sorted(rows, key=lambda r: (r["model"], r["subagents"], r["replicate"])):
        recorded = f"{row['recorded_usd']:7.2f}" if row["recorded_usd"] is not None else "      -"
        print(f"{row['model']:28s} {'sub' if row['subagents'] else '   '} {row['replicate']}"
              f"  ${row['usd']:6.2f}  recorded {recorded}  list {row['list_usd']:6.2f}"
              f"  {'; '.join(row['flags'])}")
    print(f"{len(rows)} runs, total ${sum(r['usd'] for r in rows):.2f} -> {args.out}")


if __name__ == "__main__":
    main()
