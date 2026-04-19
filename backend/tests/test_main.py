import os
import tempfile
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from backend.main import (
    _ensure_agent_session_schema,
    _ensure_secret_key,
    _seed_providers,
)
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


def test_ensure_agent_session_schema_backfills_legacy_sqlite_columns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE agent_sessions (
                        id VARCHAR NOT NULL PRIMARY KEY,
                        user_goal TEXT NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        turns_json TEXT NOT NULL,
                        recipe_json TEXT,
                        graph_json TEXT,
                        rationale_text TEXT,
                        workflow_id VARCHAR,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )

        _ensure_agent_session_schema(engine)

        column_names = {
            column["name"] for column in inspect(engine).get_columns("agent_sessions")
        }
        assert "answered_dims_json" in column_names
        assert "events_json" in column_names
    finally:
        engine.dispose()
        os.unlink(db_path)
