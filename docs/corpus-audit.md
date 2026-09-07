# Corpus audit

The current direct subscription runner exposes only `/work/prompt.txt` and the
four JSONL files in the configured data variant. Its canary lists those files
and compares the list with the expected mounts before the model starts. The
human report, grading rubrics, prior model reports, repository documentation,
and transformation scripts are not mounted. A successful 120-minute Codex
transcript confirms that `/work` held exactly those four JSONLs and the prompt:
`runs/20260907T080039Z_codex_gpt-6-astra_r1_blind-120_1659fd46a446/transcript.jsonl`.

This is a boundary for the current direct runner, not a claim about historical
runs or every future backend. Each backend needs the same mount audit. Run
metadata should also record a checksum of the data files, not only their
variant name, so completed runs remain attributable after a variant changes.

## Corpus readability

The image provides Python, `jq`, `ripgrep`, and SQLite. An agent can stream or
index all 42,182 records in `raw_stripped` (about 40 MB); there is no sandbox
read cap. Whether a short run manages to analyse all of it is a time-and-method
question, not an access restriction. The current variants are:

| Variant | Records | Difference from stripped data |
|---|---:|---|
| `raw_stripped` | 42,182 | Wiki records after analysis fields are removed |
| `verbatim` | 42,205 | Report-derived requests plus the intentional administrator-impersonation clue |

Use the read-only audit before changing a variant:

```sh
python3 scripts/audit_corpus.py data/raw_stripped
python3 scripts/audit_corpus.py data/verbatim
```

## Intended administrator-impersonation evidence

The existing `verbatim` labels file has 3,104 records. 3,103 have the ordinary
label schema. The remaining row is a zero-revision `Friedrich1982` account with
the unique field `role: administrator`. Five revision labels spell the same
apparent name with Cyrillic U+0435 instead of the first Latin `e`; it occurs in
11 JSONL records overall. `raw_stripped` has no U+0435 records.

This intentionally makes the inference available by scanning for a rare field, a
zero-revision identity, or Unicode confusables. A 120-minute Muse trajectory
does exactly the first: it prints `with role 1` and the administrator row before
investigating the name
(`runs/20260906T212827Z_react_meta_muse-spark-1.3_r3_blind-120_2edab294b693/transcript.jsonl`).
Across 366 parsed historical transcripts, 123 mention the names or
confusable-related terms and 58 contain the exact U+0435 spelling. These are
evidence that models can discover the intended clue from the labels and
revisions, not signs of document leakage.

The name mapping, Latin administrator account, and Cyrillic `е` spelling are
intentional augmentation. The report establishes a look-alike; the exact
letter choice is a designed presentation of that clue. An evaluation should
therefore record how a model found it, rather than treating a Unicode scan as
an accidental leak or as evidence that the model saw an answer key.

## What still needs watching

The report, rubrics, prior reports, and transformation documentation remain
outside the mounted data directory. Preserve that boundary, record the data
checksum in run metadata, and audit each backend's visible file list. Those are
the checks that distinguish discovery of an intended corpus clue from an
unintended disclosure of evaluation materials.
