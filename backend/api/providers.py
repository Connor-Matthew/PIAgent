from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.crypto import encrypt, decrypt, mask_key
from backend.core.graph_schema import get_node_config
from backend.database import get_db
from backend.models.provider import Provider
from backend.models.workflow import Workflow
from backend.providers import PROVIDER_REGISTRY, build_provider
from backend.providers.base import ProviderAuthError, ProviderError
from backend.tts import TTS_PROVIDER_REGISTRY, build_tts_provider

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    type: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=256)
    api_key: str = Field(min_length=1)
    enabled: bool = True
    category: str = "llm"


class ProviderUpdate(BaseModel):
    type: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=256)
    api_key: str | None = None
    enabled: bool | None = None
    selected_models: list[str] | None = None
    category: str | None = None


def _provider_to_dict(provider: Provider, mask: bool = True) -> dict:
    try:
        api_key = decrypt(provider.api_key_encrypted)
    except Exception:
        api_key = "[decrypt_failed]"
    return {
        "id": provider.id,
        "type": provider.type,
        "category": provider.category,
        "name": provider.name,
        "base_url": provider.base_url,
        "api_key": mask_key(api_key) if mask else api_key,
        "enabled": provider.enabled,
        "extra_config": provider.extra_config or {},
        "selected_models": provider.selected_models or [],
        "created_at": provider.created_at.isoformat() if provider.created_at else None,
        "updated_at": provider.updated_at.isoformat() if provider.updated_at else None,
    }


def _find_provider_references(db: Session, provider_id: int) -> list[dict]:
    workflows = db.query(Workflow).all()
    refs = []
    for wf in workflows:
        graph = wf.graph
        for node in graph.get("nodes", []):
            node_config = get_node_config(node)
            if node.get("type") == "llm" and node_config.get("provider_id") == provider_id:
                refs.append({"workflow_id": wf.id, "workflow_name": wf.name, "node_id": node.get("id")})
            if node.get("type") == "tts" and node_config.get("provider_id") == provider_id:
                refs.append({"workflow_id": wf.id, "workflow_name": wf.name, "node_id": node.get("id")})
    return refs





@router.get("/types")
def list_provider_types():
    result = []
    for ptype, cls in PROVIDER_REGISTRY.items():
        result.append({
            "type": ptype,
            "category": "llm",
            "requires_base_url": cls.default_base_url is None,
            "default_base_url": cls.default_base_url,
            "supports_list_models": cls.supports_list_models,
        })
    for ptype, cls in TTS_PROVIDER_REGISTRY.items():
        result.append({
            "type": ptype,
            "category": "tts",
            "requires_base_url": getattr(cls, "default_base_url", None) is None,
            "default_base_url": getattr(cls, "default_base_url", None),
            "supports_list_models": False,
        })
    return result


@router.get("")
def list_providers(category: str | None = Query(None), db: Session = Depends(get_db)):
    query = db.query(Provider)
    if category:
        query = query.filter(Provider.category == category)
    providers = query.all()
    return [_provider_to_dict(p) for p in providers]


@router.post("", status_code=201)
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)):
    if body.category == "llm" and body.type not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown provider type: {body.type}")
    if body.category == "tts" and body.type not in TTS_PROVIDER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown TTS provider type: {body.type}")
    if body.type == "openai_compatible" and not body.base_url:
        raise HTTPException(status_code=400, detail="base_url is required for openai_compatible providers")
    provider = Provider(
        type=body.type,
        category=body.category,
        name=body.name,
        base_url=body.base_url,
        api_key_encrypted=encrypt(body.api_key),
        enabled=body.enabled,
    )
    db.add(provider)
    try:
        db.commit()
        db.refresh(provider)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Provider name already exists: {body.name}")
    except Exception:
        db.rollback()
        raise
    return _provider_to_dict(provider)


@router.get("/{provider_id}")
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _provider_to_dict(provider)


@router.put("/{provider_id}")
def update_provider(provider_id: int, body: ProviderUpdate, db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if body.type is not None:
        category = body.category or provider.category or "llm"
        if category == "llm" and body.type not in PROVIDER_REGISTRY:
            raise HTTPException(status_code=400, detail=f"Unknown provider type: {body.type}")
        if category == "tts" and body.type not in TTS_PROVIDER_REGISTRY:
            raise HTTPException(status_code=400, detail=f"Unknown TTS provider type: {body.type}")
        provider.type = body.type
    if body.category is not None:
        effective_type = body.type or provider.type
        if body.category == "llm" and effective_type not in PROVIDER_REGISTRY:
            raise HTTPException(status_code=400, detail=f"Unknown provider type: {effective_type}")
        if body.category == "tts" and effective_type not in TTS_PROVIDER_REGISTRY:
            raise HTTPException(status_code=400, detail=f"Unknown TTS provider type: {effective_type}")
        provider.category = body.category
    if body.name is not None:
        provider.name = body.name
    if body.base_url is not None:
        provider.base_url = body.base_url
    if body.api_key is not None and body.api_key.strip():
        provider.api_key_encrypted = encrypt(body.api_key)
    if body.enabled is not None:
        provider.enabled = body.enabled
    if body.selected_models is not None:
        provider.selected_models = body.selected_models

    effective_type = body.type or provider.type
    effective_base_url = provider.base_url if body.base_url is None else body.base_url
    if effective_type == "openai_compatible" and not effective_base_url:
        raise HTTPException(status_code=400, detail="base_url cannot be empty for openai_compatible providers")

    try:
        db.commit()
        db.refresh(provider)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Provider name already exists: {body.name or provider.name}")
    except Exception:
        db.rollback()
        raise

    return _provider_to_dict(provider)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        refs = _find_provider_references(db, provider_id)
        if refs:
            raise HTTPException(status_code=409, detail={"message": "Provider is referenced by workflows", "references": refs})

        db.delete(provider)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete provider")
    return None


@router.post("/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        if provider.category == "tts":
            prov = build_tts_provider(provider)
            prov.test_connection()
        else:
            prov = build_provider(provider)
            prov.test_connection()
    except ProviderAuthError as e:
        raise HTTPException(status_code=401, detail={"status": "auth_failed", "error": str(e)})
    except ProviderError as e:
        raise HTTPException(status_code=502, detail={"status": "network_error", "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=502, detail={"status": "network_error", "error": str(e)})

    return {"status": "ok"}


@router.get("/{provider_id}/models")
def get_models(provider_id: int, refresh: bool = Query(False), db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider.category == "tts":
        if provider.type == "minimax_tts":
            models = ["speech-2.8-hd", "speech-2.5-hd"]
            return {"provider_id": provider_id, "models": models, "cached_at": None, "selected_models": provider.selected_models or []}
        return {"provider_id": provider_id, "models": [], "cached_at": None, "selected_models": provider.selected_models or []}

    extra = dict(provider.extra_config or {})
    cached_models = extra.get("cached_models")
    cached_at = extra.get("cached_at")

    if not refresh and cached_models is not None:
        return {"provider_id": provider_id, "models": cached_models, "cached_at": cached_at, "selected_models": provider.selected_models or []}

    try:
        prov = build_provider(provider)
        models = prov.list_models()
    except ProviderAuthError as e:
        raise HTTPException(status_code=401, detail={"status": "auth_failed", "error": str(e)})
    except ProviderError as e:
        raise HTTPException(status_code=502, detail={"status": "network_error", "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=502, detail={"status": "network_error", "error": str(e)})

    now = datetime.now(timezone.utc).isoformat()
    extra["cached_models"] = models
    extra["cached_at"] = now
    provider.extra_config = extra
    try:
        db.commit()
        db.refresh(provider)
    except Exception:
        db.rollback()

    return {"provider_id": provider_id, "models": models, "cached_at": now, "selected_models": provider.selected_models or []}
