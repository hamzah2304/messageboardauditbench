import json
import subprocess
from pathlib import Path

import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatMessageUser,
    ModelName,
    ModelOutput,
    ModelUsage,
    get_model,
)
from inspect_ai.scorer import Target
from inspect_ai.solver import TaskState

from messageboard_audit_bench.scorer import process_metrics, rubric_scorer
from messageboard_audit_bench.solver import _fold, replay, subscription_agent


def _run_dir(path: Path) -> Path:
    path.mkdir()
    (path / "transcript.jsonl").write_text(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "agent_message",
                    "text": "Investigation complete.",
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "cached_input_tokens": 3,
                },
            }
        )
        + "\n"
    )
    (path / "report.md").write_text("# Report\n\nThe agents coordinated.")
    (path / "meta.json").write_text(
        json.dumps(
            {
                "exit_code": 0,
                "agent": "codex",
                "model": "gpt-test",
                "config": "blind-10",
                "prompt": "blind",
                "budget_min": 10,
                "data_variant": "verbatim",
                "wall_seconds": 7,
                "replicate": 1,
            }
        )
    )
    return path


def _state(run_dir: Path | None = None) -> TaskState:
    metadata = {"run_dir": str(run_dir), "agent": "codex"} if run_dir else {}
    return TaskState(
        model=ModelName("mockllm/model"),
        sample_id="sample",
        epoch=1,
        input="Investigate",
        messages=[ChatMessageUser(content="Investigate")],
        metadata=metadata,
        target=Target(""),
    )


def test_fold_imports_report_transcript_and_usage(tmp_path: Path) -> None:
    state = _fold(_state(), _run_dir(tmp_path / "run"), "codex")

    assert state.completed
    assert state.output.completion.startswith("# Report")
    assert state.output.usage is not None
    assert state.output.usage.input_tokens == 9
    assert state.output.usage.total_tokens == 16
    assert state.output.usage.input_tokens_cache_read == 3
    assert state.metadata["input_tokens_uncached"] == 9
    assert state.metadata["cache_read_fraction"] == 0.25
    assert state.metadata["usage_schema"] == 2
    assert state.metadata["condition"] == "blind"
    assert state.metadata["report_written"] is True
    assert state.metadata["wall_seconds"] == 7


@pytest.mark.asyncio
async def test_rubric_scorer_clamps_penalty_only_result() -> None:
    replies = iter(["NO: absent"] * 12 + ["YES: unsupported claim"] * 3)
    mock_model = get_model(
        "mockllm/model",
        custom_outputs=lambda *_args: ModelOutput(
            model="mockllm/model",
            completion=next(replies),
            usage=ModelUsage(),
        ),
    )
    state = _state()
    state.output = ModelOutput.from_content(
        model="external-agent", content="A non-empty report."
    )

    score = await rubric_scorer(judge=mock_model)(state, Target(""))

    assert score.value == 0.0
    assert score.answer == "0/23 positive, -7 penalty"


@pytest.mark.parametrize(
    ("judge_reply", "expected_value", "expected_answer"),
    [
        ("NO: absent", 0.0, "0/23 positive, -0 penalty"),
        ("YES: present", 16 / 23, "23/23 positive, -7 penalty"),
    ],
)
def test_replay_eval_runs_end_to_end_with_mock_model(
    tmp_path: Path,
    monkeypatch,
    judge_reply: str,
    expected_value: float,
    expected_answer: str,
) -> None:
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(tmp_path / "trace.log"))
    mock_model = get_model(
        "mockllm/model",
        custom_outputs=lambda *_args: ModelOutput(
            model="mockllm/model",
            completion=judge_reply,
            usage=ModelUsage(),
        ),
    )
    run_dir = _run_dir(tmp_path / "run")
    task = Task(
        dataset=[
            Sample(
                input="Investigate",
                id="replay-smoke",
                metadata={"run_dir": str(run_dir), "agent": "codex"},
            )
        ],
        solver=replay(),
        scorer=[rubric_scorer(judge=mock_model), process_metrics()],
    )

    [log] = eval(
        task,
        model=mock_model,
        display="none",
        log_realtime=False,
        log_dir=str(tmp_path / "logs"),
    )

    assert log.status == "success", log.error
    assert log.samples is not None
    assert log.samples[0].scores is not None
    scores = log.samples[0].scores
    assert set(scores) == {"rubric_scorer", "process_metrics"}
    assert scores["rubric_scorer"].value == pytest.approx(expected_value)
    assert scores["rubric_scorer"].answer == expected_answer
    assert scores["rubric_scorer"].metadata["judge"] == "mockllm/model"
    assert scores["process_metrics"].value == 1.0
    assert scores["process_metrics"].metadata["wall_seconds"] == 7


@pytest.mark.asyncio
async def test_subscription_agent_folds_successful_trial(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = _run_dir(tmp_path / "run")
    captured: dict = {}

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured.update(command=command, **kwargs)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=f"building\nrun: {run_dir}\n",
            stderr="",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver.subprocess.run", fake_run)

    state = await subscription_agent(
        agent="codex",
        model="gpt-test",
        condition="blind",
        time_limit_minutes=37,
        timeout_minutes=37,
        prompt="blind",
        data_variant="verbatim",
        effort="xhigh",
    )(
        _state(), None
    )

    assert state.completed
    assert state.metadata["run_dir"] == str(run_dir)
    assert captured["command"][-3:] == ["codex", "gpt-test", "1"]
    assert captured["env"]["CONFIG"] == "blind"
    assert captured["env"]["PROMPT"] == "blind"
    assert captured["env"]["DATA_DIR"].endswith("/data/verbatim")
    assert captured["env"]["EFFORT"] == "xhigh"
    assert captured["env"]["BUDGET_MIN"] == "37"
    assert captured["env"]["TIMEOUT"] == "37m"
    assert captured["timeout"] == 42 * 60


@pytest.mark.asyncio
async def test_subscription_agent_surfaces_trial_failure(monkeypatch) -> None:
    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=command,
            returncode=2,
            stdout="",
            stderr="docker unavailable",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver.subprocess.run", fake_run)

    with pytest.raises(
        RuntimeError,
        match="before producing a run directory with exit code 2: docker unavailable",
    ):
        await subscription_agent(agent="codex", model="gpt-test", condition="blind")(
            _state(), None
        )


@pytest.mark.asyncio
async def test_subscription_agent_folds_timed_out_trial(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = _run_dir(tmp_path / "timed-out")

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=f"run: {run_dir}\n",
            stderr="time limit reached",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver.subprocess.run", fake_run)

    state = await subscription_agent(
        agent="codex",
        model="gpt-test",
        condition="blind",
        timeout_minutes=3,
    )(_state(), None)

    assert state.completed
    assert state.metadata["runner_returncode"] == 124
    assert state.metadata["trial_failed"] is True
    assert "Investigation complete" in state.messages[-1].text


@pytest.mark.asyncio
async def test_subscription_agent_recovers_host_guard_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = _run_dir(tmp_path / "host-timeout")
    cleaned = []

    def fake_run(command: list[str], **_kwargs):
        raise subprocess.TimeoutExpired(
            command,
            timeout=480,
            output=f"run: {run_dir}\n".encode(),
            stderr=b"stuck cleanup",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver.subprocess.run", fake_run)
    monkeypatch.setattr(
        "messageboard_audit_bench.solver._cleanup_interrupted_run",
        lambda path: cleaned.append(path),
    )

    state = await subscription_agent(
        agent="codex",
        model="gpt-test",
        condition="blind",
        timeout_minutes=3,
    )(_state(), None)

    assert cleaned == [run_dir]
    assert state.metadata["runner_returncode"] == 124
    assert state.metadata["trial_failed"] is True
    assert state.metadata["run_dir"] == str(run_dir)


@pytest.mark.asyncio
async def test_subscription_refusal_reruns_twice_with_same_model(
    tmp_path: Path, monkeypatch
) -> None:
    run_dirs = [_run_dir(tmp_path / f"refusal-{index}") for index in range(3)]
    calls = 0

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        nonlocal calls
        run_dir = run_dirs[calls]
        calls += 1
        return subprocess.CompletedProcess(
            args=command,
            returncode=5,
            stdout=f"run: {run_dir}\n",
            stderr="model refusal",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver.subprocess.run", fake_run)

    state = await subscription_agent(
        agent="claude",
        model="same-model",
        condition="blind",
        timeout_minutes=3,
    )(_state(), None)

    assert calls == 3
    assert state.metadata["refusal_rerun_limit"] == 2
    assert state.metadata["refusal_reruns"] == 2
    assert state.metadata["runner_returncode"] == 5
    assert state.metadata["prior_run_dirs"] == [str(path) for path in run_dirs[:2]]
