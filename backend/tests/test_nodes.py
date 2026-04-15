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
    assert result["node_outputs"]["end"]["outputs"] == {}
    assert result["node_outputs"]["end"]["answer"] == ""


@pytest.mark.asyncio
async def test_end_node_with_outputs_and_answer():
    node = EndNode(config={
        "outputs": [
            {"name": "audio_url", "source": "reference", "value": "{{tts_1.audio_url}}"},
            {"name": "title", "source": "input", "value": "今天的 AI 播客"},
        ],
        "answer": "🎧 {{title}} 已生成，链接：{{audio_url}}",
    })
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "/audio/test.mp3",
        "node_outputs": {
            "tts_1": {"audio_url": "/audio/final.mp3"},
        },
    }
    result = await node.execute(state)
    assert result["node_outputs"]["end"]["outputs"]["audio_url"] == "/audio/final.mp3"
    assert result["node_outputs"]["end"]["outputs"]["title"] == "今天的 AI 播客"
    assert result["node_outputs"]["end"]["answer"] == "🎧 今天的 AI 播客 已生成，链接：/audio/final.mp3"
    assert result["answer"] == "🎧 今天的 AI 播客 已生成，链接：/audio/final.mp3"
    assert result["outputs"]["audio_url"] == "/audio/final.mp3"


@pytest.mark.asyncio
async def test_end_node_omitted_node_outputs():
    node = EndNode(config={})
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "/audio/test.mp3",
    }
    result = await node.execute(state)
    assert result["node_outputs"]["end"]["outputs"] == {}
    assert result["node_outputs"]["end"]["answer"] == ""


@pytest.mark.asyncio
async def test_start_node_missing_required_raises():
    node = StartNode(config={
        "inputs": [{"name": "topic", "type": "text", "required": True}]
    })
    state: WorkflowState = {
        "input": "", "messages": [], "context": "",
        "llm_output": "", "audio_url": "", "node_outputs": {},
    }
    with pytest.raises(ValueError, match="Missing required input field"):
        await node.execute(state, inputs={})


@pytest.mark.asyncio
async def test_end_node_answer_with_direct_reference():
    """End node answer template can directly reference upstream node outputs."""
    node = EndNode(config={
        "outputs": [
            {"name": "audio_url", "source": "reference", "value": "{{tts_1.audio_url}}"},
        ],
        "answer": "Direct: {{tts_1.audio_url}} / Local: {{audio_url}}",
    })
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "",
        "node_outputs": {
            "tts_1": {"audio_url": "/audio/direct.mp3"},
        },
    }
    result = await node.execute(state)
    assert result["answer"] == "Direct: /audio/direct.mp3 / Local: /audio/direct.mp3"


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
            "provider_id": 1,
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

        node = LLMNode(config={"provider_id": 1})
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

        node = LLMNode(config={"provider_id": 1})
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


@pytest.mark.asyncio
async def test_llm_node_emits_stream_events():
    from backend.nodes.llm_node import LLMNode
    from langchain_core.messages import AIMessageChunk

    class StreamingChatModel:
        async def astream(self, messages):
            for token in ["你好", "，世界"]:
                yield AIMessageChunk(content=token)

        async def ainvoke(self, messages):
            raise AssertionError("ainvoke should not be used when streaming succeeds")

    events = []

    async def on_event(event):
        events.append(event)

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model", return_value=StreamingChatModel()):
        node = LLMNode(config={"provider_id": 1, "id": "llm_1"})
        state: WorkflowState = {
            "input": "Say hello",
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state, on_event=on_event)

    assert [event["delta"] for event in events] == ["你好", "，世界"]
    assert result["llm_output"] == "你好，世界"
    assert result["node_outputs"]["llm_1"]["text"] == "你好，世界"


def test_agent_node_missing_provider_id_raises():
    from backend.nodes.agent_node import AgentNode

    node = AgentNode(config={})
    with pytest.raises(ValueError, match="provider_id is required"):
        node._build_agent()


def test_agent_node_unknown_tool_raises():
    from backend.nodes.agent_node import AgentNode

    mock_row = MagicMock()
    mock_row.enabled = True
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = mock_row

    with patch("backend.nodes.agent_node.SessionLocal", return_value=mock_session):
        with patch("backend.nodes.agent_node.build_provider") as mock_build:
            mock_build.return_value = MagicMock()
            node = AgentNode(config={"provider_id": 1, "tools": ["unknown_tool"]})
            with pytest.raises(ValueError, match="Unknown tool"):
                node._build_agent()


def test_llm_node_missing_provider_id_raises():
    from backend.nodes.llm_node import LLMNode

    node = LLMNode(config={})
    with pytest.raises(ValueError, match="provider_id is required"):
        node._get_chat_model()


@pytest.mark.asyncio
async def test_tts_node_generates_audio_url():
    from backend.nodes.tts_node import TTSNode

    with patch("backend.nodes.tts_node.TTSNode._get_tts_provider") as mock_get:
        mock_provider = AsyncMock()
        mock_provider.synthesize.return_value = "/audio/test123.mp3"
        mock_get.return_value = mock_provider

        node = TTSNode(config={"provider_id": 1, "voice_id": "default"})
        state: WorkflowState = {
            "input": "test", "messages": [], "context": "",
            "llm_output": "Hello, welcome to the podcast.",
            "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["audio_url"].endswith(".mp3")


def test_tts_node_missing_provider_id_raises():
    from backend.nodes.tts_node import TTSNode

    node = TTSNode(config={})
    with pytest.raises(ValueError, match="provider_id is required"):
        node._get_tts_provider()


@pytest.mark.asyncio
async def test_tts_node_fallback_to_input():
    from backend.nodes.tts_node import TTSNode

    with patch("backend.nodes.tts_node.TTSNode._get_tts_provider") as mock_get:
        mock_provider = AsyncMock()
        mock_provider.synthesize.return_value = "/audio/fallback.mp3"
        mock_get.return_value = mock_provider

        node = TTSNode(config={"provider_id": 1, "voice_id": "default"})
        state: WorkflowState = {
            "input": "Fallback text",
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["audio_url"].endswith(".mp3")
        mock_provider.synthesize.assert_awaited_once()
        # Verify it used the input text since llm_output was empty
        call_kwargs = mock_provider.synthesize.await_args.kwargs
        assert call_kwargs["text"] == "Fallback text"


@pytest.mark.asyncio
async def test_tts_node_populates_node_outputs():
    from backend.nodes.tts_node import TTSNode

    with patch("backend.nodes.tts_node.TTSNode._get_tts_provider") as mock_get:
        mock_provider = AsyncMock()
        mock_provider.synthesize.return_value = "/audio/output.mp3"
        mock_get.return_value = mock_provider

        node = TTSNode(config={"provider_id": 1, "voice_id": "default", "id": "tts_1"})
        state: WorkflowState = {
            "input": "test",
            "messages": [],
            "context": "",
            "llm_output": "Hello world",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["node_outputs"]["tts_1"]["audio_url"] == "/audio/output.mp3"


@pytest.mark.asyncio
async def test_rag_node_retrieves_context():
    from backend.nodes.rag_node import RAGNode

    with patch("backend.nodes.rag_node.RAGNode._get_retriever") as mock_get:
        from langchain_core.documents import Document
        mock_retriever = AsyncMock()
        mock_retriever.ainvoke.return_value = [
            Document(page_content="AI is transforming education worldwide."),
            Document(page_content="Personalized learning is a key benefit."),
        ]
        mock_get.return_value = mock_retriever

        node = RAGNode(config={"knowledge_base_id": "kb1", "top_k": 3})
        state: WorkflowState = {
            "input": "AI in education", "messages": [], "context": "",
            "llm_output": "", "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert "AI is transforming" in result["context"]
        assert "Personalized learning" in result["context"]
        assert len(result["node_outputs"]["rag"]["documents"]) == 2
        assert "AI is transforming" in result["node_outputs"]["rag"]["context"]


@pytest.mark.asyncio
async def test_rag_node_clears_context_when_no_docs():
    from backend.nodes.rag_node import RAGNode

    with patch("backend.nodes.rag_node.RAGNode._get_retriever") as mock_get:
        mock_retriever = AsyncMock()
        mock_retriever.ainvoke.return_value = []
        mock_get.return_value = mock_retriever

        node = RAGNode(config={"knowledge_base_id": "kb1", "top_k": 3})
        state: WorkflowState = {
            "input": "AI in education", "messages": [], "context": "existing context",
            "llm_output": "", "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["context"] == ""
        assert len(result["node_outputs"]["rag"]["documents"]) == 0


@pytest.mark.asyncio
async def test_agent_node_executes():
    from backend.nodes.agent_node import AgentNode

    with patch("backend.nodes.agent_node.AgentNode._build_agent") as mock_build:
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [MagicMock(content="Agent completed the task. Here's the podcast script.")]
        }
        mock_build.return_value = mock_agent

        node = AgentNode(config={
            "provider_id": 1,
            "model": "gpt-4o",
            "system_prompt": "You are a helpful agent.",
            "tools": ["rag", "tts"],
        })
        state: WorkflowState = {
            "input": "Make a podcast about AI", "messages": [], "context": "",
            "llm_output": "", "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["llm_output"] == "Agent completed the task. Here's the podcast script."
        assert result["node_outputs"]["agent"]["text"] == "Agent completed the task. Here's the podcast script."
        assert result["node_outputs"]["agent"]["steps"] == []
