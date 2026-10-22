"""The Inspect tasks and the subscription runner give the agent the same trial.

For every standard config, the Inspect prompt is byte-identical to the one run_trial.sh
assembles with its own commands, the minimum-runtime fraction is the config's, and the
settings the sandbox-side hooks read reach the agent's environment on both paths.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

import slopvestigator_bench.task as task_module
from slopvestigator_bench import native, standard
from slopvestigator_bench.configs import load_config

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "sandbox/docker/run_trial.sh").read_text()
STD = [(b, standard.config_name(b, budget)) for b in standard.benchmark_ids()
       for budget in standard.standard()["shared"]["budgets"]]


def _runner_prompt(config: Path, data_dir: Path) -> str:
    """run_trial.sh's prompt assembly, its three commands as written there."""
    script = r'''
set -euo pipefail
eval "$(python3 "$ROOT/scripts/read_config.py" "$CONFIG")"
MIN_RUNTIME_FRACTION="$(python3 "$ROOT/slopvestigator_bench/runtime_policy.py" --validate-fraction "${CFG_MIN_RUNTIME_FRACTION:-0.75}")"
SUBAGENTS_ARG=(); case "$(printf '%s' "${CFG_SUBAGENTS:-}" | tr 'A-Z' 'a-z')" in true) SUBAGENTS_ARG=(--subagents) ;; esac
PROMPT_FILE="$ROOT/sandbox/prompts/$CFG_PROMPT.txt"; BUDGET_MIN="$CFG_BUDGET_MIN"
''' + "\n".join(line for line in RUNNER.splitlines()
                if line.startswith(('python3 "$ROOT/slopvestigator_bench/report_length.py" --template',
                                    'python3 "$ROOT/slopvestigator_bench/runtime_policy.py" --instruction',
                                    '[ -z "${CFG_MEMORY_LIMIT:-}" ] || python3')))
    out = data_dir.parent / "prompt.txt"
    env = {"PATH": os.environ["PATH"], "ROOT": str(ROOT), "CONFIG": str(config), "DATA_DIR": str(data_dir),
           "REPORT_MIN_WORDS": "", "REPORT_MAX_WORDS": "", "PROMPT_OUT": str(out)}
    # The runner sets REPORT_*_WORDS from the config before this point.
    env["REPORT_MIN_WORDS"] = str(load_config(config.stem, _benchmark(config.stem))["report_min_words"])
    env["REPORT_MAX_WORDS"] = str(load_config(config.stem, _benchmark(config.stem))["report_max_words"])
    subprocess.run(["bash", "-c", script], env=env, check=True)
    return out.read_text()


def _benchmark(name: str) -> str:
    return next(b for b, n in STD if n == name)


def _build(benchmark_id: str, name: str, **kwargs):
    build = {"messageboard": task_module.german_wiki_report, "urlquery": task_module.transluce_report,
             "aivillage": task_module.aivillage_report}[benchmark_id]
    return build(config=name, **kwargs)


@pytest.fixture
def small_data(tmp_path, monkeypatch):
    """One data directory for both paths (the memory note lists its large files)."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "events.jsonl").write_text("{}\n")
    real = task_module._data_mount
    monkeypatch.setattr(task_module, "_data_mount", lambda variant, bench: (data, real(variant, bench)[1])
                        if bench != "urlquery" else (data, {}))
    return data


@pytest.mark.parametrize(("benchmark_id", "name"), STD, ids=[n for _, n in STD])
def test_inspect_prompt_is_byte_identical_to_the_runners(benchmark_id, name, small_data):
    cfg = load_config(name, benchmark_id)
    prompt = task_module._prompt_for(name, None, cfg["min_runtime_fraction"], benchmark_id)
    assert prompt == _runner_prompt(ROOT / "configs" / f"{name}.toml", small_data)


@pytest.mark.parametrize(("benchmark_id", "name"), STD, ids=[n for _, n in STD])
def test_inspect_task_takes_the_configs_minimum_runtime(benchmark_id, name, small_data, monkeypatch):
    from slopvestigator_bench.grading import findings as fj

    real = fj.article_text
    monkeypatch.setattr(fj, "article_text", lambda c: "ARTICLE" if c == "full" else real(c))
    task = _build(benchmark_id, name, agent="react")
    assert task.metadata["min_runtime_fraction"] == load_config(name, benchmark_id)["min_runtime_fraction"] == 0.9
    assert "Do not try to finish before" in task.dataset[0].input


def _runner_env_keys() -> set[str]:
    line = next(line for line in RUNNER.splitlines() if line.startswith("TIME_ENV=("))
    return set(re.findall(r"-e (MBAB_[A-Z_]+)=", line))


@pytest.mark.parametrize(("benchmark_id", "name"), STD, ids=[n for _, n in STD])
def test_config_settings_for_the_hooks_reach_both_runners(benchmark_id, name):
    cfg = load_config(name, benchmark_id)
    env = task_module._agent_env(cfg, "claude")
    # Every config-driven setting the Inspect agent gets is one the runner passes too.
    assert {k for k in env if k.startswith("MBAB_")} <= _runner_env_keys()
    assert env["MBAB_EARLY_STOP_NOTE"] == cfg["early_stop_note"]
    assert env["MBAB_SAFEGUARD_RETRY_LIMIT"] == str(cfg["safeguard_retry_limit"])
    assert env["MBAB_SAFEGUARD_RETRY_MESSAGE"] == cfg["safeguard_retry_message"]
    # The runner passes the same two settings (TIME_ENV), from the same config keys.
    assert '-e MBAB_SAFEGUARD_RETRY_MESSAGE="${CFG_SAFEGUARD_RETRY_MESSAGE:-}"' in RUNNER
    assert env["BASH_MAX_OUTPUT_LENGTH"] == str(cfg["bash_max_output_length"])


def test_native_codex_with_multi_agent_off_uses_the_stripped_catalog(monkeypatch):
    seen = {}
    monkeypatch.setattr(native, "codex_cli", lambda **kw: seen.update(kw))
    native.inspect_agent("codex", claude_disallowed_tools=[], codex_features_off=("multi_agent", "multi_agent_v2"))
    assert seen["config_overrides"]["model_catalog_json"] == '"/work/.codex/model-catalog.json"'
    native.inspect_agent("codex", claude_disallowed_tools=[], codex_features_off=())
    assert "model_catalog_json" not in seen["config_overrides"]
    assert "multi_agent_version" in native._STRIP_MULTI_AGENT and "model-catalog" in native.CODEX_MODEL_CATALOG
