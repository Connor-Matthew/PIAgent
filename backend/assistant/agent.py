from pathlib import Path

from sqlalchemy.orm import Session

from backend.assistant.prompt import build_system_prompt
from backend.assistant.tools import build_readonly_tools
from backend.core.crypto import decrypt
from backend.models.provider import Provider


def _resolve_model_name(provider: Provider) -> str:
    if provider.selected_models:
        return provider.selected_models[0]
    defaults = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
        "deepseek": "deepseek-chat",
        "google": "gemini-1.5-flash",
        "openai_compatible": "gpt-4o-mini",
    }
    return defaults.get(provider.type, "gpt-4o-mini")


def build_assistant_agent(db: Session, workflow_id: str):
    from mini_harness.config import load_config, set_app_config
    from mini_harness.config.models import ModelConfig

    cfg_path = Path(__file__).parent / "mini_harness.yaml"
    config = load_config(cfg_path)

    provider = (
        db.query(Provider)
        .filter(Provider.category == "llm", Provider.enabled.is_(True))
        .first()
    )

    if provider:
        api_key = decrypt(provider.api_key_encrypted)
        config.models = [
            ModelConfig(
                name="default",
                display_name="Workflow Assistant",
                model=_resolve_model_name(provider),
                api_key=api_key,
                base_url=provider.base_url or None,
                temperature=0.2,
                timeout=120.0,
            )
        ]
        set_app_config(config)

    from mini_harness.agent.graph import create_agent

    return create_agent(
        system_prompt=build_system_prompt(),
        tool_instances=build_readonly_tools(db, workflow_id),
    )
