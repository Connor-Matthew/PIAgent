from unittest.mock import patch, MagicMock


def test_create_provider(client):
    resp = client.post("/api/providers", json={
        "type": "openai",
        "name": "Test OpenAI",
        "api_key": "sk-test123456",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "openai"
    assert data["name"] == "Test OpenAI"
    assert data["api_key"] == "sk-***3456"  # masked
    assert "id" in data


def test_list_providers(client):
    client.post("/api/providers", json={"type": "openai", "name": "P1", "api_key": "sk-1"})
    client.post("/api/providers", json={"type": "anthropic", "name": "P2", "api_key": "sk-2"})
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert names == {"P1", "P2"}


def test_get_provider(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P1", "api_key": "sk-secret"})
    pid = create_resp.json()["id"]
    resp = client.get(f"/api/providers/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "P1"
    # masked
    assert data["api_key"].endswith("cret")
    assert "***" in data["api_key"]


def test_update_provider(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P1", "api_key": "sk-old"})
    pid = create_resp.json()["id"]
    resp = client.put(f"/api/providers/{pid}", json={"name": "P1-new", "api_key": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "P1-new"
    # empty api_key should not update
    old_key = client.get(f"/api/providers/{pid}").json()["api_key"]
    assert old_key.endswith("-old")

    resp = client.put(f"/api/providers/{pid}", json={"api_key": "sk-new"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"].endswith("-new")


def test_delete_provider(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P-del", "api_key": "sk-del"})
    pid = create_resp.json()["id"]
    resp = client.delete(f"/api/providers/{pid}")
    assert resp.status_code == 204
    resp = client.get(f"/api/providers/{pid}")
    assert resp.status_code == 404


def test_delete_provider_with_reference_blocked(client):
    provider_resp = client.post("/api/providers", json={"type": "openai", "name": "P-ref", "api_key": "sk-ref"})
    pid = provider_resp.json()["id"]

    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {"provider_id": pid, "model": "gpt-4"}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }
    wf_resp = client.post("/api/workflows", json={"name": "WF", "graph": graph})
    assert wf_resp.status_code == 201

    resp = client.delete(f"/api/providers/{pid}")
    assert resp.status_code == 409
    data = resp.json()
    assert "references" in data["detail"]


def test_test_provider_success(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P-test", "api_key": "sk-test"})
    pid = create_resp.json()["id"]

    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov = MagicMock()
        mock_build.return_value = mock_prov
        resp = client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_prov.test_connection.assert_called_once()


def test_test_provider_auth_failed(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P-test", "api_key": "sk-test"})
    pid = create_resp.json()["id"]

    from backend.providers.base import ProviderAuthError
    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov = MagicMock()
        mock_prov.test_connection.side_effect = ProviderAuthError("bad key")
        mock_build.return_value = mock_prov
        resp = client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 401


def test_get_models_cached(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P-models", "api_key": "sk-test"})
    pid = create_resp.json()["id"]

    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov = MagicMock()
        mock_prov.list_models.return_value = ["gpt-4", "gpt-3.5"]
        mock_build.return_value = mock_prov
        resp = client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == ["gpt-4", "gpt-3.5"]
        assert "cached_at" in data
        mock_prov.list_models.assert_called_once()


def test_get_models_uses_cache(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P-models2", "api_key": "sk-test"})
    pid = create_resp.json()["id"]

    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov = MagicMock()
        mock_prov.list_models.return_value = ["gpt-4"]
        mock_build.return_value = mock_prov
        client.get(f"/api/providers/{pid}/models")

    # second call should use cache without calling list_models again
    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov2 = MagicMock()
        mock_build.return_value = mock_prov2
        resp = client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        assert resp.json()["models"] == ["gpt-4"]
        mock_prov2.list_models.assert_not_called()


def test_get_models_refresh(client):
    create_resp = client.post("/api/providers", json={"type": "openai", "name": "P-models3", "api_key": "sk-test"})
    pid = create_resp.json()["id"]

    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov = MagicMock()
        mock_prov.list_models.return_value = ["gpt-4"]
        mock_build.return_value = mock_prov
        client.get(f"/api/providers/{pid}/models")

    with patch("backend.api.providers.build_provider") as mock_build:
        mock_prov2 = MagicMock()
        mock_prov2.list_models.return_value = ["gpt-4", "gpt-4o"]
        mock_build.return_value = mock_prov2
        resp = client.get(f"/api/providers/{pid}/models?refresh=true")
        assert resp.status_code == 200
        assert resp.json()["models"] == ["gpt-4", "gpt-4o"]
        mock_prov2.list_models.assert_called_once()


def test_list_provider_types(client):
    resp = client.get("/api/providers/types")
    assert resp.status_code == 200
    data = resp.json()
    types = {t["type"] for t in data}
    assert "openai" in types
    assert "openai_compatible" in types
    assert "minimax_tts" in types
    for t in data:
        if t["type"] == "openai_compatible":
            assert t["requires_base_url"] is True
        if t["type"] == "openai":
            assert t["requires_base_url"] is False
            assert t["default_base_url"] is not None
        if t["type"] == "minimax_tts":
            assert t["category"] == "tts"


def test_test_tts_provider_success(client):
    create_resp = client.post("/api/providers", json={
        "type": "minimax_tts",
        "category": "tts",
        "name": "P-tts-test",
        "api_key": "sk-test",
    })
    pid = create_resp.json()["id"]

    with patch("backend.api.providers.build_tts_provider") as mock_build:
        mock_prov = MagicMock()
        mock_build.return_value = mock_prov
        resp = client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_prov.test_connection.assert_called_once()


def test_test_tts_provider_auth_failed(client):
    create_resp = client.post("/api/providers", json={
        "type": "minimax_tts",
        "category": "tts",
        "name": "P-tts-auth",
        "api_key": "sk-test",
    })
    pid = create_resp.json()["id"]

    from backend.providers.base import ProviderAuthError
    with patch("backend.api.providers.build_tts_provider") as mock_build:
        mock_prov = MagicMock()
        mock_prov.test_connection.side_effect = ProviderAuthError("bad key")
        mock_build.return_value = mock_prov
        resp = client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 401


def test_create_tts_provider(client):
    resp = client.post("/api/providers", json={
        "type": "minimax_tts",
        "category": "tts",
        "name": "Test MiniMax",
        "api_key": "sk-test",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "minimax_tts"
    assert data["category"] == "tts"


def test_list_providers_filter_by_category(client):
    client.post("/api/providers", json={"type": "openai", "name": "P1", "api_key": "sk-1"})
    client.post("/api/providers", json={"type": "minimax_tts", "category": "tts", "name": "P2", "api_key": "sk-2"})

    resp = client.get("/api/providers?category=llm")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "P1"

    resp = client.get("/api/providers?category=tts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "P2"


def test_get_models_minimax_tts(client):
    create_resp = client.post("/api/providers", json={
        "type": "minimax_tts",
        "category": "tts",
        "name": "P-minimax",
        "api_key": "sk-test",
    })
    pid = create_resp.json()["id"]

    resp = client.get(f"/api/providers/{pid}/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == ["speech-2.8-hd", "speech-2.5-hd"]
    assert data["selected_models"] == []


def test_get_models_fish_audio_empty(client):
    create_resp = client.post("/api/providers", json={
        "type": "fish_audio",
        "category": "tts",
        "name": "P-fish",
        "api_key": "sk-test",
    })
    pid = create_resp.json()["id"]

    resp = client.get(f"/api/providers/{pid}/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == []
    assert data["selected_models"] == []


def test_create_openai_compatible_without_base_url_returns_400(client):
    resp = client.post("/api/providers", json={
        "type": "openai_compatible",
        "name": "P-compatible",
        "api_key": "sk-test",
    })
    assert resp.status_code == 400
