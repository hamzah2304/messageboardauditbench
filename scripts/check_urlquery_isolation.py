#!/usr/bin/env python3
"""Model-free check of the frozen dataset in a credential-free Docker mount."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from messageboard_audit_bench.dataset_manifest import validate_dataset


def check(dataset: Path, image: str):
    dataset = dataset.resolve()
    manifest = validate_dataset(dataset)
    result = subprocess.run([
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "-v", f"{dataset}:/work/data:ro", image,
        "python3", "/sandbox/isolation_preflight.py", "--benchmark", "urlquery",
        "--expected-sha256", manifest["dataset_sha256"]], check=True, capture_output=True, text=True)
    audit = json.loads(result.stdout)
    if not audit["ok"]:
        raise ValueError("Docker input preflight failed")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--image", required=True, help="Exact trial image, including its configured CLI-version suffix")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = check(args.dataset, args.image)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k not in {"files", "visible_files"}}))
