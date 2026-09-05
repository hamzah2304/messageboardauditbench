"""Canonical repo paths.

Every build/grading script resolves its inputs through this module so the repo
works from a plain clone. Import it from anywhere in the tree:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from paths import CLAIMS, RUBRICS, GRADED
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- benchmark ground truth ---
BENCH = ROOT / "benchmark"
HUMAN_REPORT = BENCH / "human_report.txt"      # the human incident report (answer key)
CLAIMS = BENCH / "claims"                      # claims.json, new_claims*.json, claim_matching.json
FEASIBILITY = BENCH / "feasibility"            # feasibility{,_verbatim,_compare}.json + batches
RUBRICS = BENCH / "rubrics"                    # rubric_N.{md,json}, rubrics_all.*, judge prompts
GRADED = BENCH / "graded"                      # graded_*.json, precision_*.json
GRADED_INPUTS = BENCH / "graded_inputs"        # the exact reports each grade corresponds to
PROMPTS = BENCH / "prompts"
SNIPPETS = BENCH / "snippets"

# --- harness / corpus ---
DATA = ROOT / "data"                           # gitignored; scripts/build_data.sh
CORPUS = ROOT / "corpus"                       # raw message-board exports
REPORTS = ROOT / "reports"                     # model report corpus
CONFIGS = ROOT / "configs"

# --- viewers ---
VIEWERS = ROOT / "viewers"                     # build_*.py; generated .html is gitignored
VIEWER_DATA = VIEWERS / "data"

ENV_FILE = ROOT / ".env"
