from types import SimpleNamespace

from backend.models.workflow import Workflow


def test_assistant_route_injects_readonly_tools_for_graph_context(client, db, monkeypatch):
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": [{"name": "question", "type": "text"}]}},
            {
                "id": "llm_1",
                "type": "llm",
                "config": {
                    "provider_id": 1,
                    "model": "gpt-4o-mini",
                    "prompt_template": "请总结：{{missing_1.text}}",
                },
            },
            {"id": "end_1", "type": "end", "config": {"answer": "{{llm_1.text}}"}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }
    workflow = Workflow(name="Missing Reference")
    workflow.graph = graph
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    def fake_create_agent(*, system_prompt, tool_instances):
        assert "不修改 graph" in system_prompt
        graph_tool = next(tool for tool in tool_instances if tool.name == "get_current_graph")

        class FakeAgent:
            async def astream(self, state, stream_mode):
                graph_payload = graph_tool.invoke({})
                prompt = graph_payload["graph"]["nodes"][1]["config"]["prompt_template"]
                yield (
                    SimpleNamespace(
                        type="ai",
                        content=f"LLM 节点引用了不存在的 missing_1：{'missing_1' in prompt}",
                    ),
                    {},
                )

        return FakeAgent()

    monkeypatch.setattr("mini_harness.agent.graph.create_agent", fake_create_agent)

    resp = client.post(
        f"/api/assistant/sessions/{workflow.id}/stream",
        json={"message": "这个 workflow 为什么会报错？"},
    )

    assert resp.status_code == 200
    assert "LLM 节点引用了不存在的 missing_1：True" in resp.text
