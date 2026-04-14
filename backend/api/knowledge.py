import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models.knowledge_base import KnowledgeBase
from backend.rag.loader import load_and_split
from backend.rag.vectorstore import get_vectorstore

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])

UPLOAD_DIR = "./uploads"

class KBCreate(BaseModel):
    name: str
    description: str = ""

class KBQuery(BaseModel):
    query: str
    top_k: int = 3

@router.post("", status_code=201)
def create_kb(body: KBCreate, db: Session = Depends(get_db)):
    kb = KnowledgeBase(name=body.name, description=body.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {"id": kb.id, "name": kb.name, "description": kb.description, "doc_count": kb.doc_count}

@router.get("/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "description": kb.description, "doc_count": kb.doc_count}

@router.post("/{kb_id}/upload")
async def upload_doc(kb_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    docs = load_and_split(file_path)
    vectorstore = get_vectorstore(collection_name=kb_id)
    vectorstore.add_documents(docs)

    kb.doc_count += len(docs)
    db.commit()

    return {"chunks": len(docs), "doc_count": kb.doc_count}

@router.post("/{kb_id}/query")
async def query_kb(kb_id: str, body: KBQuery, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    vectorstore = get_vectorstore(collection_name=kb_id)
    retriever = vectorstore.as_retriever(search_kwargs={"k": body.top_k})
    docs = await retriever.ainvoke(body.query)

    return {"results": [{"content": d.page_content, "metadata": d.metadata} for d in docs]}
