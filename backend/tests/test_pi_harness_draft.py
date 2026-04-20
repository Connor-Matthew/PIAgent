from __future__ import annotations

import json
from pathlib import Path

from backend.pi_harness.runtime.skills.loader import load_skills
from backend.pi_harness.state import WorkflowGraphDraft
from backend.pi_harness.tools.finalize import build_finalize_draft_tool
from backend.pi_harness.tools.graph_ops import build_graph_op_tools
from backend.pi_harness.tools.validate import build_validate_graph_tool
from backend.models.provider import Provider


def test_workflow_graph_draft_and_graph_tools_mutate_snapshot():
    events: list[dict] = []
    draft = WorkflowGraphDraft()
    tools = {tool.name: tool for tool in build_graph_op_tools(draft, event_sink=events.append)}

    add_node = tools["add_node"]
    connect_nodes = tools["connect_nodes"]
    patch_node_config = tools["patch_node_config"]
    remove_edge = tools["remove_edge"]

    start_payload = json.loads(add_node.invoke({"node_type": "start", "node_id": "start"}))
    llm_payload = json.loads(
            add_node.invoke(
                {
                    "node_type": "llm",
                    "node_id": "llm_1",
                    "node_config": {"provider_id": 7},
                    "parent_id": "branch_parent",
                    "branch_id": "then",
                }
            )
        )
    edge_payload = json.loads(
        connect_nodes.invoke(
            {"from_id": "start", "to_id": "llm_1", "source_handle": "main"}
        )
    )
    patched_payload = json.loads(
        patch_node_config.invoke(
            {"node_id": "llm_1", "fields": {"temperature": 0.2}}
        )
    )

    snapshot = draft.snapshot()
    llm_node = next(node for node in snapshot["nodes"] if node["id"] == "llm_1")
    edge = snapshot["edges"][0]

    assert start_payload["node_id"] == "start"
    assert llm_payload["node_id"] == "llm_1"
    assert edge_payload["edge_id"] == "start-llm_1"
    assert patched_payload["node_id"] == "llm_1"
    assert llm_node["config"]["provider_id"] == 7
    assert llm_node["config"]["temperature"] == 0.2
    assert llm_node["parentId"] == "branch_parent"
    assert llm_node["branchId"] == "then"
    assert edge["sourceHandle"] == "main"
    assert [event["operation"] for event in events] == [
        "add_node",
        "add_node",
        "connect_nodes",
        "patch_node_config",
    ]

    json.loads(remove_edge.invoke({"from_id": "start", "to_id": "llm_1"}))
    assert draft.snapshot()["edges"] == []


def test_validate_graph_tool_reports_findings_for_invalid_draft():
    draft = WorkflowGraphDraft()
    validate_tool = build_validate_graph_tool(draft)

    payload = json.loads(validate_tool.invoke({}))

    codes = {finding["code"] for finding in payload["findings"]}
    assert "missing_start" in codes
    assert "missing_end" in codes


def test_vendored_skill_loader_reads_pi_harness_skill_directories():
    skills = load_skills(Path("backend/pi_harness/skills"))
    names = {skill.name for skill in skills}

    assert {"llm_basic", "rag_qa", "io_contract", "simple_pipeline", "tts_podcast"} <= names


def test_finalize_draft_tool_marks_valid_graph_ready(db):
    db.add(
        Provider(
            type="openai",
            name="Finalize Provider",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.commit()

    draft = WorkflowGraphDraft()
    draft.add_node(
        node_type="start",
        node_id="start",
        config={"inputs": [{"name": "question", "type": "string", "required": True}]},
    )
    draft.add_node(
        node_type="llm",
        node_id="llm_1",
        config={"provider_id": 1, "model": "gpt-4o-mini"},
    )
    draft.add_node(
        node_type="end",
        node_id="end",
        config={
            "outputs": [
                {"name": "answer", "source": "reference", "value": "{{llm_1.text}}"}
            ]
        },
    )
    draft.connect_nodes(from_id="start", to_id="llm_1")
    draft.connect_nodes(from_id="llm_1", to_id="end")

    finalize_tool = build_finalize_draft_tool(draft, db=db)
    payload = json.loads(finalize_tool.invoke({}))

    assert payload["ready"] is True
    assert payload["graph"]["nodes"][-1]["id"] == "end"
    assert payload["findings"] == []
