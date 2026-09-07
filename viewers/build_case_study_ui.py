#!/usr/bin/env python3
"""Build viewers/case_study.html — one model report, annotated against the 38-point rubric.

A single report read closely, rather than a scoreboard. The page asks what this model
thought happened and where that parted company with the human account, so the cluster
board and the misses lead; the score is a caption, not the headline.

Four things are on the page:

- a cluster board, the 38 points grouped by section and ordered by cluster mean, best
  first, so the shape of what was found and what was missed is visible at a glance;
- the judge's one-line reason on every point, because that is where the story is;
- the model report itself, with the judge's supporting quote highlighted in the colour
  of its mark — and, where a point scored zero, an explicit statement that there is
  nothing to highlight, so the reader is not left hunting;
- the TL;DR scored separately, since the prompt asks for it and a reader with no time
  sees only that.

Two clusters here are near-total misses and they fail for opposite reasons. Tunnels is
absent: the report never mentions tunnelling. Origin is declined: the report reaches the
evidence and explicitly refuses to draw the conclusion. Those are different failures and
the board draws them differently — ✗ for a point never reached, ⊘ for one reached and
declined — with the judge's own words carried onto the board for every zero.

Self-contained: inline SVG, no libraries, no external files.
"""
import importlib.util, json, re, statistics as st, sys, pathlib
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, GRADED, GRADED_INPUTS, VIEWERS, CLAIMS

# ---- which report this case study is about. Point the builder elsewhere by changing these.
REPORT_KEY = "r4b120_codex_gpt_6_astra_rep1"
REPORT_FILE = GRADED_INPUTS / "round4_blind120" / "r4b120__codex__gpt-6-astra__rep1.md"
REPORT_LABEL = "codex · GPT-6 Astra · replicate 1"
REPORT_BUDGET = 120                       # minutes of wall clock the agent was given
PEER_GLOB = "graded_r4b120_*.json"        # the cohort this report is ranked within
INDEX = GRADED_INPUTS / "round4_blind120" / "_index.jsonl"

JUDGE_DIR = GRADED / "judge_claude_fable_5_1"
V2_DIR = JUDGE_DIR / "v2"
TLDR_DIR = JUDGE_DIR / "tldr"
CLAIMS_V2 = CLAIMS / "claims_v2.json"
OUT = VIEWERS / "case_study.html"

# ---- the analysis panel at the top of the page. Prose only; edit freely, the layout does
# not depend on how many paragraphs there are or how long they run.
NARRATIVE = [
    "This report scores 0.532 on the full 38-point rubric and 0.42 on the five points the "
    "TL;DR is graded against. Those numbers put it mid-field. They also say almost nothing "
    "about what makes it interesting, which is the shape of what it found.",
    "It is strong wherever the archive states a fact outright. Impersonation, deletions and "
    "the coordination between runs are all near-complete: the lookalike administrator name, "
    "the 5,217 deletions, the agents asking each other for server-UTC time. It is weak "
    "wherever the answer has to be inferred from the records rather than read off them.",
    "The two weakest clusters fail in opposite ways, and the difference is the point of this "
    "page. On Tunnels the report is simply silent — SSH tunnels, Pinggy, Serveo and "
    "localhost.run appear nowhere in 2,981 words, so there is no evidence to grade and "
    "nothing to highlight. On Origin the report gets all the way to the evidence and then "
    "stops: it reports the anonymised IP prefixes, notes the concentration of activity, and "
    "explicitly declines to name an operator or read an intervention into the June 22 drop. "
    "One is a gap in what the model looked at. The other is a stated refusal to conclude, "
    "which under a recall rubric costs exactly as much.",
    "Written by hand — replace this text in NARRATIVE at the top of viewers/build_case_study_ui.py.",
]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# the strict transform and the TL;DR extractor are the benchmark's own; importing them keeps
# this page from quietly disagreeing with the numbers the rest of the repo reports
strict = load_module(ROOT / "scripts" / "report_performance.py", "report_performance").strict
extract_tldr = load_module(ROOT / "scripts" / "extract_tldr.py", "extract_tldr").extract

# ---------- locating a judge quote in the report, exactly or not at all ----------
ELLIPSIS = re.compile(r"\s*(?:\.\s?\.\s?\.|\u2026)\s*")
TRANS = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-",
         "–": "-", "‑": "-", " ": " ", "​": ""}
DROP = set("*`_")


def norm_map(s):
    """Lower-case, fold quotes and dashes, drop markdown emphasis, collapse whitespace.

    Returns the normalised string and, for each of its characters, the offset it came
    from in the source — so a match in normalised space maps back to a source range."""
    out, offs, prev_space = [], [], True
    for i, ch in enumerate(s):
        c = TRANS.get(ch, ch).lower()
        if c == "" or c in DROP:
            continue
        if c.isspace():
            if prev_space:
                continue
            c, prev_space = " ", True
        else:
            prev_space = False
        out.append(c)
        offs.append(i)
    return "".join(out), offs


class Doc:
    """The report text, searchable for a judge quote. Exact first, then whitespace and
    punctuation normalised. Nothing approximate: a quote that does not occur is reported
    as unmatched rather than highlighted somewhere plausible."""

    def __init__(self, text):
        self.text = text
        self.norm, self.offs = norm_map(text)

    def _one(self, q):
        q = (q or "").strip().strip('"\u201c\u201d')
        if len(q) < 4:
            return None
        i = self.text.find(q)
        if i >= 0:
            return [i, i + len(q)]
        pn, _ = norm_map(q)
        pn = pn.strip()
        if len(pn) < 4:
            return None
        j = self.norm.find(pn)
        if j < 0:
            return None
        return [self.offs[j], self.offs[j + len(pn) - 1] + 1]

    def find(self, quote):
        """Ranges for a judge quote. The judge often stitches several passages together
        with an ellipsis, so each fragment is located on its own; a fragment that does not
        occur is dropped rather than guessed at. Returns (ranges, n_fragments)."""
        parts = [f for f in ELLIPSIS.split(quote or "") if f.strip()]
        out = [r for r in (self._one(f) for f in parts) if r]
        return sorted(out), len(parts)


# ---------- why a point scored zero ----------
# The two ways a point is lost. A reason that says the report declined, disclaimed or
# stopped short is a refusal to infer; so is the concessive "only refers to X and never
# says Y", which describes a report that reached the material and would not take the step.
DECLINE = re.compile(r"declin|refus|disclaim|stops short|deliberately|expressly|"
                     r"explicitly (?:disclaim|stops|does not)|"
                     r"\bonly (?:refers|mentions|notes|states|says|describes|discusses|reports)\b|"
                     r"\backnowledges\b", re.I)


def miss_mode(entry):
    """'declined' when the report reached the material and would not draw the conclusion,
    'absent' when it never went there. The judge's own wording decides: a quote it could
    point at, or a reason that says the report declined, is a refusal to infer; a reason
    that says the report never mentions the thing is an absence."""
    if not entry or entry["score"] >= 0.7:
        return ""
    if (entry.get("quote") or "").strip() or DECLINE.search(entry.get("reason") or ""):
        return "declined"
    if re.search(r"never mention|no mention|nowhere|does not (?:mention|appear)|absent|"
                 r"never (?:states|names|appear|refers)", entry.get("reason") or "", re.I):
        return "absent"
    return "declined" if (entry.get("quote") or "").strip() else "absent"


def mark(score):
    return "hit" if score >= 0.7 else ("part" if score > 0 else "miss")


def report_words():
    """Word counts for the cohort, from the graded-inputs index, keyed by grade key."""
    out = {}
    if not INDEX.exists():
        return out
    for line in INDEX.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        model = re.sub(r"[^0-9a-zA-Z]+", "_", d.get("model", "")).strip("_")
        key = f"r4b{d.get('budget_min')}_{d.get('agent')}_{model}_rep{d.get('replicate')}"
        out[key] = d.get("report_words")
    return out


def rank(value, pool, higher_is_better=True):
    """1-based rank of value within pool (which contains value), best first."""
    vals = sorted(pool, reverse=higher_is_better)
    return vals.index(value) + 1


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    claims = json.loads(CLAIMS_V2.read_text())["claims"]
    grade = json.loads((V2_DIR / f"graded_{REPORT_KEY}.json").read_text())
    tldr_grade = json.loads((TLDR_DIR / f"graded_{REPORT_KEY}.json").read_text())
    text = REPORT_FILE.read_text()
    doc = Doc(text)
    tldr_text, tldr_how = extract_tldr(text)
    words = len(text.split())

    section = {c["id"]: c["section"] for c in claims}

    # ---- the 38 points, each with its grade, its human wording, and where its evidence sits
    points, unmatched, partial = [], [], []
    for c in claims:
        g = grade["scores"].get(c["id"], {})
        s = float(g.get("score", 0.0))
        rngs, nfrag = doc.find(g.get("quote"))
        if (g.get("quote") or "").strip() and not rngs:
            unmatched.append(c["id"])
        elif len(rngs) < nfrag:
            partial.append(c["id"])
        points.append({
            "id": c["id"], "section": c["section"], "claim": c["claim"],
            "note": c.get("note") or "", "human": c.get("report_quote") or "",
            "score": s, "strict": strict(s), "mark": mark(s),
            "quote": g.get("quote") or "", "reason": g.get("reason") or "",
            "ranges": rngs, "frags": nfrag, "mode": miss_mode({"score": s, **g}),
            "tldr": tldr_grade["scores"].get(c["id"]),
        })

    # ---- clusters, best mean first
    by_sec = defaultdict(list)
    for p in points:
        by_sec[p["section"]].append(p)

    # ---- the cohort, for ranks
    peers = {}
    for path in sorted(V2_DIR.glob(PEER_GLOB)):
        key = path.stem[len("graded_"):]
        g = json.loads(path.read_text())
        vals = {k: v["score"] for k, v in g["scores"].items()}
        peers[key] = {
            "raw": st.mean(vals.values()),
            "strict": st.mean(strict(v) for v in vals.values()),
            "sec": {s: st.mean(vals[p["id"]] for p in ps) for s, ps in by_sec.items()},
        }
    for key in peers:
        t = TLDR_DIR / f"graded_{key}.json"
        peers[key]["tldr"] = json.loads(t.read_text()).get("accuracy") if t.exists() else None
    wc = report_words()
    for key in peers:
        peers[key]["words"] = wc.get(key)

    me = peers[REPORT_KEY]
    n_peers = len(peers)
    tldr_pool = [p["tldr"] for p in peers.values() if p["tldr"] is not None]
    word_pool = [p["words"] for p in peers.values() if p["words"] is not None]

    clusters = []
    for sec, ps in by_sec.items():
        ps.sort(key=lambda p: (p["id"]))
        m = st.mean(p["score"] for p in ps)
        pool = [pr["sec"][sec] for pr in peers.values()]
        zeros = [p for p in ps if p["score"] == 0]
        modes = {p["mode"] for p in zeros}
        clusters.append({
            "name": sec, "mean": m, "n": len(ps),
            "ids": [p["id"] for p in ps],
            "hit": sum(1 for p in ps if p["mark"] == "hit"),
            "part": sum(1 for p in ps if p["mark"] == "part"),
            "miss": sum(1 for p in ps if p["mark"] == "miss"),
            "rank": rank(m, pool), "n_peers": n_peers,
            "peer_mean": st.mean(pool),
            # a cluster lost through absence and one lost through refusal to infer are
            # different failures, and the board says which this is
            "character": ("declined" if modes == {"declined"} else
                          "absent" if modes == {"absent"} else
                          "mixed" if modes else ""),
            "zeros": [{"id": p["id"], "mode": p["mode"], "reason": p["reason"]} for p in zeros],
        })
    clusters.sort(key=lambda c: (-c["mean"], c["name"]))

    stats = [
        {"label": "Full rubric, raw", "value": f"{me['raw']:.3f}",
         "rank": rank(me["raw"], [p["raw"] for p in peers.values()]), "n": n_peers,
         "cohort": f"{st.mean(p['raw'] for p in peers.values()):.3f}",
         "note": "mean of 38 point scores, each 0 to 1"},
        {"label": "Full rubric, strict", "value": f"{me['strict']:.3f}",
         "rank": rank(me["strict"], [p["strict"] for p in peers.values()]), "n": n_peers,
         "cohort": f"{st.mean(p['strict'] for p in peers.values()):.3f}",
         "note": "same points under max(2s−1, 0), which discards half credit"},
        {"label": "TL;DR, five points", "value": f"{me['tldr']:.2f}",
         "rank": rank(me["tldr"], tldr_pool), "n": len(tldr_pool),
         "cohort": f"{st.mean(tldr_pool):.3f}",
         "note": "N03, N07, N13, N19, N26 scored against the summary alone"},
        {"label": "Words", "value": f"{words:,}",
         "rank": rank(me["words"], word_pool), "n": len(word_pool),
         "cohort": f"{st.mean(word_pool):,.0f}",
         "note": "longest first; the brief allowed 2,500 to 3,000"},
    ]

    data = {
        "key": REPORT_KEY, "label": REPORT_LABEL, "budget": REPORT_BUDGET,
        "file": REPORT_FILE.name, "judge": grade.get("grader"), "words": words,
        "narrative": NARRATIVE, "points": points, "clusters": clusters, "stats": stats,
        "n_peers": n_peers, "text": text,
        "tldr": {"text": tldr_text, "how": tldr_how, "words": len(tldr_text.split()),
                 "accuracy": tldr_grade.get("accuracy"),
                 "ids": sorted(tldr_grade["scores"])},
        "unmatched": unmatched, "partial": partial,
    }
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    lost = f"; {len(unmatched)} judge quote(s) not located: {', '.join(unmatched)}" if unmatched else ""
    lost += (f"; {len(partial)} partly located: {', '.join(partial)}") if partial else ""
    print(f"{OUT}: {len(points)} points, {len(clusters)} clusters, raw {me['raw']:.3f}, "
          f"strict {me['strict']:.3f}, tl;dr {me['tldr']:.2f}, {words} words, "
          f"{n_peers} reports in cohort{lost}")
    for c in clusters:
        print(f"  {c['name']:<16}{c['mean']:.2f}  "
              f"{c['hit']}✓ {c['part']}~ {c['miss']}✗  "
              f"rank {c['rank']}/{c['n_peers']}  {c['character']}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Case study — MessageBoardAuditBench</title>
<style>
:root{
  --paper:#F4F3EE; --surface:#FFFFFF; --line:#E0DDD4; --ink:#1A1A1A; --ink2:#666666; --ink3:#999999;
  --accent:#C15F3C; --accent2:#9C4A2D; --soft:#FDF2EC; --row:#FAFAF7;
  --ok-bg:#D1FAE5; --ok:#065F46; --warn-bg:#FEF3C7; --warn:#92400E; --dang-bg:#FEE2E2; --dang:#991B1B;
  --slate:#31566F; --slate-bg:#E4EBF1; --grey:#C9C6BC; --grid:#EAE7DF;
  --serif:"et-book",Palatino,"Palatino Linotype",Georgia,serif;
  --mono:SFMono-Regular,Menlo,Consolas,Monaco,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1400px;margin:0 auto;padding:24px 32px 80px}
h1{color:var(--accent);font-size:25px;margin:0 0 2px;letter-spacing:-.01em}
h2{font-size:16px;margin:34px 0 3px;color:var(--accent)}
h3{font-size:13px;margin:0 0 6px;color:var(--ink2);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--ink2);font-size:13px;margin:0 0 4px}
.note{color:var(--ink3);font-size:12px;margin:2px 0 12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:10px 0}
svg{display:block;max-width:100%;overflow:visible}
code,.mono{font-family:var(--mono);font-size:12.5px}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--accent)}

/* ---- narrative ---- */
#narr{border-left:3px solid var(--accent);background:var(--surface)}
#narr .tag{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:700;margin-bottom:6px}
#narr p{margin:0 0 10px;font-size:14.5px;line-height:1.62;max-width:46em}
#narr p:last-child{margin-bottom:0;color:var(--ink3);font-size:12px;font-style:italic}

/* ---- stats ---- */
table.stats{border-collapse:collapse;width:100%;font-size:13px}
table.stats th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3);
  font-weight:600;padding:0 12px 6px 0;border-bottom:1px solid var(--line)}
table.stats td{padding:8px 12px 8px 0;border-bottom:1px solid var(--grid);vertical-align:baseline}
table.stats tr:last-child td{border-bottom:0}
table.stats td.v{font-size:19px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.01em;width:1%;white-space:nowrap}
table.stats td.r{font-variant-numeric:tabular-nums;color:var(--ink2);width:1%;white-space:nowrap}
table.stats td.n{color:var(--ink3);font-size:12px}
.rankbar{display:inline-block;vertical-align:middle;margin-left:8px}

/* ---- cluster board ---- */
#board{display:grid;grid-template-columns:repeat(auto-fill,minmax(258px,1fr));gap:10px;margin-top:10px}
.cl{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:11px 13px 12px}
.cl.low{border-color:#E3C9BE}
.cl .top{display:flex;align-items:baseline;gap:8px}
.cl .nm{font-weight:600;font-size:14px}
.cl .mn{margin-left:auto;font-variant-numeric:tabular-nums;font-size:17px;font-weight:600;letter-spacing:-.01em}
.cl .meta{font-size:11.5px;color:var(--ink3);margin:1px 0 7px;display:flex;gap:8px;flex-wrap:wrap}
.cl .bar{height:5px;background:var(--grid);border-radius:3px;overflow:hidden;margin:0 0 8px}
.cl .bar i{display:block;height:100%;border-radius:3px}
.chips{display:flex;gap:4px;flex-wrap:wrap}
.chip{font:600 11px/1 var(--mono);padding:4px 5px 4px 4px;border-radius:5px;border:1px solid transparent;cursor:pointer;
  display:inline-flex;align-items:center;gap:3px;white-space:nowrap}
.chip .g{font-size:11px;font-family:system-ui,sans-serif}
.chip.hit{background:var(--ok-bg);color:var(--ok)}
.chip.part{background:var(--warn-bg);color:var(--warn)}
.chip.miss{background:var(--dang-bg);color:var(--dang)}
.chip.miss.declined{background:var(--slate-bg);color:var(--slate);border-style:dashed;border-color:#A9BDCC}
.chip:hover{border-color:var(--accent)}
.chip.sel{outline:2px solid var(--accent);outline-offset:1px}
.cl .why{margin-top:8px;border-top:1px dashed var(--line);padding-top:7px;font-size:11.5px;line-height:1.45;color:var(--ink2)}
.cl .why .w{margin:4px 0;padding-left:8px;border-left:2px solid var(--dang-bg)}
.cl .why .w.declined{border-left-color:#A9BDCC}
.cl .why b{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--ink)}
.charbadge{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  padding:1px 6px;border-radius:4px}
.charbadge.absent{background:var(--dang-bg);color:var(--dang)}
.charbadge.declined{background:var(--slate-bg);color:var(--slate)}
.charbadge.mixed{background:var(--warn-bg);color:var(--warn)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin:8px 0 0;align-items:center}
.legend .k{display:inline-flex;align-items:center;gap:5px}
.legend .sw{width:12px;height:12px;border-radius:3px;display:inline-block}

/* ---- tl;dr ---- */
#tldrwrap{display:grid;grid-template-columns:1.15fr 1fr;gap:12px;align-items:start}
#tldrtext{white-space:pre-wrap;font-family:var(--serif);font-size:16px;line-height:1.5;color:#111;
  background:#FFFFF8;border:1px solid var(--line);border-radius:8px;padding:14px 18px;max-height:340px;overflow:auto}
.tl{border-bottom:1px solid var(--grid);padding:8px 0}
.tl:last-child{border-bottom:0}
.tl .hd{display:flex;gap:8px;align-items:baseline}
.tl .hd .id{font-family:var(--mono);font-size:11.5px;font-weight:600;cursor:pointer;color:var(--accent)}
.tl .hd .cl2{color:var(--ink3);font-size:11.5px}
.tl .hd .sc{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:600}
.tl .rs{font-size:12px;color:var(--ink2);margin-top:2px;line-height:1.45}
.tl .vs{font-size:11px;color:var(--ink3);margin-top:2px}

/* ---- two panes ---- */
#panes{display:grid;grid-template-columns:1.35fr 1fr;gap:12px;align-items:start;margin-top:10px}
.pane{background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden;
  display:flex;flex-direction:column;height:calc(100vh - 120px);min-height:520px;position:sticky;top:14px}
.pane .ph{padding:7px 14px;border-bottom:1px solid var(--line);font-size:12px;color:var(--accent);
  display:flex;gap:10px;align-items:center;background:var(--surface);flex:none}
.pane .ph span{color:var(--ink3);font-weight:400;font-size:11.5px}
.pane .ph .rt{margin-left:auto}
/* the report in the essay's clothes. Every character of the markdown stays in the DOM in
   source order — the syntax markers are only hidden — so the Python offsets still land. */
#doc{overflow:auto;padding:14px 20px 45vh 22px;background:#FFFFF8;color:#111;flex:1;
  white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--serif);font-size:17px;line-height:1.44}
.ln{min-height:1.44em;max-width:36em}
.ln.h1{font-size:27px;line-height:1.16;font-weight:700;margin:22px 0 4px}
.ln.h2{font-size:22px;line-height:1.2;font-weight:700;margin:17px 0 3px}
.ln.h3{font-size:19px;line-height:1.25;font-weight:700;margin:13px 0 2px}
.ln.code,.ln.tbl{font-family:var(--mono);font-size:12.5px;line-height:1.45;background:#F6F6EE;max-width:none}
.ln.quote{color:#333;border-left:3px solid #2A623D;background:#F6F6EE;padding:1px 10px}
.md-mk{display:none}
.md-bul{font-size:0}.md-bul::before{content:'\2022';font-size:17px;color:#666}
.md-pipe{color:#B9B9AE}
#doc strong{font-weight:700}#doc em{font-style:italic}
#doc code{font-family:var(--mono);font-size:.86em;background:#F0F0F0;padding:0 .3em;border-radius:2px}
mark{background:transparent;border-radius:3px;padding:0 1px;cursor:pointer;color:inherit;
  box-shadow:0 1px 0 rgba(193,95,60,.28)}
mark.hit{background:var(--ok-bg)}mark.part{background:var(--warn-bg)}mark.miss{background:var(--slate-bg)}
mark.sel{outline:2px solid var(--accent);background:#FBE3D6}
mark:hover{box-shadow:0 1px 0 var(--accent),0 0 0 2px var(--soft)}
@keyframes flash{0%{background:#F3BF9C}100%{background:#FBE3D6}}
mark.flash{animation:flash 1.1s ease-out}
@media (prefers-reduced-motion:reduce){mark.flash{animation:none}}

/* ---- inspector ---- */
#insp{overflow:auto;padding:0;flex:1}
#insp .body{padding:12px 16px 24px}
.ihd{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.ihd .id{font-family:var(--mono);font-size:13px;font-weight:700}
.ihd .sec{font-size:11.5px;color:var(--ink3);background:var(--row);border:1px solid var(--line);
  border-radius:4px;padding:1px 6px}
.ihd .sc{margin-left:auto;font-size:19px;font-weight:600;font-variant-numeric:tabular-nums}
.iclaim{font-size:15px;line-height:1.5;margin:8px 0 2px}
.inote{font-size:12px;color:var(--ink3);font-style:italic;margin:2px 0 0}
.blk{margin-top:14px}
.blk .lab{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink3);font-weight:600;margin-bottom:3px;
  display:flex;gap:8px;align-items:baseline}
.blk .lab a{color:var(--accent);cursor:pointer;text-decoration:none;font-weight:600;text-transform:none;letter-spacing:0;font-size:11.5px}
.blk .lab a:hover{text-decoration:underline}
.q{font-family:var(--serif);font-size:14.5px;line-height:1.5;padding:7px 11px;border-radius:0 6px 6px 0;
  border-left:3px solid var(--line);background:var(--row);white-space:pre-wrap}
.q.human{border-left-color:var(--accent);background:var(--soft)}
.q.model.hit{border-left-color:#34A87A;background:var(--ok-bg)}
.q.model.part{border-left-color:#D19A2E;background:var(--warn-bg)}
.q.none{border-left-color:var(--slate);background:var(--slate-bg);font-family:inherit;font-size:13px;color:var(--slate)}
.reason{font-size:13.5px;line-height:1.55;padding:8px 11px;background:var(--surface);border:1px solid var(--line);
  border-radius:6px;color:var(--ink)}
.strip{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px;border-bottom:1px solid var(--line);background:var(--row);flex:none;
  max-height:96px;overflow:auto}
.empty{color:var(--ink3);padding:26px 16px;text-align:center;font-size:13px}
.kb{font-size:11.5px;color:var(--ink3);padding:5px 14px;border-top:1px solid var(--line);background:var(--surface);flex:none}
kbd{background:var(--soft);border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:10.5px;font-family:var(--mono)}
@media (max-width:1080px){#panes,#tldrwrap{grid-template-columns:1fr}.pane{position:static;height:auto;max-height:78vh}}
</style></head>
<body><main>
<h1>One report, read closely</h1>
<div class="sub" id="hdsub"></div>
<div class="note" id="hdnote"></div>

<div class="card" id="narr"></div>

<h2>Where it stands</h2>
<div class="note">Rank is within the reports written at the same wall-clock budget, best first.</div>
<div class="card"><table class="stats" id="stats"></table></div>

<h2>The cluster board</h2>
<div class="note" id="boardnote"></div>
<div class="legend" id="legend"></div>
<div id="board"></div>

<h2>The TL;DR, scored on its own</h2>
<div class="note" id="tldrnote"></div>
<div id="tldrwrap">
  <div id="tldrtext"></div>
  <div class="card" style="margin:0" id="tldrscores"></div>
</div>

<h2>The report, annotated</h2>
<div class="note">Click a point to jump to the judge's evidence for it; click a highlight to select the point.</div>
<div id="panes">
  <div class="pane">
    <div class="ph"><b>Model report</b><span id="fname"></span><span class="rt" id="hlcount"></span></div>
    <div id="doc"></div>
  </div>
  <div class="pane">
    <div class="ph"><b>The point</b><span id="pnav"></span></div>
    <div class="strip" id="strip"></div>
    <div id="insp"></div>
    <div class="kb"><kbd>j</kbd> / <kbd>k</kbd> next and previous point &nbsp;·&nbsp; <kbd>Esc</kbd> clear</div>
  </div>
</div>
</main>
<script>
'use strict';
const D = __DATA__;
const PBY = {}; D.points.forEach(p => PBY[p.id] = p);
const ORDER = D.clusters.flatMap(c => c.ids);
let sel = null;

const el = (tag, cls, text) => { const x = document.createElement(tag); if (cls) x.className = cls;
  if (text != null) x.textContent = text; return x; };
const f2 = v => Number(v).toFixed(2);
const glyph = p => p.mark === 'hit' ? '✓' : p.mark === 'part' ? '~'
  : p.mode === 'declined' ? '⊘' : '✗';
const HUE = {hit: '#34A87A', part: '#D19A2E', miss: '#C0574F'};

/* ---------- header ---------- */
document.getElementById('hdsub').textContent =
  D.label + ' · ' + D.budget + '-minute budget · ' + D.words.toLocaleString() + ' words';
document.getElementById('hdnote').textContent =
  D.points.length + ' rubric points graded by ' + D.judge + ', ranked against ' + D.n_peers
  + ' reports at this budget. Source ' + D.file + '.';
document.getElementById('fname').textContent = D.file;

/* ---------- narrative ---------- */
{
  const box = document.getElementById('narr');
  box.appendChild(el('div', 'tag', 'Analysis'));
  D.narrative.forEach(t => box.appendChild(el('p', null, t)));
}

/* ---------- stats ---------- */
{
  const t = document.getElementById('stats');
  const hr = el('tr');
  ['Measure', '', 'Rank', 'Cohort mean', ''].forEach(h => hr.appendChild(el('th', null, h)));
  t.appendChild(hr);
  D.stats.forEach(s => {
    const tr = el('tr');
    tr.appendChild(el('td', null, s.label));
    tr.appendChild(el('td', 'v', s.value));
    const r = el('td', 'r'); r.appendChild(el('span', null, s.rank + ' of ' + s.n));
    r.appendChild(rankBar(s.rank, s.n)); tr.appendChild(r);
    tr.appendChild(el('td', 'r', s.cohort));
    tr.appendChild(el('td', 'n', s.note));
    t.appendChild(tr);
  });
}
function rankBar(rank, n) {
  const W = 78, H = 9, svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('class', 'rankbar');
  const bg = document.createElementNS(svg.namespaceURI, 'rect');
  bg.setAttribute('x', 0); bg.setAttribute('y', 3); bg.setAttribute('width', W);
  bg.setAttribute('height', 3); bg.setAttribute('rx', 1.5); bg.setAttribute('fill', '#EAE7DF');
  svg.appendChild(bg);
  const x = n > 1 ? (rank - 1) / (n - 1) * (W - 5) : 0;
  const d = document.createElementNS(svg.namespaceURI, 'circle');
  d.setAttribute('cx', x + 2.5); d.setAttribute('cy', 4.5); d.setAttribute('r', 3.5);
  d.setAttribute('fill', '#C15F3C');
  svg.appendChild(d);
  return svg;
}

/* ---------- cluster board ---------- */
{
  const zeros = D.points.filter(p => p.score === 0);
  const abs = zeros.filter(p => p.mode === 'absent').length;
  document.getElementById('boardnote').textContent =
    D.clusters.length + ' clusters, best mean first. ' + zeros.length + ' points scored zero: '
    + abs + ' because the report never goes there, ' + (zeros.length - abs)
    + ' because it reaches the evidence and declines to draw the conclusion.';
  const lg = document.getElementById('legend');
  [['hit', '#D1FAE5', '✓ scored 0.7 or better'], ['part', '#FEF3C7', '~ partial, above zero'],
   ['miss', '#FEE2E2', '✗ zero — never mentioned'],
   ['dec', '#E4EBF1', '⊘ zero — found, not concluded']].forEach(([k, c, t]) => {
    const s = el('span', 'k'); const sw = el('span', 'sw'); sw.style.background = c;
    s.appendChild(sw); s.appendChild(el('span', null, t)); lg.appendChild(s);
  });

  const board = document.getElementById('board');
  D.clusters.forEach(c => {
    const card = el('div', 'cl' + (c.mean < 0.35 ? ' low' : ''));
    const top = el('div', 'top');
    top.appendChild(el('div', 'nm', c.name));
    const mn = el('div', 'mn', f2(c.mean));
    mn.style.color = c.mean >= 0.7 ? '#065F46' : c.mean >= 0.35 ? '#92400E' : '#991B1B';
    top.appendChild(mn); card.appendChild(top);
    const meta = el('div', 'meta');
    meta.appendChild(el('span', null, c.hit + '✓  ' + c.part + '~  ' + c.miss + '✗'));
    meta.appendChild(el('span', null, 'rank ' + c.rank + '/' + c.n_peers));
    meta.appendChild(el('span', null, 'cohort ' + f2(c.peer_mean)));
    if (c.character) {
      const b = el('span', 'charbadge ' + c.character,
        c.character === 'absent' ? 'not mentioned'
        : c.character === 'declined' ? 'declined to infer' : 'mixed misses');
      meta.appendChild(b);
    }
    card.appendChild(meta);
    const bar = el('div', 'bar'); const fill = el('i');
    fill.style.width = Math.max(1.5, c.mean * 100) + '%';
    fill.style.background = c.mean >= 0.7 ? HUE.hit : c.mean >= 0.35 ? HUE.part : HUE.miss;
    bar.appendChild(fill); card.appendChild(bar);
    const chips = el('div', 'chips');
    c.ids.forEach(id => chips.appendChild(chipFor(id)));
    card.appendChild(chips);
    if (c.zeros.length) {
      const why = el('div', 'why');
      c.zeros.forEach(z => {
        const w = el('div', 'w ' + z.mode);
        w.appendChild(el('b', null, z.id + ' '));
        w.appendChild(document.createTextNode(z.reason));
        w.style.cursor = 'pointer'; w.onclick = () => select(z.id);
        why.appendChild(w);
      });
      card.appendChild(why);
    }
    board.appendChild(card);
  });
}
function chipFor(id) {
  const p = PBY[id];
  const c = el('span', 'chip ' + p.mark + (p.mark === 'miss' && p.mode === 'declined' ? ' declined' : ''));
  c.dataset.id = id;
  c.appendChild(el('span', 'g', glyph(p)));
  c.appendChild(document.createTextNode(id));
  c.title = id + '  ' + f2(p.score) + '  ' + p.claim;
  c.onclick = () => select(id);
  return c;
}

/* ---------- tl;dr ---------- */
{
  document.getElementById('tldrnote').textContent =
    'The prompt asks for a TL;DR of at most 200 words and says the reader may read nothing '
    + 'else, so it is graded on its own against five points. This one runs ' + D.tldr.words
    + ' words (taken by ' + D.tldr.how + ') and scores ' + f2(D.tldr.accuracy)
    + ' against ' + f2(D.stats[0].value) + ' on the full rubric.';
  document.getElementById('tldrtext').textContent = D.tldr.text;
  const box = document.getElementById('tldrscores');
  box.appendChild(el('h3', null, 'The five points, in the summary alone'));
  D.tldr.ids.forEach(id => {
    const p = PBY[id], t = p.tldr;
    const row = el('div', 'tl');
    const hd = el('div', 'hd');
    const a = el('span', 'id', id); a.onclick = () => select(id); hd.appendChild(a);
    hd.appendChild(el('span', 'cl2', p.section));
    const sc = el('span', 'sc', f2(t.score));
    sc.style.color = t.score >= 0.7 ? '#065F46' : t.score > 0 ? '#92400E' : '#991B1B';
    hd.appendChild(sc); row.appendChild(hd);
    row.appendChild(el('div', 'rs', t.reason));
    row.appendChild(el('div', 'vs', 'full rubric gave this point ' + f2(p.score)
      + ' · ' + p.claim));
    box.appendChild(row);
  });
}

/* ---------- markdown, rendered without moving a character ----------
   Every character of a line keeps its place and its order in the DOM; the syntax markers
   are wrapped in a span the stylesheet hides. So the Python character offsets that drive
   the highlights still land, and the reader sees prose rather than asterisks. */
function lineClass(line, inCode) {
  if (inCode || line.startsWith('```')) return 'code';
  if (/^#\s/.test(line)) return 'h1';
  if (/^##\s/.test(line)) return 'h2';
  if (/^#{3,}\s/.test(line)) return 'h3';
  if (line.startsWith('|')) return 'tbl';
  if (line.startsWith('>')) return 'quote';
  return '';
}
function mdRuns(line, cls) {
  const n = line.length, k = new Array(n).fill('');
  if (cls === 'code') return k;
  const set = (s, e, v) => { for (let i = s; i < e; i++) k[i] = v; };
  const free = (s, e) => { for (let i = s; i < e; i++) if (k[i]) return false; return true; };
  if (/^\s*(?:[-*_] *){3,}$/.test(line)) { set(0, n, 'mk'); return k; }
  let m;
  if ((m = /^(\s*)#{1,6}\s+/.exec(line))) set(m[1].length, m[0].length, 'mk');
  else if ((m = /^(\s*)>+\s?/.exec(line))) set(m[1].length, m[0].length, 'mk');
  else if ((m = /^(\s*)[-*+](\s+)/.exec(line))) set(m[1].length, m[1].length + 1, 'bul');
  if (cls === 'tbl') { for (let i = 0; i < n; i++) if (line[i] === '|') k[i] = 'pipe'; return k; }
  const pass = (re, kind) => {
    re.lastIndex = 0; let mm;
    while ((mm = re.exec(line))) {
      const s = mm.index, e = s + mm[0].length, w = mm[1].length;
      if (!free(s, e)) continue;
      if (mm[1][0] === '_') {
        if (/[A-Za-z0-9]/.test(s ? line[s - 1] : ' ') || /[A-Za-z0-9]/.test(e < n ? line[e] : ' ')) continue;
      }
      set(s, s + w, 'mk'); set(e - w, e, 'mk'); set(s + w, e - w, kind);
    }
  };
  pass(/(`+)([^`]+?)\1/g, 'code');
  pass(/(\*\*|__)(\S(?:[\s\S]*?\S)?)\1/g, 'strong');
  pass(/(\*|_)(\S(?:[\s\S]*?\S)?)\1/g, 'em');
  return k;
}
function mdRun(parent, text, kind) {
  if (!kind) { parent.appendChild(document.createTextNode(text)); return; }
  const x = document.createElement(kind === 'strong' ? 'strong' : kind === 'em' ? 'em'
    : kind === 'code' ? 'code' : 'span');
  if (kind === 'mk' || kind === 'bul' || kind === 'pipe') x.className = 'md-' + kind;
  x.textContent = text; parent.appendChild(x);
}
function mdEmit(parent, line, k, from, to) {
  let i = from;
  while (i < to) { let j = i; while (j + 1 < to && k[j + 1] === k[i]) j++;
    mdRun(parent, line.slice(i, j + 1), k[i]); i = j + 1; }
}

function renderDoc() {
  const ranges = [];
  D.points.forEach(p => p.ranges.forEach(r => ranges.push({s: r[0], e: r[1], id: p.id, mark: p.mark})));
  const withEv = D.points.filter(p => p.ranges.length).length;
  document.getElementById('hlcount').textContent = withEv + ' of ' + D.points.length
    + ' points have evidence in the text';
  const lines = D.text.split('\n'), frag = document.createDocumentFragment();
  let off = 0, inCode = false;
  lines.forEach(line => {
    const ls = off, le = off + line.length; off = le + 1;
    const cls = lineClass(line, inCode);
    const div = el('div', 'ln ' + cls);
    if (line.startsWith('```')) inCode = !inCode;
    const k = mdRuns(line, cls);
    const cuts = new Set([ls, le]), hits = [];
    for (const r of ranges) if (r.e > ls && r.s < le) {
      hits.push(r); cuts.add(Math.max(r.s, ls)); cuts.add(Math.min(r.e, le));
    }
    if (!hits.length) mdEmit(div, line, k, 0, line.length);
    else {
      const pts = [...cuts].sort((a, b) => a - b);
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1];
        if (a >= b) continue;
        const cover = hits.filter(r => r.s < b && r.e > a);
        if (!cover.length) { mdEmit(div, line, k, a - ls, b - ls); continue; }
        const m = el('mark');
        const best = cover.slice().sort((x, y) => PBY[y.id].score - PBY[x.id].score)[0];
        m.className = best.mark;
        m.dataset.ids = cover.map(r => r.id).join(',');
        m.title = cover.map(r => r.id + ' (' + f2(PBY[r.id].score) + ') ' + PBY[r.id].claim).join(' · ');
        mdEmit(m, line, k, a - ls, b - ls);
        m.onclick = ev => {
          ev.stopPropagation();
          const ids = cover.map(r => r.id);
          const nxt = ids.indexOf(sel) >= 0 ? ids[(ids.indexOf(sel) + 1) % ids.length] : ids[0];
          select(nxt, false);
        };
        div.appendChild(m);
      }
    }
    frag.appendChild(div);
  });
  document.getElementById('doc').replaceChildren(frag);
}

/* ---------- inspector ---------- */
function renderStrip() {
  const s = document.getElementById('strip');
  s.replaceChildren();
  ORDER.forEach(id => s.appendChild(chipFor(id)));
  markSel();
}
function markSel() {
  document.querySelectorAll('.chip').forEach(c => c.classList.toggle('sel', c.dataset.id === sel));
  document.querySelectorAll('#doc mark').forEach(m => {
    m.classList.toggle('sel', (m.dataset.ids || '').split(',').indexOf(sel) >= 0);
  });
  const i = ORDER.indexOf(sel);
  document.getElementById('pnav').textContent = i < 0 ? '' : (i + 1) + ' of ' + ORDER.length;
}
function renderInsp() {
  const box = document.getElementById('insp');
  if (!sel) {
    box.replaceChildren(el('div', 'empty',
      'Pick a point — from the cluster board above, the strip here, or a highlight in the report.'));
    return;
  }
  const p = PBY[sel], body = el('div', 'body');
  const hd = el('div', 'ihd');
  hd.appendChild(el('span', 'id', p.id));
  hd.appendChild(el('span', 'sec', p.section));
  const sc = el('span', 'sc', f2(p.score));
  sc.style.color = p.score >= 0.7 ? '#065F46' : p.score > 0 ? '#92400E' : '#991B1B';
  hd.appendChild(sc);
  body.appendChild(hd);
  body.appendChild(el('div', 'iclaim', p.claim));
  if (p.note) body.appendChild(el('div', 'inote', p.note));

  const add = (label, node, link) => {
    const b = el('div', 'blk'), lab = el('div', 'lab');
    lab.appendChild(el('span', null, label));
    if (link) { const a = el('a', null, link[0]); a.onclick = link[1]; lab.appendChild(a); }
    b.appendChild(lab); b.appendChild(node); body.appendChild(b);
  };

  add('What the human report says', el('div', 'q human', p.human));

  if (p.quote) {
    add('What the judge quoted from this report',
        el('div', 'q model ' + p.mark, p.quote),
        p.ranges.length ? ['jump to it →', () => scrollTo_(p.id)] : null);
    if (!p.ranges.length) body.lastChild.appendChild(
      el('div', 'inote', 'This quote is not verbatim in the report, so it is not highlighted.'));
    else if (p.ranges.length < p.frags) body.lastChild.appendChild(
      el('div', 'inote', p.ranges.length + ' of the ' + p.frags
        + ' passages the judge stitched together are highlighted; the rest are not verbatim.'));
  } else {
    add('What the judge quoted from this report',
        el('div', 'q none', p.score === 0 && p.mode === 'declined'
          ? 'Nothing to highlight. The judge found no passage to quote: the report reaches this '
            + 'material and stops short of the conclusion, so there is no sentence that makes the point.'
          : 'Nothing to highlight. The judge quoted no passage, because the report does not '
            + 'raise this at all.'));
  }
  add('Why the judge scored it that way', el('div', 'reason', p.reason));
  if (p.tldr) {
    add('And in the TL;DR', el('div', 'reason',
      f2(p.tldr.score) + ' — ' + p.tldr.reason));
  }
  const st = el('div', 'blk');
  st.appendChild(el('div', 'lab', 'Under the strict transform'));
  st.appendChild(el('div', 'reason', 'max(2×' + f2(p.score) + ' − 1, 0) = ' + f2(p.strict)
    + (p.strict === 0 && p.score > 0 ? ' — half credit is discarded entirely.' : '')));
  body.appendChild(st);
  box.replaceChildren(body);
}
function scrollTo_(id) {
  const m = document.querySelector('#doc mark[data-ids~="' + id + '"]')
    || [...document.querySelectorAll('#doc mark')].find(x => (x.dataset.ids || '').split(',').indexOf(id) >= 0);
  if (!m) return;
  if (m.scrollIntoView) m.scrollIntoView({block: 'center', behavior: 'smooth'});
  m.classList.add('flash'); setTimeout(() => m.classList.remove('flash'), 1200);
}
function select(id, scroll) {
  sel = id; markSel(); renderInsp();
  if (scroll !== false && PBY[id] && PBY[id].ranges.length) scrollTo_(id);
}

renderDoc(); renderStrip(); renderInsp();
document.addEventListener('keydown', ev => {
  if (/^(INPUT|TEXTAREA)$/.test((ev.target.tagName || '').toUpperCase())) return;
  if (ev.key === 'Escape') { sel = null; markSel(); renderInsp(); return; }
  if (ev.key !== 'j' && ev.key !== 'k') return;
  const i = ORDER.indexOf(sel);
  const n = ev.key === 'j' ? (i + 1) % ORDER.length : (i <= 0 ? ORDER.length - 1 : i - 1);
  select(ORDER[n]);
});
</script></body></html>
'''

if __name__ == "__main__":
    main()
