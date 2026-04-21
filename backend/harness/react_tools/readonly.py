"""Read-only authoring tools for the ReAct builder agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from backend.harness.react_tools.base import ToolContext, _json_compact
from backend.harness.tools.list_knowledge_bases import ListKnowledgeBasesTool
from backend.harness.tools.list_node_types import ListNodeTypesTool
from backend.harness.tools.list_providers import ListProvidersTool
from backend.harness.tools.peek_knowledge_base import PeekKnowledgeBaseTool
from backend.harness.tools.recall_preference import RecallPreferenceTool


# ── config schemas for node types (reused from harness v2) ──

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

_AUTHORING_EXCLUDED = {"agent"}


def _node_types_json() -> list[dict]:
    from backend.nodes.registry import node_registry
    nodes = []
    for nt in node_registry.list_types():
        if nt in _AUTHORING_EXCLUDED:
            continue
        nodes.append({
            "node_type": nt,
            "description": _NODE_DESCRIPTIONS.get(nt, ""),
            "config_schema": _NODE_CONFIG_SCHEMAS.get(nt, {}),
        })
    return nodes


def make_readonly_tools(ctx: ToolContext) -> list[Any]:
    """Build read-only LangChain tools bound to a ToolContext."""

    @tool
    def inspect_canvas() -> str:
        """Inspect the current workflow graph draft, validation findings, and open questions.

        Returns a JSON summary of:
        - current nodes and edges
        - last validation findings
        - any open question awaiting user input
        - step budget remaining
        """
        snapshot = ctx.builder.snapshot()
        findings = ctx.workspace.facts.to_dict().get("validation_findings", [])
        open_q = ctx.workspace.open_question
        budget = ctx.workspace.budget.to_dict()
        return _json_compact({
            "graph": snapshot,
            "validation_findings": findings,
            "open_question": open_q,
            "budget": budget,
        })

    @tool
    def list_node_types() -> str:
        """List all available workflow node types (excluding runtime-only agent).

        Returns node types with descriptions and config schemas.
        """
        return _json_compact({"node_types": _node_types_json()})

    @tool
    def list_providers(provider_type: str | None = None) -> str:
        """List available LLM or TTS providers.

        Args:
            provider_type: Filter by "llm" or "tts". Omit to list all.
        """
        from backend.harness.tools.base import EmptyToolInput, HarnessContext
        t = ListProvidersTool()
        result = t.run(EmptyToolInput(), ctx=HarnessContext(db=ctx.db))
        rows = json.loads(result.model_dump_json())
        if provider_type:
            rows["providers"] = [p for p in rows.get("providers", []) if p.get("type") == provider_type]
        return _json_compact(rows)

    @tool
    def list_knowledge_bases() -> str:
        """List available knowledge bases."""
        from backend.harness.tools.base import EmptyToolInput, HarnessContext
        t = ListKnowledgeBasesTool()
        result = t.run(EmptyToolInput(), ctx=HarnessContext(db=ctx.db))
        return result.model_dump_json()

    @tool
    def peek_knowledge_base(knowledge_base_id: str) -> str:
        """Peek at a knowledge base to see its summary or sample documents.

        Args:
            knowledge_base_id: The ID of the knowledge base to inspect.
        """
        from backend.harness.tools.base import HarnessContext
        from backend.harness.tools.peek_knowledge_base import PeekKnowledgeBaseInput
        t = PeekKnowledgeBaseTool()
        inp = PeekKnowledgeBaseInput(knowledge_base_id=knowledge_base_id)
        result = t.run(inp, ctx=HarnessContext(db=ctx.db))
        return result.model_dump_json()

    @tool
    def recall_preference() -> str:
        """Recall user preferences recorded for this project."""
        from backend.harness.tools.base import EmptyToolInput, HarnessContext
        t = RecallPreferenceTool()
        result = t.run(EmptyToolInput(), ctx=HarnessContext(db=ctx.db))
        return result.model_dump_json()

    @tool
    def load_skill(skill_name: str) -> str:
        """Load a skill markdown file into context.

        Args:
            skill_name: Name of the skill file (without .md extension).
        """
        try:
            content = ctx.skills.load(skill_name)
            ctx.workspace.record_skill(skill_name, content)
            return json.dumps({
                "skill": skill_name,
                "loaded": True,
                "length": len(content),
                "snippet": content[:500],
            }, ensure_ascii=False)
        except FileNotFoundError as exc:
            return json.dumps({"skill": skill_name, "loaded": False, "error": str(exc)}, ensure_ascii=False)

    return [
        inspect_canvas,
        list_node_types,
        list_providers,
        list_knowledge_bases,
        peek_knowledge_base,
        recall_preference,
        load_skill,
    ]
