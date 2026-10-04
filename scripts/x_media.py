#!/usr/bin/env python3
"""Fetch the photos (and video thumbnails) for X posts in an extraction run.

Reads <run>/sample-posts.json, fetches each thread from api.fxtwitter.com
(unofficial; it needs a browser-like user agent), matches the thread's tweets to
the post's `---`-separated parts in order, and downloads each part's media:
`name=large` (up to 2048 px) for the model, `name=medium` for the review page.
Writes <run>/media.json; threads and files are cached, so reruns only fetch
what is missing. Tweets after the last exported part (usually a "watch the
agents live" plug) are ignored.

    uv run python scripts/x_media.py runs/x-extraction-sample-YYYYMMDD
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def thread(run, post):
    path = run / "threads" / f"{post['id']}.json"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        data = {"error": None}
        for kind in ("thread", "status"):
            try:
                data = json.loads(fetch(f"https://api.fxtwitter.com/2/{kind}/{post['id']}"))
                break
            except urllib.error.HTTPError as e:
                data = {"error": e.code}
        path.write_text(json.dumps(data))
        time.sleep(1)
    data = json.loads(path.read_text())
    if data.get("error"):
        return None
    tweets = data.get("thread") or [data["status"]]
    return [t for t in tweets if (t.get("author") or {}).get("screen_name", "").lower() == post["author"].lower()]


def sized(url, name):
    base = url.split("?")[0]
    return f"{base}?name={name}"


def main():
    run = ROOT / sys.argv[1]
    (run / "media").mkdir(exist_ok=True)
    manifest = {}
    for post in json.loads((run / "sample-posts.json").read_text()):
        tweets = thread(run, post)
        if tweets is None:
            manifest[post["id"]] = {"status": "post unavailable on X", "media": []}
            continue
        parts = post["text"].split("\n---\n")
        items, n = [], 0
        for part, tweet in enumerate(tweets[: len(parts)], 1):
            for m in (tweet.get("media") or {}).get("all", []):
                n += 1
                src = m["url"] if m["type"] == "photo" else m.get("thumbnail_url")
                if not src:
                    continue
                item = {"n": n, "part": part, "type": m["type"], "tweet_id": tweet["id"], "source_url": m["url"],
                        "duration_s": m.get("duration"), "alt": m.get("altText") or m.get("alt_text")}
                for size in ("large", "medium"):
                    f = run / "media" / f"{post['id']}-{n}-{size}.jpg"
                    if not f.exists():
                        f.write_bytes(fetch(sized(src, size)))
                    item[size] = f.name
                items.append(item)
        manifest[post["id"]] = {"status": "ok", "thread_tweets": len(tweets), "parts": len(parts), "media": items}
        print(post["date"], post["id"], f"{len(items)} media")
    (run / "media.json").write_text(json.dumps(manifest, indent=1) + "\n")


if __name__ == "__main__":
    main()
