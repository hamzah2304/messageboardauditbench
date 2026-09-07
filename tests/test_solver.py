import json
import subprocess
from pathlib import Path

import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatMessageTool,
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
    assert state.metadata["usage_schema"] == 3
    assert state.metadata["condition"] == "blind"
    assert state.metadata["config"] == "blind-10"
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

    async def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured.update(command=command, **kwargs)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=f"building\nrun: {run_dir}\n",
            stderr="",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver._run_async", fake_run)

    state = await subscription_agent(
        allow_networked_subscription=True,
        agent="codex",
        model="gpt-test",
        config="blind",
        time_limit_minutes=37,
        timeout_minutes=37,
        prompt="blind",
        data_variant="verbatim",
        effort="xhigh",
        min_runtime_fraction=0.6,
    )(_state(), None)

    assert state.completed
    assert state.metadata["run_dir"] == str(run_dir)
    assert captured["command"][-3:] == ["codex", "gpt-test", "1"]
    assert captured["env"]["CONFIG"] == "blind"
    assert captured["env"]["PROMPT"] == "blind"
    assert captured["env"]["DATA_DIR"].endswith("/data/verbatim")
    assert captured["env"]["EFFORT"] == "xhigh"
    assert captured["env"]["BUDGET_MIN"] == "37"
    assert captured["env"]["TIMEOUT"] == "37m"
    assert captured["env"]["MBAB_MIN_RUNTIME_FRACTION"] == "0.6"
    assert captured["timeout"] == 42 * 60


@pytest.mark.asyncio
async def test_subscription_agent_surfaces_trial_failure(monkeypatch) -> None:
    async def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=command,
            returncode=2,
            stdout="",
            stderr="docker unavailable",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver._run_async", fake_run)

    with pytest.raises(
        RuntimeError,
        match="before producing a run directory with exit code 2: docker unavailable",
    ):
        await subscription_agent(
            allow_networked_subscription=True,
            agent="codex",
            model="gpt-test",
            config="blind",
        )(_state(), None)


@pytest.mark.asyncio
async def test_subscription_agent_can_refuse_proxy_tradeoff() -> None:
    with pytest.raises(ValueError, match="restricted proxy"):
        await subscription_agent(
            agent="codex", model="gpt-test", allow_networked_subscription=False
        )(_state(), None)


@pytest.mark.asyncio
async def test_subscription_agent_folds_timed_out_trial(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = _run_dir(tmp_path / "timed-out")

    async def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=f"run: {run_dir}\n",
            stderr="time limit reached",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver._run_async", fake_run)

    state = await subscription_agent(
        allow_networked_subscription=True,
        agent="codex",
        model="gpt-test",
        config="blind",
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

    async def fake_run(command: list[str], **_kwargs):
        raise subprocess.TimeoutExpired(
            command,
            timeout=480,
            output=f"run: {run_dir}\n".encode(),
            stderr=b"stuck cleanup",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver._run_async", fake_run)
    monkeypatch.setattr(
        "messageboard_audit_bench.solver._cleanup_interrupted_run",
        lambda path: cleaned.append(path),
    )

    state = await subscription_agent(
        allow_networked_subscription=True,
        agent="codex",
        model="gpt-test",
        config="blind",
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
    with (run_dirs[0] / "transcript.jsonl").open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "retry-command",
                        "type": "command_execution",
                        "command": "rg retry data",
                        "aggregated_output": "",
                    },
                }
            )
            + "\n"
        )
    calls = 0

    async def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        nonlocal calls
        run_dir = run_dirs[calls]
        calls += 1
        return subprocess.CompletedProcess(
            args=command,
            returncode=5,
            stdout=f"run: {run_dir}\n",
            stderr="model refusal",
        )

    monkeypatch.setattr("messageboard_audit_bench.solver._run_async", fake_run)

    state = await subscription_agent(
        allow_networked_subscription=True,
        agent="codex",
        model="same-model",
        config="blind",
        timeout_minutes=3,
    )(_state(), None)

    assert calls == 3
    assert state.metadata["refusal_rerun_limit"] == 2
    assert state.metadata["refusal_reruns"] == 2
    assert state.metadata["runner_returncode"] == 5
    assert state.metadata["prior_run_dirs"] == [str(path) for path in run_dirs[:2]]
    assert state.metadata["usage_scope"] == "final_attempt"
    assert state.metadata["trajectory_scope"] == "all_imported_attempts"
    assert state.metadata["trajectory_attempt_count"] == 3
    assert [
        item["trajectory_imported"] for item in state.metadata["prior_attempts"]
    ] == [True, True]
    prior_tool = next(
        message for message in state.messages if isinstance(message, ChatMessageTool)
    )
    assert prior_tool.tool_call_id.startswith("retry-1:")


@pytest.mark.asyncio
async def test_cancellation_terminates_runner_and_cleans_recorded_resources(
    tmp_path, monkeypatch
):
    import asyncio
    import sys

    from messageboard_audit_bench.solver import _run_async

    ready = tmp_path / "ready"
    cleaned = []
    monkeypatch.setattr(
        "messageboard_audit_bench.solver._cleanup_interrupted_run",
        lambda path: cleaned.append(path),
    )
    script = (
        "import pathlib,time; print('run: ' + "
        + repr(str(tmp_path))
        + ", flush=True); pathlib.Path("
        + repr(str(ready))
        + ").touch(); time.sleep(60)"
    )
    task = asyncio.create_task(
        _run_async([sys.executable, "-c", script], cwd=tmp_path, env={}, timeout=60)
    )
    for _ in range(100):
        if ready.exists():
            break
        await asyncio.sleep(0.01)
    assert ready.exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert cleaned == [tmp_path]
