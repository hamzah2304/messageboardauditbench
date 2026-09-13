# Mythos 5 judge sheets (draft)

v2-style accuracy sheets for a candidate second incident: Anthropic's Claude
Mythos 5 cybersecurity transcript
([`anthropics/mythos-5-incident-transcript`](https://github.com/anthropics/mythos-5-incident-transcript)).
Same shape, scale, and scoring rules as the wiki `v2_*` sheets; only the answer
key and the worked examples differ. Rationale and the full derivable/not-derivable
split are in [`docs/mythos5-findings-draft.md`](../../../docs/mythos5-findings-draft.md);
the general recipe this incident follows is
[`docs/adding-an-incident.md`](../../../docs/adding-an-incident.md).

## Files

| file | what it is |
|---|---|
| `claims_m5.json` | the 13 scored points, each with a `report_quote` span from the answer key, a scoring `note`, a `derivable` verdict (`yes`/`partial`), and a `transcript_anchor` — the action number(s) that establish it in the released transcript |
| `mythos5_report.txt` | the answer key: the Mythos 5 sections of the write-up, inserted into each sheet at grading time |
| `m5_1.md` … `m5_3.md` | the judge sheets the grader reads (up to 5 points each) |
| `m5_1.json` … `m5_3.json` | structured form of each sheet |
| `m5_all.md` | all three sheets concatenated |
| `m5tldrh_1.md` / `.json` | holistic score for the report's 200-word summary, limited to the visible transcript |

Rebuild: `python benchmark/rubrics/build_rubrics_m5.py` (reads `claims_m5.json` +
`mythos5_report.txt`, imports the 0–1 scale from `build_rubrics.py` so it can't
drift from v1/v2).

## What these sheets deliberately do NOT score

Only findings **derivable from the released transcript** are here. The transcript's
`index` field is Anthropic's action number; **actions 1–81 and everything after
2145 are redacted**. Excluded, and belonging in a separate calibration set (reward
"not determinable", penalise a confident assertion):

- **told no internet / fictional company** — in the redacted opening brief;
- **15 installs, security-vendor attribution, vendor-DB access, the ~90-minute
  takedown, "three versions", the timed-out ending** — server-side or in the
  redacted tail;
- **every percentage** (79% / 1% / 72% / 56% / 7% …), all **resampling**,
  **follow-up-question**, and **interpretability** (T-lens / NLA) findings —
  produced by experiments the human team ran after the fact, not present in the
  transcript;
- **monitor / classifier results** and **newer-model comparisons** — separate study.

The five `partial` points are derivable in substance but have a specific quantity or
moment in a redacted region; each one's `note` tells the grader what NOT to require.

## Runnable draft

`scripts/build_data.sh` fetches the pinned source and writes only its 2,064 message
records to `data/mythos5/transcript.jsonl`; the release's editorial metadata row is
removed. Run a trial with `-T config=mythos5`; its default graders are `m5` and
`m5tldrh`. See the open questions in the findings draft before treating any number
as comparable to the wiki cells — contamination and judge independence in particular.

For separately staged reports, grade with `-T rubric=m5` and
`-T rubric=m5tldrh`, export both eval logs, then compute the same 70/30 formula:

```bash
uv run python scripts/score_reports.py \
  --findings benchmark/graded/judge_<judge>/m5 \
  --summary benchmark/graded/judge_<judge>/m5tldrh
```
