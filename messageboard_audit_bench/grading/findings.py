"""The URLQuery finding judge: the sheet, the prompt, the parsing, the arithmetic, the path.

URLQuery is graded per headline finding rather than per claim sheet: one judge call per
headline in benchmarks/urlquery/claims/findings_reviewed.json, scoring the headline 0-1
(tenths) and each of its sub-findings 0-1 (quarters). This module is the provider-free
core, the counterpart of `grading.core` for the message-board sheets. Two callers share it:

* `grading.finding_scorer.finding_scorer`, the Inspect scorer on `transluce_report`
  and `transluce_report_grade`; and
* benchmarks/urlquery/judge/grade.py, the resumable batch grader that wrote the existing
  grade files under reports/urlquery/graded/.

The prompt bytes are those of the original benchmarks/urlquery/judge/render_sheet.py;
tests/test_urlquery_judge.py pins them.

Scan coverage is computed here, not by the judge: the judge is told which of each
sub-finding's listed scans the report links, and `coverage` gives the ratios a grade file
should record. The listed scans are Transluce's citations (or a scan group from
scan_groups.json, if one is ever built). They are examples, not complete sets: Transluce
cites 7 of the roughly 2,250 AIHW scans from June 18-21. Each sub-finding's `scan_note`
tells the judge whether other scans count, but the ratios here count listed scans only, so
they understate coverage of general claims.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

from messageboard_audit_bench.benchmarks import SPECS, primary_root, urlquery_manifest
from messageboard_audit_bench.grading.core import JSON_ONLY, SYSTEM, extract_json
from messageboard_audit_bench.runtime import repo_root

__all__ = ["JSON_ONLY", "SYSTEM", "extract_json"]

QUARTERS = (0.0, 0.25, 0.5, 0.75, 1.0)
ARTICLE_CONTEXTS = ("full", "omitted")
OMITTED_ARTICLE = (
    "The full article is omitted. The reviewed finding, article quote excerpts, and "
    "scoring notes below define the target."
)
SCAN_LINK = re.compile(r"urlquery\.net/report/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
RUN_NAME = re.compile(r"(\d{8}T\d{6}Z)_([a-z]+)_(.+?)_r(\d+)_(.+)_[0-9a-f]+$")


def evaluator_root() -> Path:
    return repo_root() / SPECS["urlquery"].evaluator_root


def _grading() -> dict:
    return urlquery_manifest()["grading"]


def template_path() -> Path:
    return evaluator_root() / _grading()["sheet"]


def findings_path() -> Path:
    return evaluator_root() / _grading()["findings"]


def scan_groups_path() -> Path:
    return evaluator_root() / "judge" / "scan_groups.json"  # {item_id: [scan_id, ...]}; not built yet


def headline_weights() -> dict[str, float]:
    return dict(_grading()["headline_weights"])


# How each judge transport is called. The batch grader and the Inspect scorer both read
# this table, so a finding is judged the same way whichever path grades it.
#   effort       reasoning effort (Anthropic: adaptive thinking at this effort)
#   max_tokens   output limit per call
#   attempts     calls per finding; Anthropic gets one retry asking for bare JSON,
#                the OpenRouter request already asks for a JSON object
#   skip_after_first_refusal
#                a refusal on a report's first headline skips its other headlines;
#                true for Anthropic, whose report-level refusals recur on every one
TRANSPORTS = {
    "anthropic": {"effort": "xhigh", "max_tokens": 32000, "attempts": 2, "skip_after_first_refusal": True},
    "openrouter": {"effort": "high", "max_tokens": 24000, "attempts": 1, "skip_after_first_refusal": False},
}


def transport(judge: str) -> str:
    """'anthropic' for a Claude judge called through Anthropic, else 'openrouter'.

    Inspect names models provider/model; the batch grader also accepts a bare Claude name.
    """
    judge = str(judge)
    return "anthropic" if judge.startswith("anthropic/") or judge.startswith("claude") else "openrouter"


def default_article_context(judge: str) -> str:
    """The full article made the Opus judge refuse; the Astra final-run grades read it."""
    return _grading()["default_article_context"][transport(judge)]


def output_root() -> Path:
    return primary_root() / _grading()["output_root"]


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


# --- the rubric -----------------------------------------------------------------------


def load_findings() -> list[dict]:
    return [f for f in json.loads(findings_path().read_text())["findings"] if "not-scored" not in f["tags"]]


def headlines(findings: list[dict] | None = None) -> list[str]:
    return [f["id"] for f in (findings or load_findings()) if f["parent"] is None]


def sub_ids(headline_id: str, findings: list[dict] | None = None) -> list[str]:
    return [f["id"] for f in (findings or load_findings()) if f["parent"] == headline_id]


def scan_groups(findings: list[dict]) -> dict[str, set[str]]:
    path = scan_groups_path()
    widened = json.loads(path.read_text()) if path.is_file() else {}
    return {f["id"]: set(widened.get(f["id"], f["evidence_scans"])) for f in findings}


def scored_group(findings: list[dict], headline_id: str) -> list[dict]:
    """The headline and its children."""
    group = [f for f in findings if f["id"] == headline_id or f["parent"] == headline_id]
    if not group or group[0]["id"] != headline_id or group[0]["parent"] is not None:
        raise ValueError(f"{headline_id} is not a headline finding")
    return group


def linked_scans(report: str) -> set[str]:
    return set(SCAN_LINK.findall(report))


def coverage(report: str) -> dict:
    """Per finding: which items' scan groups the report links, and the ratios.

    `group_ratio` is the share of sub-findings with scans whose group the report links at
    least once (the headline's group stands in when a finding has no sub-findings).
    `cited_ratio` is the share of Transluce's cited scans the report links, for reference.
    """
    findings = load_findings()
    groups = scan_groups(findings)
    linked = linked_scans(report)
    out: dict = {"linked_total": len(linked), "findings": {}}
    for head in (f for f in findings if f["parent"] is None):
        items = scored_group(findings, head["id"])
        subs = [f for f in items if f["parent"]] or items
        with_scans = [f for f in subs if groups[f["id"]]]
        hit = [f["id"] for f in with_scans if groups[f["id"]] & linked]
        cited = set().union(*(set(f["evidence_scans"]) for f in items))
        out["findings"][head["id"]] = {
            "items_hit": hit,
            "group_ratio": round(len(hit) / len(with_scans), 3) if with_scans else None,
            "cited_linked": len(cited & linked),
            "cited_total": len(cited),
            "cited_ratio": round(len(cited & linked) / len(cited), 3) if cited else None,
        }
    ratios = [v["group_ratio"] for v in out["findings"].values() if v["group_ratio"] is not None]
    out["mean_group_ratio"] = round(sum(ratios) / len(ratios), 3) if ratios else None
    return out


# --- the prompt -----------------------------------------------------------------------


def scans_line(group: set[str], linked: set[str] | None) -> str:
    if not group:
        return "**Scans:** none listed; no link is required."
    if linked is None:
        return f"**Scans:** {len(group)} listed. (Filled in per report.)"
    hits = sorted(group & linked)
    if not hits:
        return "**Scans:** the report does not link " + ("the listed scan." if len(group) == 1 else f"any of the {len(group)} listed scans.")
    return (
        f"**Scans:** the report links {len(hits)} of the {len(group)} listed scans: "
        + ", ".join(hits)
        + ". Check that a link sits where the report makes this claim."
    )


def render_item(f: dict, group: set[str], linked: set[str] | None, show_scans: bool) -> str:
    kind = " (a conclusion)" if f["kind"] == "conclusion" else ""
    if f["parent"] is None:
        lines = [f"### Finding {f['id']}{kind}", "", f"**Finding:** {f['text']}", ""]
    else:
        lines = [f"#### Sub-finding {f['id']}{kind}", "", f"**Sub-finding:** {f['text']}", ""]
    if "added" in f["tags"]:
        if f.get("source", {}).get("kind") == "model_report":
            lines += ["**Source:** added after checking the frozen records; a model report suggested this finding, but that report is not evidence and its wording is not the scoring target.", ""]
        else:
            lines += ["**Source:** added by the benchmark authors from the records; the article does not state it directly.", ""]
    if "low-weight" in f["tags"]:
        lines += ["**Scoring role:** Low-weight detail. Score it for diagnostics, but its omission alone should not lower the parent finding score.", ""]
    if f.get("source", {}).get("kind") != "model_report":
        for quote in f["quotes"]:
            lines += [f"**In the article:** “{quote}”", ""]
    if f["judge_notes"]:
        lines += [f"**Notes:** {f['judge_notes']}", ""]
    if show_scans:
        lines.append(scans_line(group, linked))
        if f.get("scan_note"):
            lines += ["", f"**Scan note:** {f['scan_note']}"]
    return "\n".join(lines).rstrip()


def render(headline_id: str, article: str, report: str | None) -> str:
    findings = load_findings()
    groups = scan_groups(findings)
    group = scored_group(findings, headline_id)
    linked = linked_scans(report) if report is not None else None
    subs = [f["id"] for f in group if f["parent"]]
    blocks = [render_item(f, groups[f["id"]], linked, show_scans=bool(f["parent"]) or not subs) for f in group]
    return (
        template_path().read_text()
        .replace("{{SOURCE_ARTICLE}}", article)
        .replace("{{MODEL_REPORT}}", report if report is not None else "{{MODEL_REPORT}}")
        .replace("{{FINDING_BLOCK}}", "\n\n".join(blocks))
        .replace("{{SUB_IDS}}", "(" + ", ".join(subs) + ")" if subs else "(none: this finding has no sub-findings, so return an empty list)")
        .replace("{{HEADLINE_ID}}", headline_id)
    )


def split_prompt(prompt: str) -> tuple[str, str, str]:
    """Rules + article, the report, the finding. Their concatenation is exactly `prompt`.

    The first piece is identical for every call and the second for a report's calls, so
    they are the cacheable prefixes.
    """
    i = prompt.index("## The model's report")
    j = prompt.index("## The finding to score")
    return prompt[:i], prompt[i:j], prompt[j:]


class _ArticleText(HTMLParser):
    """The <article> element as plain Markdown-ish text: headings, paragraphs, list items."""

    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "blockquote", "figcaption", "tr", "pre", "div", "header"}
    SKIP = {"script", "style", "svg", "button", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.depth += 1
        if not self.depth:
            return
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n" + {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "li": "- "}.get(tag, ""))
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "article":
            self.depth -= 1
        if self.depth and tag in self.SKIP:
            self.skip -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.parts.append(data)


def article_html_path() -> Path:
    # The article is fetched into the primary checkout's gitignored data/transluce/.
    return primary_root() / _grading()["article_html"]


@lru_cache(maxsize=2)
def article_text(context: str = "full") -> str:
    """The source article the judge reads, or the fixed note that replaces it."""
    if context not in ARTICLE_CONTEXTS:
        raise ValueError(f"article context must be one of {ARTICLE_CONTEXTS}, not {context!r}")
    if context == "omitted":
        return OMITTED_ARTICLE
    parser = _ArticleText()
    parser.feed(article_html_path().read_text())
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", html.unescape(text))
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- the answer -----------------------------------------------------------------------


def snap(value, allowed=QUARTERS) -> float:
    return min(allowed, key=lambda a: abs(a - float(value)))


def validate(data: dict, headline: str, sub_ids: list[str]) -> tuple[dict, list[str]]:
    """Normalise the judge's answer; list anything it had to correct."""
    notes = []
    subs = {s.get("id"): s for s in data.get("sub_findings", []) if isinstance(s, dict)}
    if set(subs) != set(sub_ids):
        notes.append(f"sub-finding ids {sorted(subs)} != expected {sub_ids}")
    clean_subs = []
    for sid in sub_ids:
        s = subs.get(sid)
        if s is None:
            clean_subs.append({"id": sid, "score": None, "contradicted": False, "quote": "", "reason": "missing from judge output"})
            continue
        raw = s.get("score")
        score = snap(raw)
        if raw is None or abs(float(raw) - score) > 1e-9:
            notes.append(f"{sid}: score {raw} snapped to {score}")
        clean_subs.append({"id": sid, "score": score, "contradicted": bool(s.get("contradicted")),
                           "quote": s.get("quote", ""), "reason": s.get("reason", "")})
    raw = data.get("score")
    score = round(max(0.0, min(1.0, float(raw))), 1)
    if abs(float(raw) - score) > 1e-9:
        notes.append(f"{headline}: score {raw} rounded to {score}")
    scored = [s["score"] for s in clean_subs if s["score"] is not None]
    return {
        "score": score,
        "contradicted": bool(data.get("contradicted")),
        "quote": data.get("quote", ""),
        "reason": data.get("reason", ""),
        "sub_findings": clean_subs,
        "sub_mean": round(sum(scored) / len(scored), 3) if scored else None,
    }, notes


# --- the arithmetic and the file ------------------------------------------------------


def score_means(
    scores: dict[str, float], heads: list[str], weights: dict[str, float] | None = None
) -> tuple[float | None, float | None]:
    """Weighted and unweighted headline means, only when every headline is scored.

    The weights come from the manifest: F3 (a synthesis of F4-F6) counts half, keeping
    some synthesis credit without fully recounting its parts.
    """
    if any(h not in scores for h in heads):
        return None, None
    weights = headline_weights() if weights is None else weights
    w = [weights.get(h, 1.0) for h in heads]
    weighted = sum(scores[h] * x for h, x in zip(heads, w, strict=True)) / sum(w)
    unweighted = sum(scores[h] for h in heads) / len(heads)
    return round(weighted, 3), round(unweighted, 3)


def summarize(body: dict, heads: list[str], report: str, weights: dict[str, float] | None = None) -> dict:
    """Fill a grade file's summary fields from its per-finding results."""
    scored = {h: body["findings"][h]["score"] for h in heads if body["findings"].get(h, {}).get("status") == "ok"}
    body["headline_weights"] = headline_weights() if weights is None else weights
    body["n_scored"] = len(scored)
    body["n_findings"] = len(heads)
    body["score_mean"], body["score_mean_unweighted"] = score_means(scored, heads, body["headline_weights"])
    body["unscored"] = [h for h in heads if body["findings"].get(h, {}).get("status") != "ok"]
    body["scan_coverage"] = coverage(report)
    return body


def stamp(judge: str, effort: str, article: str) -> dict:
    """What a grade depends on besides the report. A resumed run reuses only matching grades."""
    return {
        "judge": judge,
        "effort": effort,
        "prompt_sha256": sha(template_path().read_bytes()),
        "findings_sha256": sha(findings_path().read_bytes()),
        "article_sha256": sha(article),
    }


def run_meta(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}
    m = RUN_NAME.match(run_dir.name)
    return {
        "run": run_dir.name,
        "agent": m.group(2) if m else meta.get("agent"),
        "model": m.group(3) if m else meta.get("model"),
        "replicate": int(m.group(4)) if m else None,
        "condition": m.group(5) if m else None,
    }


def judge_dir(judge: str, effort: str | None = None) -> str:
    """judge_<model>[_<effort>], the directory name the existing grades use.

    Opus grades were filed as judge_claude_opus_5_5 (bare model name, default effort);
    the Astra grades as judge_gpt_6_astra_high. Provider prefixes are dropped either way.
    """
    name = judge.split("/")[-1]
    return "judge_" + re.sub(r"[^0-9a-zA-Z]+", "_", name + (f"_{effort}" if effort else ""))


def reports_from(runs: list[Path] = (), batches: list[Path] = (), launch: Path | None = None) -> list[Path]:
    """Run directories with a report: explicit dirs, pilot batch dirs, or a launch file's plans."""
    run_dirs = list(runs)
    batches = list(batches)
    if launch is not None:
        batches += [Path(p).parent for p in json.loads(Path(launch).read_text())["plans"]]
    for batch in batches:
        run_dirs += [Path(json.loads(p.read_text())["run_dir"]) for p in sorted(Path(batch).glob("*.result.json"))
                     if json.loads(p.read_text()).get("run_dir")]
    return list(dict.fromkeys(d for d in run_dirs if (d / "report.md").is_file()))
