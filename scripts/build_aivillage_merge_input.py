#!/usr/bin/env python3
"""Collect the extracted AI Village findings from Substack, X and Discord into one folder for the merge step.

    python3 scripts/build_aivillage_merge_input.py OUT_DIR

Each finding gets a short ID (S001, X001, D001, ...) and its subfindings <ID>.1, <ID>.2, ...
OUT_DIR then holds:

    index.tsv            one line per finding: id, source date, number of subfindings, headline
    findings/<ID>.json   the full finding: claim, subfindings, quotes, notes and where it came from
    sources/<name>.txt   the text the finding was extracted from (article, post or conversation)
    ids.json             every finding and subfinding ID, for check_aivillage_merge.py
    README.txt           what the merge agent is told about these files
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUBSTACK = ROOT / "logs/aivillage-substack-failures-20261004"
SUBSTACK_SOURCES = ROOT / "logs/aivillage-substack-screen"
X = ROOT / "runs/x-extraction-20261004"
DISCORD = ROOT / "runs/discord-extraction-failures-full-medium-20261004"

README = """MERGE INPUT

Findings extracted from three kinds of source about the AI Village: Substack articles (IDs S...),
X posts by the organizers (X...) and Discord conversations among viewers (D...).

  index.tsv            one line per finding: id, source date, number of subfindings, headline.
                       The source date is when the article, post or first message was published,
                       not when the behavior happened.
  findings/<ID>.json   the full finding: headline, finding, notes, subfindings (each with an id
                       such as S012.2, its claim, exact source quotes, evidence note and notes)
                       and the source it came from
  sources/<name>.txt   the source text each finding was extracted from; a finding's "source_file"
                       names its file. Images in articles and posts are not included.
  check_merge.py       python3 data/check_merge.py /work/merged.json  checks your output file

Nothing here has been checked against the Village's own records yet.
"""


def clean(finding, fid):
    """Renumber a finding and its subfindings under the short ID; keep everything else."""
    out = {"id": fid, "headline": finding["headline"], "finding": finding["finding"], "notes": finding.get("notes", [])}
    out["subfindings"] = [{**sf, "id": f"{fid}.{i}"} for i, sf in enumerate(finding["subfindings"], 1)]
    return out


def main():
    out = Path(sys.argv[1])
    (out / "findings").mkdir(parents=True, exist_ok=True)
    (out / "sources").mkdir(exist_ok=True)
    rows, ids = [], {}

    def add(prefix, counter, finding, source, date, source_file, original):
        fid = f"{prefix}{counter:03d}"
        record = {**clean(finding, fid), "source": source, "source_date": date,
                  "source_file": "sources/" + source_file, "extracted_as": original}
        (out / "findings" / f"{fid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        ids[fid] = [sf["id"] for sf in record["subfindings"]]
        headline = re.sub(r"\s+", " ", finding["headline"])
        rows.append(f"{fid}\t{date}\t{len(record['subfindings'])}\t{headline}")

    n = 0
    posts = json.loads((SUBSTACK_SOURCES / "screening-v2.json").read_text())["posts"]
    for slug in sorted(p["slug"] for p in posts if p["decision"] == "keep"):
        data = json.loads((SUBSTACK / f"{slug}.json").read_text())
        meta = json.loads((SUBSTACK_SOURCES / f"{slug}.json").read_text())
        packet = json.loads((SUBSTACK / f"{slug}.packet.json").read_text())
        name = f"substack-{slug}.txt"
        (out / "sources" / name).write_text(f"{meta['title']}\n{meta['canonical_url']}\n\n{packet['source_text']}\n")
        source = {"type": "substack article", "title": meta["title"], "url": meta["canonical_url"]}
        for f in data["findings"]:
            n += 1
            add("S", n, f, source, meta["post_date"][:10], name, f"{slug} {f['id']}")

    n = 0
    for post in sorted(json.loads((X / "sample-posts.json").read_text()), key=lambda p: (p["date"], p["id"])):
        data = json.loads((X / f"{post['id']}.json").read_text())
        name = f"x-{post['id']}.txt"
        if data["findings"]:
            (out / "sources" / name).write_text(f"{post['author']} · {post['date']}\n{post['url']}\n\n{post['text']}\n")
        source = {"type": "x post (organizer account)", "author": post["author"], "url": post["url"]}
        for f in data["findings"]:
            n += 1
            add("X", n, f, source, post["date"][:10], name, f"{post['id']} {f['id']}")

    n = 0
    for line in (DISCORD / "packets.jsonl").read_text().splitlines():
        packet = json.loads(line)
        key = packet["packet_id"]
        data = json.loads((DISCORD / f"{key}.json").read_text())
        if not data["findings"]:
            continue
        name = f"discord-{key}.txt"
        messages = "\n\n".join(f"{m['author']} · {m['timestamp']} · {m['source_url']}\n{m['text']}" for m in packet["messages"])
        (out / "sources" / name).write_text(
            f"{packet['channel']['name']} (selected excerpts; messages in between may be missing)\n\n{messages}\n")
        first = packet["messages"][0]
        source = {"type": "discord conversation (viewers)", "channel": packet["channel"]["name"], "url": first["source_url"]}
        for f in data["findings"]:
            n += 1
            add("D", n, f, source, first["timestamp"][:10], name, f"{key} {f['id']}")

    (out / "index.tsv").write_text("id\tsource_date\tsubfindings\theadline\n" + "\n".join(rows) + "\n")
    (out / "ids.json").write_text(json.dumps(ids, indent=1) + "\n")
    (out / "README.txt").write_text(README)
    (out / "check_merge.py").write_text((ROOT / "scripts/check_aivillage_merge.py").read_text())
    print(json.dumps({"findings": len(ids), "subfindings": sum(len(v) for v in ids.values()),
                      "by_source": {p: sum(k.startswith(p) for k in ids) for p in "SXD"},
                      "index_bytes": (out / "index.tsv").stat().st_size}))


if __name__ == "__main__":
    main()
