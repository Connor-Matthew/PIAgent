"""PIAgent ReAct Builder Agent — Runner.

Replaces LeadAgent.decide() with a LangGraph create_react_agent loop.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from backend.config import settings
from backend.harness.builder import GraphBuilder
from backend.harness.react_tools.ask_user import PauseAgentRun
from backend.harness.react_tools.base import ToolContext
from backend.harness.react_tools.readonly import make_readonly_tools
from backend.harness.react_tools.write import make_write_tools
from backend.harness.react_tools.ask_user import make_ask_user_tool
from backend.harness.skills.loader import SkillLoader
from backend.harness.workspace import Workspace
from backend.models.provider import Provider
from backend.providers import build_provider

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

_DEFAULT_LLM_MODEL_BY_TYPE: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "google": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
    "openai_compatible": "gpt-4o-mini",
}


def _resolve_default_model(provider_type: str, selected_models: list[str] | None = None) -> str:
    if selected_models:
        return selected_models[0]
    return _DEFAULT_LLM_MODEL_BY_TYPE.get(provider_type, "gpt-4o")


def _resolve_harness_provider(db: Any) -> Provider:
    effective_id = settings.agent_llm_provider_id
    query = db.query(Provider).filter(
        Provider.enabled.is_(True),
        Provider.category == "llm",
    )
    if effective_id is not None:
        row = query.filter(Provider.id == effective_id).first()
    else:
        row = query.order_by(Provider.id.asc()).first()
    if row is None:
        raise RuntimeError("No enabled LLM provider available for harness")
    return row


def _create_chat_model(db: Any):
    row = _resolve_harness_provider(db)
    provider = build_provider(row)
    model_name = settings.agent_llm_model or _resolve_default_model(
        row.type,
        selected_models=row.selected_models or [],
    )
    return provider.create_chat_model(
        model=model_name,
        temperature=0.3,
        streaming=True,
    )


def _builder_snapshot_hash(builder: GraphBuilder) -> str:
    payload = json.dumps(builder.snapshot(), sort_keys=True)
    import hashlib
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _build_prompt_fn(workspace: Workspace, skills: SkillLoader):
    """Build a prompt callable that injects workspace summary."""
    skills_catalog = skills.catalog()

    def prompt(state):
        messages = list(state["messages"])
        parts = []
        parts.append("You are the PIAgent Workflow Builder Agent.")
        parts.append(
            "Your goal is to help the user build a correct, runnable workflow graph by calling authoring tools."
        )
        parts.append("")
        parts.append("## Rules")
        parts.append("1. Gather information first (inspect_canvas, list_node_types, list_providers, list_knowledge_bases).")
        parts.append("2. Then build the graph using add_node, connect_nodes, update_node_config.")
        parts.append("3. Validate the graph before finalizing.")
        parts.append("4. If the user's goal is ambiguous, use ask_user — do NOT guess.")
        parts.append("5. You are an authoring agent. Do NOT create workflow nodes of type `agent`.")
        parts.append("6. Build runnable workflows from ordinary nodes: start, llm, rag, tts, end.")
        parts.append("")
        parts.append("## User Goal")
        parts.append(workspace.goal or "(no goal set)")
        parts.append("")

        # Graph summary
        graph = workspace.graph_draft
        parts.append("## Current Graph Draft")
        parts.append(f"Nodes: {len(graph.get('nodes', []))}, Edges: {len(graph.get('edges', []))}")
        if graph.get("nodes"):
            for n in graph["nodes"]:
                parts.append(f"- {n['id']} ({n.get('type', '?')})")
        if graph.get("edges"):
            for e in graph["edges"]:
                parts.append(f"- {e['source']} -> {e['target']}")
        parts.append("")

        # Validation findings
        findings = workspace.facts.to_dict().get("validation_findings", [])
        if findings:
            parts.append("## Validation Findings")
            for f in findings:
                sev = f.get("severity", "error")
                msg = f.get("message", "")
                parts.append(f"- [{sev.upper()}] {msg}")
            parts.append("")

        # Open question
        if workspace.open_question:
            parts.append("## Open Question")
            parts.append(f"Question: {workspace.open_question.get('question', '')}")
            opts = workspace.open_question.get("options")
            if opts:
                for i, opt in enumerate(opts, 1):
                    parts.append(f"  {i}. {opt}")
            parts.append("")

        # Budget
        parts.append(f"## Budget\nRemaining steps: {workspace.budget.remaining()}")
        parts.append("")

        # Skills catalog
        if skills_catalog:
            parts.append("## Available Skills")
            for sk in skills_catalog:
                parts.append(f"- {sk['name']}: {sk['description']}")
            parts.append("")

        system_content = "\n".join(parts)
        return [SystemMessage(content=system_content)] + messages

    return prompt


class ReActBuilderAgentRunner:
    """Runs a LangGraph ReAct agent for workflow authoring."""

    def __init__(
        self,
        session_id: str,
        workspace: Workspace,
        builder: GraphBuilder,
        db: Any,
        skills: SkillLoader,
    ):
        self.session_id = session_id
        self.workspace = workspace
        self.builder = builder
        self.db = db
        self.skills = skills
        self._checkpointer = MemorySaver()

    def _build_agent(self):
        model = _create_chat_model(self.db)
        ctx = ToolContext(
            session_id=self.session_id,
            workspace=self.workspace,
            builder=self.builder,
            db=self.db,
            skills=self.skills,
        )
        tools = (
            make_readonly_tools(ctx)
            + make_write_tools(ctx)
            + [make_ask_user_tool(ctx)]
        )
        prompt_fn = _build_prompt_fn(self.workspace, self.skills)
        return create_react_agent(
            model=model,
            tools=tools,
            state_modifier=prompt_fn,
            checkpointer=self._checkpointer,
        )

    async def run(
        self,
        messages: list[HumanMessage | AIMessage | ToolMessage],
        on_event: EventCallback | None = None,
    ) -> list[Any]:
        """Run the ReAct agent and emit SSE events.

        Returns the final message list (including any new messages produced).
        """
        agent = self._build_agent()
        config = {"configurable": {"thread_id": self.session_id}}

        last_snapshot_hash = _builder_snapshot_hash(self.builder)
        accumulated_content = ""
        last_ai_message_had_tool_calls = False

        async def _emit(event_type: str, payload: dict) -> None:
            if on_event is not None:
                await on_event({"type": event_type, **payload})

        await _emit("session_start", {"session_id": self.session_id, "goal": self.workspace.goal})

        try:
            async for event in agent.astream(
                {"messages": messages},
                config,
                stream_mode="messages",
            ):
                msg, metadata = event

                # Handle AI message (content or tool calls)
                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        last_ai_message_had_tool_calls = True
                        for tc in msg.tool_calls:
                            await _emit("tool_call", {
                                "tool": tc.get("name"),
                                "args": tc.get("args"),
                                "tool_call_id": tc.get("id"),
                            })
                    if msg.content:
                        accumulated_content += str(msg.content)
                        await _emit("agent_message_delta", {
                            "content": str(msg.content),
                        })

                # Handle ToolMessage
                if isinstance(msg, ToolMessage):
                    await _emit("tool_result", {
                        "tool": msg.name,
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    })

                    # Detect ask_user pause marker
                    try:
                        data = json.loads(msg.content)
                        if isinstance(data, dict) and data.get("__pause__"):
                            await _emit("awaiting_user_input", {
                                "question_id": data.get("question_id"),
                                "prompt": data.get("question"),
                                "options": data.get("options"),
                            })
                            # End stream gracefully — caller will resume with user answer
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass

                    # Detect graph changes after write tools
                    current_hash = _builder_snapshot_hash(self.builder)
                    if current_hash != last_snapshot_hash:
                        last_snapshot_hash = current_hash
                        snapshot = self.builder.snapshot()
                        await _emit("graph_update", {
                            "snapshot": snapshot,
                            "node_count": len(snapshot.get("nodes", [])),
                            "edge_count": len(snapshot.get("edges", [])),
                        })

                    # Detect validation report from validate_graph or finalize_graph
                    try:
                        data = json.loads(msg.content)
                        if isinstance(data, dict) and "errors" in data and "warnings" in data:
                            await _emit("validator_report", {
                                "findings": data.get("errors", []) + data.get("warnings", []),
                            })
                        if isinstance(data, dict) and data.get("status") == "ready":
                            await _emit("harness_ready", {
                                "snapshot": self.builder.snapshot(),
                            })
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Emit final accumulated message if there was content and no tool calls
            if accumulated_content and not last_ai_message_had_tool_calls:
                await _emit("agent_message", {"content": accumulated_content})

            # Return final state messages
            final_state = await agent.aget_state(config)
            return list(final_state.values.get("messages", []))

        except PauseAgentRun as exc:
            # Safety net for direct raise (should not happen with marker approach)
            await _emit("awaiting_user_input", {
                "question_id": exc.question_id,
                "prompt": exc.question,
                "options": exc.options,
            })
            final_state = await agent.aget_state(config)
            return list(final_state.values.get("messages", []))
