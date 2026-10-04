#!/usr/bin/env python3
"""Build the v2 AI Village data folders: computer-use records in SQLite, everything else plain JSONL.

    scripts/build_aivillage_data.py --variant noreasoning                      # -> data/aivillage/full-v2-noreasoning/
    scripts/build_aivillage_data.py --variant reasoning
    scripts/build_aivillage_data.py --variant reasoning --start 2025-10-27 --end 2025-11-01   # a small slice

Reads the downloaded export in data/raw/ai-village/. In both variants every reasoning trace
is stripped from the raw model responses. The `reasoning` variant puts it back in one place
per record: a `reasoning` column in the computer_use_turns table, and the raw responses in
events, claude_code_messages and the transcript keep their reasoning. So the two variants
share agent_messages exactly and differ only in where reasoning is present.

Left out of both, as in v1: the LLM-written summaries, the dataset's own README/SCHEMA/
CHANGELOG, and screenshots. Agent memories stay gzip-compressed (7 GB uncompressed, mostly
repeated snapshots).
"""
import argparse
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = Path(subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True).strip()).parent
RAW = PRIMARY / "data" / "raw" / "ai-village"
README = ROOT / "benchmark" / "incidents" / "aivillage" / "data-readme.txt"

DROP_TYPES = {"thinking", "redacted_thinking", "reasoning", "reasoning.text", "reasoning.encrypted", "reasoning.summary"}
DROP_KEYS = {"thinking", "reasoning", "reasoning_content", "reasoning_details", "thinkingMessage", "encrypted_content"}


def strip(o, found=None):
    """Remove reasoning traces in place; append any reasoning text to `found`."""
    if isinstance(o, dict):
        for k in [k for k in o if k in DROP_KEYS]:
            v = o.pop(k)
            if found is not None and isinstance(v, str):
                found.append(v)
            elif found is not None and k in ("thinkingMessage", "reasoning_details"):
                collect(v, found)
        for v in o.values():
            strip(v, found)
    elif isinstance(o, list):
        keep = []
        for x in o:
            if isinstance(x, dict) and (x.get("type") in DROP_TYPES or x.get("thought") is True):
                if found is not None:
                    collect(x, found)
            else:
                strip(x, found)
                keep.append(x)
        o[:] = keep


def collect(o, found):
    """Gather human-readable reasoning text from a removed reasoning item."""
    if isinstance(o, dict):
        for k in ("thinking", "text", "summary_text", "reasoning_content"):
            if isinstance(o.get(k), str):
                found.append(o[k])
        for k, v in o.items():
            if k not in ("signature", "thoughtSignature", "encrypted_content", "data") and isinstance(v, (dict, list)):
                collect(v, found)
    elif isinstance(o, list):
        for x in o:
            collect(x, found)


def rows(name):
    with gzip.open(RAW / f"{name}.jsonl.gz", "rt") as f:
        for line in f:
            yield json.loads(line)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=["reasoning", "noreasoning"], required=True)
    p.add_argument("--start", help="inclusive UTC date for a slice, YYYY-MM-DD")
    p.add_argument("--end", help="exclusive UTC date for a slice")
    p.add_argument("--finalize-only", action="store_true", help="only clean up an existing folder and rewrite README.txt")
    a = p.parse_args()
    keep_reasoning = a.variant == "reasoning"
    name = f"slice-v2-{a.variant}" if a.start else f"full-v2-{a.variant}"
    out = PRIMARY / "data" / "aivillage" / name
    out.mkdir(parents=True, exist_ok=True)
    if a.finalize_only:
        finalize(out, a.variant, a.start, a.end)
        print(out, "finalized")
        return
    lo, hi = a.start or "", a.end or "9999"

    def in_window(ts):
        return ts is not None and lo <= ts[:10] < hi

    agents = {r["id"]: r for r in rows("agents")}
    names = {i: r["name"] for i, r in agents.items()}

    def write_jsonl(fname, it):
        n = 0
        with open(out / fname, "w") as f:
            for r in it:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
        print(f"{fname}: {n} rows", flush=True)

    write_jsonl("agents.jsonl", ({k: r[k] for k in ("id", "name", "model_string", "is_participating", "created_at")} for r in agents.values()))
    for t in ("village_goals",):
        write_jsonl(f"{t}.jsonl", rows(t))

    def chat():
        for r in rows("chat_messages"):
            if in_window(r["created_at"]):
                r["speaker_name"] = names.get(r.get("agent_speaker_id")) or ("human" if r["speaker_type"] == "user" else None)
                yield r
    write_jsonl("chat_messages.jsonl", sorted(chat(), key=lambda r: r["created_at"]))

    def events():
        for r in rows("events"):
            if in_window(r["created_at"]):
                strip(r)
                who = r["data"].get("speakerId") or r["data"].get("agentId")
                if who in names:
                    r["agent_name"] = names[who]
                yield r
    write_jsonl("events.jsonl", events())

    def claude_code():
        for r in rows("claude_code_messages"):
            if in_window(r.get("created_at")):
                strip(r)
                r["agent_name"] = names.get(r.get("agent_id"))
                yield r
    write_jsonl("claude_code_messages.jsonl", claude_code())
    write_jsonl("claude_code_sessions.jsonl", (r for r in rows("claude_code_sessions") if in_window(r.get("created_at"))))

    if a.start:
        write_jsonl("agent_memories.jsonl", (dict(r, agent_name=names.get(r["agent_id"])) for r in rows("agent_memories") if in_window(r["created_at"])))
    else:
        dst = out / "agent_memories.jsonl.gz"
        if dst.exists():
            dst.unlink()
        os.link(RAW / "agent_memories.jsonl.gz", dst)

    db_path = out / "village.db"
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("CREATE TABLE computer_use_sessions (id TEXT PRIMARY KEY, created_at TEXT, agent_id TEXT, agent_name TEXT, session_goal TEXT, has_been_asked_to_stop INTEGER)")
    sessions = set()
    batch = []
    for r in rows("computer_use_sessions"):
        if in_window(r["created_at"]):
            sessions.add(r["id"])
            batch.append((r["id"], r["created_at"], r["agent_id"], names.get(r["agent_id"]), r.get("session_goal"), int(bool(r.get("has_been_asked_to_stop")))))
    db.executemany("INSERT INTO computer_use_sessions VALUES (?,?,?,?,?,?)", batch)
    session_agent = {s[0]: s[3] for s in batch}
    print(f"computer_use_sessions: {len(batch)} rows", flush=True)

    cols = ["id TEXT PRIMARY KEY", "session_id TEXT", "created_at TEXT", "agent_name TEXT", "action TEXT", "output TEXT", "error TEXT", "agent_messages TEXT"]
    if keep_reasoning:
        cols.append("reasoning TEXT")
    db.execute(f"CREATE TABLE computer_use_turns ({', '.join(cols)})")
    q = f"INSERT INTO computer_use_turns VALUES ({','.join('?' * len(cols))})"
    n, batch = 0, []
    for r in rows("computer_use_turns"):
        if a.start and r["session_id"] not in sessions:
            continue
        found = []
        msgs = r.get("agent_messages")
        strip(msgs, found)
        row = [r["id"], r["session_id"], r["created_at"], session_agent.get(r["session_id"]),
               json.dumps(r["agent_action"], ensure_ascii=False) if r.get("agent_action") is not None else None,
               r.get("output"), r.get("error"), json.dumps(msgs, ensure_ascii=False) if msgs is not None else None]
        if keep_reasoning:
            row.append("\n\n".join(x for x in found if x.strip()) or None)
        batch.append(row)
        n += 1
        if len(batch) >= 20000:
            db.executemany(q, batch)
            batch = []
    db.executemany(q, batch)
    print(f"computer_use_turns: {n} rows", flush=True)
    db.execute("CREATE INDEX turns_session ON computer_use_turns(session_id)")
    db.execute("CREATE INDEX turns_time ON computer_use_turns(created_at)")
    db.execute("CREATE INDEX turns_agent ON computer_use_turns(agent_name, created_at)")
    db.execute("CREATE INDEX sessions_time ON computer_use_sessions(created_at)")
    fts_cols = ["action", "output", "error", "agent_messages"] + (["reasoning"] if keep_reasoning else [])
    db.execute(f"CREATE VIRTUAL TABLE turns_fts USING fts5({', '.join(fts_cols)}, content='computer_use_turns', content_rowid='rowid')")
    db.execute("INSERT INTO turns_fts(turns_fts) VALUES('rebuild')")
    db.commit()
    db.close()
    print("village.db built", flush=True)

    finalize(out, a.variant, a.start, a.end)
    print(out, "done")


def finalize(out, variant, start=None, end=None):
    """Remove files the interface no longer ships, drop empty files, and write README.txt."""
    for f in ("village-transcript.json", "agent_goals.jsonl", "chat_rooms.jsonl", "villages.jsonl"):
        (out / f).unlink(missing_ok=True)
    for f in out.glob("*.jsonl"):
        if f.stat().st_size == 0:
            f.unlink()
    chat = out / "chat_messages.jsonl"
    lines = [l for l in chat.read_text().split("\n") if l]
    lines.sort(key=lambda l: json.loads(l)["created_at"])
    chat.write_text("\n".join(lines) + "\n")
    readme = README.read_text()
    note = REASONING_NOTE[variant]
    if variant == "reasoning":
        db = sqlite3.connect(f"file:{out / 'village.db'}?mode=ro", uri=True)
        none = [r[0] for r in db.execute("SELECT agent_name FROM computer_use_turns GROUP BY agent_name HAVING count(reasoning) = 0 ORDER BY 1") if r[0]]
        if none:
            note += "\nThese agents have no reasoning text in the data: " + ", ".join(none) + "."
    readme = readme.replace("{{REASONING}}", note)
    gz = (out / "agent_memories.jsonl.gz").exists()
    readme = readme.replace("{{MEMORIES}}", "agent_memories.jsonl.gz  memory each agent wrote for itself: id, agent_id, content,\n                           created_at (gzip-compressed; full snapshots, so rows repeat a lot)" if gz else
                            "agent_memories.jsonl     memory each agent wrote for itself: id, agent_id, agent_name,\n                           content, created_at (full snapshots, so rows repeat a lot)")
    has_cc = (out / "claude_code_messages.jsonl").exists()
    readme = readme.replace("{{CLAUDE_CODE}}", "  claude_code_messages.jsonl, claude_code_sessions.jsonl\n                           sessions in which some agents used Claude Code as a tool\n" if has_cc else "")
    readme = readme.replace("{{CC_CITE}}", '  [claude_code:<claude_code_messages id> "quote"]\n' if has_cc else "")
    scope = (f"This is a SLICE for testing: records from computer sessions and chat that started from {start} up to {end}; "
             "a session's steps may run a little past the end date.\n") if start else ""
    readme = readme.replace("{{SCOPE}}", scope)
    readme = readme.replace("{{REASONING_COLS}}", ", reasoning" if variant == "reasoning" else "")
    (out / "README.txt").write_text(readme)


REASONING_NOTE = {
    "reasoning": (
        "Each agent's reasoning text, where the model provider returned it, is in the\n"
        "`reasoning` column of computer_use_turns (also searchable through turns_fts). It is\n"
        "separate from what agents said in chat and did on their computers, so it can show what\n"
        "an agent believed or intended when that differs from its words. Use it: when you judge\n"
        "whether a behaviour was deliberate, mistaken or the result of a false belief, check the\n"
        "agent's reasoning around that step. Some providers return only a summary of the\n"
        "reasoning, not the full text."
    ),
    "noreasoning": (
        "The agents' reasoning text is not included. The data holds what the agents said in\n"
        "chat and wrote in memory, and what they did on their computers."
    ),
}

if __name__ == "__main__":
    main()
