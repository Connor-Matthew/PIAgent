import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.state import WorkflowState
from backend.nodes.registry import NodeRegistry
from backend.nodes.base import BaseNode
from backend.nodes.start_node import StartNode
from backend.nodes.end_node import EndNode


def test_workflow_state_has_required_fields():
    state: WorkflowState = {
        "input": "",
    }
    assert state["input"] == ""


def test_node_registry_register_and_get():
    class FakeNode(BaseNode):
        node_type = "fake"

        async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
            return state

    registry = NodeRegistry()
    registry.register(FakeNode)
    node_cls = registry.get("fake")
    assert node_cls is FakeNode


def test_node_registry_get_unknown_raises():
    registry = NodeRegistry()

    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_base_node_subclass_without_node_type_raises():
    with pytest.raises(ValueError, match="must define a non-empty node_type"):
        class BadNode(BaseNode):
            async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
                return state


def test_node_registry_register_duplicate_raises():
    class FakeNode(BaseNode):
        node_type = "duplicate"

        async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
            return state

    registry = NodeRegistry()
    registry.register(FakeNode)

    with pytest.raises(KeyError, match="already registered"):
        registry.register(FakeNode)


def test_base_node_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseNode()


@pytest.mark.asyncio
async def test_start_node_writes_input():
    node = StartNode(config={})
    state: WorkflowState = {
        "input": "", "messages": [], "context": "",
        "llm_output": "", "audio_url": "", "node_outputs": {},
    }
    result = await node.execute(state, user_input="你好世界")
    assert result["input"] == "你好世界"
    assert "start" in result["node_outputs"]


@pytest.mark.asyncio
async def test_start_node_omitted_node_outputs():
    node = StartNode(config={})
    state: WorkflowState = {
        "input": "", "messages": [], "context": "",
        "llm_output": "", "audio_url": "",
    }
    result = await node.execute(state, user_input="hello")
    assert result["input"] == "hello"
    assert result["node_outputs"]["start"] == {"input": "hello"}


@pytest.mark.asyncio
async def test_start_node_falls_back_to_state_input():
    node = StartNode(config={})
    state: WorkflowState = {
        "input": "existing input", "messages": [], "context": "",
        "llm_output": "", "audio_url": "",
    }
    result = await node.execute(state)
    assert result["input"] == "existing input"
    assert result["node_outputs"]["start"] == {"input": "existing input"}


@pytest.mark.asyncio
async def test_end_node_collects_output():
    node = EndNode(config={})
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "/audio/test.mp3",
        "node_outputs": {},
    }
    result = await node.execute(state)
    assert result["node_outputs"]["end"]["llm_output"] == "generated text"
    assert result["node_outputs"]["end"]["audio_url"] == "/audio/test.mp3"


@pytest.mark.asyncio
async def test_end_node_omitted_node_outputs():
    node = EndNode(config={})
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "/audio/test.mp3",
    }
    result = await node.execute(state)
    assert result["node_outputs"]["end"]["llm_output"] == "generated text"
    assert result["node_outputs"]["end"]["audio_url"] == "/audio/test.mp3"


@pytest.mark.asyncio
async def test_llm_node_generates_output():
    from backend.nodes.llm_node import LLMNode

    mock_response = MagicMock()
    mock_response.content = "Generated podcast script about AI."

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_get:
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        mock_get.return_value = mock_model

        node = LLMNode(config={
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "system_prompt": "You are a podcast writer.",
        })
        state: WorkflowState = {
            "input": "AI in education",
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["llm_output"] == "Generated podcast script about AI."
        assert len(result["messages"]) > 0


@pytest.mark.asyncio
async def test_llm_node_with_rag_context():
    from backend.nodes.llm_node import LLMNode

    mock_response = MagicMock()
    mock_response.content = "Answer with context."

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_get:
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        mock_get.return_value = mock_model

        node = LLMNode(config={})
        state: WorkflowState = {
            "input": "What is RAG?",
            "messages": [],
            "context": "RAG stands for Retrieval-Augmented Generation.",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["llm_output"] == "Answer with context."
        # Verify the user message includes the context
        user_message = result["messages"][0]
        assert "RAG stands for Retrieval-Augmented Generation" in user_message.content
        assert "What is RAG?" in user_message.content


@pytest.mark.asyncio
async def test_llm_node_preserves_message_history():
    from backend.nodes.llm_node import LLMNode
    from langchain_core.messages import AIMessage

    mock_response = MagicMock()
    mock_response.content = "Second response."

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_get:
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        mock_get.return_value = mock_model

        node = LLMNode(config={})
        existing_message = AIMessage(content="First response.")
        state: WorkflowState = {
            "input": "Follow up",
            "messages": [existing_message],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state)
        assert existing_message in result["messages"]
        assert len(result["messages"]) == 3  # existing + HumanMessage + response


def test_llm_node_unknown_provider_raises():
    from backend.nodes.llm_node import LLMNode

    node = LLMNode(config={"provider": "unknown_provider"})
    with pytest.raises(ValueError, match="Unknown provider"):
        node._get_chat_model()
