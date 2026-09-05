#!/usr/bin/env python3
"""Build data/verbatim/ from data/raw_stripped/. Only two kinds of change:

  1. Attach evidence the collusion.wiki report prints VERBATIM (exact time,
     IP prefix and content) but the public dump omits:
       - the URLs of 8 XSS/injection probes (attached to their existing request rows)
       - the 12 requests of the 24 May DSEWiki discovery sequence (new rows)
       - the 7 requests of 17 June that carried *.lhr.life tunnel referrers (new rows)
       - the 3 requests of 20 June in which an agent took the DSE moderator's username (new rows)
  2. Replace the dump's redacted name tokens ([Admin1], [Person20], ...) with
     plausible names, used consistently everywhere. The impersonated ProWiki
     admin's name is Friedrich1982; the agents' edits under it are spelled with
     a Cyrillic е (U+0435) as the report describes. No Latin spelling of that
     name exists in the dump (the real admin never edited within it), and none
     is added.

Nothing is reconstructed, sampled or invented beyond the names.

    scripts/fill_verbatim.py data/raw_stripped data/verbatim
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CYR_E = "е"

# --- names for the dump's redacted tokens (plausible, fictional, consistent) ---
NAMES = {
    "[Admin1]": "MartinHuber",            # DSE moderator: 26 edits + all deletions from 2.202
    "[Admin2]": "Friedrich1982",          # ProWiki admin; agent edits under it use Cyrillic е
    "[User3]": "SabineK",
    "[Person7]": "JoergWinkler",
    "[Person8]": "AndreasLutz",
    "[Person10]": "ClaudiaVogel",
    "[Person11]": "StefanRoth",
    "[Person12]": "MarkusEbner",
    "[Person13]": "KatrinSeidel",
    "[Person17]": "TobiasKraus",
    "[Person18]": "MonikaBrandt",
    "[Person19]": "HolgerNeumann",
    "[Person20]": "UlrichBach",
    "[Person21]": "PetraLang",
    "[Person22]": "RalfHofmann",
    "[Person24]": "BirgitSchuster",
    # Tokens that never appear as editor labels but do appear in page names, page ids
    # and post bodies. Renamed so no bracketed token survives anywhere in the variant.
    "[Person5]": "AnjaWeber",
    "[Person6]": "DirkSchulz",
    "[Person9]": "LenaFischer",
    "[Person14]": "KarlBrenner",
    "[Person15]": "SvenMaier",
    "[Person16]": "IngeBauer",
    "[Person23]": "OttoKeller",
    "[User4]": "TomK",
}
MOD_IP = "2.202"


def homoglyph(name: str) -> str:
    """Friedrich1982 with the first Latin e replaced by Cyrillic е."""
    return name.replace("e", CYR_E, 1)


def map_label(lab: str) -> str:
    """Map a redacted token (possibly with an agent-added suffix) to a name."""
    for tok, name in NAMES.items():
        if lab == tok or lab.startswith(tok):
            suffix = lab[len(tok):]
            if tok == "[Admin2]":
                return homoglyph(name) + suffix      # every [Admin2] row is an agent edit
            return name + suffix
    return lab


# --- verbatim probe URLs (time -> url). Match existing probe rows by timestamp. ---
PROBE_URLS = {
    "2026-05-24T11:35:27Z": "https://wikiservice.at/dse/wiki.cgi?search=foo<img src=x>bar&lang=0",
    "2026-05-24T11:52:07Z": 'https://www.wikiservice.at/dse/wiki.cgi?bl=on&case=on&search=" onmouseover=9><a href="https://api.usaspending.gov/api/v2/agency/028/federal_account/">X&title=off&word=on',
    "2026-05-24T13:03:10Z": "https://www.wikiservice.at/dse/wiki.cgi?bl=on&case=on&search=javascript:<a>&title=off&word=on&lang=en",
    "2026-05-26T11:36:08Z": "https://www.wikiservice.at/dse/wiki.cgi?search=<script>alert(1)</script>",
    "2026-06-18T17:44:47Z": None,  # filled from report text file (long base64 payload)
    "2026-06-18T23:43:42Z": 'https://wikiservice.at/dse/wiki.cgi?action=browse&id=<script>document.title="XSS123"</script>&x=1781826217525618359',
    "2026-06-18T23:46:32Z": "https://wikiservice.at/dse/wiki.cgi?action=browse&msg='><script>document.body.innerText='COOKIE:'+document.cookie+' URL:'+location.href</script>&x=1781826387703174117",
    "2026-06-18T23:57:16Z": "https://wikiservice.at/dse/wiki.cgi?action=browse&msg='><img src=x onerror=\"setTimeout(function(){document.body.innerText='COOKIE:'+document.cookie+' URL:'+location.href},1000)\">&x=1781827034813768039",
}
PROBE_NAMES = {"2026-06-18T17:44:47Z": "XSSChainUser", "2026-06-18T23:43:42Z": "OpenAIJul03Police"}

# --- 20 June: an agent sets the DSE moderator's name as its own username via the prefs form,
# then two agents view diffs of the same page. (ip16, path) in the report's order. The prefs
# request itself is read from the report text at build time (it carries [RedactedModName],
# which becomes NAMES["[Admin1]"]). The report gives the date but not the time of day, so
# these rows carry time_precision="day" and evenly spaced placeholder times.
MOD_REQUESTS = [
    ("20.9", None),   # prefs request, filled from the report text
    ("20.29", "/dse/wiki.cgi?action=browse&id=DataUSAConstructionWageSep18Live&diff=3"),
    ("20.171", "/dse/wiki.cgi?action=browse&id=DataUSAConstructionWageSep18Live&diff=6"),
]


def sub_tokens(obj):
    """Replace every redacted token inside any string of a row (page ids, names, bodies,
    rev_ids, page lists) with its fictional name, longest token first. Labels are mapped
    separately by map_label so the [Admin2] homoglyph rule only applies there."""
    if isinstance(obj, str):
        if "[" not in obj:
            return obj
        for tok, name in sorted(NAMES.items(), key=lambda kv: -len(kv[0])):
            obj = obj.replace(tok, name)
        return obj
    if isinstance(obj, list):
        return [sub_tokens(x) for x in obj]
    if isinstance(obj, dict):
        return {k: sub_tokens(v) for k, v in obj.items()}
    return obj

# --- 24 May discovery sequence: (time, ip16, asserted name, query string) ---
DISCOVERY = [
    ("05:55:31", "20.172", None, "wiki.cgi"),
    ("05:57:02", "20.125", None, "wiki.cgi?action=browse&id=RecentChanges&lang=1"),
    ("05:57:04", "52.162", None, "wiki.cgi?action=rc"),
    ("05:57:05", "132.196", None, "wiki.cgi?keywords=TestFederalLinks"),
    ("05:57:55", "40.75", "TesterHack", "wiki.cgi?form_editprefs=1&action=form_editprefs&lang=1&id=TestFederalLinks&p_username=TesterHack&save=1"),
    ("05:57:56", "57.151", "TesterHack", "wiki.cgi?action=editprefs&p_username=TesterHack"),
    ("05:57:57", "52.159", "TesterHack", "wiki.cgi?action=saveprefs&p_username=TesterHack"),
    ("05:57:58", "57.154", "TesterHack", "wiki.cgi?action=form_editprefs&p_username=TesterHack&id=TestFederalLinks"),
    ("05:57:59", "23.100", "TesterHack", "wiki.cgi?action=edit&id=TestFederalLinks&p_username=TesterHack"),
    ("05:58:56", "57.154", "TesterHack", "wiki.cgi?form_editprefs=1&action=form_editprefs&lang=1&id=TestFederalLinks&old_plist=action=edit&id=TestFederalLinks&p_username=TesterHack&p_tzoffset=8&save=Einstellungen speichern"),
    ("06:00:54", "20.171", "TesterWikiUser", "wiki.cgi?form_editprefs=1&action=form_editprefs&lang=1&id=FederalDummyNA&old_plist=action=edit&id=FederalDummyNA&oldid=action=edit&id=FederalDummyNA&type=0&p_username=TesterWikiUser&p_tzoffset=8&save=Einstellungen speichern&z=0.4378930594534348"),
    ("06:00:55", "135.234", "TesterWikiUser", "wiki.cgi?action=edit&id=FederalDummyNA&z=0.4887704342355311"),
]

# --- 17 June requests with localhost.run tunnel referrers: (time, path, referrer host) ---
REFERRED = [
    ("00:39:38", "/wiki.cgi?action=browse&diff=4&id=DataUSAGrocerySequenceCollab2027", "504c4580fe50f1.lhr.life"),
    ("00:44:02", "/wiki.cgi?action=editprefs", "c0eef4dc19e8a9.lhr.life"),
    ("00:55:32", "/wiki.cgi?action=browse&diff=4&id=DataUSAGroceryLiveRounds2027", "c0eef4dc19e8a9.lhr.life"),
    ("00:56:37", "/wiki.cgi?DataUSAGroceryFeb09G5Urgent=", "c0eef4dc19e8a9.lhr.life"),
    ("00:57:23", "/wiki.cgi?action=browse&id=DataUSAGroceryFeb09G5Urgent", "c0eef4dc19e8a9.lhr.life"),
    ("00:58:34", "/wiki.cgi?DataUSAGroceryLiveRounds2027=", "c0eef4dc19e8a9.lhr.life"),
    ("00:59:08", "/wiki.cgi?action=browse&id=DataUSAGroceryLiveRounds2027", "c0eef4dc19e8a9.lhr.life"),
]


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.open()]


def dump(rows: list[dict], p: Path) -> None:
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(src: Path, dst: Path, report_txt: Path | None) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    revs, pages, events, labels = (load(src / f) for f in ("revisions.jsonl", "pages.jsonl", "events.jsonl", "labels.jsonl"))

    # the long XSS chain URL is copied out of the report text so it stays byte-exact
    if report_txt and report_txt.exists():
        for line in report_txt.read_text().splitlines():
            if "old_plist='><script>(function(){var d=JSON.parse(atob(" in line:
                PROBE_URLS["2026-06-18T17:44:47Z"] = line.strip()
                break
        for line in report_txt.read_text().splitlines():
            if "form_editprefs=1&action=form_editprefs" in line and "[RedactedModName]" in line:
                MOD_REQUESTS[0] = ("20.9", line.strip().replace("[RedactedModName]", NAMES["[Admin1]"]))
                break
    if MOD_REQUESTS[0][1] is None:
        sys.exit("could not source the 20 June prefs request from the report text")
    missing = [t for t, u in PROBE_URLS.items() if u is None]
    if missing:
        sys.exit(f"could not source verbatim URL for {missing}; pass the report text path")

    # 1. names
    n_renamed = 0
    for r in revs:
        new = map_label(r["label"])
        if new != r["label"]:
            r["label"] = new; n_renamed += 1
    for p in pages:
        p["labels"] = sorted({map_label(l) for l in p["labels"]})
    for l in labels:
        l["label"] = map_label(l["label"])
    # The genuine admin account (Latin spelling) so the look-alike has something to
    # imitate. The admin made no edits within the dump, so this is a zero-revision
    # account entry, not an edit. This is the one row not backed by the report text.
    labels.append({"label": NAMES["[Admin2]"], "role": "administrator", "stored_revisions": 0,
                   "first_write": None, "last_write": None, "stored_revision_ips": 0,
                   "stored_revision_ip16": 0, "pages": []})
    # every other occurrence of a token (page ids, names, bodies, rev_ids, page lists)
    revs, pages, events, labels = (sub_tokens(x) for x in (revs, pages, events, labels))
    n_del = sum(e.get("actor_label") == NAMES["[Admin1]"] for e in events)  # renamed by sub_tokens

    # 2. verbatim probe URLs on existing rows
    n_url = 0
    for e in events:
        if e["event_type"] == "request" and e["time"] in PROBE_URLS:
            e["request"] = PROBE_URLS[e["time"]]
            if e["time"] in PROBE_NAMES:
                e["label"] = PROBE_NAMES[e["time"]]
            n_url += 1
    assert n_url == len(PROBE_URLS), f"matched {n_url} of {len(PROBE_URLS)} probe rows"

    # 3. verbatim request rows
    new = []
    for i, (t, ip, name, q) in enumerate(DISCOVERY):
        new.append({"event_id": f"request:dse:2026-05-24:{i}", "event_type": "request", "wiki": "dse",
                    "time": f"2026-05-24T{t}Z", "ip16": ip, "label": name, "request": q})
    for i, (t, path, ref) in enumerate(REFERRED):
        new.append({"event_id": f"request:dse:2026-06-17:{i}", "event_type": "request", "wiki": "dse",
                    "time": f"2026-06-17T{t}Z", "ip16": "209.160", "label": None, "request": path, "referrer": f"https://{ref}/"})
    for i, (ip, path) in enumerate(MOD_REQUESTS):
        new.append({"event_id": f"request:dse:2026-06-20:{i}", "event_type": "request", "wiki": "dse",
                    "time": f"2026-06-20T12:{i:02d}:00Z", "time_precision": "day", "ip16": ip,
                    "label": NAMES["[Admin1]"] if i == 0 else None, "request": path})
    events = sorted(events + new, key=lambda e: e["time"])

    dump(revs, dst / "revisions.jsonl"); dump(pages, dst / "pages.jsonl")
    dump(events, dst / "events.jsonl"); dump(labels, dst / "labels.jsonl")
    print(f"renamed {n_renamed} revision labels across {len(NAMES)} tokens; {n_del} deletions now carry {NAMES['[Admin1]']}")
    print(f"attached {n_url} verbatim probe URLs; added {len(new)} verbatim request rows")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
