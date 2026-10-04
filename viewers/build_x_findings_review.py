#!/usr/bin/env python3
"""Build the X findings review artifact page from an extraction run.

    uv run python viewers/build_x_findings_review.py runs/x-extraction-YYYYMMDD OUT.html

Images load from img/<post id>.json, built by viewers/pack_x_images.py and
published alongside the page.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run, out = ROOT / sys.argv[1], Path(sys.argv[2])
media = json.loads((run / "media.json").read_text()) if (run / "media.json").exists() else {}
selection = json.loads((run / "selection.json").read_text())
hand = set(selection.get("hand_picked", []))
posts = []
for p in json.loads((run / "sample-posts.json").read_text()):
    ex = json.loads((run / f"{p['id']}.json").read_text())
    ex.pop("run", None)
    posts.append({"id": p["id"], "date": p["date"], "author": p["author"], "url": p["url"], "text": p["text"],
                  "hand_picked": p["id"] in hand, "extraction": ex,
                  "media_status": media.get(p["id"], {}).get("status", "ok"),
                  "media": [{"n": m["n"], "part": m["part"], "type": m["type"], "duration_s": m.get("duration_s"),
                             "alt": m.get("alt")}
                            for m in media.get(p["id"], {}).get("media", [])]})
summary = json.loads((run / "summary.json").read_text())
data = {"model": "GPT-6.1 Sol", "effort": summary["reasoning_effort"], "posts": posts,
        "prompt_url": "https://docs.google.com/document/d/18990mApAhiePaBvboLdEJNPudffXaLdGaIVNUH58xSE/edit?tab=t.63e1fm9fhnrm"}
# "</" would close the script element early; JSON allows the escaped form.
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
page = (ROOT / "viewers/x_findings_review.template.html").read_text().replace("__DATA__", blob)
out.write_text(page)
print(out, len(page))
