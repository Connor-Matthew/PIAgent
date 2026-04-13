import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import engine, Base

app = FastAPI(title="PIAgent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=settings.audio_dir), name="audio")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/api/health")
def health():
    return {"status": "ok"}
