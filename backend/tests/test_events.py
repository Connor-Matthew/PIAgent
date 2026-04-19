from backend.core import events


def test_node_start_event_has_stable_shape():
    event = events.node_start(
        node_id="llm_1",
        node_type="llm",
        scope_id="iter_1",
        iteration_index=2,
    )

    assert event == {
        "type": "node_start",
        "node_id": "llm_1",
        "node_type": "llm",
        "status": "running",
        "scope_id": "iter_1",
        "iteration_index": 2,
    }


def test_workflow_end_completed_event_has_outputs():
    event = events.workflow_end(
        status="completed",
        duration=1.2,
        answer="done",
        outputs={"answer": "done"},
    )

    assert event["type"] == "workflow_end"
    assert event["status"] == "completed"
    assert event["outputs"] == {"answer": "done"}
