#!/usr/bin/env python3
"""GPT-5.6 Sol writes a reply to every coverage-review comment (covered / gap / partial).
Output: snippets/comment_replies.json -> {comment_id: {verdict, claim_ids, text}}.
IDs match build_combined_coverage.py's scheme (author:ts:index)."""
import re, json, glob
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("/workspace/collusion/.env")
from openai import OpenAI
import os

HERE = Path("/workspace/collusion/messageboardauditbench/hasan")
ROOT = Path("/workspace/collusion")
MODEL = os.getenv("MODEL", "gpt-5.6-sol")
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]
client = OpenAI()

GENERIC = {"coverage", "review", "hackathon", "combined", "export", "json", "data", "final", "v1", "v2"}
def author_of(p):
    toks = [t for t in re.split(r"[_\-.]", Path(p).stem.lower()) if t and t not in GENERIC]
    return toks[0] if toks else Path(p).stem.lower()

def is_review(p):
    try:
        d = json.loads(Path(p).read_text())
        return isinstance(d, dict) and isinstance(d.get("comments"), list) and "collusion.wiki" in str(d.get("report", ""))
    except Exception:
        return False

merged = []
for p in sorted(glob.glob(str(HERE / "*.json"))):
    if Path(p).name in ("coverage_data.json", "validation_data.json", "coverage_combined.json"):
        continue
    if not is_review(p):
        continue
    a = author_of(p)
    d = json.loads(Path(p).read_text())
    for j, c in enumerate(d.get("comments", [])):
        merged.append({"id": f"{a}:{c.get('ts', j)}:{j}", "author": a, "type": c.get("type", "note"),
                       "quote": c.get("quote", ""), "note": c.get("note", ""), "claim": c.get("claim")})

claims = json.loads((ROOT / "report/claims.json").read_text())["claims"]
CLAIMS = "\n".join(f'{c["id"]}: {c["claim"]}' for c in claims)
COMMENTS = "\n".join(
    f'[{m["id"]}] type={m["type"]} linked={m["claim"] or "-"} | quote: {m["quote"][:220]} | note: {m["note"][:220]}'
    for m in merged)

sysmsg, user_tmpl = (lambda md: (lambda b: (re.sub(r"^SYSTEM:\n", "", b[0]).strip(), b[1].strip()))(
    re.split(r"\nUSER:\n", re.sub(r"^# .*\n", "", md, count=1).strip(), maxsplit=1)))((HERE / "prompts/reply_to_comments.md").read_text())
user = user_tmpl.replace("{{CLAIMS}}", CLAIMS).replace("{{COMMENTS}}", COMMENTS)

print(f"{len(merged)} comments -> {MODEL}")
last = None
for eff in EFFORTS:
    try:
        r = client.chat.completions.create(model=MODEL, reasoning_effort=eff,
            response_format={"type": "json_object"}, max_completion_tokens=32000,
            messages=[{"role": "system", "content": sysmsg}, {"role": "user", "content": user}])
        data = json.loads(r.choices[0].message.content)
        arr = data.get("replies", data if isinstance(data, list) else [])
        byid = {x["id"]: x for x in arr if isinstance(x, dict) and "id" in x}
        (HERE / "snippets" / "comment_replies.json").write_text(json.dumps({"model": MODEL, "effort": eff, "replies": byid}, indent=1, ensure_ascii=False))
        print(f"ok: {len(byid)}/{len(merged)} replies (effort={eff}) -> snippets/comment_replies.json")
        break
    except Exception as e:
        last = e
        if "effort" in str(e).lower():
            continue
        raise
else:
    raise RuntimeError(f"failed: {last}")
