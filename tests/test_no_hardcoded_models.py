"""Models, judges and helper models come from configuration, not from code.

configs/lineup.toml names the models that run, configs/standard.toml the judge and the helper
scripts' models ([helpers]). This test fails on a model name in Python string literals
(docstrings and comments skipped) or in shell code outside comments, except where a file uses
model names as data, not as a choice of which model to call. Each exception says why.
"""
from __future__ import annotations

import io
import re
import subprocess
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = re.compile(
    r"\b(claude-(opus|sonnet|haiku|fable)[-0-9.]*|gpt-[0-9][-0-9a-z.]*|gemini-[0-9][-0-9a-z.]*|kimi-k[0-9]+"
    r"|glm-[0-9.]+|deepseek-v[0-9]|muse-(spark|wonder)|grok-[0-9]|qwen[0-9])"
)
# Whole files whose model names are data.
ALLOWED_FILES = {
    "scripts/viewers/": "display names, colours and which recorded grades a figure shows",
    "scripts/make_report_artifact.py": "display names for recorded runs",
    "scripts/aivillage/aivillage_run_costs.py": "prices of the models in recorded runs",
    "scripts/aivillage/aivillage_batch.sh": "the model list of the AI Village v1.0 batch (published runs)",
    "scripts/run_followup.sh": "the round-4 systems the follow-up continues (published runs)",
    "benchmarks/transluce/judge/grade_openrouter.py": "preset that reproduces the v1.0 grades with their judge",
    "benchmarks/transluce/judge/grade_openai_batch.py": "reproduces the v1.0 judge; filters recorded runs by model",
    "benchmarks/transluce/judge/grade_openai_sync.py": "orders recorded runs by the model they used",
    "sandbox/llm_scan.py": "a tool inside the sandbox, which has no access to configs/",
}
# Single assignments whose model names are data: (file, start of the line).
ALLOWED_LINES = {
    ("scripts/synthesise_report.py", "EXCLUDE ="): "which recorded round-4 reports the synthesis leaves out",
    ("benchmarks/transluce/judge/grade.py", "PRICES ="): "API prices for cost reporting",
    ("slopvestigator_bench/grading/core.py", "ROOT_GRADES_JUDGE ="): "names the judge whose grades sit at graded/ (storage layout)",
    ("slopvestigator_bench/grading/aivillage.py", "MODEL ="): "the v1.0 judge the batch grader's frozen plans check against",
    ("scripts/score_reports.py", '"    # figures used Fable'): "a hint naming the published judge",
    ("scripts/e2e_smoke.sh", '[ -n "${MODEL:-}" ]'): "an example in the usage message",
    ("benchmarks/aivillage/extraction/discord_extract_sample_run.py", "'pricing_url'"): "a pricing link",
    ("benchmarks/aivillage/extraction/discord_screen_run.py", '"model": MODEL'): "a pricing link",
}


def _allowed(name: str, line: str) -> bool:
    if any(name.startswith(prefix) for prefix in ALLOWED_FILES):
        return True
    return any(name == f and line.strip().startswith(start) or (name == f and start in line)
               for f, start in ALLOWED_LINES)


def _python_literals(path: Path):
    source = path.read_text()
    lines = source.splitlines()
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    previous = None
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.STRING and MODEL.search(tok.string):
            docstring = (previous is None or previous.type in (tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE)) \
                and tokens[i + 1].type in (tokenize.NEWLINE, tokenize.ENDMARKER)
            if not docstring:
                yield tok.start[0], lines[tok.start[0] - 1]
        if tok.type not in (tokenize.COMMENT, tokenize.NL):
            previous = tok


def _shell_lines(path: Path):
    for number, line in enumerate(path.read_text().splitlines(), 1):
        code = line.split(" #", 1)[0] if not line.lstrip().startswith("#") else ""
        if MODEL.search(code):
            yield number, line


def test_no_model_names_in_code_outside_configs():
    files = subprocess.run(["git", "ls-files", "*.py", "*.sh"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    found = []
    for name in files:
        if name.startswith("tests/"):
            continue
        scan = _python_literals if name.endswith(".py") else _shell_lines
        found += [f"{name}:{number}: {line.strip()[:90]}" for number, line in scan(ROOT / name)
                  if not _allowed(name, line)]
    assert not found, "model names in code; put them in configs/lineup.toml or configs/standard.toml:\n" + \
        "\n".join(found)
