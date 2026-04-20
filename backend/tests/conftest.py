import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from backend.database import Base, get_db
from backend.main import app
from backend.config import settings
import backend.models

# Set a test secret key for crypto tests
TEST_FERNET_KEY = "FI-QGnkmDa163f8iyECd1p0fKCSIUR8LvZ_rI-ECdng="
settings.secret_key = settings.secret_key.__class__(TEST_FERNET_KEY)

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db():
    # Ensure all database operations (including app lifespan) use in-memory DB
    with patch("backend.main.engine", test_engine), patch("backend.database.engine", test_engine):
        Base.metadata.create_all(bind=test_engine)
        yield
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with patch("backend.main.engine", test_engine), patch("backend.database.engine", test_engine):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
