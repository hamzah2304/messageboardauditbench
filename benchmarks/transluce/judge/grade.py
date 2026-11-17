"""Grade URLQuery reports against the Transluce answer key: scripts/grade_answer_key.py for Transluce.

    uv run python benchmarks/transluce/judge/grade.py RUN_DIR [RUN_DIR ...] [--workers 8]

Kept so the commands and presets that used this path (grade_openrouter.py) still work; every
benchmark's batch grading is scripts/grade_answer_key.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.grade_answer_key import (  # noqa: E402, F401 — re-exported for older callers
    DEFAULT_EFFORT,
    DEFAULT_JUDGE,
    PRICES,
    SYSTEM,
    TRANSPORTS,
    Judge,
    extract_json,
    main,
    parser,
    provider_of,
    run_meta,
    sha,
    split_blocks,
    transport_of,
    validate,
)

if __name__ == "__main__":
    main()
