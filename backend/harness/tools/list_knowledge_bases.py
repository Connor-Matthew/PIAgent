from __future__ import annotations

import asyncio

from pydantic import BaseModel

from backend.harness.tools.base import EmptyToolInput, HarnessContext, Tool
from backend.models.knowledge_base import KnowledgeBase


class KnowledgeBaseInfo(BaseModel):
    id: str
    name: str
    description: str
    doc_count: int


class ListKnowledgeBasesOutput(BaseModel):
    knowledge_bases: list[KnowledgeBaseInfo]


class ListKnowledgeBasesTool:
    name = "list_knowledge_bases"
    description = "List all knowledge bases with their names and document counts."
    input_schema = EmptyToolInput
    output_schema = ListKnowledgeBasesOutput
    side_effects = False

    async def run(self, args: BaseModel, ctx: HarnessContext) -> ListKnowledgeBasesOutput:
        db = ctx.db
        if db is None:
            raise RuntimeError("HarnessContext.db is required for list_knowledge_bases")

        def _query() -> list[KnowledgeBase]:
            return db.query(KnowledgeBase).all()

        rows: list[KnowledgeBase] = await asyncio.to_thread(_query)

        return ListKnowledgeBasesOutput(
            knowledge_bases=[
                KnowledgeBaseInfo(
                    id=str(row.id),
                    name=row.name,
                    description=row.description or "",
                    doc_count=row.doc_count or 0,
                )
                for row in rows
            ]
        )
