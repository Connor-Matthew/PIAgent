from __future__ import annotations

from pydantic import BaseModel, Field

from backend.harness.tools.base import EmptyToolInput, HarnessContext, Tool
from backend.nodes.registry import node_registry


class NodeTypeInfo(BaseModel):
    node_type: str
    description: str
    config_schema: dict = Field(default_factory=dict)


class ListNodeTypesOutput(BaseModel):
    nodes: list[NodeTypeInfo]


# Config schemas manually derived from each node's self.config usage.
_NODE_CONFIG_SCHEMAS: dict[str, dict] = {
    "start": {
        "type": "object",
        "properties": {
            "inputs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "default": "string"},
                        "required": {"type": "boolean", "default": False},
                        "description": {"type": "string"},
                    },
                },
                "description": "Input fields declared by the start node.",
            },
        },
    },
    "end": {
        "type": "object",
        "properties": {
            "outputs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "source": {"type": "string", "enum": ["reference", "static"]},
                        "value": {"type": "string"},
                    },
                },
                "description": "Output mappings.",
            },
            "answer": {
                "type": "string",
                "description": "Template string for the final answer.",
            },
        },
    },
    "llm": {
        "type": "object",
        "properties": {
            "provider_id": {
                "type": "integer",
                "description": "ID of the LLM provider to use.",
            },
            "model": {"type": "string", "default": "gpt-4o"},
            "temperature": {"type": "number", "default": 0.7},
            "streaming": {"type": "boolean", "default": True},
            "system_prompt": {"type": "string"},
        },
        "required": ["provider_id"],
    },
    "rag": {
        "type": "object",
        "properties": {
            "knowledge_base_id": {"type": "string", "default": "default"},
            "top_k": {"type": "integer", "default": 3},
        },
    },
    "tts": {
        "type": "object",
        "properties": {
            "provider_id": {
                "type": "integer",
                "description": "ID of the TTS provider to use.",
            },
            "voice_id": {"type": "string", "default": "default"},
            "emotion": {"type": "string", "default": "happy"},
            "speed": {"type": "number", "default": 1.0},
            "max_chars": {"type": "integer", "default": 500},
            "max_concurrency": {"type": "integer", "default": 5},
        },
        "required": ["provider_id"],
    },
}

_NODE_DESCRIPTIONS: dict[str, str] = {
    "start": "Workflow entry point. Declares input fields and injects them into state.",
    "end": "Workflow exit point. Maps outputs and renders the final answer template.",
    "llm": "Calls an LLM provider with a configurable model, temperature, and system prompt.",
    "rag": "Retrieves relevant documents from a knowledge base using vector search.",
    "tts": "Converts text to speech using a TTS provider with voice and emotion settings.",
}

_AUTHORING_EXCLUDED_NODE_TYPES = {"agent"}


class ListNodeTypesTool:
    name = "list_node_types"
    description = (
        "List all available workflow node types, their descriptions, "
        "and the JSON schema of their configuration fields."
    )
    input_schema = EmptyToolInput
    output_schema = ListNodeTypesOutput
    side_effects = False

    async def run(self, args: BaseModel, ctx: HarnessContext) -> ListNodeTypesOutput:
        nodes: list[NodeTypeInfo] = []
        for node_type in node_registry.list_types():
            if node_type in _AUTHORING_EXCLUDED_NODE_TYPES:
                continue
            nodes.append(
                NodeTypeInfo(
                    node_type=node_type,
                    description=_NODE_DESCRIPTIONS.get(node_type, ""),
                    config_schema=_NODE_CONFIG_SCHEMAS.get(node_type, {}),
                )
            )
        return ListNodeTypesOutput(nodes=nodes)
