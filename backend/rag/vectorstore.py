from backend.rag.embeddings import get_embedding_model
from backend.config import settings


def get_vectorstore(collection_name: str, embedding_provider: str = "openai"):
    from langchain_chroma import Chroma
    embedding = get_embedding_model(embedding_provider)
    return Chroma(
        collection_name=collection_name,
        embedding_function=embedding,
        persist_directory=settings.chroma_dir,
    )
