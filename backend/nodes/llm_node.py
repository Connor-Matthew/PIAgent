from langchain_core.messages import HumanMessage, SystemMessage

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.google_provider import GoogleProvider
from backend.providers.deepseek_provider import DeepSeekProvider

PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "deepseek": DeepSeekProvider(),
}

class LLMNode(BaseNode):
    node_type = "llm"

    def _get_chat_model(self):
        provider_name = self.config.get("provider", "openai")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)
        streaming = self.config.get("streaming", True)

        provider = PROVIDERS.get(provider_name)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")

        return provider.get_chat_model(
            model=model_name,
            temperature=temperature,
            streaming=streaming,
        )

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        chat_model = self._get_chat_model()

        messages = []
        system_prompt = self.config.get("system_prompt", "")
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        # Include RAG context if available
        user_content = state["input"]
        if state.get("context"):
            user_content = f"Reference context:\n{state['context']}\n\nUser input:\n{state['input']}"

        messages.append(HumanMessage(content=user_content))

        response = await chat_model.ainvoke(messages)

        state["llm_output"] = response.content
        state["messages"] = messages + [response]
        state["node_outputs"][self.config.get("node_id", "llm")] = {
            "output": response.content,
        }

        return state
