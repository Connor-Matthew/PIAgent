import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import update
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.models.knowledge_base import KnowledgeBase
from backend.rag.loader import load_and_split
from backend.rag.vectorstore import get_vectorstore
from backend.config import settings

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])


class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""


class KBQuery(BaseModel):
    query: str
    top_k: int = Field(3, ge=1, le=50)


@router.get("")
def list_kbs(db: Session = Depends(get_db)):
    kbs = db.query(KnowledgeBase).all()
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "doc_count": kb.doc_count,
            "created_at": kb.created_at,
        }
        for kb in kbs
    ]


@router.post("", status_code=201)
def create_kb(body: KBCreate, db: Session = Depends(get_db)):
    kb = KnowledgeBase(name=body.name, description=body.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "doc_count": kb.doc_count,
        "created_at": kb.created_at,
    }


@router.get("/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "doc_count": kb.doc_count,
        "created_at": kb.created_at,
    }


@router.post("/{kb_id}/upload")
def upload_doc(kb_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1]
    allowed_exts = {".txt", ".pdf", ".md"}
    if ext.lower() not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    MAX_SIZE = 10 * 1024 * 1024
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    safe_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(settings.upload_dir, safe_filename)

    docs = []
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        docs = load_and_split(file_path)
        vectorstore = get_vectorstore(collection_name=kb_id)
        vectorstore.add_documents(docs)

        db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(doc_count=KnowledgeBase.doc_count + len(docs))
        )
        db.commit()
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    return {"chunks": len(docs), "doc_count": kb.doc_count + len(docs)}


@router.post("/{kb_id}/query")
def query_kb(kb_id: str, body: KBQuery, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    vectorstore = get_vectorstore(collection_name=kb_id)
    retriever = vectorstore.as_retriever(search_kwargs={"k": body.top_k})
    docs = retriever.invoke(body.query)

    return {"results": [{"content": d.page_content, "metadata": d.metadata} for d in docs]}
