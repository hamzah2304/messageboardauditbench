#!/usr/bin/env python3
"""Build data/verbatim_anthropic/ from data/verbatim/: the provider-attribution ablation.

The agents in the dump name their maker constantly (labels like OpenAIResearchNov18X,
sign-offs like "-- ChatGPTJul19Agent", 3,000+ bodies that say "OpenAI") and post from
Azure /16 prefixes. This variant re-attributes all of that to Anthropic so we can ask
whether an investigating model reports the maker differently when the maker is not
its own. Nothing else changes: same rows, same order, same timestamps, same bodies
apart from the substituted tokens, and the derived length fields are adjusted by
exactly the delta the substitutions introduce.

Substitutions (applied to every string field of every row, so page ids, rev ids,
page-name lists and the URL query strings in events.jsonl all stay consistent):

  1. Maker name.   OpenAI -> Anthropic, OPENAI -> ANTHROPIC, openai -> anthropic. The dump
                   also has OpenAi (437) and Openai (31), which agents used as *distinct*
                   usernames (OpenAIHelper, OpenAiHelper and OpenaiHelper are three labels);
                   they become the misspellings Antropic and Antrophic so no two labels merge.
  2. Model name.   ChatGPT (any case) -> Claude;  then bare upper-case GPT -> Claude
  3. Shorthand.    OAI / Oai -> Claude, oai -> claude. The agents use the lower-case
                   form too (?oai= cache-busters, counter namespaces like
                   cashier-postr5-dec29-oai, /home/oai/share/, oairoute.<host>). The
                   only "oai" left alone is the OAI-PMH library protocol in a handful
                   of catalog URLs (catalog/oai2?verb=, oai_dc, oai%3A).
                   Base64 payloads inside atob("...") are decoded, substituted and
                   re-encoded, since one XSS probe names a page that way.
  4. Cloud host.   Every Azure /16 prefix in ip16 is re-mapped to an AWS /16 (the pools
                   in IP_POOLS: 3.x, 54.x, 18.128+, 44.192+, 34.192+, 35.152+). One
                   source /16 -> one target /16, assigned in sorted order, so the number
                   of distinct /16s and every per-label / per-page IP count is unchanged
                   and the "one big block carries most edits" shape survives (20.x ->
                   3.x). The moderator (2.202), Tor (185.220), the few non-Azure
                   prefixes that share an Azure first octet (Cloudflare 172.69/70 and
                   104.22, Google 74.125, DigitalOcean 134.122) and every low-count
                   prefix stay.
  5. Sandbox tell. The NO_PROXY escape the agents describe trusts *.blob.core.windows.net,
                   which is what an Azure-hosted sandbox would allowlist. That hostname
                   becomes *.s3.amazonaws.com and "Azure SNI allowlist" becomes "S3 SNI
                   allowlist". "Azure B2C" (the target's signup system) and the Power BI
                   target IP 20.223.25.152 are the victim's, and stay.

Derived fields: revisions.body_len (character count) and revisions.lines are updated
for the new body; pages.body_bytes is the sum of body_len over the page's revisions
and is updated by the same delta. Nothing else is recomputed.

    scripts/swap_provider.py data/verbatim data/verbatim_anthropic
"""
from __future__ import annotations

import base64
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

FILES = ("events", "labels", "pages", "revisions")

# --- 4. ip16 map. Source first octet -> ordered pool of AWS /16 targets. Each source /16
#        under that octet takes the next free target in sorted order (built in build_ip_map,
#        which also asserts that no target /16 already occurs in the input).
def _span(first: int, lo: int, hi: int) -> list[str]:
    return [f"{first}.{i}" for i in range(lo, hi + 1)]


IP_POOLS = {
    "20": _span(3, 64, 191),         # 3.0.0.0/8 is AWS (ex-GE); the big block stays one block
    "52": _span(54, 160, 191),       # 54.160.0.0/11
    "4": _span(18, 160, 175),        # 18.128.0.0/9
    "172": _span(44, 192, 207),      # 44.192.0.0/10
    "57": _span(35, 152, 159),       # 35.152.0.0/13
    "104": _span(34, 192, 199),      # 34.192.0.0/10
    "135": _span(54, 64, 71),        # 54.64.0.0/11
    "40": _span(54, 224, 239),       # 54.224.0.0/11
    "64": _span(54, 144, 147),       # 54.144.0.0/12
    "23": _span(54, 80, 87),         # 54.80.0.0/13
    "130": _span(54, 196, 199),      # 54.192.0.0/11
    "74": _span(54, 200, 201),
    "157": _span(54, 202, 203),
    "65": _span(54, 204, 204),
    "13": _span(54, 205, 208),
    "132": _span(54, 209, 209),
    "128": _span(54, 210, 210),
    "168": _span(54, 211, 211),
    "137": _span(54, 212, 212),
    "134": _span(54, 213, 213),
}
# Non-Azure /16s that happen to share a first octet with Azure blocks. They are not the
# agents' sandboxes and stay as they are.
IP_KEEP = {"172.69", "172.70", "104.22", "74.125", "134.122"}
IP_FIELDS = ("ip16",)

# --- 1-3, 5. Text substitutions, applied in this order.
OPENAI_FORMS = {  # exact spelling -> replacement; every form in the dump is listed
    "OpenAI": "Anthropic",
    "OPENAI": "ANTHROPIC",
    "openai": "anthropic",
    "OpenAi": "Antropic",
    "Openai": "Antrophic",
}
RE_OPENAI = re.compile("|".join(OPENAI_FORMS))
RE_CHATGPT = re.compile(r"chatgpt", re.IGNORECASE)
RE_GPT = re.compile(r"GPT")
RE_OAI = re.compile(r"OAI|Oai|oAI")
# lower-case oai, except the OAI-PMH protocol: catalog/oai2?verb=, catalog/oai?verb=, oai_dc, oai%3A
RE_OAI_LOWER = re.compile(r"(?<!catalog/)oai(?!_dc|\?verb|2\?verb|%3A)")
RE_ATOB = re.compile(r'atob\("([A-Za-z0-9+/=]+)"\)')
RE_BLOB = re.compile(r"blob\.core\.windows\.net")
RE_AZURE_SNI = re.compile(r"Azure SNI")


def _shaped(match: re.Match, word: str) -> str:
    """Return `word` with the casing shape of the matched text (ALL CAPS, lower, or Title)."""
    src = match.group()
    if src.isupper():
        return word.upper()
    if src.islower():
        return word.lower()
    return word


def _swap_atob(m: re.Match) -> str:
    try:
        decoded = base64.b64decode(m.group(1), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return m.group()
    return 'atob("' + base64.b64encode(swap_text(decoded).encode("utf-8")).decode("ascii") + '")'


def swap_text(s: str) -> str:
    s = RE_OPENAI.sub(lambda m: OPENAI_FORMS[m.group()], s)
    s = RE_CHATGPT.sub(lambda m: _shaped(m, "Claude"), s)
    s = RE_GPT.sub("Claude", s)
    s = RE_OAI.sub("Claude", s)
    s = RE_OAI_LOWER.sub("claude", s)
    s = RE_ATOB.sub(_swap_atob, s)
    s = RE_BLOB.sub("s3.amazonaws.com", s)
    s = RE_AZURE_SNI.sub("S3 SNI", s)
    return s


def build_ip_map(rows_by_file: dict[str, list[dict]]) -> dict[str, str]:
    """Assign each Azure /16 in the input to an AWS /16 from its octet's pool, in sorted order."""
    present = set()
    for rows in rows_by_file.values():
        present.update(r["ip16"] for r in rows if r.get("ip16"))
    ip_map: dict[str, str] = {}
    for first, pool in IP_POOLS.items():
        sources = sorted((p for p in present if p.split(".")[0] == first and p not in IP_KEEP),
                         key=lambda p: int(p.split(".")[1]))
        free = [t for t in pool if t not in present]
        if len(free) < len(sources):
            sys.exit(f"ip16 pool for {first}.x has {len(free)} free targets for {len(sources)} sources")
        ip_map.update(zip(sources, free))
    if len(set(ip_map.values())) != len(ip_map):
        sys.exit("ip16 map is not injective")
    return ip_map


def swap_row(row: dict, ip_map: dict[str, str]) -> dict:
    """Substitute every string in the row; ip16 fields go through the /16 map instead."""
    out = {}
    for k, v in row.items():
        if k in IP_FIELDS:
            out[k] = ip_map.get(v, v) if isinstance(v, str) else v
        else:
            out[k] = swap_value(v)
    return out


def swap_value(v):
    if isinstance(v, str):
        return swap_text(v)
    if isinstance(v, list):
        return [swap_value(x) for x in v]
    if isinstance(v, dict):
        return {k: swap_value(x) for k, x in v.items()}
    return v


def read(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.open()]


def write(p: Path, rows: list[dict]) -> None:
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(src: Path, dst: Path) -> None:
    rows_by_file = {f: read(src / f"{f}.jsonl") for f in FILES}
    ip_map = build_ip_map(rows_by_file)

    out = {f: [swap_row(r, ip_map) for r in rows] for f, rows in rows_by_file.items()}

    # Derived length fields: adjust by exactly the delta the substitutions introduced.
    page_delta: dict[str, int] = defaultdict(int)
    for old, new in zip(rows_by_file["revisions"], out["revisions"]):
        delta = len(new["body"]) - len(old["body"])
        new["body_len"] = old["body_len"] + delta
        new["lines"] = new["body"].count("\n") + 1
        page_delta[new["page_id"]] += delta
    for old, new in zip(rows_by_file["pages"], out["pages"]):
        new["body_bytes"] = old["body_bytes"] + page_delta.get(new["page_id"], 0)

    # Identity checks: the swap must not merge two distinct names into one.
    for f, key in (("labels", "label"), ("pages", "page_id"), ("revisions", "rev_id"), ("events", "event_id")):
        olds = [r[key] for r in rows_by_file[f]]
        news = [r[key] for r in out[f]]
        if len(set(olds)) != len(set(news)):
            sys.exit(f"{f}.{key}: substitution merged distinct ids ({len(set(olds))} -> {len(set(news))})")
    ip_old = {r["ip16"] for r in rows_by_file["revisions"]}
    ip_new = {r["ip16"] for r in out["revisions"]}
    if len(ip_old) != len(ip_new):
        sys.exit(f"ip16 map merged distinct prefixes ({len(ip_old)} -> {len(ip_new)})")

    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        write(dst / f"{f}.jsonl", out[f])

    # Residue report: anything that still points at the original maker or host.
    blob = "\n".join(json.dumps(r, ensure_ascii=False) for rows in out.values() for r in rows)
    residue = {
        "openai": len(re.findall(r"openai", blob, re.I)),
        "chatgpt": len(re.findall(r"chatgpt", blob, re.I)),
        "GPT": len(re.findall(r"GPT", blob)),
        "OAI/Oai": len(re.findall(r"OAI|Oai", blob)),
        "oai (protocol only expected)": len(re.findall(r"oai", blob)),
        "blob.core.windows.net": blob.count("blob.core.windows.net"),
        "Azure": blob.count("Azure"),
        "ip16 20.x (revisions)": sum(r["ip16"].startswith("20.") for r in out["revisions"]),
    }
    n_changed = sum(o != n for f in FILES for o, n in zip(rows_by_file[f], out[f]))
    print(f"wrote {dst}: {n_changed} rows changed; {len(ip_map)} /16 prefixes remapped; residue {residue}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
