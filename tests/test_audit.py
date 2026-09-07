from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
from inspect_ai.tool import ToolCall, ToolCallError

from messageboard_audit_bench.audit import trajectory_metrics


def _messages(command: str, *, error: ToolCallError | None = None, output: str = ""):
    call = ToolCall(id="call", function="bash", arguments={"command": command})
    return [
        ChatMessageAssistant(content=[], tool_calls=[call]),
        ChatMessageTool(content=output, tool_call_id="call", function="bash", error=error),
    ]


def test_empty_rg_result_is_not_an_actionable_tool_error() -> None:
    metrics = trajectory_metrics(
        _messages("rg absent data", error=ToolCallError(type="unknown", message="exit code 1"))
    )

    assert metrics["tool_error_count"] == 0
    assert metrics["empty_search_exit_1"] == 1
    assert metrics["no_match_exit_1"] == 1


def test_other_exit_one_remains_a_tool_error() -> None:
    metrics = trajectory_metrics(
        _messages("python3 analysis.py", error=ToolCallError(type="unknown", message="exit code 1"))
    )

    assert metrics["tool_error_count"] == 1
    assert metrics["empty_search_exit_1"] == 0


def test_time_feedback_and_parallelism_are_observable_but_limited() -> None:
    calls = [
        ToolCall(id="one", function="bash", arguments={"command": "date"}),
        ToolCall(id="two", function="bash", arguments={"command": "rg labels data"}),
    ]
    messages = [
        ChatMessageAssistant(content=[], tool_calls=calls),
        ChatMessageTool(content="[Time budget: about 12 of 20 minutes left.]", tool_call_id="one", function="bash"),
        ChatMessageTool(content="", tool_call_id="two", function="bash"),
    ]

    metrics = trajectory_metrics(messages)

    assert metrics["max_tool_calls_in_assistant_message"] == 2
    assert metrics["multi_tool_messages"] == 1
    assert metrics["time_check_commands"] == 1
    assert metrics["time_feedback_messages"] == 1
