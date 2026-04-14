from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.nodes.llm_node import PROVIDERS


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
        provider_name = self.config.get("provider", "openai")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)

        provider = PROVIDERS.get(provider_name)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")

        llm = provider().get_chat_model(model=model_name, temperature=temperature, streaming=True)

        tool_names = self.config.get("tools", [])
        tools = [AVAILABLE_TOOLS[t] for t in tool_names if t in AVAILABLE_TOOLS]

        system_prompt = self.config.get("system_prompt", "You are a helpful AI agent.")

        return create_react_agent(llm, tools, prompt=system_prompt)

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        agent = self._build_agent()

        input_messages = [HumanMessage(content=state.get("input", ""))]
        if state.get("context"):
            input_messages.insert(0, SystemMessage(content=f"Context:\n{state['context']}"))

        result = await agent.ainvoke({"messages": input_messages})

        # Extract the last AI message as output
        last_message = result["messages"][-1]
        state["llm_output"] = last_message.content
        state["messages"] = result["messages"]
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.config.get("id", "agent")] = {
            "output": last_message.content,
            "total_messages": len(result["messages"]),
        }

        return state
