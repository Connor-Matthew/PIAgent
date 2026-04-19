from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from backend.harness.llm_client import HarnessLLMClient
from backend.harness.schemas import Decision, Finalize
from backend.models.provider import Provider


def test_structured_invoke_validates_annotated_union_schema(db: Session):
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    structured_model = MagicMock()
    structured_model.invoke.return_value = {
        "kind": "finalize",
        "reason": "workflow is ready",
    }

    chat_model = MagicMock()
    chat_model.with_structured_output.return_value = structured_model

    provider = MagicMock()
    provider.create_chat_model.return_value = chat_model

    with patch("backend.harness.llm_client.build_provider", return_value=provider):
        client = HarnessLLMClient(db)
        result = client.structured_invoke(
            schema=Decision,
            system_prompt="system",
            user_prompt="user",
        )

    assert isinstance(result, Finalize)
    assert result.reason == "workflow is ready"
