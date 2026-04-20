from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.tools import BaseTool
from pydantic import Field

from backend.models.provider import Provider
from backend.pi_harness.adapters.provider_bridge import DBModelResolver
from backend.pi_harness.runtime.agent.graph import create_agent
from backend.pi_harness.state import WorkflowGraphDraft
from backend.pi_harness.tools.finalize import build_finalize_draft_tool
from backend.pi_harness.tools.graph_ops import build_graph_op_tools


class SessionTool(BaseTool):
    name: str = "session_tool"
    description: str = "Record a session-scoped value."
    calls: list[str] = Field(default_factory=list)

    def _run(self, value: str) -> str:
        self.calls.append(value)
        return f"recorded:{value}"

    async def _arun(self, value: str) -> str:
        return self._run(value)


class ToolCallingFakeModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_create_agent_prefers_injected_model_and_tool_instances(monkeypatch):
    fake_model = object()
    fake_tool = SessionTool()
    captured: dict[str, object] = {}

    def fake_create_react_agent(model, tools, **kwargs):
        captured["model"] = model
        captured["tools"] = tools
        captured["kwargs"] = kwargs
        return "agent"

    monkeypatch.setattr(
        "backend.pi_harness.runtime.agent.graph.create_react_agent",
        fake_create_react_agent,
    )

    agent = create_agent(
        model=fake_model,
        tool_instances=[fake_tool],
        enable_summarization=False,
        enable_loop_detection=False,
        enable_clarification=False,
    )

    assert agent == "agent"
    assert captured["model"] is fake_model
    assert captured["tools"] == [fake_tool]


@pytest.mark.asyncio
async def test_create_agent_smoke_runs_session_scoped_tool():
    tool = SessionTool()
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "name": "session_tool",
                        "args": {"value": "draft-node"},
                    }
                ],
            ),
            AIMessage(content="draft ready"),
        ]
    )

    agent = create_agent(
        model=model,
        tool_instances=[tool],
        enable_summarization=False,
        enable_loop_detection=False,
        enable_clarification=False,
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content="build a draft")]})

    assert tool.calls == ["draft-node"]
    assert result["messages"][-1].content == "draft ready"


def test_db_model_resolver_builds_chat_model_from_provider_row(db, monkeypatch):
    monkeypatch.setattr(
        "backend.pi_harness.adapters.provider_bridge.settings.agent_llm_model",
        None,
    )

    db.add(
        Provider(
            type="openai",
            name="Harness Provider",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.commit()

    chat_model = object()
    provider = MagicMock()
    provider.create_chat_model.return_value = chat_model

    with patch(
        "backend.pi_harness.adapters.provider_bridge.build_provider",
        return_value=provider,
    ):
        resolver = DBModelResolver(db)
        result = resolver.get_model()

    assert result is chat_model
    provider.create_chat_model.assert_called_once_with(
        model="gpt-4o-mini",
        temperature=0,
        streaming=True,
    )


@pytest.mark.asyncio
async def test_create_agent_can_build_valid_workflow_draft_with_pi_harness_tools(db):
    db.add(
        Provider(
            type="openai",
            name="Runtime Draft Provider",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.commit()

    draft = WorkflowGraphDraft()
    tools = [
        *build_graph_op_tools(draft),
        build_finalize_draft_tool(draft, db=db),
    ]
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_start",
                        "name": "add_node",
                        "args": {
                            "node_type": "start",
                            "node_id": "start",
                            "node_config": {
                                "inputs": [
                                    {
                                        "name": "question",
                                        "type": "string",
                                        "required": True,
                                    }
                                ]
                            },
                        },
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_llm",
                        "name": "add_node",
                        "args": {
                            "node_type": "llm",
                            "node_id": "llm_1",
                            "node_config": {
                                "provider_id": 1,
                                "model": "gpt-4o-mini",
                            },
                        },
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_end",
                        "name": "add_node",
                        "args": {
                            "node_type": "end",
                            "node_id": "end",
                            "node_config": {
                                "outputs": [
                                    {
                                        "name": "answer",
                                        "source": "reference",
                                        "value": "{{llm_1.text}}",
                                    }
                                ]
                            },
                        },
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_edge_1",
                        "name": "connect_nodes",
                        "args": {"from_id": "start", "to_id": "llm_1"},
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_edge_2",
                        "name": "connect_nodes",
                        "args": {"from_id": "llm_1", "to_id": "end"},
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_finalize",
                        "name": "finalize_draft",
                        "args": {},
                    }
                ],
            ),
            AIMessage(content="workflow ready"),
        ]
    )

    agent = create_agent(
        model=model,
        tool_instances=tools,
        enable_summarization=False,
        enable_loop_detection=False,
        enable_clarification=False,
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content="build a workflow")]})
    tool_messages = [msg for msg in result["messages"] if getattr(msg, "type", "") == "tool"]
    finalize_messages = [
        msg for msg in tool_messages if getattr(msg, "name", None) == "finalize_draft"
    ]

    assert draft.snapshot()["nodes"][-1]["id"] == "end"
    assert any(json.loads(msg.content)["ready"] is True for msg in finalize_messages)
    assert result["messages"][-1].content == "workflow ready"
