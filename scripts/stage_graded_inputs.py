#!/usr/bin/env python3
"""Stage a round's reports into benchmark/graded_inputs/<dir>/ for `grade_with_rubrics.py --dir <dir>`.

    scripts/stage_graded_inputs.py reports/round3 \
        blind-10=round3_blind10:r3b10 blind-30=round3_blind30:r3b30 blind-120=round3_blind120:r3b120

Each `<config>=<out dir>:<key prefix>` spec selects that config's rows from the round's
index.jsonl and copies every report byte-for-byte to
    <prefix>__<agent>__<model>__rep<n>[__served-<model>][__partial].md
(slashes in model names become dashes). A round that lives on another branch can be read
straight from it by passing `<git ref>:<path>` instead of a directory. The grader keys its
output on the sanitized stem,
so the prefix must be unique per round and budget. `_index.jsonl` in each out dir carries
the selected index rows plus `graded_input`, the staged filename. Refuses to overwrite a
staged file whose content differs.
"""
import json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import GRADED_INPUTS, ROOT


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    raw = sys.argv[1]
    from_git = None
    if ":" in raw and not Path(raw).exists():        # <git ref>:<path>, e.g. origin/branch:reports/round4
        from_git, raw = raw.split(":", 1)
    src = Path(raw) if Path(raw).is_absolute() else ROOT / raw
    specs = {}
    for a in sys.argv[2:]:
        cfg, rest = a.split("=", 1)
        out, prefix = rest.split(":", 1)
        specs[cfg] = (out, prefix)
    def read(rel):
        if from_git:
            return subprocess.run(["git", "show", f"{from_git}:{raw}/{rel}"], cwd=ROOT,
                                  capture_output=True, check=True).stdout
        return (src / rel).read_bytes()

    rows = [json.loads(l) for l in read("index.jsonl").decode().splitlines() if l.strip()]
    staged: dict[Path, dict] = {}
    for r in rows:
        if r["config"] not in specs:
            continue
        out, prefix = specs[r["config"]]
        model = str(r["model"]).replace("/", "-")
        name = f"{prefix}__{r['agent']}__{model}__rep{r['replicate']}"
        # some rounds record model_served even when nothing switched; only a real
        # fallback belongs in the name
        served = r.get("model_served")
        if served and str(served) != str(r["model"]):
            name += f"__served-{str(served).replace('/', '-')}"
        if r.get("partial"):
            name += "__partial"
        dest = GRADED_INPUTS / out / f"{name}.md"
        if dest in staged:
            sys.exit(f"collision: {dest.name} <- {r['report']} and {staged[dest]['report']}")
        data = read(r["report"])
        if dest.exists() and dest.read_bytes() != data:
            sys.exit(f"refusing to overwrite {dest} with different content")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        staged[dest] = r
    for cfg, (out, prefix) in specs.items():
        d = GRADED_INPUTS / out
        sel = sorted(((p.name, r) for p, r in staged.items() if p.parent == d), key=lambda x: x[0])
        (d / "_index.jsonl").write_text("".join(json.dumps(dict(r, graded_input=n)) + "\n" for n, r in sel))
        print(f"{cfg} -> {out}/ ({prefix}__*): {len(sel)} reports")


if __name__ == "__main__":
    main()
