import contextlib
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import engine, Base
import backend.models


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
app.include_router(workflows_router)
app.include_router(knowledge_router)
app.include_router(providers_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
