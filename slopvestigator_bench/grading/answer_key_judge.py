"""The finding judge every benchmark shares: a report graded against its answer key (answer-key-v1).

Every benchmark is graded the same way. There is one judge call per headline finding, with that
finding's own sub-findings; the judge scores each sub-finding 0-1 in quarters and the headline
0-1 in tenths, following one prompt (benchmarks/judge/finding-sheet.md). The call, its retries and
the answer's validation are `grading.finding_scorer.grade_finding` and `grading.findings.validate`.

What a benchmark configures (`SPECS`):

* three prompt modules from benchmarks/judge/modules/: the framing (what was investigated and how
  the key was built), the benchmark's own parts of a finding, and any extra rules;
* the source document the judge reads for context: Transluce's article, the German wiki human
  report, or none (the AI Village);
* the extra material shown on each item: quotes from the source, Transluce's scan links (computed
  per report), the AI Village records;
* how headline scores make the report score. By default it is the mean over headlines, a minor
  headline counting half (Transluce's F3). The AI Village takes the mean of the report's 20 best
  findings (`top_k`), because a report is asked for 20 findings and the key has 96.

Findings the answer-key QA dropped, and sub-findings it did not find in the records, are not graded.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from functools import lru_cache

from slopvestigator_bench.grading import findings as fj
from slopvestigator_bench.runtime import repo_root

TEMPLATE = "benchmarks/judge/finding-sheet.md"
MODULES = "benchmarks/judge/modules"
MINOR_HEADLINE_WEIGHT = 0.5
KEPT_OUTCOMES = {"keep", "narrow"}
KEPT_VERDICTS = {"supported", "partly"}
NO_SUBS = "(none: this finding has no sub-findings, so return an empty list)"


@dataclass(frozen=True)
class Spec:
    name: str
    key: str
    source: str | None  # "article" (Transluce's, from findings.article_text), a file path, or None
    source_title: str = ""
    source_tag: str = ""
    quote_label: str | None = None  # "In the article", ...; None shows no source quotes
    evidence: str | None = None  # "scans" (Transluce links), "records" (AI Village), or None
    top_k: int | None = None  # report score = mean of the best top_k headlines; None = weighted mean

    @property
    def source_stamp(self) -> str:
        return "article_sha256" if self.source == "article" else "source_sha256"


SPECS = {
    "transluce": Spec("transluce", "benchmarks/transluce/answer-key.json", "article",
                      "Transluce's article", "article", "In the article", "scans"),
    "german-wiki": Spec("german-wiki", "benchmarks/german-wiki/answer-key.json",
                        "benchmarks/german-wiki/human_report.txt", "The human report", "human_report",
                        "In the human report"),
    "aivillage": Spec("aivillage", "benchmarks/aivillage/answer-key.json", None, evidence="records", top_k=20),
}


# --- the key --------------------------------------------------------------------------


def load_key(name: str) -> dict:
    from slopvestigator_bench import answer_key

    path = repo_root() / SPECS[name].key
    key = answer_key.load(path)
    if problems := answer_key.validate(key):
        raise ValueError(f"{path}: " + "; ".join(problems[:5]))
    return key


def graded_findings(key: dict) -> list[dict]:
    """The headlines that are graded, each with only the sub-findings that are graded."""
    out = []
    for f in key["findings"]:
        if (f.get("qa") and f["qa"].get("outcome") not in KEPT_OUTCOMES) or "not-scored" in f["fields"].get("tags", []):
            continue
        subs = [s for s in f["subfindings"] if not s.get("qa") or s["qa"].get("verdict") in KEPT_VERDICTS]
        out.append({**f, "subfindings": subs})
    return out


def headline_weights(findings: list[dict]) -> dict[str, float]:
    return {f["id"]: MINOR_HEADLINE_WEIGHT for f in findings if f["significance"] == "minor"}


def key_sha(key: dict) -> str:
    return fj.sha(json.dumps(key, indent=1, ensure_ascii=False) + "\n")


# --- the prompt -----------------------------------------------------------------------


def _module(kind: str, name: str) -> str:
    path = repo_root() / MODULES / f"{kind}-{name}.md"
    return path.read_text().strip() if path.is_file() else ""


def sheet(name: str) -> str:
    """The shared template with the benchmark's modules: everything but the source, report and finding."""
    rules = _module("rules", name)
    return ((repo_root() / TEMPLATE).read_text()
            .replace("{{FRAMING}}", _module("framing", name))
            .replace("{{PARTS}}", _module("parts", name))
            .replace("{{RULES}}", f"\n{rules}\n" if rules else ""))


@lru_cache(maxsize=4)
def source_text(name: str, article_context: str | None = None) -> str | None:
    """The source document the judge reads; Transluce's article may be replaced by a fixed note."""
    spec = SPECS[name]
    if spec.source == "article":
        return fj.article_text(article_context or "full")
    return (repo_root() / spec.source).read_text() if spec.source else None


def _scan_group(item: dict) -> set[str]:
    return {c["ref"].removeprefix("scan:") for e in item["evidence"] for c in e["citations"] if c["ref"].startswith("scan:")}


def render_item(spec: Spec, item: dict, headline: bool, linked: set[str] | None, show_scans: bool) -> str:
    fields = item.get("fields", {})
    kind = " (a conclusion)" if fields.get("kind") == "conclusion" else ""
    label = "Finding" if headline else "Sub-finding"
    lines = [f"{'###' if headline else '####'} {label} {item['id']}{kind}", "", f"**{label}:** {item['claim']}", ""]
    if headline and item.get("detail"):
        lines += [f"**Detail:** {item['detail']}", ""]
    if headline and spec.evidence == "records" and fields.get("behavior_dates"):
        lines += [f"**When:** {fields['behavior_dates']}", ""]
    from_report = fields.get("source", {}).get("kind") == "model_report"
    if "added" in fields.get("tags", []):
        lines += ["**Source:** added after checking the frozen records; a model report suggested this finding, but that report is not evidence and its wording is not the scoring target." if from_report
                  else "**Source:** added by the benchmark authors from the records; the article does not state it directly.", ""]
    if not headline and item["significance"] == "minor":
        lines += ["**Scoring role:** Low-weight detail. Score it for diagnostics, but its omission alone should not lower the parent finding score.", ""]
    if spec.quote_label and not from_report:
        quotes = fields.get("quotes") or ([fields["report_quote"]] if fields.get("report_quote") else [])
        lines += [x for q in quotes for x in (f"**{spec.quote_label}:** “{q}”", "")]
    if item.get("judge_notes"):
        lines += [f"**Notes:** {item['judge_notes']}", ""]
    if spec.evidence == "records" and not headline and item.get("evidence"):
        traces = " Shown only in reasoning traces." if fields.get("needs_reasoning_traces") else ""
        lines += ["**Records:** " + " ".join(e["text"] for e in item["evidence"]) + traces, ""]
    if spec.evidence == "scans" and show_scans:
        lines.append(fj.scans_line(_scan_group(item), linked))
        if fields.get("scan_note"):
            lines += ["", f"**Scan note:** {fields['scan_note']}"]
    return "\n".join(lines).rstrip()


def render_finding(name: str, finding: dict, report: str | None = None) -> str:
    spec = SPECS[name]
    linked = fj.linked_scans(report) if report is not None and spec.evidence == "scans" else None
    subs = finding["subfindings"]
    blocks = [render_item(spec, finding, True, linked, show_scans=not subs)]
    blocks += [render_item(spec, s, False, linked, show_scans=True) for s in subs]
    return "\n\n".join(blocks)


def render(name: str, finding: dict, report: str | None, source: str | None = None,
           variables: dict[str, str] | None = None) -> str:
    """The prompt for one headline. Report text goes in last, so nothing in it is substituted."""
    spec = SPECS[name]
    subs = [s["id"] for s in finding["subfindings"]]
    prompt = (sheet(name)
              .replace("{{FINDING_BLOCK}}", render_finding(name, finding, report))
              .replace("{{SUB_IDS}}", "(" + ", ".join(subs) + ")" if subs else NO_SUBS)
              .replace("{{HEADLINE_ID}}", finding["id"]))
    for var, value in (variables or {}).items():
        prompt = prompt.replace("{{" + var + "}}", value)
    section = (f"\n## {spec.source_title}\n\n<{spec.source_tag}>\n{source}\n</{spec.source_tag}>\n"
               if spec.source and source is not None else "")
    prompt = prompt.replace("{{SOURCE}}", section)
    return prompt.replace("{{MODEL_REPORT}}", report if report is not None else "{{MODEL_REPORT}}")


def report_variables(name: str, data_variant: str | None) -> dict[str, str]:
    """Per-report prompt values: whether the AI Village investigator had reasoning traces."""
    if name != "aivillage":
        return {}
    from slopvestigator_bench.grading.aivillage import reasoning_available

    reasoning = reasoning_available(data_variant or "aivillage/full-v2-reasoning")
    return {"REASONING_CONDITION": "It also had reasoning traces wherever those were present." if reasoning
            else "It did not have reasoning traces."}


# --- the grade ------------------------------------------------------------------------


def stamp(name: str, judge: str, effort: str, source: str | None, key: dict | None = None) -> dict:
    """What a grade depends on besides the report. A resumed batch reuses only matching grades."""
    spec = SPECS[name]
    out = {
        "judge": judge,
        "effort": effort,
        "rubric": "answer-key",
        "prompt_sha256": fj.sha(sheet(name)),
        "findings_sha256": key_sha(key or load_key(name)),
    }
    if spec.source:
        out[spec.source_stamp] = fj.sha(source or "")
    return out


def summarize(name: str, body: dict, heads: list[str], weights: dict[str, float], report: str) -> dict:
    """Fill a grade's summary fields from its per-finding results.

    `score` is the report's score: the weighted mean over headlines, or for a `top_k` benchmark the
    mean of its best `top_k`. It is None unless every headline scored, because a mean over a subset
    is not comparable with a complete one.
    """
    spec = SPECS[name]
    scored = {h: body["findings"][h]["score"] for h in heads if body["findings"].get(h, {}).get("status") == "ok"}
    body["headline_weights"] = weights
    body["n_scored"] = len(scored)
    body["n_findings"] = len(heads)
    body["score_mean"], body["score_mean_unweighted"] = fj.score_means(scored, heads, weights)
    body["unscored"] = [h for h in heads if h not in scored]
    if spec.top_k:
        body["top_k"] = spec.top_k
        body["score_top_k"] = (round(sum(sorted(scored.values(), reverse=True)[:spec.top_k]) / spec.top_k, 3)
                               if len(scored) == len(heads) else None)
    body["score"] = body["score_top_k"] if spec.top_k else body["score_mean"]
    if spec.evidence == "scans":
        body["scan_coverage"] = fj.coverage(report)
    return body


async def grade_report(name: str, model, effort: str, report: str, source: str | None,
                       variables: dict[str, str], findings: list[dict], body: dict) -> dict:
    """Judge every headline of `findings` for one report, into `body["findings"]`, and summarize."""
    from slopvestigator_bench.grading.finding_scorer import grade_finding

    by_id = {f["id"]: f for f in findings}
    heads = list(by_id)

    async def one(h: str) -> None:
        subs = [s["id"] for s in by_id[h]["subfindings"]]
        body["findings"][h] = await grade_finding(model, effort, h, subs, render(name, by_id[h], report, source, variables))

    # The first call warms the shared prefix. For Anthropic, a report-level refusal on it
    # recurs on every finding, so it is kept as unscored rather than repeated.
    await one(heads[0])
    skip = fj.TRANSPORTS[fj.transport(str(model))]["skip_after_first_refusal"]
    if not (skip and body["findings"][heads[0]]["status"] == "refused"):
        await asyncio.gather(*(one(h) for h in heads[1:]))
    return summarize(name, body, heads, headline_weights(findings), report)
