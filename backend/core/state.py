from typing import TypedDict, Any


class WorkflowState(TypedDict, total=False):
    inputs: dict[str, Any]
    node_outputs: dict[str, dict]
    answer: str
    outputs: dict[str, Any]

    # Legacy fields (kept for backward compatibility)
    input: str
    messages: list[Any]
    context: str
    llm_output: str
    audio_url: str
