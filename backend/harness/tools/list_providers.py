from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from backend.harness.tools.base import HarnessContext, Tool
from backend.models.provider import Provider


class ListProvidersInput(BaseModel):
    type: str | None = Field(
        default=None,
        description="Optional filter by provider category (llm, tts, embedding).",
    )


class ProviderInfo(BaseModel):
    id: str
    name: str
    type: str
    model: str
    enabled: bool


class ListProvidersOutput(BaseModel):
    providers: list[ProviderInfo]


class ListProvidersTool:
    name = "list_providers"
    description = (
        "List configured providers from the database. "
        "Optionally filter by category type."
    )
    input_schema = ListProvidersInput
    output_schema = ListProvidersOutput
    side_effects = False

    async def run(
        self, args: ListProvidersInput, ctx: HarnessContext
    ) -> ListProvidersOutput:
        db = ctx.db
        if db is None:
            raise RuntimeError("HarnessContext.db is required for list_providers")

        def _query() -> list[Provider]:
            q = db.query(Provider)
            if args.type:
                q = q.filter(Provider.category == args.type)
            return q.all()

        rows: list[Provider] = await asyncio.to_thread(_query)

        providers: list[ProviderInfo] = []
        for row in rows:
            # Derive a representative model name from selected_models or type
            model = ""
            if row.selected_models and isinstance(row.selected_models, list):
                model = row.selected_models[0]
            if not model:
                model = row.type or ""

            providers.append(
                ProviderInfo(
                    id=str(row.id),
                    name=row.name,
                    type=row.type or "",
                    model=model,
                    enabled=bool(row.enabled),
                )
            )

        return ListProvidersOutput(providers=providers)
