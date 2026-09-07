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
    # <config>=<dir>:<prefix>, or <config>@<budget>=<dir>:<prefix> where a round runs
    # several budgets under one config name and they must not share a directory
    specs = {}
    for a in sys.argv[2:]:
        sel, rest = a.split("=", 1)
        out, prefix = rest.split(":", 1)
        cfg, _, budget = sel.partition("@")
        specs[(cfg, int(budget) if budget else None)] = (out, prefix)
    def read(rel):
        if from_git:
            return subprocess.run(["git", "show", f"{from_git}:{raw}/{rel}"], cwd=ROOT,
                                  capture_output=True, check=True).stdout
        return (src / rel).read_bytes()

    rows = [json.loads(l) for l in read("index.jsonl").decode().splitlines() if l.strip()]
    staged: dict[Path, dict] = {}
    for r in rows:
        key = (r["config"], r.get("budget_min"))
        spec = specs.get(key) or specs.get((r["config"], None))
        if spec is None:
            continue
        out, prefix = spec
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
        # a budget can hold two runs of the same model under different prompts; keep both
        # by naming the prompt rather than letting one silently win
        if dest in staged or (dest.exists() and dest.read_bytes() != (src / r["report"]).read_bytes()
                              if not from_git else dest in staged):
            other = staged.get(dest)
            if other is not None and other.get("prompt_id") == r.get("prompt_id"):
                sys.exit(f"collision: {dest.name} <- {r['report']} and {other['report']}")
            name += f"__p{r.get('prompt_id', '?')}"
            if other is not None:
                alt = GRADED_INPUTS / out / f"{Path(staged[dest]['graded_input']).stem}__p{other.get('prompt_id','?')}.md"
                alt.write_bytes(read(other["report"])); other["graded_input"] = alt.name
                staged[alt] = other; del staged[dest]; dest.unlink(missing_ok=True)
            dest = GRADED_INPUTS / out / f"{name}.md"
        data = read(r["report"])
        if dest.exists() and dest.read_bytes() != data:
            sys.exit(f"refusing to overwrite {dest} with different content")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        r["graded_input"] = dest.name
        staged[dest] = r
    for (cfg, _b), (out, prefix) in specs.items():
        d = GRADED_INPUTS / out
        sel = sorted(((p.name, r) for p, r in staged.items() if p.parent == d), key=lambda x: x[0])
        (d / "_index.jsonl").write_text("".join(json.dumps(dict(r, graded_input=n)) + "\n" for n, r in sel))
        print(f"{cfg} -> {out}/ ({prefix}__*): {len(sel)} reports")


if __name__ == "__main__":
    main()
