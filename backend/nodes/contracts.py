"""PIAgent Node Contract — single source of truth for node definitions.

Used by:
- backend runtime (compiler, validator, engine)
- frontend (NodeConfig panel field metadata)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

class ConfigFieldDef(BaseModel):
    """A configuration field set through the workflow editor or API."""

    name: str
    type: Literal["string", "number", "integer", "boolean", "array", "object"]
    description: str
    default: Any = None
    required: bool = False
    enum: list[str] | None = None
    ui_component: str = "text"  # text, textarea, select, slider, number, reference_input
    ui_label: str = ""
    ui_placeholder: str = ""


class InputRefDef(BaseModel):
    """Describes a config field that accepts upstream data via {{nodeId.field}} refs."""

    config_field: str
    description: str
    default_value: str = ""
    supports_template: bool = True


class OutputFieldDef(BaseModel):
    """A field written by the node into state['node_outputs'][node_id]."""

    name: str
    type: Literal["string", "number", "boolean", "array", "object"]
    description: str


# ---------------------------------------------------------------------------
# Node Contract
# ---------------------------------------------------------------------------

class NodeContract(BaseModel):
    """Complete contract for a node type."""

    node_type: str
    description: str
    config_fields: list[ConfigFieldDef]
    input_refs: list[InputRefDef]
    output_fields: list[OutputFieldDef]

    def to_json_schema(self) -> dict[str, Any]:
        """Convert config_fields to a JSON Schema object."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for field in self.config_fields:
            prop: dict[str, Any] = {"type": field.type, "description": field.description}
            if field.default is not None:
                prop["default"] = field.default
            if field.enum is not None:
                prop["enum"] = field.enum
            properties[field.name] = prop
            if field.required:
                required.append(field.name)

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema


# ---------------------------------------------------------------------------
# Contract instances
# ---------------------------------------------------------------------------

_START_CONTRACT = NodeContract(
    node_type="start",
    description="Workflow entry point. Declares input fields and injects them into state.",
    config_fields=[
        ConfigFieldDef(
            name="inputs",
            type="array",
            description="Input fields declared by the start node.",
            default=[],
            ui_component="array",
            ui_label="输入字段",
        ),
    ],
    input_refs=[],
    output_fields=[],  # dynamic: one per declared input field
)

_END_CONTRACT = NodeContract(
    node_type="end",
    description="Workflow exit point. Maps outputs and renders the final answer template.",
    config_fields=[
        ConfigFieldDef(
            name="outputs",
            type="array",
            description="Output mappings. Each item has name, source ('reference'|'static'), value.",
            default=[],
            ui_component="array",
            ui_label="输出变量",
        ),
        ConfigFieldDef(
            name="answer",
            type="string",
            description="Template string for the final answer. Supports {{nodeId.field}} and {{localVar}} refs.",
            default="",
            ui_component="textarea",
            ui_label="回答模板",
            ui_placeholder="例如：{{answer}}",
        ),
    ],
    input_refs=[],
    output_fields=[
        OutputFieldDef(name="outputs", type="object", description="Mapped output variables"),
        OutputFieldDef(name="answer", type="string", description="Rendered final answer"),
    ],
)

_LLM_CONTRACT = NodeContract(
    node_type="llm",
    description="Calls an LLM provider with a configurable model, temperature, and system prompt.",
    config_fields=[
        ConfigFieldDef(
            name="provider_id",
            type="integer",
            description="ID of the LLM provider to use.",
            required=True,
            ui_component="select",
            ui_label="Provider",
        ),
        ConfigFieldDef(
            name="model",
            type="string",
            description="Model name to use.",
            default="gpt-4o",
            ui_component="text",
            ui_label="模型",
        ),
        ConfigFieldDef(
            name="temperature",
            type="number",
            description="Sampling temperature.",
            default=0.7,
            ui_component="slider",
            ui_label="Temperature",
        ),
        ConfigFieldDef(
            name="streaming",
            type="boolean",
            description="Whether to stream tokens.",
            default=True,
            ui_component="select",
            ui_label="流式输出",
        ),
        ConfigFieldDef(
            name="system_prompt",
            type="string",
            description="System prompt sent to the LLM.",
            default="",
            ui_component="textarea",
            ui_label="System Prompt",
        ),
        ConfigFieldDef(
            name="prompt_template",
            type="string",
            description="User message template. Supports {{nodeId.field}} references. If empty, falls back to state['input'].",
            default="",
            ui_component="textarea",
            ui_label="Prompt 模板",
            ui_placeholder="例如：基于以下资料回答：{{rag_1.context}}\n\n问题：{{start_1.question}}",
        ),
    ],
    input_refs=[
        InputRefDef(
            config_field="prompt_template",
            description="Template referencing upstream node outputs to build the user message.",
            default_value="",
            supports_template=True,
        ),
    ],
    output_fields=[
        OutputFieldDef(name="text", type="string", description="Generated text from the LLM"),
    ],
)

_RAG_CONTRACT = NodeContract(
    node_type="rag",
    description="Retrieves relevant documents from a knowledge base using vector search.",
    config_fields=[
        ConfigFieldDef(
            name="knowledge_base_id",
            type="string",
            description="ID of the knowledge base collection.",
            default="default",
            ui_component="text",
            ui_label="知识库 ID",
        ),
        ConfigFieldDef(
            name="top_k",
            type="integer",
            description="Number of top documents to retrieve.",
            default=3,
            ui_component="slider",
            ui_label="Top-K",
        ),
        ConfigFieldDef(
            name="query_ref",
            type="string",
            description="Reference to the query text, e.g. {{start_1.question}}. If empty, falls back to state['input'].",
            default="",
            ui_component="reference_input",
            ui_label="查询引用",
            ui_placeholder="例如：{{start_1.question}}",
        ),
    ],
    input_refs=[
        InputRefDef(
            config_field="query_ref",
            description="Reference to upstream output providing the query string.",
            default_value="",
            supports_template=True,
        ),
    ],
    output_fields=[
        OutputFieldDef(name="context", type="string", description="Concatenated retrieved document texts"),
        OutputFieldDef(name="documents", type="array", description="List of retrieved documents with metadata"),
    ],
)

_TTS_CONTRACT = NodeContract(
    node_type="tts",
    description="Converts text to speech using a TTS provider with voice and emotion settings.",
    config_fields=[
        ConfigFieldDef(
            name="provider_id",
            type="integer",
            description="ID of the TTS provider to use.",
            required=True,
            ui_component="select",
            ui_label="Provider",
        ),
        ConfigFieldDef(
            name="voice_id",
            type="string",
            description="Voice identifier.",
            default="default",
            ui_component="text",
            ui_label="音色 ID",
        ),
        ConfigFieldDef(
            name="emotion",
            type="string",
            description="Emotion style.",
            default="happy",
            enum=["happy", "sad", "angry", "neutral"],
            ui_component="select",
            ui_label="情感",
        ),
        ConfigFieldDef(
            name="speed",
            type="number",
            description="Speech speed multiplier.",
            default=1.0,
            ui_component="slider",
            ui_label="语速",
        ),
        ConfigFieldDef(
            name="max_chars",
            type="integer",
            description="Max characters per synthesis chunk.",
            default=500,
            ui_component="number",
            ui_label="最大分段长度",
        ),
        ConfigFieldDef(
            name="max_concurrency",
            type="integer",
            description="Max parallel synthesis tasks.",
            default=5,
            ui_component="number",
            ui_label="最大并发度",
        ),
        ConfigFieldDef(
            name="text_ref",
            type="string",
            description="Reference to the text to synthesize, e.g. {{llm_1.text}}. If empty, falls back to state['llm_output'] or state['input'].",
            default="",
            ui_component="reference_input",
            ui_label="文本引用",
            ui_placeholder="例如：{{llm_1.text}}",
        ),
    ],
    input_refs=[
        InputRefDef(
            config_field="text_ref",
            description="Reference to upstream output providing the text to synthesize.",
            default_value="",
            supports_template=True,
        ),
    ],
    output_fields=[
        OutputFieldDef(name="audio_url", type="string", description="URL of the generated audio file"),
        OutputFieldDef(name="duration", type="number", description="Estimated audio duration in seconds"),
    ],
)

_IF_ELSE_CONTRACT = NodeContract(
    node_type="if_else",
    description="Conditional branch node. Evaluates conditions and routes to true/false branches.",
    config_fields=[
        ConfigFieldDef(
            name="branches",
            type="array",
            description="Branch definitions. Each has id, condition (left/op/right or null for default), outputField.",
            default=[],
            required=True,
            ui_component="array",
            ui_label="分支配置",
        ),
    ],
    input_refs=[],
    output_fields=[
        OutputFieldDef(name="branchTaken", type="string", description="ID of the branch that was taken"),
        OutputFieldDef(name="result", type="object", description="Result extracted from the branch outputField"),
    ],
)

_ITERATION_CONTRACT = NodeContract(
    node_type="iteration",
    description="Iterates over an array input, executing child nodes for each item.",
    config_fields=[
        ConfigFieldDef(
            name="inputRef",
            type="string",
            description="Reference to the array input, e.g. {{start_1.items}}.",
            default="",
            ui_component="reference_input",
            ui_label="输入引用",
        ),
        ConfigFieldDef(
            name="itemVar",
            type="string",
            description="Variable name for the current item in iteration context.",
            default="item",
            ui_component="text",
            ui_label="项变量名",
        ),
        ConfigFieldDef(
            name="indexVar",
            type="string",
            description="Variable name for the current index in iteration context.",
            default="index",
            ui_component="text",
            ui_label="索引变量名",
        ),
        ConfigFieldDef(
            name="outputField",
            type="string",
            description="Field to extract from each iteration result, e.g. echo_1.text.",
            default="",
            ui_component="text",
            ui_label="输出字段",
        ),
        ConfigFieldDef(
            name="maxConcurrency",
            type="integer",
            description="Maximum number of concurrent iterations.",
            default=5,
            ui_component="slider",
            ui_label="最大并发度",
        ),
        ConfigFieldDef(
            name="errorStrategy",
            type="string",
            description="How to handle errors during iteration.",
            default="fail_fast",
            enum=["fail_fast", "continue", "ignore_error_output"],
            ui_component="select",
            ui_label="错误策略",
        ),
    ],
    input_refs=[
        InputRefDef(
            config_field="inputRef",
            description="Reference to upstream output providing the array to iterate over.",
            default_value="",
            supports_template=True,
        ),
    ],
    output_fields=[
        OutputFieldDef(name="results", type="array", description="Results collected from each iteration"),
        OutputFieldDef(name="errors", type="array", description="Errors encountered during iteration"),
    ],
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

NODE_CONTRACTS: dict[str, NodeContract] = {
    "start": _START_CONTRACT,
    "end": _END_CONTRACT,
    "llm": _LLM_CONTRACT,
    "rag": _RAG_CONTRACT,
    "tts": _TTS_CONTRACT,
    "if_else": _IF_ELSE_CONTRACT,
    "iteration": _ITERATION_CONTRACT,
}


def get_contract(node_type: str) -> NodeContract:
    if node_type not in NODE_CONTRACTS:
        raise KeyError(f"No contract defined for node type: {node_type}")
    return NODE_CONTRACTS[node_type]


def list_contracts() -> list[NodeContract]:
    return list(NODE_CONTRACTS.values())
