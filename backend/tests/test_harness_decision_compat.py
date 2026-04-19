from unittest.mock import MagicMock

from backend.harness.lead_agent import LeadAgent
from backend.harness.schemas import CallTool, Finalize, LoadSkill, ProposeAction, validate_decision_payload
from backend.harness.tools import ToolRegistry
from backend.harness.workspace import Workspace


def test_validate_decision_payload_normalizes_legacy_load_skill_shape():
    decision = validate_decision_payload({
        "decision": "load_skill",
        "skill_name": "tts_podcast",
    })

    assert isinstance(decision, LoadSkill)
    assert decision.skill == "tts_podcast"


def test_validate_decision_payload_normalizes_old_call_tool_shape():
    decision = validate_decision_payload({
        "kind": "call_tool",
        "name": "list_providers",
        "arguments": {"type": "llm", "detailed": True},
    })

    assert isinstance(decision, CallTool)
    assert decision.tool == "list_providers"
    assert decision.args == {"type": "llm", "detailed": True}


def test_validate_decision_payload_normalizes_legacy_finalize_shape():
    decision = validate_decision_payload({
        "done": True,
        "reasoning": "graph is complete",
    })

    assert isinstance(decision, Finalize)
    assert decision.reason == "graph is complete"


def test_validate_decision_payload_normalizes_legacy_add_node_action_shape():
    decision = validate_decision_payload({
        "kind": "propose_action",
        "action": {
            "kind": "add_node",
            "node": {
                "id": "start_1",
                "type": "start",
                "data": {"inputs": []},
            },
        },
    })

    assert isinstance(decision, ProposeAction)
    assert decision.action.kind == "add_node"
    assert decision.action.node_type == "start"
    assert decision.action.node_id == "start_1"
    assert decision.action.config == {"inputs": []}


def test_lead_agent_decide_adapts_legacy_payload():
    workspace = Workspace()
    workspace.bootstrap("做一期带 TTS 的播客工作流")

    agent = LeadAgent(
        db=MagicMock(),
        tool_registry=ToolRegistry(),
        skill_catalog=[],
    )
    agent.llm = MagicMock()
    agent.llm.structured_invoke.return_value = {
        "decision": "load_skill",
        "skill_name": "tts_podcast",
    }

    decision = agent.decide(workspace)

    assert isinstance(decision, LoadSkill)
    assert decision.skill == "tts_podcast"


def test_validate_decision_payload_normalizes_from_to_node_edge_aliases():
    decision = validate_decision_payload({
        "kind": "propose_action",
        "action": {
            "kind": "add_edge",
            "from_node": "start",
            "to_node": "llm_1",
        },
    })

    assert isinstance(decision, ProposeAction)
    assert decision.action.kind == "add_edge"
    assert decision.action.source == "start"
    assert decision.action.target == "llm_1"


def test_validate_decision_payload_normalizes_short_from_to_edge_aliases():
    decision = validate_decision_payload({
        "kind": "propose_action",
        "action": {
            "kind": "delete_edge",
            "from": "a",
            "to": "b",
        },
    })

    assert isinstance(decision, ProposeAction)
    assert decision.action.kind == "delete_edge"
    assert decision.action.source == "a"
    assert decision.action.target == "b"


def test_validate_decision_payload_normalizes_top_level_node_type_alias():
    decision = validate_decision_payload({
        "kind": "propose_action",
        "action": {
            "kind": "add_node",
            "type": "tts",
            "id": "tts_1",
            "config": {"voice": "alloy"},
        },
    })

    assert isinstance(decision, ProposeAction)
    assert decision.action.kind == "add_node"
    assert decision.action.node_type == "tts"
    assert decision.action.node_id == "tts_1"
    assert decision.action.config == {"voice": "alloy"}


def test_validate_decision_payload_maps_validate_graph_to_finalize():
    decision = validate_decision_payload({
        "kind": "validate_graph",
        "action": {"kind": "add_edge", "source": "llm_1", "target": "end"},
    })

    assert isinstance(decision, Finalize)
    assert decision.reason


def test_validate_decision_payload_maps_commit_to_finalize():
    decision = validate_decision_payload({"kind": "commit", "reason": "ready"})

    assert isinstance(decision, Finalize)
    assert decision.reason == "ready"
