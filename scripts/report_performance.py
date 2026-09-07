#!/usr/bin/env python3
"""Per-report performance under the auditor's strict transform, max(2s - 1, 0).

    scripts/report_performance.py benchmark/graded/judge_claude_opus_5/v2

The rubric scores a point 0 to 1 for how completely the report covers it. Averaging
those raw gives half credit to a report that only gestures at every point. The
transform discards everything at or below the midpoint and rescales the rest, so

    1.0 -> 1.00   0.9 -> 0.80   0.7 -> 0.40   0.5 -> 0.00   0.3 -> 0.00   0.0 -> 0.00

A report's performance is the mean of its transformed point scores. Raw mean is
printed alongside, since the transform changes the ranking as well as the level and
the difference between the two is itself worth reading.
"""
import json, re, statistics as st, sys, collections
from pathlib import Path

RX = re.compile(r"graded_(r(\d)b(\d+))_(claude|codex|react)_(.+?)_rep(\d)(?:_served_(.+))?\.json$")
NAMES = {"gpt_5_6_sol": "GPT-5.6 Sol", "openai_gpt_5_6_sol": "GPT-5.6 Sol", "gpt_5_6_luna": "GPT-5.6 Luna",
         "gpt_5_6_terra": "GPT-5.6 Terra", "gpt_6_astra": "GPT-6 Astra",
         "google_gemini_3_8_flash": "Gemini 3.8 Flash", "meta_muse_spark_1_3": "Muse Spark 1.3",
         "moonshotai_kimi_k3": "Kimi K3", "z_ai_glm_5_3": "GLM 5.3", "claude_opus_5": "Opus 5",
         "claude_opus_4_8": "Opus 4.8", "claude_sonnet_5": "Sonnet 5", "claude_haiku_4_5": "Haiku 4.5",
         "claude_fable_5_1": "Fable 5.1"}


def strict(s):
    return max(2 * s - 1, 0.0)


def load(d):
    rows = []
    for p in sorted(Path(d).glob("graded_*.json")):
        m = RX.search(p.name)
        if not m:
            continue
        g = json.loads(p.read_text())
        vals = [v["score"] for v in g["scores"].values()]
        rows.append({"key": p.stem[len("graded_"):], "round": int(m.group(2)), "budget": int(m.group(3)),
                     "lab": f"{m.group(4)} · {NAMES.get(m.group(5), m.group(5))}", "rep": int(m.group(6)),
                     "served": m.group(7), "grader": g.get("grader"), "rubric": g.get("rubric", "recall"),
                     "raw": st.mean(vals), "strict": st.mean(strict(v) for v in vals),
                     "n": len(vals), "scores": g["scores"]})
    return rows


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rows = load(sys.argv[1])
    if not rows:
        sys.exit(f"no grades in {sys.argv[1]}")
    g = {r["grader"] for r in rows}
    print(f"{len(rows)} reports, {rows[0]['n']} points each, judge {', '.join(sorted(map(str, g)))}, "
          f"rubric {rows[0]['rubric']}\n")
    print(f"{'report':<44}{'raw':>7}{'strict':>8}{'drop':>7}")
    for r in sorted(rows, key=lambda r: -r["strict"]):
        print(f"{r['key']:<44}{r['raw']:>7.3f}{r['strict']:>8.3f}{r['raw']-r['strict']:>7.3f}")
    print(f"\nmean raw {st.mean(r['raw'] for r in rows):.3f}   mean strict {st.mean(r['strict'] for r in rows):.3f}")
    by = collections.defaultdict(list)
    for r in rows:
        if not r["served"]:
            by[r["lab"]].append(r)
    print(f"\n{'harness · model':<26}{'raw':>8}{'strict':>9}{'n':>4}")
    for lab in sorted(by, key=lambda l: -st.mean(x["strict"] for x in by[l])):
        v = by[lab]
        print(f"{lab:<26}{st.mean(x['raw'] for x in v):>8.3f}{st.mean(x['strict'] for x in v):>9.3f}{len(v):>4}")
    # does the transform reorder anything?
    a = [r["key"] for r in sorted(rows, key=lambda r: -r["raw"])]
    b = [r["key"] for r in sorted(rows, key=lambda r: -r["strict"])]
    moved = sum(1 for i, k in enumerate(a) if b.index(k) != i)
    print(f"\nreports whose rank changes under the transform: {moved} of {len(rows)}")
    pts = collections.defaultdict(list)
    for r in rows:
        for cid, s in r["scores"].items():
            pts[cid].append(s["score"])
    dead = [c for c, v in pts.items() if all(strict(x) == 0 for x in v)]
    print(f"points no report scores above 0.5 on (zero under the transform): {sorted(dead) or 'none'}")


if __name__ == "__main__":
    main()
