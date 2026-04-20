from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from backend.pi_harness.runtime.agent.loop_detection import wrap_tools_with_loop_detection
from backend.pi_harness.runtime.memory.summarizer import Summarizer
from backend.pi_harness.runtime.skills.prompt import build_skills_state_modifier
from backend.pi_harness.runtime.tools.builtins.clarification import AskClarificationTool
from backend.pi_harness.runtime.tools.registry import ToolRegistry, get_tool_registry


def create_agent(
    model_name: str | None = None,
    tools: list[str] | None = None,
    system_prompt: str | None = None,
    *,
    model=None,
    model_factory: Callable[[str | None], Any] | None = None,
    tool_instances: Sequence[BaseTool] | None = None,
    tool_registry: ToolRegistry | None = None,
    skills_path: str | Path | None = None,
    enable_loop_detection: bool = True,
    loop_warn_threshold: int = 3,
    loop_hard_limit: int = 5,
    enable_clarification: bool = True,
    enable_summarization: bool = True,
    summarization_trigger_messages: int = 30,
    summarization_keep_messages: int = 10,
):
    """Create a ReAct agent from the vendored pi_harness runtime.

    The vendored runtime intentionally avoids external config and global API
    assumptions. Callers are expected to inject the model and, for
    session-scoped flows, inject tool instances directly.
    """

    if model is None:
        if model_factory is None:
            raise ValueError("create_agent requires either `model` or `model_factory`")
        model = model_factory(model_name)

    if tool_instances is None:
        registry = tool_registry or get_tool_registry()
        resolved_tools = registry.get_tools(tools)
    else:
        resolved_tools = list(tool_instances)

    prompt_fn = _build_prompt_fn(system_prompt, skills_path)

    if enable_summarization:
        summarizer = Summarizer(
            model=model,
            trigger_messages=summarization_trigger_messages,
            keep_messages=summarization_keep_messages,
        )
        base_fn = prompt_fn

        def summarized_prompt(state):
            messages = base_fn(state) if base_fn else list(state["messages"])
            return summarizer.compress(messages)

        prompt_fn = summarized_prompt

    if enable_loop_detection:
        resolved_tools = wrap_tools_with_loop_detection(
            list(resolved_tools),
            warn_threshold=loop_warn_threshold,
            hard_limit=loop_hard_limit,
        )

    if enable_clarification:
        resolved_tools = list(resolved_tools)
        resolved_tools.append(AskClarificationTool())

    return create_react_agent(
        model=model,
        tools=list(resolved_tools),
        state_modifier=prompt_fn,
    )


def _build_prompt_fn(system_prompt: str | None, skills_path: str | Path | None):
    skills_modifier = build_skills_state_modifier(skills_path)
    if skills_modifier:
        if system_prompt:
            def combined_prompt(state):
                skills_messages = skills_modifier(state)
                return [SystemMessage(content=system_prompt)] + skills_messages

            return combined_prompt
        return skills_modifier

    if system_prompt:
        def sys_prompt(state):
            return [SystemMessage(content=system_prompt)] + list(state["messages"])

        return sys_prompt

    return None

