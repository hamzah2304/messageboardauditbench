"""The v1.0 Transluce answer key rebuilds the reviewed findings byte for byte, so earlier grades keep
their findings hash; the grader reads the v1.1 key, which keeps v1.0's weights."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from slopvestigator_bench import answer_key
from slopvestigator_bench.answer_key_transluce import V1_0_KEY, to_transluce
from slopvestigator_bench.grading import findings as fj

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/transluce/claims/findings_reviewed.json"


def test_written_key_is_current_and_valid():
    result = subprocess.run([sys.executable, "scripts/transluce/convert_answer_key.py", "--check"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert answer_key.validate(answer_key.load(ROOT / V1_0_KEY)) == []
    assert answer_key.validate(answer_key.load(fj.answer_key_path())) == []


def test_key_rebuilds_the_reviewed_file_byte_for_byte():
    key = answer_key.load(ROOT / V1_0_KEY)
    assert json.dumps(to_transluce(key), indent=1, ensure_ascii=False) + "\n" == SOURCE.read_text()


def test_grader_reads_v1_1_with_v1_0_weights():
    legacy = json.loads(SOURCE.read_text())["findings"]
    findings = fj.load_findings()
    assert {f["id"] for f in findings} <= {f["id"] for f in legacy}
    assert {f["id"] for f in findings if f["parent"] is None} == {f["id"] for f in legacy if f["parent"] is None}
    assert fj.stamp("j", "e", "a")["findings_sha256"] != fj.sha(SOURCE.read_bytes())
    key = answer_key.load(fj.answer_key_path())
    minor = {f["id"] for f in key["findings"] if f["significance"] == "minor"}
    assert minor == set(fj.headline_weights()) == {"F3"}
    for finding in key["findings"]:
        for sub in finding["subfindings"]:
            assert (sub["significance"] == "minor") == ("low-weight" in sub["fields"]["tags"])
