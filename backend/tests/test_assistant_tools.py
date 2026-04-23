from types import SimpleNamespace

from backend.core.crypto import encrypt
from backend.models.knowledge_base import KnowledgeBase
from backend.models.provider import Provider
from backend.models.run import WorkflowRun
from backend.models.run_event import WorkflowRunEvent
from backend.models.workflow import Workflow
from backend.assistant.tools import build_readonly_tools


GRAPH = {
    "version": 2,
    "nodes": [
        {
            "id": "start_1",
            "type": "start",
            "label": "Start",
            "config": {"inputs": [{"name": "question", "type": "text"}]},
        },
        {
            "id": "llm_1",
            "type": "llm",
            "label": "Writer",
            "config": {"provider_id": 7, "model": "gpt-4o-mini"},
        },
        {"id": "end_1", "type": "end", "label": "End", "config": {"answer": "{{llm_1.text}}"}},
    ],
    "edges": [
        {"source": "start_1", "target": "llm_1"},
        {"source": "llm_1", "target": "end_1"},
    ],
}


def _tool(tools, name):
    return next(tool for tool in tools if tool.name == name)


def _seed_workflow(db):
    workflow = Workflow(name="Assistant Test", description="Demo")
    workflow.graph = GRAPH
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def test_graph_and_node_tools_return_current_workflow_context(db):
    workflow = _seed_workflow(db)
    tools = build_readonly_tools(db, workflow.id)

    graph = _tool(tools, "get_current_graph").invoke({})
    node_config = _tool(tools, "get_node_config").invoke({"node_id": "llm_1"})

    assert graph["id"] == workflow.id
    assert graph["graph"]["nodes"][1]["id"] == "llm_1"
    assert node_config == {
        "node_id": "llm_1",
        "type": "llm",
        "label": "Writer",
        "config": {"provider_id": 7, "model": "gpt-4o-mini"},
    }


def test_list_node_types_uses_backend_contracts(db):
    workflow = _seed_workflow(db)
    tools = build_readonly_tools(db, workflow.id)

    result = _tool(tools, "list_node_types").invoke({})

    assert "llm" in {item["node_type"] for item in result["node_types"]}
    llm = next(item for item in result["node_types"] if item["node_type"] == "llm")
    assert "provider_id" in {field["name"] for field in llm["config_fields"]}


def test_provider_and_kb_tools_return_redacted_metadata(db):
    workflow = _seed_workflow(db)
    db.add(
        Provider(
            id=7,
            type="openai",
            category="llm",
            name="OpenAI",
            api_key_encrypted=encrypt("sk-secret"),
            enabled=True,
            selected_models=["gpt-4o-mini"],
        )
    )
    db.add(KnowledgeBase(id="kb_1", name="Docs", description="Product docs", doc_count=3))
    db.commit()
    tools = build_readonly_tools(db, workflow.id)

    providers = _tool(tools, "list_providers").invoke({})
    knowledge_bases = _tool(tools, "list_knowledge_bases").invoke({})

    assert providers["providers"][0]["api_key"] == "sk-***cret"
    assert providers["providers"][0]["selected_models"] == ["gpt-4o-mini"]
    assert knowledge_bases["knowledge_bases"] == [
        {"id": "kb_1", "name": "Docs", "description": "Product docs", "doc_count": 3}
    ]


def test_peek_knowledge_base_queries_vectorstore(db, monkeypatch):
    workflow = _seed_workflow(db)
    db.add(KnowledgeBase(id="kb_1", name="Docs", description="", doc_count=1))
    db.commit()

    class FakeRetriever:
        def invoke(self, query):
            assert query == "pricing"
            return [SimpleNamespace(page_content="pricing chunk", metadata={"source": "doc.md"})]

    class FakeVectorstore:
        def as_retriever(self, search_kwargs):
            assert search_kwargs == {"k": 3}
            return FakeRetriever()

    monkeypatch.setattr("backend.assistant.tools.get_vectorstore", lambda collection_name: FakeVectorstore())
    tools = build_readonly_tools(db, workflow.id)

    result = _tool(tools, "peek_knowledge_base").invoke({"kb_id": "kb_1", "query": "pricing"})

    assert result["chunks"] == [{"content": "pricing chunk", "metadata": {"source": "doc.md"}}]


def test_run_tools_return_recent_runs_and_persisted_events(db):
    workflow = _seed_workflow(db)
    older = WorkflowRun(workflow_id=workflow.id, status="failed", input_text="old")
    newer = WorkflowRun(workflow_id=workflow.id, status="completed", input_text="new")
    db.add_all([older, newer])
    db.commit()
    db.refresh(older)
    db.refresh(newer)

    first_event = WorkflowRunEvent(workflow_id=workflow.id, run_id=newer.id, seq=1, event_type="node_start")
    first_event.event = {"type": "node_start", "node_id": "llm_1"}
    second_event = WorkflowRunEvent(workflow_id=workflow.id, run_id=newer.id, seq=2, event_type="workflow_end")
    second_event.event = {"type": "workflow_end", "status": "completed"}
    db.add_all([first_event, second_event])
    db.commit()

    tools = build_readonly_tools(db, workflow.id)

    runs = _tool(tools, "get_recent_runs").invoke({"limit": 2})
    events = _tool(tools, "get_run_events").invoke({"run_id": newer.id})

    assert [run["id"] for run in runs["runs"]] == [newer.id, older.id]
    assert events["events"] == [
        {"type": "node_start", "node_id": "llm_1"},
        {"type": "workflow_end", "status": "completed"},
    ]


def test_readonly_tool_surface_excludes_mutations(db):
    workflow = _seed_workflow(db)
    names = {tool.name for tool in build_readonly_tools(db, workflow.id)}

    assert names == {
        "get_current_graph",
        "get_node_config",
        "list_node_types",
        "list_providers",
        "list_knowledge_bases",
        "peek_knowledge_base",
        "get_recent_runs",
        "get_run_events",
    }
    assert names.isdisjoint({"update_node", "add_node", "delete_node", "apply_graph"})
