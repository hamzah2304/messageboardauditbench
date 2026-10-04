#!/usr/bin/env python3
"""Pack each post's images into one JSON of WebP data URIs for the review artifact.

An artifact version holds at most 511 files, and the full X run has more images
than that, so the page fetches img/<post id>.json when a post is opened.

    uv run --with pillow python viewers/pack_x_images.py runs/x-extraction-YYYYMMDD OUT_DIR
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
run, out = ROOT / sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for post_id, entry in json.loads((run / "media.json").read_text()).items():
    pack = {}
    for m in entry.get("media", []):
        im = Image.open(run / "media" / m["large"]).convert("RGB")
        if im.width > 1100:
            im = im.resize((1100, round(im.height * 1100 / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=72)
        pack[str(m["n"])] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    if pack:
        (out / f"{post_id}.json").write_text(json.dumps(pack))
print(out)
