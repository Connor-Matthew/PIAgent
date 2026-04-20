from backend.pi_harness.schemas import Finding
from backend.pi_harness.validators import validate_graph


def test_validate_graph_returns_pi_harness_findings():
    findings = validate_graph({"version": 2, "nodes": [], "edges": []})

    assert findings
    assert all(isinstance(item, Finding) for item in findings)
    assert {item.code for item in findings} >= {"missing_start", "missing_end"}


def test_validate_graph_passes_for_simple_linear_graph():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start", "type": "start", "config": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1}},
            {"id": "end", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"id": "start-llm_1", "source": "start", "target": "llm_1"},
            {"id": "llm_1-end", "source": "llm_1", "target": "end"},
        ],
    }

    findings = validate_graph(graph)
    assert not any(f.severity == "error" for f in findings)
