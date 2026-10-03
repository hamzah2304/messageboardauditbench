#!/usr/bin/env python3
"""Cut one goal window out of the AI Village export into an agent-readable data folder.

    scripts/build_aivillage_slice.py --start 2025-10-20 --end 2025-11-03 --out data/aivillage/2025-10-20-poverty-v1

Reads the downloaded Hugging Face export in data/raw/ai-village/. Keeps the raw
records of the window and adds a resolved `speaker_name`/`agent_name` so the
agent does not have to join tables to know who spoke. Leaves out the
LLM-written `summaries` (secondary narrative, not evidence) and the screenshots.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "ai-village"


def rows(name):
    with gzip.open(RAW / f"{name}.jsonl.gz", "rt") as f:
        for line in f:
            yield json.loads(line)


def in_window(ts, start, end):
    return ts is not None and start <= ts < end


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="inclusive UTC date, YYYY-MM-DD")
    p.add_argument("--end", required=True, help="exclusive UTC date, YYYY-MM-DD")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--memories", action="store_true", help="include agent_memories in the window")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    agents = {r["id"]: r for r in rows("agents")}
    names = {i: r["name"] for i, r in agents.items()}

    def write(name, it):
        n = 0
        with open(a.out / f"{name}.jsonl", "w") as f:
            for r in it:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
        print(f"{name}: {n}")
        return n

    write("agents", ({k: r[k] for k in ("id", "name", "model_string", "is_participating", "created_at")} for r in agents.values()))
    write("goals", (g for g in rows("village_goals") if in_window(g["start_time"], a.start, a.end)))

    def events():
        for r in rows("events"):
            if in_window(r["created_at"], a.start, a.end):
                d = r["data"]
                who = d.get("speakerId") or d.get("agentId")
                if who in names:
                    r["agent_name"] = names[who]
                yield r
    write("events", events())

    def chat():
        for r in rows("chat_messages"):
            if in_window(r["created_at"], a.start, a.end):
                r["speaker_name"] = names.get(r.get("agent_speaker_id"), "human viewer" if r["speaker_type"] == "user" else None)
                yield r
    write("chat_messages", chat())

    session_ids = set()

    def sessions():
        for r in rows("computer_use_sessions"):
            if in_window(r["created_at"], a.start, a.end):
                session_ids.add(r["id"])
                r["agent_name"] = names.get(r["agent_id"])
                yield r
    write("computer_use_sessions", sessions())
    session_agent = {}
    for line in open(a.out / "computer_use_sessions.jsonl"):
        r = json.loads(line)
        session_agent[r["id"]] = r["agent_name"]

    def turns():
        for r in rows("computer_use_turns"):
            if r["session_id"] in session_ids:
                r["agent_name"] = session_agent.get(r["session_id"])
                yield r
    write("computer_use_turns", turns())

    if a.memories:
        write("agent_memories", (dict(r, agent_name=names.get(r["agent_id"])) for r in rows("agent_memories") if in_window(r["created_at"], a.start, a.end)))

    digest = hashlib.sha256()
    for f in sorted(a.out.glob("*.jsonl")):
        digest.update(f.name.encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    print("dataset sha256:", digest.hexdigest())


if __name__ == "__main__":
    main()
