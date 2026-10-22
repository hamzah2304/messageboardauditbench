#!/usr/bin/env python3
"""Write benchmarks/transluce/answer-key.json (answer-key-v1) from the reviewed findings.

    uv run python scripts/transluce/convert_answer_key.py           # write it
    uv run python scripts/transluce/convert_answer_key.py --check   # exit 1 if the written key is stale

The source is benchmarks/transluce/claims/findings_reviewed.json, the v1.0 rubric; headline weights
come from benchmark.json (F3 weighs half and is the one minor headline).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from slopvestigator_bench import answer_key  # noqa: E402
from slopvestigator_bench.answer_key_transluce import SOURCE, from_transluce  # noqa: E402
from slopvestigator_bench.grading import findings  # noqa: E402


def main() -> int:
    key = from_transluce(json.loads((ROOT / SOURCE).read_text()), findings.headline_weights())
    if problems := answer_key.validate(key):
        raise SystemExit("; ".join(problems))
    text = json.dumps(key, ensure_ascii=False, indent=1) + "\n"
    path = findings.answer_key_path()
    if "--check" in sys.argv:
        if not path.is_file() or path.read_text() != text:
            print(f"stale: {path}", file=sys.stderr)
            return 1
        return 0
    path.write_text(text)
    print(f"wrote {path.relative_to(ROOT)}: {len(key['findings'])} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
