import contextlib
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import engine, Base
import backend.models

logger = logging.getLogger(__name__)


def _ensure_secret_key():
    if settings.secret_key.get_secret_value():
        return
    if settings.env == "production":
        raise RuntimeError("SECRET_KEY is required in production environment")
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    env_path = os.path.join(os.getcwd(), ".env")
    existing = ""
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            existing = f.read()
    if "SECRET_KEY=" not in existing:
        with open(env_path, "a") as f:
            f.write(f"\nSECRET_KEY={key}\n")
    else:
        # If SECRET_KEY already exists in .env but wasn't loaded, don't overwrite
        pass
    settings.secret_key = settings.secret_key.__class__(key)
    logger.warning("Auto-generated SECRET_KEY and wrote to .env")


def _seed_providers(db: Session):
    from backend.models.provider import Provider
    from backend.core.crypto import encrypt

    count = db.query(Provider).count()
    if count > 0:
        return

    seeds = []
    if settings.openai_api_key.get_secret_value():
        seeds.append(("openai", "Default OpenAI", settings.openai_api_key.get_secret_value()))
    if settings.anthropic_api_key.get_secret_value():
        seeds.append(("anthropic", "Default Anthropic", settings.anthropic_api_key.get_secret_value()))
    if settings.google_api_key.get_secret_value():
        seeds.append(("google", "Default Google", settings.google_api_key.get_secret_value()))
    if settings.deepseek_api_key.get_secret_value():
        seeds.append(("deepseek", "Default DeepSeek", settings.deepseek_api_key.get_secret_value()))

    for ptype, name, key in seeds:
        provider = Provider(
            type=ptype,
            name=name,
            api_key_encrypted=encrypt(key),
            enabled=True,
        )
        db.add(provider)
    if seeds:
        db.commit()
        logger.info("Seeded %d default providers from environment variables", len(seeds))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_secret_key()
    from pathlib import Path
    from mini_harness.config import load_config, set_app_config

    assistant_config_path = Path(__file__).resolve().parent / "assistant" / "mini_harness.yaml"
    set_app_config(load_config(assistant_config_path))
    db = Session(bind=engine)
    try:
        _seed_providers(db)
    finally:
        db.close()
    yield


app = FastAPI(title="PIAgent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=settings.audio_dir), name="audio")

from backend.api.workflows import router as workflows_router
from backend.api.knowledge import router as knowledge_router
from backend.api.providers import router as providers_router
from backend.assistant.routes import router as assistant_router
app.include_router(workflows_router)
app.include_router(knowledge_router)
app.include_router(providers_router)
app.include_router(assistant_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
