SAMPLE_GRAPH = {
    "nodes": [
        {"id": "start_1", "type": "start", "data": {}},
        {"id": "end_1", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "start_1", "target": "end_1"},
    ],
}


def test_create_workflow(client):
    resp = client.post("/api/workflows", json={
        "name": "Test Flow",
        "description": "A test",
        "graph": SAMPLE_GRAPH,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Flow"
    assert "id" in data


def test_list_workflows(client):
    client.post("/api/workflows", json={"name": "Flow 1", "graph": SAMPLE_GRAPH})
    client.post("/api/workflows", json={"name": "Flow 2", "graph": SAMPLE_GRAPH})
    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "My Flow", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Flow"


def test_update_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "Old Name", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.put(f"/api/workflows/{wf_id}", json={"name": "New Name", "graph": SAMPLE_GRAPH})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_delete_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "To Delete", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.delete(f"/api/workflows/{wf_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 404


def test_run_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "Run Test", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.post(f"/api/workflows/{wf_id}/run", json={"input": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "run_id" in data


def test_list_runs(client):
    create_resp = client.post("/api/workflows", json={"name": "Run Test", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    run_resp = client.post(f"/api/workflows/{wf_id}/run", json={"input": "hello"})
    assert run_resp.status_code == 200
    resp = client.get(f"/api/workflows/{wf_id}/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_stream_run_events(client):
    create_resp = client.post("/api/workflows", json={"name": "Run Test", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    run_resp = client.post(f"/api/workflows/{wf_id}/run", json={"input": "hello"})
    run_id = run_resp.json()["run_id"]
    resp = client.get(f"/api/workflows/{wf_id}/runs/{run_id}/events")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "text/event-stream; charset=utf-8"
