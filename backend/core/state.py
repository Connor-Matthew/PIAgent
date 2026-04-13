from typing import TypedDict
from langchain_core.messages import BaseMessage


class WorkflowState(TypedDict):
    input: str
    messages: list[BaseMessage]
    context: str
    llm_output: str
    audio_url: str
    node_outputs: dict
