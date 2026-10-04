"""Extract screened AI Village articles with image-aware Responses API calls.

Run with uv run --no-project --with openai --with python-dotenv --with pillow.
The output directory must contain the approved extraction-prompt.md snapshot.
Requests retain their selected model and effort; partial outputs are archived,
validated, and never presented as completed extractions. Re-running skips saved
validated results. A stored raw response can be repaired locally without another
paid request when only its serialization needs correction.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewers"))
from build_aivillage_findings_review import Article, download_image


class SourceText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"p", "h1", "h2", "h3", "li", "blockquote", "figure", "br"}:
            self.parts.append("\n")
        if tag == "img":
            self.parts.append(f"\n[Source image {attrs['data-source-image']}]\n")
        if tag == "a":
            self.parts.append(" [link: " + attrs.get("href", "") + "] ")

    def handle_data(self, data):
        self.parts.append(data)


TRANSPORT = """
Transport instruction: preserve the extraction criteria above, but serialize the
requested Markdown content as one JSON object so the review UI can display it.
Use this structure (include all fields; empty lists/strings when unnecessary):
{
 "source": {"title": "...", "url": "...", "source_type": "article", "coverage": "..."},
 "findings": [{"id": "F1", "headline": "...", "finding": "...", "notes": [],
  "subfindings": [{"id": "F1.1", "claim": "...", "notes": [],
   "source_support": [{"quote": "exact source quote", "location": "section and/or image number",
    "url": "article or embedded post URL", "source_kind": "organizer account|community observation|agent statement|generated summary|unknown",
    "image_number": null, "image_url": null, "record_links": []}],
   "log_evidence": "not yet verified", "evidence_note": "..."}]}],
 "excluded_source_claims": [{"claim": "...", "reason": "..."}],
 "source_limits": [],
 "image_review": {"inspected": 0, "total": 0, "unreadable": [],
  "images": [{"number": 1, "note": "brief account of the visible evidence", "unreadable": false}]}
}
Use the supplied image manifest for numbering and URLs. Every image must have
an inspection entry, including decorative or irrelevant images. Cite the
original image number when reading a numbered tile. Do not claim to have read
missing images or linked pages. Embedded posts supplied in the article are
available evidence; other parts of their threads may be missing. Do not use
thread headings alone to reconstruct missing evidence. Notes are optional
scoring context, not additional claims deserving credit. Keep subfindings
independently creditable, without fragmenting the context needed to explain one
observation. Frozen logs have not been provided: all log evidence stays unverified.
"""


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def markdown(data):
    out = ["# " + data["source"]["title"], data["source"]["url"], ""]
    for f in data["findings"]:
        out.extend([f"## {f['id']} — {f['headline']}", f["finding"], ""])
        for note in f.get("notes", []):
            out.append("Note: " + note)
        for sf in f["subfindings"]:
            out.extend([f"### {sf['id']}", sf["claim"], ""])
            for support in sf["source_support"]:
                out.extend(
                    [
                        "> " + support["quote"].replace("\n", "\n> "),
                        support["location"] + " · " + support["url"],
                    ]
                )
            out.extend(["Log evidence: " + sf["log_evidence"], sf["evidence_note"]])
            for note in sf.get("notes", []):
                out.append("Note: " + note)
            out.append("")
    out.extend(["## Source limits", *data["source_limits"], "", "## Excluded claims"])
    for item in data["excluded_source_claims"]:
        out.append("- " + item["claim"] + ": " + item["reason"])
    return "\n\n".join(out) + "\n"


def image_parts(path, number):
    """Send original pixels in overlapping tiles, avoiding tiny text after resizing."""
    with Image.open(path) as original:
        original.load()
        width, height = original.size
        tiles = []
        for top in range(0, height, 1500):
            for left in range(0, width, 1500):
                box = (left, top, min(left + 1600, width), min(top + 1600, height))
                cropped = original.crop(box).convert("RGB")
                buffer = io.BytesIO()
                cropped.save(buffer, format="PNG")
                tiles.extend(
                    [
                        {
                            "type": "input_text",
                            "text": f"Source image {number}, pixel crop {box} of original {width}×{height}.",
                        },
                        {
                            "type": "input_image",
                            "detail": "high",
                            "image_url": "data:image/png;base64,"
                            + base64.b64encode(buffer.getvalue()).decode(),
                        },
                    ]
                )
        return tiles, {"width": width, "height": height, "tiles": len(tiles) // 2}


def validate(data, source, manifest):
    if data["source"]["url"] != source["canonical_url"]:
        raise ValueError("Source URL changed")
    seen = set()
    for f in data["findings"]:
        if f["id"] in seen:
            raise ValueError("Duplicate finding ID")
        seen.add(f["id"])
        for sf in f["subfindings"]:
            if sf["id"] in seen or not sf["id"].startswith(f["id"] + "."):
                raise ValueError("Duplicate or misplaced subfinding ID")
            seen.add(sf["id"])
            if sf["log_evidence"] != "not yet verified":
                raise ValueError("Invented log verification")
            if not sf["source_support"]:
                raise ValueError("Subfinding lacks source evidence")
            for support in sf["source_support"]:
                num = support.get("image_number")
                if num is not None:
                    match = next((m for m in manifest if m["number"] == num), None)
                    if not match or support.get("image_url") != match["url"]:
                        raise ValueError("Invalid image citation")
    review = data["image_review"]
    expected = {m["number"] for m in manifest if not m.get("error")}
    actual = [entry["number"] for entry in review["images"]]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Missing or duplicate image inspection entries")
    if review["total"] != len(manifest) or review["inspected"] != len(expected):
        raise ValueError("Image coverage count mismatch")


def run_post(post, args, prompt):
    slug = post["slug"]
    result_path = args.output / f"{slug}.json"
    if result_path.exists():
        saved = json.loads(result_path.read_text())
        run = saved["run"]
        if (
            run["model"] != args.model
            or run["reasoning"]["effort"] != args.effort
            or run["prompt_sha256"] != hashlib.sha256(prompt.encode()).hexdigest()
        ):
            raise ValueError(
                "Saved result uses different settings; choose a new output directory"
            )
        return {"slug": slug, "status": "cached"}
    source = json.loads((args.input / f"{slug}.json").read_text())
    parsed = Article(slug)
    parsed.feed(source["body_html"])
    sanitized_html = "".join(parsed.parts)
    text = SourceText()
    text.feed(sanitized_html)
    source_text = "".join(text.parts)

    # Keep per-occurrence image numbers even when an image is reused.
    class ImageList(HTMLParser):
        def __init__(self):
            super().__init__()
            self.items = []

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                self.items.append(dict(attrs))

    image_list = ImageList()
    image_list.feed(sanitized_html)
    reverse = {name: url for url, name in parsed.images.items()}
    manifest = []
    for item in image_list.items:
        url = reverse[item["src"]]
        error = download_image((url, item["src"]), args.output)
        manifest.append(
            {
                "number": int(item["data-source-image"]),
                "url": url,
                "path": item["src"],
                **({"error": error["error"]} if error else {}),
            }
        )
    content = []
    for image in manifest:
        if image.get("error"):
            continue
        tiles, info = image_parts(args.output / image["path"], image["number"])
        image.update(info)
        content.extend(tiles)
    packet = {
        "title": source["title"],
        "url": source["canonical_url"],
        "source_text": source_text,
        "images": manifest,
        "prefilter": {
            "mode": "human-reviewed source screening",
            "decision": post["decision"],
        },
    }
    write_json(args.output / f"{slug}.packet.json", packet)
    instructions = prompt.replace("{{SOURCE_TYPE}}", "article").replace(
        "{{TASK_STAGE}}", "extract"
    )
    instructions = instructions.replace("{{PREFILTER_MODE}}", "none").replace(
        "{{PREFILTER_CONTEXT}}", "Whole selected article; no within-article filtering."
    )
    instructions = instructions.replace(
        "{{SOURCE_TITLE_AND_URL}}", "Provided in source packet."
    ).replace("{{SOURCE_TEXT}}", "Provided in source packet.")
    instructions = instructions.replace(
        "{{FROZEN_EVIDENCE_DESCRIPTION}}",
        "Chat, computer-use actions and outputs, memories, session summaries; optionally reasoning traces; April 2025–September 2026. No screenshots. Exact frozen logs are not supplied for extraction.",
    )
    (args.output / f"{slug}.instructions.txt").write_text(instructions + TRANSPORT)
    content.insert(
        0,
        {
            "type": "input_text",
            "text": "Source packet for JSON extraction:\n"
            + json.dumps(packet, ensure_ascii=False),
        },
    )
    request_meta = {
        "model": args.model,
        "reasoning": {"effort": args.effort},
        "max_output_tokens": 40000,
        "image_detail": "high",
        "source_images": len(manifest),
        "submitted_tiles": sum(m.get("tiles", 0) for m in manifest),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(args.output / f"{slug}.request.json", request_meta)
    print(
        json.dumps(
            {
                "slug": slug,
                "status": "started",
                "images": len(manifest),
                "tiles": request_meta["submitted_tiles"],
            }
        ),
        flush=True,
    )
    client = OpenAI(timeout=1800, max_retries=2)
    response = client.responses.create(
        model=args.model,
        reasoning={"effort": args.effort},
        instructions=instructions + TRANSPORT,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_object"}},
        max_output_tokens=40000,
        store=False,
    )
    write_json(args.output / f"{slug}.response.json", response.model_dump(mode="json"))
    if response.status != "completed":
        raise ValueError(f"Response status: {response.status}")
    data = json.loads(response.output_text)
    validate(data, source, manifest)
    data["run"] = {
        **request_meta,
        "response_id": response.id,
        "usage": response.usage.model_dump(mode="json"),
    }
    write_json(result_path, data)
    (args.output / f"{slug}.md").write_text(markdown(data))
    return {
        "slug": slug,
        "status": "complete",
        "findings": len(data["findings"]),
        "subfindings": sum(len(f["subfindings"]) for f in data["findings"]),
        "usage": data["run"]["usage"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--effort", default="high", choices=["high"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--slug", action="append")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "images").mkdir(exist_ok=True)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    prompt = (args.output / "extraction-prompt.md").read_text()
    (args.output / "transport-instruction.txt").write_text(TRANSPORT)
    posts = [
        p
        for p in json.loads((args.input / "screening-v2.json").read_text())["posts"]
        if p["decision"] == "keep" and (not args.slug or p["slug"] in args.slug)
    ]
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_post, post, args, prompt): post for post in posts}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 — archive failures and continue independent posts
                result = {
                    "slug": futures[future]["slug"],
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            results.append(result)
            print(json.dumps(result), flush=True)
            write_json(
                args.output / "status.json",
                {
                    "model": args.model,
                    "effort": args.effort,
                    "total": len(posts),
                    "finished": len(results),
                    "results": results,
                },
            )
    if any(r["status"] == "error" for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
