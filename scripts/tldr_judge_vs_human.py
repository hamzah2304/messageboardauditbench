#!/usr/bin/env python3
"""Score a holistic TL;DR judge against a person's labels.

The question is not whether the judge lands on the same number — a judge that reads a
tenth low everywhere is still perfectly useful for ranking reports. So this reports two
things separately: how close the numbers are, on the auditor's own bands (within 0.1 is
approximately equal, 0.2 or more apart is a real disagreement), and whether the judge
orders reports the way the person does.

Pairwise accuracy is the ordering measure. Every pair of reports the person scored 0.2 or
more apart is a preference they actually hold; the judge either reproduces it, ties, or
reverses it. Pairs the person scored within 0.1 are dropped: they express no preference,
so there is nothing there to get right or wrong.

    uv run python scripts/tldr_judge_vs_human.py --judge claude-fable-5-1 --who Hasan
"""
import argparse, json, math, re, statistics as st, sys, pathlib
from itertools import combinations

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, GRADED

SCORES = ROOT / "benchmark" / "audit" / "tldr_human_scores.json"
APPROX, STRICT = 0.1, 0.2


def san(s):
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")


def judge_scores(model, rubric="tldrh"):
    d = GRADED / f"judge_{san(model)}" / rubric
    out = {}
    for p in sorted(d.glob("graded_*.json")):
        g = json.loads(p.read_text())
        if g.get("scores"):
            out[p.stem[len("graded_"):]] = round(float(g["total"]), 3)
    return out


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):          # average ranks within ties
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    return pearson(rank(xs), rank(ys))


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return round(num / den, 3) if den else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default="claude-fable-5-1")
    ap.add_argument("--who", default="Hasan")
    ap.add_argument("--rubric", default="tldrh")
    ap.add_argument("--exclude", default="", help="drop reports whose key contains this "
                    "substring, e.g. haiku — a model far below the rest inflates pairwise "
                    "accuracy, because every pair it is in is an easy one")
    ap.add_argument("--json", help="write the per-report table here")
    a = ap.parse_args()

    human = {k: v["score"] for k, v in
             json.loads(SCORES.read_text())["graders"][a.who]["scores"].items()
             if v.get("score") is not None}
    jud = judge_scores(a.judge, a.rubric)
    pairs = [(k, human[k], jud[san(k)]) for k in sorted(human) if san(k) in jud
             and not (a.exclude and a.exclude.lower() in k.lower())]
    missing = [k for k in human if san(k) not in jud]
    if not pairs:
        raise SystemExit(f"no overlap: {len(human)} human, {len(jud)} judge scores")

    hs = [h for _, h, _ in pairs]
    js = [j for _, _, j in pairs]
    d = [j - h for _, h, j in pairs]
    ad = [abs(x) for x in d]
    approx = sum(1 for x in ad if x <= APPROX + 1e-9)
    strict = sum(1 for x in ad if x >= STRICT - 1e-9)
    print(f"judge {a.judge} ({a.rubric}) vs {a.who} — {len(pairs)} reports"
          + (f", excluding '{a.exclude}'" if a.exclude else "")
          + (f"  [{len(missing)} of {a.who}'s labels have no judge grade]" if missing else ""))
    print(f"  {a.who}: mean {st.mean(hs):.3f}  sd {st.pstdev(hs):.3f}  range {min(hs)}–{max(hs)}")
    print(f"  judge: mean {st.mean(js):.3f}  sd {st.pstdev(js):.3f}  range {min(js)}–{max(js)}")
    print(f"  bias (judge − {a.who}): {st.mean(d):+.3f}   MAE {st.mean(ad):.3f}")
    print(f"  within 0.1 (approximately equal): {approx}/{len(pairs)} = {approx/len(pairs):.1%}")
    print(f"  0.2 or more apart (real disagreement): {strict}/{len(pairs)} = {strict/len(pairs):.1%}")
    print(f"  exact: {sum(1 for x in ad if x < 1e-9)}/{len(pairs)}")
    print(f"  Pearson r {pearson(hs, js)}   Spearman rho {spearman(hs, js)}")

    # --- ordering -------------------------------------------------------------------
    agree = tie = reverse = 0
    for (ka, ha, ja), (kb, hb, jb) in combinations(pairs, 2):
        if abs(ha - hb) < STRICT - 1e-9:
            continue                      # no preference expressed; nothing to be right about
        want = 1 if ha > hb else -1
        got = 0 if abs(ja - jb) < 1e-9 else (1 if ja > jb else -1)
        if got == 0: tie += 1
        elif got == want: agree += 1
        else: reverse += 1
    n = agree + tie + reverse
    print(f"\n  pairwise, over the {n} pairs {a.who} scored {STRICT} or more apart:")
    print(f"    same order   {agree:5d}  {agree/n:.1%}")
    print(f"    tied         {tie:5d}  {tie/n:.1%}")
    print(f"    reversed     {reverse:5d}  {reverse/n:.1%}")
    print(f"    pairwise accuracy  {(agree + tie/2)/n:.1%}  (ties half credit)")
    print(f"    of the pairs it called at all: {agree/(agree+reverse):.1%}" if agree + reverse else "")

    worst = sorted(pairs, key=lambda t: -abs(t[2] - t[1]))[:8]
    print(f"\n  furthest apart:")
    for k, h, j in worst:
        print(f"    {k:52s} {a.who} {h:.1f}  judge {j:.1f}   {j-h:+.1f}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(
            {"judge": a.judge, "who": a.who, "n": len(pairs),
             "rows": [{"key": k, "human": h, "judge": j} for k, h, j in pairs]}, indent=1))


if __name__ == "__main__":
    main()
