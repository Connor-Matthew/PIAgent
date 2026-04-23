from backend.models.run_event import WorkflowRunEvent


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "start_1", "type": "start", "data": {}},
        {"id": "end_1", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "start_1", "target": "end_1"},
    ],
}


def test_stream_run_events_persists_event_history(client, db):
    create_resp = client.post(
        "/api/workflows",
        json={"name": "Run History Test", "graph": SAMPLE_GRAPH},
    )
    workflow_id = create_resp.json()["id"]
    run_resp = client.post(f"/api/workflows/{workflow_id}/run", json={"input": "hello"})
    run_id = run_resp.json()["run_id"]

    stream_resp = client.get(f"/api/workflows/{workflow_id}/runs/{run_id}/events")

    assert stream_resp.status_code == 200
    rows = (
        db.query(WorkflowRunEvent)
        .filter(WorkflowRunEvent.workflow_id == workflow_id)
        .filter(WorkflowRunEvent.run_id == run_id)
        .order_by(WorkflowRunEvent.seq)
        .all()
    )
    assert [row.seq for row in rows] == list(range(1, len(rows) + 1))
    assert rows
    assert rows[-1].event["type"] == "workflow_end"
