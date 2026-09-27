"""The investigating agent: a ReAct lead or Claude Code, optionally with an analyst subagent.

ReAct: the analyst is exposed to the lead as a tool (``as_tool``): the lead sends it
one focused question, the analyst works in the same sandbox with its own context,
and only its final answer comes back.

The analyst's model is the ``subagent`` model role (``--model-role subagent=...``),
defaulting to the lead's model.

Claude Code (``inspect_swe``): the real CLI runs in its own ``claude`` container, and its
API calls go to a bridge there that relays them to Inspect on the host, so no credential
enters any sandbox. Its native tools are all disabled. Instead it gets Inspect's ``bash``
and ``text_editor``, bridged over MCP and executed in the ``default`` container with the
corpus. Nothing the model runs shares a network, filesystem or process with the bridge.
It works alone: no web, no subagents, no background tasks.

Both leads' tools end every result with the harness note (``feedback.py``): time remaining,
and the report and TL;DR word counts whenever report.md changed. The analyst gets no note.
"""

from __future__ import annotations

from typing import Literal

from inspect_ai.agent import (
    Agent,
    AgentPrompt,
    BridgedToolsSpec,
    agent,
    as_solver,
    as_tool,
    react,
)
from inspect_ai.model import get_model
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import bash, text_editor
from inspect_ai.tool._sandbox_tools_utils.sandbox import sandbox_with_injected_tools
from inspect_ai.util import message_limit
from inspect_swe import claude_code

from report_eval_harness import prompts
from report_eval_harness.feedback import Feedback, with_feedback

ANALYST_PROMPT = prompts.render(
    prompts.load("analyst.txt"),
    {"FINISH_NOTE": "When you have answered, call submit() with your answer."},
)
ANALYST_DESCRIPTION = (
    "A forensic analyst with its own shell on the same logs. Give it ONE focused "
    "question (e.g. 'decode the ref parameter in record X', 'which hosts appear in "
    "every record?', 'build a timeline for domain Y'). It returns findings with "
    "record IDs. Check what it returns against the records."
)

Truncation = Literal["auto", "disabled"]
AgentKind = Literal["react", "claude_code"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Every native Claude Code tool that touches files, the shell, the web, other agents or the
# scheduler. What's left are the bridged tools: mcp__sandbox__bash, mcp__sandbox__text_editor.
CLAUDE_CODE_DISALLOWED = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit", "WebSearch", "WebFetch",
    "Agent", "Task", "TaskOutput", "TaskStop", "Workflow", "Skill", "CronCreate", "CronDelete",
    "CronList", "ScheduleWakeup", "EnterWorktree", "ExitWorktree", "ReportFindings",
    "SendMessage", "ListAgents",
]  # fmt: skip


@agent
def analyst(tool_timeout: int = 180, truncation: Truncation = "auto") -> Agent:
    return react(
        name="analyst",
        description=ANALYST_DESCRIPTION,
        prompt=AgentPrompt(instructions=ANALYST_PROMPT, handoff_prompt=None),
        tools=[bash(timeout=tool_timeout), text_editor(timeout=tool_timeout)],
        model=get_model(role="subagent"),
        truncation=truncation,
    )


@agent
def investigator(
    report_min_words: int = 0,
    report_max_words: int = 0,
    subagents: bool = True,
    subagent_message_limit: int = 60,
    tool_timeout: int = 180,
    truncation: Truncation = "auto",
) -> Agent:
    tools = [bash(timeout=tool_timeout), text_editor(timeout=tool_timeout)]
    if subagents:
        tools.append(
            as_tool(
                analyst(tool_timeout=tool_timeout, truncation=truncation),
                limits=[message_limit(subagent_message_limit)],
            )
        )
    feedback = Feedback(report_min_words, report_max_words)
    tools = [with_feedback(tool, feedback) for tool in tools]
    return react(
        name="investigator",
        description="Lead investigator; writes /work/report.md.",
        prompt=AgentPrompt(handoff_prompt=None),
        tools=tools,
        truncation=truncation,
    )


@solver
def investigate(**kwargs) -> Solver:
    """Build the agent at run time, so the ``subagent`` model role is resolved in the eval."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        return await as_solver(investigator(**kwargs))(state, generate)

    return solve


@solver
def claude_code_investigate(
    effort: Effort | None = None,
    tool_timeout: int = 180,
    report_min_words: int = 0,
    report_max_words: int = 0,
) -> Solver:
    """Claude Code in the ``claude`` container, its shell in the ``default`` container."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # text_editor takes no sandbox name: it runs in the first sandbox that already has
        # Inspect's tools installed. The bridge installs them in `claude`, so install them
        # in `default` (first in order) now. test_claude_code_sandbox_is_locked_down checks it.
        await sandbox_with_injected_tools(sandbox_name="default")
        feedback = Feedback(report_min_words, report_max_words)
        tools = [
            with_feedback(tool, feedback)
            for tool in (bash(timeout=tool_timeout), text_editor(timeout=tool_timeout))
        ]
        agent = claude_code(
            disallowed_tools=CLAUDE_CODE_DISALLOWED,
            bridged_tools=[BridgedToolsSpec(name="sandbox", tools=tools)],
            env={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"},
            sandbox="claude",
            cwd="/work",  # tmpfs; matches the bridged shell's working directory
            version="sandbox",  # baked into sandbox/Dockerfile (stage `claude`)
            effort=effort,
        )
        return await as_solver(agent)(state, generate)

    return solve
