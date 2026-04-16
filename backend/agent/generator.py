from sqlalchemy.orm import Session

from backend.agent.capabilities import AgentCapabilities
from backend.agent.llm import AgentLLMClient
from backend.agent.prompts import (
    build_generator_system_prompt,
    build_generator_repair_user_prompt,
    build_generator_user_prompt,
)
from backend.agent.schemas import RecipeIR


class AgentGenerator:
    def __init__(self, db: Session):
        self.db = db
        self.llm = AgentLLMClient(db)

    def generate(
        self,
        *,
        goal: str,
        answered_dims: dict,
        supported_recipes: list[str],
        capabilities: AgentCapabilities,
        heuristic_defaults: dict,
        ) -> RecipeIR:
        return self.llm.structured_invoke(
            schema=RecipeIR,
            system_prompt=build_generator_system_prompt(),
            user_prompt=build_generator_user_prompt(
                goal=goal,
                answered_dims=answered_dims,
                supported_recipes=supported_recipes,
                capabilities_summary={
                    "llm_providers": [
                        {
                            "id": provider.id,
                            "name": provider.name,
                            "default_model": provider.default_model,
                        }
                        for provider in capabilities.llm_providers
                    ],
                    "tts_providers": [
                        {
                            "id": provider.id,
                            "name": provider.name,
                            "voices": provider.voices,
                        }
                        for provider in capabilities.tts_providers
                    ],
                    "knowledge_bases": [
                        {
                            "id": knowledge_base.id,
                            "name": knowledge_base.name,
                        }
                        for knowledge_base in capabilities.knowledge_bases
                    ],
                },
                heuristic_defaults=heuristic_defaults,
            ),
        )

    def repair(
        self,
        *,
        goal: str,
        answered_dims: dict,
        supported_recipes: list[str],
        capabilities: AgentCapabilities,
        heuristic_defaults: dict,
        attempt: int,
        previous_recipe: dict | None,
        errors: list[str],
    ) -> RecipeIR:
        return self.llm.structured_invoke(
            schema=RecipeIR,
            system_prompt=build_generator_system_prompt(),
            user_prompt=build_generator_repair_user_prompt(
                goal=goal,
                answered_dims=answered_dims,
                supported_recipes=supported_recipes,
                capabilities_summary={
                    "llm_providers": [
                        {
                            "id": provider.id,
                            "name": provider.name,
                            "default_model": provider.default_model,
                        }
                        for provider in capabilities.llm_providers
                    ],
                    "tts_providers": [
                        {
                            "id": provider.id,
                            "name": provider.name,
                            "voices": provider.voices,
                        }
                        for provider in capabilities.tts_providers
                    ],
                    "knowledge_bases": [
                        {
                            "id": knowledge_base.id,
                            "name": knowledge_base.name,
                        }
                        for knowledge_base in capabilities.knowledge_bases
                    ],
                },
                heuristic_defaults=heuristic_defaults,
                attempt=attempt,
                previous_recipe=previous_recipe,
                errors=errors,
            ),
        )
