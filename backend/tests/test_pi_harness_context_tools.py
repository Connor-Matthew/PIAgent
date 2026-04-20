from __future__ import annotations

import json

from backend.models.knowledge_base import KnowledgeBase
from backend.models.project_preference import ProjectPreference
from backend.models.provider import Provider
from backend.pi_harness.tools.context import build_context_tools


def test_context_tools_list_nodes_skills_providers_and_preferences(db):
    db.add(
        Provider(
            type="openai",
            name="Default OpenAI",
            api_key_encrypted="enc",
            enabled=True,
            category="llm",
            selected_models=["gpt-4o-mini"],
        )
    )
    db.add(KnowledgeBase(id="kb-demo", name="Demo KB", description="For tests", doc_count=3))
    db.add(
        ProjectPreference(
            key="default",
            preferred_llm_provider_id=1,
            preferred_tts_voice_id="voice-1",
        )
    )
    db.commit()

    tools = {tool.name: tool for tool in build_context_tools(db)}

    node_types = json.loads(tools["list_node_types"].invoke({}))
    skills = json.loads(tools["list_skills"].invoke({}))
    providers = json.loads(tools["list_providers"].invoke({"category": "llm"}))
    knowledge_bases = json.loads(tools["list_knowledge_bases"].invoke({}))
    preferences = json.loads(tools["recall_preference"].invoke({}))

    node_names = {node["node_type"] for node in node_types["nodes"]}
    skill_names = {skill["name"] for skill in skills["skills"]}

    assert {"start", "llm", "end"} <= node_names
    assert {"llm_basic", "rag_qa", "tts_podcast"} <= skill_names
    assert providers["providers"][0]["name"] == "Default OpenAI"
    assert knowledge_bases["knowledge_bases"][0]["id"] == "kb-demo"
    assert preferences["preferences"]["preferred_tts_voice_id"] == "voice-1"
