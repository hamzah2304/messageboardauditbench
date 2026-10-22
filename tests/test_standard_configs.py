"""The standard condition: one shared file, one generated config per eval and budget."""
import subprocess
import sys
from pathlib import Path

import pytest

from slopvestigator_bench import benchmarks, standard
from slopvestigator_bench.configs import load_config

ROOT = Path(__file__).parents[1]
SHARED = ("effort", "min_runtime_fraction", "memory_limit", "subagents", "claude_cli_version",
          "codex_cli_version", "claude_disallowed_tools", "runtime_notice", "report_accept_min_words",
          "safeguard_retry_limit", "safeguard_retry_message")


def test_generated_configs_are_current():
    result = subprocess.run([sys.executable, "scripts/standard_configs.py", "--check"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("benchmark_id", ["messageboard", "urlquery", "aivillage"])
def test_each_eval_registers_and_loads_its_standard_configs(benchmark_id):
    names = standard.config_names(benchmark_id)
    assert len(names) == 2 and set(names) <= set(benchmarks.config_names(benchmark_id))
    for name, budget in zip(names, (10, 30)):
        cfg = load_config(name, benchmark_id)
        assert cfg["benchmark_id"] == benchmark_id
        assert (cfg["budget_min"], cfg["timeout_min"]) == (budget, budget + 5)


def test_the_shared_settings_are_identical_across_evals():
    configs = [load_config(standard.config_name(b, 30), b) for b in ("messageboard", "urlquery", "aivillage")]
    for key in SHARED:
        assert len({repr(c[key]) for c in configs}) == 1, key
    assert configs[0]["effort"] == "medium" and configs[0]["min_runtime_fraction"] == 0.9
    assert configs[0]["subagents"] is False and {"Task", "Agent"} <= set(configs[0]["claude_disallowed_tools"])


def test_one_judge():
    assert standard.judge() == ("openai/gpt-6.1-sol", "high")


@pytest.mark.parametrize("name", [standard.config_name(b, m) for b in standard.benchmark_ids()
                                  for m in standard.standard()["shared"]["budgets"]])
def test_the_shell_runners_parser_reads_every_generated_config_unchanged(name):
    """scripts/read_config.py is a regex parser (no quotes or '#' inside values); it must read the
    generated files exactly as tomllib does."""
    import tomllib

    sys.path.insert(0, str(ROOT / "scripts"))
    from read_config import load

    path = ROOT / "configs" / f"{name}.toml"
    exact, parsed = tomllib.loads(path.read_text()), load(str(path))
    assert parsed.keys() == exact.keys()
    for key, value in exact.items():
        assert (float(parsed[key]) if isinstance(value, float) else parsed[key]) == value, key
