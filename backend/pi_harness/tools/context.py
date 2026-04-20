from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import StructuredTool

from backend.models.knowledge_base import KnowledgeBase
from backend.models.project_preference import ProjectPreference
from backend.models.provider import Provider
from backend.pi_harness.runtime.skills.loader import load_skills

_SKILLS_PATH = Path(__file__).resolve().parent.parent / "skills"

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
    "agent": {
        "type": "object",
        "properties": {
            "provider_id": {
                "type": "integer",
                "description": "ID of the LLM provider to use.",
            },
            "model": {"type": "string", "default": "gpt-4o"},
            "temperature": {"type": "number", "default": 0.7},
            "system_prompt": {"type": "string"},
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of tools available to the agent node.",
            },
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
    "agent": "Runs a ReAct agent with tool-calling capabilities.",
}


def _get_or_create_preferences(db) -> ProjectPreference:
    row = db.query(ProjectPreference).filter(ProjectPreference.key == "default").first()
    if row is None:
        row = ProjectPreference(key="default")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def build_context_tools(db) -> list[StructuredTool]:
    def list_node_types() -> str:
        nodes = [
            {
                "node_type": node_type,
                "description": _NODE_DESCRIPTIONS.get(node_type, ""),
                "config_schema": _NODE_CONFIG_SCHEMAS.get(node_type, {}),
            }
            for node_type in sorted(_NODE_CONFIG_SCHEMAS.keys())
        ]
        return json.dumps({"nodes": nodes}, ensure_ascii=False)

    def list_skills() -> str:
        skills = load_skills(_SKILLS_PATH)
        payload = [
            {
                "name": skill.name,
                "description": skill.description,
                "location": str(skill.skill_file),
            }
            for skill in skills
        ]
        return json.dumps({"skills": payload}, ensure_ascii=False)

    def list_providers(category: str | None = None) -> str:
        query = db.query(Provider)
        if category:
            query = query.filter(Provider.category == category)
        rows = query.all()
        providers = []
        for row in rows:
            model = ""
            if row.selected_models and isinstance(row.selected_models, list):
                model = row.selected_models[0]
            if not model:
                model = row.type or ""
            providers.append(
                {
                    "id": str(row.id),
                    "name": row.name,
                    "type": row.type or "",
                    "model": model,
                    "enabled": bool(row.enabled),
                }
            )
        return json.dumps({"providers": providers}, ensure_ascii=False)

    def list_knowledge_bases() -> str:
        rows = db.query(KnowledgeBase).all()
        payload = [
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description or "",
                "doc_count": row.doc_count or 0,
            }
            for row in rows
        ]
        return json.dumps({"knowledge_bases": payload}, ensure_ascii=False)

    def recall_preference(key: str | None = None) -> str:
        row = _get_or_create_preferences(db)
        snapshot = {
            "preferred_llm_provider_id": row.preferred_llm_provider_id,
            "preferred_tts_provider_id": row.preferred_tts_provider_id,
            "preferred_tts_voice_id": row.preferred_tts_voice_id,
            "preferred_knowledge_base_id": row.preferred_knowledge_base_id,
            "graph_style": row.graph_style,
        }
        if key:
            snapshot = {key: snapshot.get(key)}
        return json.dumps({"preferences": snapshot}, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            list_node_types,
            name="list_node_types",
            description="List supported workflow node types and their configuration schemas.",
        ),
        StructuredTool.from_function(
            list_skills,
            name="list_skills",
            description="List available pi_harness workflow-building skills.",
        ),
        StructuredTool.from_function(
            list_providers,
            name="list_providers",
            description="List configured providers from the database, optionally filtered by category.",
        ),
        StructuredTool.from_function(
            list_knowledge_bases,
            name="list_knowledge_bases",
            description="List available knowledge bases and their document counts.",
        ),
        StructuredTool.from_function(
            recall_preference,
            name="recall_preference",
            description="Recall stored project preferences.",
        ),
    ]
