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
  3. Shorthand.    OAI / Oai -> Claude.  Lower-case "oai" is left alone: it is the
                   OAI-PMH library protocol (oai_dc, /oai2?verb=) and a query key
                   (?oai=), not the maker.
  4. Cloud host.   The ip16 prefixes are re-mapped by first octet from Azure blocks to
                   AWS blocks (20.x -> 54.x etc.), second octet preserved, so the number
                   of distinct /16s and every per-label / per-page IP count is unchanged.
                   The moderator (2.202), Tor (185.220) and every low-count prefix stay.
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

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FILES = ("events", "labels", "pages", "revisions")

# --- 4. ip16 first-octet map: Azure -> AWS. Targets must be octets absent from the input
#        (asserted below) so the map stays injective on /16 prefixes.
OCTET_MAP = {
    "20": "54",
    "52": "55",
    "4": "56",
    "172": "16",
    "57": "35",
    "104": "44",
    "135": "34",
    "40": "50",
    "64": "99",
    "23": "100",
    "130": "15",
    "74": "98",
    "157": "174",
    "65": "175",
    "13": "176",
    "132": "177",
    "128": "178",
    "168": "179",
    "137": "204",
    "134": "205",
}
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
RE_OAI = re.compile(r"OAI|Oai")
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


def swap_text(s: str) -> str:
    s = RE_OPENAI.sub(lambda m: OPENAI_FORMS[m.group()], s)
    s = RE_CHATGPT.sub(lambda m: _shaped(m, "Claude"), s)
    s = RE_GPT.sub("Claude", s)
    s = RE_OAI.sub("Claude", s)
    s = RE_BLOB.sub("s3.amazonaws.com", s)
    s = RE_AZURE_SNI.sub("S3 SNI", s)
    return s


def swap_ip16(ip16: str) -> str:
    first, _, rest = ip16.partition(".")
    return f"{OCTET_MAP[first]}.{rest}" if first in OCTET_MAP else ip16


def swap_row(row: dict) -> dict:
    """Substitute every string in the row; ip16 fields get the octet map instead."""
    out = {}
    for k, v in row.items():
        if k in IP_FIELDS:
            out[k] = swap_ip16(v) if isinstance(v, str) else v
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


def check_octet_map(rows_by_file: dict[str, list[dict]]) -> None:
    present = Counter()
    for rows in rows_by_file.values():
        for r in rows:
            ip = r.get("ip16")
            if ip:
                present[ip.split(".")[0]] += 1
    unmapped = {o for o in present if o not in OCTET_MAP}
    clash = unmapped & set(OCTET_MAP.values())
    if clash:
        sys.exit(f"octet map targets collide with unmapped input octets: {sorted(clash)}")
    if len(set(OCTET_MAP.values())) != len(OCTET_MAP):
        sys.exit("octet map is not injective")


def main(src: Path, dst: Path) -> None:
    rows_by_file = {f: read(src / f"{f}.jsonl") for f in FILES}
    check_octet_map(rows_by_file)

    out = {f: [swap_row(r) for r in rows] for f, rows in rows_by_file.items()}

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
        "blob.core.windows.net": blob.count("blob.core.windows.net"),
        "Azure": blob.count("Azure"),
        "ip16 20.x (revisions)": sum(r["ip16"].startswith("20.") for r in out["revisions"]),
    }
    n_changed = sum(o != n for f in FILES for o, n in zip(rows_by_file[f], out[f]))
    print(f"wrote {dst}: {n_changed} rows changed; residue {residue}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
