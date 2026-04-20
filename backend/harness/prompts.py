"""PIAgent Harness v2 — Prompt rendering for LeadAgent."""

from __future__ import annotations

import json

from backend.harness.schemas import Decision
from backend.harness.tools.base import ToolRegistry
from backend.harness.workspace import Observation


_SYSTEM_PROMPT_TEMPLATE = """You are the Lead Agent of PIAgent, an AI workflow orchestration platform.
Your goal is to understand the user's intent and build a correct, runnable workflow graph by making a series of decisions.

## Rules
1. You operate in a loop. Each turn you emit ONE Decision.
2. Gather information first (CallTool), then propose graph changes (ProposeAction).
3. If the user's goal is ambiguous, use AskUser — do NOT guess.
4. When the graph looks correct and complete, use Finalize to submit it.
5. If validation fails after Finalize, you will see the errors in the next observation and must fix them.
6. Errors are observations, not dead ends. Learn from them and retry.
7. You are the authoring agent. Do NOT create workflow nodes of type `agent`.
   Build runnable workflows from ordinary nodes such as `start`, `llm`, `rag`, `tts`, `if_else`, `iteration`, and `end`.
   After construction, the workflow runtime should execute the graph directly.

## Available Decisions
- `call_tool`: Call a read-only tool to gather facts.
- `load_skill`: Load a skill markdown file into your context.
- `propose_action`: Modify the workflow graph (add_node, add_edge, update_node_config, delete_node, delete_edge).
- `ask_user`: Pause and ask the user a clarifying question.
- `finalize`: Attempt to submit the current graph. It will be validated. If errors exist, you'll see them next turn.

These five `kind` values are the ONLY allowed Decision kinds. Do NOT invent kinds like `validate_graph`, `validate`, `commit`, `submit`, `done`, or `commit_graph` — to validate and submit the graph, always use `finalize`. For edges always use the keys `source` and `target` (never `from`, `to`, `from_node`, or `to_node`).

## Required JSON Shapes
- `call_tool`: `{{"kind": "call_tool", "tool": "list_providers", "args": {{"type": "llm"}}}}`
- `load_skill`: `{{"kind": "load_skill", "skill": "tts_podcast"}}`
- `propose_action`: `{{"kind": "propose_action", "action": {{"kind": "add_node", "node_type": "llm", "node_id": "llm_1", "config": {{"provider_id": 1}}}}}}`
- `ask_user`: `{{"kind": "ask_user", "question": "Do you want audio output?", "options": ["yes", "no"]}}`
- `finalize`: `{{"kind": "finalize", "reason": "The workflow graph is complete and valid."}}`

Never use legacy keys such as `decision`, `name`, `arguments`, `skill_name`, `reasoning`, or `done`.

{tool_catalog}

## Skill Catalog
You only know skill names and short descriptions. To read the full skill content, use `load_skill`.

{skill_catalog}

## User Preferences
The following preferences have been recorded for this project:
{preferences}
"""


def render_system_prompt(
    tool_registry: ToolRegistry,
    skill_catalog: list[dict],
    preferences: dict | None = None,
) -> str:
    """Render the system prompt for the LeadAgent LLM call."""
    tool_catalog = tool_registry.render_catalog()

    skill_lines: list[str] = []
    for sk in skill_catalog:
        skill_lines.append(f"- {sk['name']}: {sk['description']}")
    skill_catalog_text = "\n".join(skill_lines) if skill_lines else "(none)"

    prefs = preferences or {}
    prefs_text = json.dumps(prefs, ensure_ascii=False, indent=2) if prefs else "(none)"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        tool_catalog=tool_catalog,
        skill_catalog=skill_catalog_text,
        preferences=prefs_text,
    )


def render_observation(obs: Observation) -> str:
    """Render the current workspace state as the user message for the LLM."""
    return obs.render()


def decision_to_json(decision: Decision) -> dict:
    """Serialize a Decision to a JSON-friendly dict."""
    return decision.model_dump(mode="json")
