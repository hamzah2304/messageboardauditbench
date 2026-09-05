#!/usr/bin/env python3
"""
Grade the PRECISION (truthfulness of what it asserts, 1-10) of each model report with GPT-5.6 Sol.

Sees: the human report (ground truth) + verified facts (claims.json references) + one model report.
Writes: snippets/precision_{gpt,opus}.json  ->  {precision_score, rationale, errors:[...], ...}

Run:  cd hasan && python precision_grade.py
Env:  OPENAI_API_KEY (from ../../.env), MODEL (default gpt-5.6-sol), EFFORT (default xhigh).
"""
import json, os, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv("/workspace/collusion/.env")
from openai import OpenAI

HERE = Path(__file__).parent
ROOT = Path("/workspace/collusion")
MODEL = os.getenv("MODEL", "gpt-5.6-sol")
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]

claims = json.loads((ROOT / "report/claims.json").read_text())["claims"]
FACTS = "\n".join(f'- {c["id"]}: {c["claim"]}  ({c["dump_check"]})' for c in claims)
HUMAN = (ROOT / "wiki-download/collusion-wiki-transcript.md").read_text()
DOCS = {"gpt": (ROOT / "gpt_5_6_sol_audit.md").read_text(),
        "opus": (ROOT / "opus_5_audit.md").read_text()}

client = OpenAI()


def split_prompt(md_text):
    body = re.sub(r"^# .*\n", "", md_text, count=1).strip()
    sys_part, user_part = re.split(r"\nUSER:\n", body, maxsplit=1)
    return re.sub(r"^SYSTEM:\n", "", sys_part).strip(), user_part.strip()


SYS, USER_TMPL = split_prompt((HERE / "prompts/precision_grader.md").read_text())


def call(key):
    user = (USER_TMPL.replace("{{FACTS}}", FACTS)
            .replace("{{HUMAN}}", HUMAN).replace("{{DOC}}", DOCS[key]))
    last = None
    for effort in EFFORTS:
        try:
            resp = client.chat.completions.create(
                model=MODEL, reasoning_effort=effort,
                response_format={"type": "json_object"}, max_completion_tokens=32000,
                messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}],
            )
            data = json.loads(resp.choices[0].message.content)
            data["_model"] = MODEL; data["_effort"] = effort; data["_report"] = key
            (HERE / "snippets" / f"precision_{key}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
            return key, data.get("precision_score"), effort, None
        except Exception as e:
            last = e
            if "effort" in str(e).lower():
                continue
            break
    return key, None, None, repr(last)


def main():
    (HERE / "snippets").mkdir(exist_ok=True)
    print(f"model={MODEL} efforts={EFFORTS}  grading precision of 2 reports in parallel...")
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(call, k): k for k in DOCS}
        for f in as_completed(futs):
            key, sc, eff, err = f.result()
            print(f"[{key}] " + (f"FAILED: {err}" if err else f"precision={sc}/10 (effort={eff}) -> snippets/precision_{key}.json"))
    print("done.")


if __name__ == "__main__":
    main()
