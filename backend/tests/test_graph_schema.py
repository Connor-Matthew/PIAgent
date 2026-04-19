from backend.core.graph_schema import (
    dump_graph,
    get_node_branch_id,
    get_node_config,
    get_node_parent_id,
    load_graph,
)


def test_load_graph_preserves_v2_config_and_structure():
    graph = load_graph({
        "version": 2,
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm",
                "parentId": "if_1",
                "branchId": "true",
                "label": "Writer",
                "locked": False,
                "config": {"provider_id": 7, "model": "gpt-4o"},
            }
        ],
        "edges": [],
    })

    node = graph.nodes[0]
    assert get_node_parent_id(node) == "if_1"
    assert get_node_branch_id(node) == "true"
    assert get_node_config(node) == {"provider_id": 7, "model": "gpt-4o"}


def test_load_graph_upgrades_v1_data_to_v2_config():
    graph = load_graph({
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm",
                "position": {"x": 1, "y": 2},
                "data": {
                    "label": "Writer",
                    "nodeType": "llm",
                    "parentId": "if_1",
                    "branchId": "true",
                    "provider_id": 9,
                    "model": "deepseek-chat",
                },
            }
        ],
        "edges": [{"id": "a-b", "source": "a", "target": "b", "sourceHandle": "true"}],
    })

    node = graph.nodes[0]
    assert graph.version == 2
    assert node.parentId == "if_1"
    assert node.branchId == "true"
    assert node.label == "Writer"
    assert node.config == {"provider_id": 9, "model": "deepseek-chat"}
    assert graph.edges[0].sourceHandle == "true"


def test_load_graph_merges_legacy_data_config_object():
    graph = load_graph({
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm",
                "data": {
                    "parentId": "if_1",
                    "provider_id": 1,
                    "config": {"provider_id": 2, "temperature": 0.2},
                },
            }
        ],
        "edges": [],
    })

    assert graph.nodes[0].config == {"provider_id": 2, "temperature": 0.2}


def test_dump_graph_emits_canonical_v2_without_data():
    graph = load_graph({
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
        ],
        "edges": [],
    })

    dumped = dump_graph(graph)

    assert dumped["version"] == 2
    assert dumped["nodes"][0]["config"] == {"inputs": []}
    assert "data" not in dumped["nodes"][0]
