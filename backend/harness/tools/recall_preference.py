from __future__ import annotations

from pydantic import BaseModel, Field

from backend.harness.preferences import PreferenceStore
from backend.harness.tools.base import HarnessContext, Tool


class RecallPreferenceInput(BaseModel):
    key: str | None = Field(
        default=None,
        description="Optional preference key to look up. If omitted, returns all preferences.",
    )


class RecallPreferenceOutput(BaseModel):
    preferences: dict


class RecallPreferenceTool:
    name = "recall_preference"
    description = "Recall user/project preferences stored in the database."
    input_schema = RecallPreferenceInput
    output_schema = RecallPreferenceOutput
    side_effects = False

    async def run(
        self, args: RecallPreferenceInput, ctx: HarnessContext
    ) -> RecallPreferenceOutput:
        db = ctx.db
        if db is None:
            raise RuntimeError("HarnessContext.db is required for recall_preference")

        store = PreferenceStore(db)
        snapshot = store.snapshot()

        if args.key:
            return RecallPreferenceOutput(
                preferences={args.key: snapshot.get(args.key)}
            )
        return RecallPreferenceOutput(preferences=snapshot)
