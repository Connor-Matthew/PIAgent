import os
import tempfile
from unittest.mock import patch

from sqlalchemy.orm import Session

from backend.main import (
    _ensure_secret_key,
    _seed_providers,
)
from backend.database import Base
from backend.models.provider import Provider


def test_ensure_secret_key_generates_in_dev():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        env_path = f.name

    try:
        with patch("backend.main.settings") as mock_settings:
            mock_settings.secret_key.get_secret_value.return_value = ""
            mock_settings.env = "development"
            with patch("backend.main.os.path.join", return_value=env_path):
                _ensure_secret_key()

            assert mock_settings.secret_key != ""
            with open(env_path) as f:
                content = f.read()
            assert "SECRET_KEY=" in content
    finally:
        os.unlink(env_path)


def test_ensure_secret_key_raises_in_production():
    with patch("backend.main.settings") as mock_settings:
        mock_settings.secret_key.get_secret_value.return_value = ""
        mock_settings.env = "production"
        try:
            _ensure_secret_key()
            assert False, "Expected RuntimeError"
        except RuntimeError as e:
            assert "SECRET_KEY is required" in str(e)


def test_seed_providers_creates_from_env(db: Session):
    with patch("backend.main.settings") as mock_settings:
        mock_settings.openai_api_key.get_secret_value.return_value = "sk-openai"
        mock_settings.anthropic_api_key.get_secret_value.return_value = ""
        mock_settings.google_api_key.get_secret_value.return_value = "sk-google"
        mock_settings.deepseek_api_key.get_secret_value.return_value = ""

        _seed_providers(db)

    providers = db.query(Provider).all()
    assert len(providers) == 2
    types = {p.type for p in providers}
    assert types == {"openai", "google"}


def test_seed_providers_skips_when_existing(db: Session):
    # Pre-seed one provider
    from backend.core.crypto import encrypt
    db.add(Provider(type="openai", name="Existing", api_key_encrypted=encrypt("sk")))
    db.commit()

    with patch("backend.main.settings") as mock_settings:
        mock_settings.openai_api_key.get_secret_value.return_value = "sk-openai"
        _seed_providers(db)

    providers = db.query(Provider).all()
    assert len(providers) == 1


def test_harness_api_is_removed(client):
    resp = client.post("/api/harness/sessions", json={"goal": "Build a workflow"})
    assert resp.status_code == 404


def test_agent_session_model_is_removed_from_metadata():
    assert "agent_sessions" not in Base.metadata.tables
    assert "project_preferences" not in Base.metadata.tables
