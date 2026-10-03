#!/usr/bin/env python3
"""Build the agent-readable AI Village data folders from the downloaded Hugging Face export.

    scripts/build_aivillage_full.py --variant reasoning     # -> data/aivillage/full-v1-reasoning/
    scripts/build_aivillage_full.py --variant noreasoning   # -> data/aivillage/full-v1-noreasoning/

Both variants cover the whole export. Files that need no change are hard links to
data/raw/ai-village/, so they cost no disk. Left out of both: the LLM-written
`summaries` (a model's narrative, not evidence), the dataset's own README,
SCHEMA, CHANGELOG and example code (they describe known incidents and steer the
agent), and the screenshots (not downloaded). The `noreasoning` variant also
removes every reasoning trace the model providers returned: Anthropic thinking
blocks, OpenAI reasoning items, Gemini thought parts, reasoning_content /
reasoning_details fields, and the transcript's `thinking` field.
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = Path(subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True).strip()).parent
RAW = PRIMARY / "data" / "raw" / "ai-village"
README = ROOT / "benchmark" / "incidents" / "aivillage" / "README.data.txt"
REASONING_NOTE = {
    "reasoning": (
        "The raw model responses include each agent's reasoning text where the model provider\n"
        "returned it: `thinking` blocks for Anthropic models, `reasoning` items with summaries for\n"
        "OpenAI models and parts marked `\"thought\": true` for Gemini models. They sit in\n"
        "events.jsonl.gz (`data.output`), computer_use_turns.jsonl.gz (`agent_messages`) and\n"
        "claude_code_messages.jsonl.gz, and village-transcript.json has a `thinking` field.\n"
        "This reasoning is separate from what agents said in chat and did on their computers,\n"
        "so it can show what an agent believed or intended when that differs from its words.\n"
        "Some providers return only a summary of the reasoning, not the full text."
    ),
    "noreasoning": (
        "The agents' reasoning text has been removed from these files. What remains is what\n"
        "the agents said in chat and wrote in memory, and what they did on their computers."
    ),
}

SMALL = ["agents", "agent_goals", "chat_rooms", "villages", "village_goals", "claude_code_sessions"]
NO_REASONING = ["chat_messages", "computer_use_sessions", "agent_memories"]
WITH_REASONING = ["events", "computer_use_turns", "claude_code_messages"]

DROP_TYPES = {"thinking", "redacted_thinking", "reasoning", "reasoning.text", "reasoning.encrypted", "reasoning.summary"}
DROP_KEYS = {"thinking", "reasoning", "reasoning_content", "reasoning_details", "thinkingMessage", "encrypted_content"}
MARKERS = ('"thinking"', '"reasoning', '"thought": true', '"thought":true', "encrypted_content", "thinkingMessage", '"redacted_thinking"')


def strip(o):
    """Remove reasoning traces anywhere in a provider-shaped object; return the count removed."""
    n = 0
    if isinstance(o, dict):
        for k in [k for k in o if k in DROP_KEYS]:
            del o[k]
            n += 1
        for v in o.values():
            n += strip(v)
    elif isinstance(o, list):
        keep = []
        for x in o:
            if isinstance(x, dict) and (x.get("type") in DROP_TYPES or x.get("thought") is True):
                n += 1
            else:
                n += strip(x)
                keep.append(x)
        o[:] = keep
    return n


def link(src, dst):
    if dst.exists():
        dst.unlink()
    os.link(src, dst)


def rewrite_jsonl_gz(src, dst):
    removed = rows = touched = 0
    reader = subprocess.Popen(["pigz", "-dc", str(src)], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    with open(dst, "wb") as out_f:
        writer = subprocess.Popen(["pigz", "-3", "-c"], stdin=subprocess.PIPE, stdout=out_f, text=True, bufsize=1 << 20)
        for line in reader.stdout:
            rows += 1
            if any(m in line for m in MARKERS):
                r = json.loads(line)
                k = strip(r)
                if k:
                    removed += k
                    touched += 1
                    line = json.dumps(r, ensure_ascii=False) + "\n"
            writer.stdin.write(line)
        writer.stdin.close()
        writer.wait()
    reader.wait()
    print(f"{src.name}: {rows} rows, {touched} rewritten, {removed} reasoning items removed", flush=True)


def check_clean(path):
    """Fail loudly if a reasoning marker survives in a rewritten file."""
    opener = (lambda p: subprocess.Popen(["pigz", "-dc", str(p)], stdout=subprocess.PIPE, text=True).stdout) if path.suffix == ".gz" else (lambda p: open(p))
    left = sum(1 for line in opener(path) if any(m in line for m in ('"type": "thinking"', '"type": "reasoning"', '"thought": true', '"reasoning_content"', '"thinking": "')))
    print(f"{path.name}: {left} lines still carry a reasoning marker", flush=True)


def write_readme(out, variant):
    (out / "README.txt").write_text(README.read_text().replace("{{REASONING}}", REASONING_NOTE[variant]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=["reasoning", "noreasoning"], required=True)
    a = p.parse_args()
    out = PRIMARY / "data" / "aivillage" / f"full-v1-{a.variant}"
    out.mkdir(parents=True, exist_ok=True)

    for name in SMALL:  # uncompressed, so the folder has plain .jsonl files and the small tables are easy to read
        with gzip.open(RAW / f"{name}.jsonl.gz", "rt") as f, open(out / f"{name}.jsonl", "w") as g:
            shutil.copyfileobj(f, g)
    for name in NO_REASONING:
        link(RAW / f"{name}.jsonl.gz", out / f"{name}.jsonl.gz")
    if a.variant == "reasoning":
        for name in WITH_REASONING:
            link(RAW / f"{name}.jsonl.gz", out / f"{name}.jsonl.gz")
        link(RAW / "village-transcript.json", out / "village-transcript.json")
    else:
        t = json.load(open(RAW / "village-transcript.json"))
        n = strip(t)
        json.dump(t, open(out / "village-transcript.json", "w"), ensure_ascii=False, indent=1)
        print(f"village-transcript.json: {n} reasoning items removed", flush=True)
        for name in WITH_REASONING:
            rewrite_jsonl_gz(RAW / f"{name}.jsonl.gz", out / f"{name}.jsonl.gz")
        for name in WITH_REASONING:
            check_clean(out / f"{name}.jsonl.gz")
        check_clean(out / "village-transcript.json")
    write_readme(out, a.variant)

    digest = hashlib.sha256()
    for f in sorted(out.iterdir()):
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 24), b""):
                h.update(chunk)
        digest.update(f.name.encode() + b"\0" + h.digest())
    print(out, "sha256:", digest.hexdigest())


if __name__ == "__main__":
    main()
