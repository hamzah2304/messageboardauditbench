#!/usr/bin/env python3
"""
Use GPT-5.6 Sol to extract, per claim, the best VERBATIM snippet (+ context + highlight)
from three documents, in one context-window call each, run in parallel:

  human -> the human collusion.wiki report      (prompts/human_report.md)
  gpt   -> the GPT-5.6 Sol model report          (prompts/model_report_gpt.md)
  opus  -> the Claude Opus 5 model report         (prompts/model_report_opus.md)

Outputs snippets/{human,gpt,opus}.json  ->  {"claims":[{id,present,quote,context,highlight}, ...]}

Run:  cd hasan && python extract_snippets.py            (reads ../../.env)
Env:  OPENAI_API_KEY (required), OPENAI_BASE_URL (optional), MODEL (default gpt-5.6-sol),
      EFFORT (default xhigh; falls back to high/medium if the API rejects it).
"""
import json, os, re, sys
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
CLAIMS_BLOCK = "\n".join(
    f'{c["id"]}: {c["claim"]}  [reference: {c["dump_check"]}]' for c in claims
)

DOCS = {
    "human": ("prompts/human_report.md", (ROOT / "wiki-download/collusion-wiki-transcript.md").read_text()),
    "gpt":   ("prompts/model_report_gpt.md", (ROOT / "gpt_5_6_sol_audit.md").read_text()),
    "opus":  ("prompts/model_report_opus.md", (ROOT / "opus_5_audit.md").read_text()),
}

client = OpenAI()  # picks up OPENAI_API_KEY / OPENAI_BASE_URL from env


def split_prompt(md_text):
    """Prompt files hold 'SYSTEM:' and 'USER:' sections; return (system, user_template)."""
    body = re.sub(r"^# .*\n", "", md_text, count=1).strip()
    sys_part, user_part = re.split(r"\nUSER:\n", body, maxsplit=1)
    sys_part = re.sub(r"^SYSTEM:\n", "", sys_part).strip()
    return sys_part, user_part.strip()


def call(key):
    prompt_file, doc = DOCS[key]
    system, user_tmpl = split_prompt((HERE / prompt_file).read_text())
    user = user_tmpl.replace("{{CLAIMS}}", CLAIMS_BLOCK).replace("{{DOC}}", doc)
    last_err = None
    for effort in EFFORTS:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                reasoning_effort=effort,
                response_format={"type": "json_object"},
                max_completion_tokens=64000,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)
            arr = data.get("claims", data if isinstance(data, list) else [])
            byid = {r["id"]: r for r in arr if isinstance(r, dict) and "id" in r}
            out = {"model": MODEL, "effort": effort, "doc": key, "claims": byid}
            (HERE / "snippets" / f"{key}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
            return key, len(byid), effort, None
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "effort" in msg and ("invalid" in msg or "unsupported" in msg or "400" in msg):
                continue  # try next effort level
            # non-effort error: stop retrying efforts
            break
    return key, 0, None, repr(last_err)


def main():
    (HERE / "snippets").mkdir(exist_ok=True)
    print(f"model={MODEL} efforts={EFFORTS}  running 3 extractions in parallel...")
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(call, k): k for k in DOCS}
        for f in as_completed(futs):
            key, n, effort, err = f.result()
            if err:
                print(f"[{key}] FAILED: {err}")
            else:
                print(f"[{key}] ok: {n}/68 claims  (effort={effort}) -> snippets/{key}.json")
    print("done.")


if __name__ == "__main__":
    main()
