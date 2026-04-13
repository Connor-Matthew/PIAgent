import pytest

from backend.core.state import WorkflowState
from backend.nodes.registry import NodeRegistry
from backend.nodes.base import BaseNode


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
    from backend.nodes.start_node import StartNode
    node = StartNode(config={})
    state: WorkflowState = {
        "input": "", "messages": [], "context": "",
        "llm_output": "", "audio_url": "", "node_outputs": {},
    }
    result = await node.execute(state, user_input="你好世界")
    assert result["input"] == "你好世界"
    assert "start" in result["node_outputs"]


@pytest.mark.asyncio
async def test_end_node_collects_output():
    from backend.nodes.end_node import EndNode
    node = EndNode(config={})
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "/audio/test.mp3",
        "node_outputs": {},
    }
    result = await node.execute(state)
    assert result["node_outputs"]["end"]["llm_output"] == "generated text"
    assert result["node_outputs"]["end"]["audio_url"] == "/audio/test.mp3"
