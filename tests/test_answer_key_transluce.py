"""The Transluce answer key (answer-key-v1) rebuilds the v1.0 reviewed findings byte for byte, so
the grader that now reads it sends the judge the same prompts, weights and resume hash."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from slopvestigator_bench import answer_key
from slopvestigator_bench.answer_key_transluce import to_transluce
from slopvestigator_bench.grading import findings as fj

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/transluce/claims/findings_reviewed.json"


def test_written_key_is_current_and_valid():
    result = subprocess.run([sys.executable, "scripts/transluce/convert_answer_key.py", "--check"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert answer_key.validate(answer_key.load(fj.answer_key_path())) == []


def test_key_rebuilds_the_reviewed_file_byte_for_byte():
    key = answer_key.load(fj.answer_key_path())
    assert json.dumps(to_transluce(key), indent=1, ensure_ascii=False) + "\n" == SOURCE.read_text()


def test_grader_inputs_are_unchanged():
    legacy = [f for f in json.loads(SOURCE.read_text())["findings"] if "not-scored" not in f["tags"]]
    assert fj.load_findings() == legacy
    assert fj.stamp("j", "e", "a")["findings_sha256"] == fj.sha(SOURCE.read_bytes())
    key = answer_key.load(fj.answer_key_path())
    minor = {f["id"] for f in key["findings"] if f["significance"] == "minor"}
    assert minor == set(fj.headline_weights()) == {"F3"}
    for finding in key["findings"]:
        for sub in finding["subfindings"]:
            assert (sub["significance"] == "minor") == ("low-weight" in sub["fields"]["tags"])
