from __future__ import annotations

from pydantic import BaseModel, Field

from backend.harness.tools.base import HarnessContext, Tool
from backend.rag.vectorstore import get_vectorstore


class PeekKnowledgeBaseInput(BaseModel):
    id: str = Field(description="Knowledge base ID")
    k: int = Field(default=3, ge=1, le=10, description="Number of sample chunks to return")


class ChunkInfo(BaseModel):
    content: str
    metadata: dict


class PeekKnowledgeBaseOutput(BaseModel):
    knowledge_base_id: str
    chunks: list[ChunkInfo]


class PeekKnowledgeBaseTool:
    name = "peek_knowledge_base"
    description = (
        "Peek into a knowledge base and return a few sample chunks "
        "so the model can see what kind of content it contains."
    )
    input_schema = PeekKnowledgeBaseInput
    output_schema = PeekKnowledgeBaseOutput
    side_effects = False

    async def run(
        self, args: PeekKnowledgeBaseInput, ctx: HarnessContext
    ) -> PeekKnowledgeBaseOutput:
        vectorstore = get_vectorstore(collection_name=args.id)
        retriever = vectorstore.as_retriever(search_kwargs={"k": args.k})

        # Use a generic query to sample documents
        docs = await retriever.ainvoke("sample")

        return PeekKnowledgeBaseOutput(
            knowledge_base_id=args.id,
            chunks=[
                ChunkInfo(
                    content=doc.page_content[:500],
                    metadata=dict(doc.metadata),
                )
                for doc in docs
            ],
        )
