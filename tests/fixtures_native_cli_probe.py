import json
import os

os.environ["INSPECT_TRACE_FILE"] = "/tmp/mbab-native-tool-telemetry-trace.log"
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessageAssistant,
    ContentReasoning,
    ModelOutput,
    ModelUsage,
    get_model,
)
from inspect_ai.tool import ToolCall

from messageboard_audit_bench.native import inspect_native_agent
from messageboard_audit_bench.native_telemetry import event_coverage, hook_coverage
from messageboard_audit_bench.scorer import process_metrics
from messageboard_audit_bench.task import _inspect_sandbox

for agent in ["claude", "codex"]:
    calls = [0]

    def respond(messages, tools, choice, config):
        calls[0] += 1
        if calls[0] <= 2:
            tool = next(
                t
                for t in tools
                if t.name in ("Bash", "bash", "exec_command", "shell_command", "shell")
            )
            key = next(k for k in ("command", "cmd") if k in tool.parameters.properties)
            commands = (
                [
                    "sleep .3; printf 'stdout evidence'; printf 'stderr evidence' >&2; exit 7",
                    "sleep .3; printf 'parallel evidence'",
                ]
                if calls[0] == 1
                else ["printf 'verified report evidence' > /work/report.md"]
            )
            return ModelOutput(
                model="mockllm/model",
                choices=[
                    ChatCompletionChoice(
                        message=ChatMessageAssistant(
                            content=[
                                ContentReasoning(reasoning="Mock reasoning retained")
                            ],
                            tool_calls=[
                                ToolCall(
                                    id=f"call-{calls[0]}-{i}",
                                    function=tool.name,
                                    arguments={key: c},
                                )
                                for i, c in enumerate(commands)
                            ],
                        ),
                        stop_reason="tool_calls",
                    )
                ],
                usage=ModelUsage(input_tokens=10, output_tokens=8, reasoning_tokens=3),
            )
        return ModelOutput.from_content("mockllm/model", "Done")

    model = get_model("mockllm/model", custom_outputs=respond)
    task = Task(
        dataset=[
            Sample(
                input="Use the tools to write /work/report.md and finish.",
                id=agent,
                metadata={
                    "report_min_words": 2,
                    "report_max_words": 3,
                    "report_accept_max_words": 3,
                    "report_accept_min_words": 0,
                },
            )
        ],
        solver=inspect_native_agent(
            agent, 60, report_min_words=2, report_max_words=3, min_runtime_fraction=0
        ),
        sandbox=_inspect_sandbox("verbatim"),
        scorer=process_metrics(),
    )
    [log] = eval(
        task,
        model=model,
        display="none",
        log_dir="/tmp/mbab-native-tool-telemetry-smoke",
        log_realtime=False,
    )
    s = read_eval_log(log.location).samples[0]
    print(
        agent,
        log.status,
        s.error.message if s.error else None,
        repr(s.output.completion),
        calls[0],
        flush=True,
    )
    records = s.metadata.get("tool_lifecycle_events", [])
    print(
        json.dumps(hook_coverage(records, ["call-1-0", "call-1-1", "call-2-0"])),
        flush=True,
    )
    print(json.dumps(event_coverage(s.events)), flush=True)
    assert log.status == "success"
    assert s.output.completion == "verified report evidence"
    assert event_coverage(s.events)["raw_model_api_complete"]
    assert event_coverage(s.events)["reasoning_token_model_events"] == 2
    assert len([r for r in records if r["event"] == "PreToolUse"]) == 3
    assert hook_coverage(records)["tool_hook_lifecycle_complete"]
