import inspect

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.providers import build_provider
from backend.database import SessionLocal
from backend.models.provider import Provider


@tool
def search_knowledge(query: str) -> str:
    """Search the knowledge base for relevant information."""
    # In real usage, this would call the RAG vectorstore
    # Placeholder for tool definition — actual retrieval injected at runtime
    return f"Knowledge base results for: {query}"


@tool
def synthesize_audio(text: str) -> str:
    """Convert text to audio using TTS service."""
    # Placeholder — actual TTS call injected at runtime
    return f"Audio synthesized for text of length {len(text)}"


AVAILABLE_TOOLS = {
    "rag": search_knowledge,
    "tts": synthesize_audio,
}


class AgentNode(BaseNode):
    node_type = "agent"

    def _build_agent(self):
        provider_id = self.config.get("provider_id")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)

        if not provider_id:
            raise ValueError("provider_id is required for Agent node")

        db = SessionLocal()
        try:
            row = db.query(Provider).filter(Provider.id == provider_id).first()
            if not row:
                raise ValueError(f"Provider not found: {provider_id}")
            if not row.enabled:
                raise ValueError(f"Provider is disabled: {provider_id}")
            provider = build_provider(row)
        finally:
            db.close()

        llm = provider.create_chat_model(model=model_name, temperature=temperature, streaming=True)

        tool_names = self.config.get("tools", [])
        tools = []
        for t in tool_names:
            if t not in AVAILABLE_TOOLS:
                raise ValueError(f"Unknown tool: {t}")
            tools.append(AVAILABLE_TOOLS[t])

        system_prompt = self.config.get("system_prompt", "You are a helpful AI agent.")

        return create_react_agent(llm, tools, prompt=system_prompt)

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        agent = self._build_agent()
        on_event = kwargs.get("on_event")

        messages = state.get("messages", [])
        input_messages = list(messages)
        input_messages.append(HumanMessage(content=state.get("input", "")))
        if state.get("context"):
            input_messages.insert(0, SystemMessage(content=f"Context:\n{state['context']}"))

        result = None
        if on_event is not None:
            seq = 0
            event_stream = agent.astream_events({"messages": input_messages}, version="v1")
            if inspect.isawaitable(event_stream):
                event_stream = await event_stream
            if hasattr(event_stream, "__aiter__"):
                async for event in event_stream:
                    event_name = event.get("event")
                    data = event.get("data") or {}
                    if event_name == "on_chat_model_stream":
                        delta = self._content_to_text(getattr(data.get("chunk"), "content", ""))
                        if not delta:
                            continue
                        seq += 1
                        await self._emit(on_event, {
                            "type": "node_stream",
                            "node_id": self.node_id,
                            "node_type": self.node_type,
                            "delta": delta,
                            "seq": seq,
                        })
                    elif event_name == "on_chain_end":
                        output = data.get("output")
                        if isinstance(output, dict) and "messages" in output:
                            result = output

        if result is None:
            result = await agent.ainvoke({"messages": input_messages})

        # Extract the last AI message as output
        result_messages = result.get("messages", [])
        last_ai_message = None
        for msg in reversed(result_messages):
            if isinstance(msg, AIMessage):
                last_ai_message = msg
                break
        if last_ai_message is None:
            last_ai_message = result_messages[-1] if result_messages else None
        state["llm_output"] = last_ai_message.content if last_ai_message else ""
        state["messages"] = result_messages

        # Build steps from message history
        steps = []
        for msg in result_messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                steps.append({
                    "type": "action",
                    "tool_calls": [
                        {"name": tc.get("name"), "args": tc.get("args")}
                        for tc in msg.tool_calls
                    ],
                })
            elif isinstance(msg, ToolMessage):
                steps.append({
                    "type": "observation",
                    "tool_name": msg.name,
                    "content": msg.content,
                })
            elif isinstance(msg, AIMessage) and msg.content:
                steps.append({
                    "type": "thought",
                    "content": msg.content,
                })

        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {
            "text": last_ai_message.content if last_ai_message else "",
            "steps": steps,
        }

        return state
