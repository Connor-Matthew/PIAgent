from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
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
        tools = []
        for t in tool_names:
            if t not in AVAILABLE_TOOLS:
                raise ValueError(f"Unknown tool: {t}")
            tools.append(AVAILABLE_TOOLS[t])

        system_prompt = self.config.get("system_prompt", "You are a helpful AI agent.")

        return create_react_agent(llm, tools, prompt=system_prompt)

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        agent = self._build_agent()

        messages = state.get("messages", [])
        input_messages = list(messages)
        input_messages.append(HumanMessage(content=state.get("input", "")))
        if state.get("context"):
            input_messages.insert(0, SystemMessage(content=f"Context:\n{state['context']}"))

        result = await agent.ainvoke({"messages": input_messages})

        # Extract the last AI message as output
        result_messages = result.get("messages", [])
        last_message = result_messages[-1]
        state["llm_output"] = last_message.content
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
            "text": last_message.content,
            "steps": steps,
        }

        return state
