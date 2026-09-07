#!/usr/bin/env python3
"""Print a small, read-only integrity summary of a benchmark data variant.

Use this before a run when changing a corpus transformation:

    python3 scripts/audit_corpus.py data/verbatim
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def records(path: Path):
    with path.open() as handle:
        for line_number, line in enumerate(handle, 1):
            yield line_number, json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()

    for path in sorted(args.data_dir.glob("*.jsonl")):
        schemas: collections.Counter[tuple[str, ...]] = collections.Counter()
        cyrillic_e: list[tuple[int, dict]] = []
        total = 0
        for line_number, record in records(path):
            total += 1
            schemas[tuple(sorted(record))] += 1
            if "\u0435" in json.dumps(record, ensure_ascii=False):
                cyrillic_e.append((line_number, record))

        print(f"{path.name}: {total} records; {len(schemas)} schemas")
        for schema, count in schemas.most_common():
            uncommon = " [uncommon]" if count < 10 else ""
            print(f"  {count:>6} {', '.join(schema)}{uncommon}")
        for line_number, record in cyrillic_e:
            print(f"  U+0435 at line {line_number}: {record}")


if __name__ == "__main__":
    main()
