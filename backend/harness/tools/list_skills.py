from __future__ import annotations

from pydantic import BaseModel

from backend.harness.skills.loader import SkillLoader
from backend.harness.tools.base import EmptyToolInput, HarnessContext, Tool


class ListSkillsOutput(BaseModel):
    skills: list[dict]


class ListSkillsTool:
    name = "list_skills"
    description = (
        "List available skill names and short descriptions. "
        "To read the full content of a skill, use the LoadSkill decision."
    )
    input_schema = EmptyToolInput
    output_schema = ListSkillsOutput
    side_effects = False

    async def run(self, args: BaseModel, ctx: HarnessContext) -> ListSkillsOutput:
        loader = SkillLoader()
        return ListSkillsOutput(skills=loader.catalog())
