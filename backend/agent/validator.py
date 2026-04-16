from backend.agent.capabilities import AgentCapabilities
from backend.agent.schemas import RecipeIR


class RecipeValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_recipe_ir(
    recipe_ir: RecipeIR,
    capabilities: AgentCapabilities,
) -> list[str]:
    errors: list[str] = []

    if not capabilities.has_llm_providers:
        errors.append("No enabled LLM provider is available")
        return errors

    recipe_has_rag = "rag" in recipe_ir.recipe
    recipe_has_tts = "tts" in recipe_ir.recipe

    if recipe_ir.llm_provider_id is not None and not capabilities.get_llm_provider(
        recipe_ir.llm_provider_id
    ):
        errors.append(
            f"Unknown llm_provider_id: {recipe_ir.llm_provider_id}"
        )

    if recipe_has_rag:
        if not capabilities.has_knowledge_bases:
            errors.append("Recipe requires a knowledge base, but none are available")
        elif recipe_ir.knowledge_base_id is not None and not capabilities.get_knowledge_base(
            recipe_ir.knowledge_base_id
        ):
            errors.append(
                f"Unknown knowledge_base_id: {recipe_ir.knowledge_base_id}"
            )

    if recipe_has_tts:
        if not capabilities.has_tts_providers:
            errors.append("Recipe requires a TTS provider, but none are available")
        else:
            provider = capabilities.get_tts_provider(
                recipe_ir.tts_provider_id
            ) or capabilities.first_tts_provider()
            if provider is None:
                errors.append("Unable to resolve a TTS provider for the selected recipe")
            elif recipe_ir.tts_voice_id is not None and (
                provider.voices and recipe_ir.tts_voice_id not in provider.voices
            ):
                errors.append(
                    f"voice_id '{recipe_ir.tts_voice_id}' is not supported by provider {provider.id}"
                )

    return errors


def ensure_valid_recipe_ir(
    recipe_ir: RecipeIR,
    capabilities: AgentCapabilities,
) -> None:
    errors = validate_recipe_ir(recipe_ir, capabilities)
    if errors:
        raise RecipeValidationError(errors)
