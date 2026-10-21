"""The batch launcher: replicate-major order, and an existing run is never rerun."""
import importlib.util
from pathlib import Path

from slopvestigator_bench import lineup

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("run_matrix", ROOT / "scripts/run_matrix.py")
run_matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_matrix)


def test_replicates_are_spread_over_the_batch():
    order = run_matrix.trials(["messageboard", "aivillage"], [10, 30], ["a", "b"], 3)
    assert [t[0] for t in order] == [1] * 8 + [2] * 8 + [3] * 8


def test_any_existing_run_counts_as_done(tmp_path):
    model = lineup.model("moonshotai/kimi-k3")
    run = tmp_path / "20261021T000000Z_react_moonshotai_kimi-k3_r2_wiki-std-30_abc"
    run.mkdir()
    assert run_matrix.existing(tmp_path, model, "wiki-std-30", 2) == []  # no meta.json yet: still running or died
    (run / "meta.json").write_text('{"launch_status": "preparing"}')      # died before reaching the model
    assert run_matrix.existing(tmp_path, model, "wiki-std-30", 2) == []
    (run / "meta.json").write_text('{"exit_code": 1}')                    # a failed run is a result
    assert run_matrix.existing(tmp_path, model, "wiki-std-30", 2) == [run]
    assert run_matrix.existing(tmp_path, model, "wiki-std-10", 2) == []
