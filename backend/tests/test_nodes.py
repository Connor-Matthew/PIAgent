from backend.core.state import WorkflowState
from backend.nodes.registry import NodeRegistry
from backend.nodes.base import BaseNode


def test_workflow_state_has_required_fields():
    state: WorkflowState = {
        "input": "",
        "messages": [],
        "context": "",
        "llm_output": "",
        "audio_url": "",
        "node_outputs": {},
    }
    assert state["input"] == ""


def test_node_registry_register_and_get():
    class FakeNode(BaseNode):
        node_type = "fake"

        async def execute(self, state: WorkflowState) -> WorkflowState:
            return state

    registry = NodeRegistry()
    registry.register(FakeNode)
    node_cls = registry.get("fake")
    assert node_cls is FakeNode


def test_node_registry_get_unknown_raises():
    registry = NodeRegistry()
    import pytest

    with pytest.raises(KeyError):
        registry.get("nonexistent")
