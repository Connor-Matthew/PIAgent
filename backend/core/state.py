from typing import TypedDict, NotRequired, Any
from langchain_core.messages import BaseMessage


class WorkflowState(TypedDict):
    input: str
    messages: NotRequired[list[BaseMessage]]
    context: NotRequired[str]
    llm_output: NotRequired[str]
    audio_url: NotRequired[str]
    node_outputs: NotRequired[dict[str, Any]]
