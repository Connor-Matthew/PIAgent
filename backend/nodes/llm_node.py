import inspect

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.core.template import render_template
from backend.providers import build_provider
from backend.database import SessionLocal
from backend.models.provider import Provider


class LLMNode(BaseNode):
    node_type = "llm"

    def _get_provider_legacy(self, provider_id):
        db = SessionLocal()
        try:
            row = db.query(Provider).filter(Provider.id == provider_id).first()
            if not row:
                raise ValueError(f"Provider not found: {provider_id}")
            if not row.enabled:
                raise ValueError(f"Provider is disabled: {provider_id}")
            return build_provider(row)
        finally:
            db.close()

    def _get_chat_model(self, run_context=None):
        provider_id = self.config.get("provider_id")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)
        streaming = self.config.get("streaming", True)

        if not provider_id:
            raise ValueError("provider_id is required for LLM node")

        if run_context is not None:
            provider = run_context.get_llm_provider(int(provider_id))
        else:
            provider = self._get_provider_legacy(provider_id)

        return provider.create_chat_model(
            model=model_name,
            temperature=temperature,
            streaming=streaming,
        )

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        chat_model = self._get_chat_model(kwargs.get("run_context"))
        on_event = kwargs.get("on_event")

        messages = []
        system_prompt = self.config.get("system_prompt", "")
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        # Build user content: prefer prompt_template, fallback to legacy behavior
        prompt_template = self.config.get("prompt_template", "")
        if prompt_template:
            user_content = render_template(prompt_template, state)
        else:
            # Legacy fallback
            user_content = state.get("input", "")
            if state.get("context"):
                user_content = f"Reference context:\n{state['context']}\n\nUser input:\n{user_content}"

        messages.append(HumanMessage(content=user_content))

        streaming = bool(self.config.get("streaming", True))
        response: AIMessage

        if streaming and on_event is not None:
            full_text = ""
            seq = 0
            stream = chat_model.astream(messages)
            if inspect.isawaitable(stream):
                stream = await stream
            if hasattr(stream, "__aiter__"):
                async for chunk in stream:
                    delta = self._content_to_text(getattr(chunk, "content", ""))
                    if not delta:
                        continue
                    full_text += delta
                    seq += 1
                    await self._emit(on_event, {
                        "type": "node_stream",
                        "node_id": self.node_id,
                        "node_type": self.node_type,
                        "delta": delta,
                        "seq": seq,
                    })

            if full_text:
                response = AIMessage(content=full_text)
            else:
                response = await chat_model.ainvoke(messages)
        else:
            response = await chat_model.ainvoke(messages)

        state.setdefault("node_outputs", {})
        state["llm_output"] = response.content
        state["messages"] = state.get("messages", []) + messages + [response]
        state["node_outputs"][self.node_id] = {
            "text": response.content,
        }

        return state
