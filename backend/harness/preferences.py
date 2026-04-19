"""PIAgent Harness v2 — PreferenceStore: read/write project_preferences."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.project_preference import ProjectPreference


def _get_or_create(db: Session, key: str = "default") -> ProjectPreference:
    row = db.query(ProjectPreference).filter(ProjectPreference.key == key).first()
    if row is None:
        row = ProjectPreference(key=key)
        db.add(row)
        db.commit()
    return row


class PreferenceStore:
    """Conservative preference learning: only update when user explicitly modifies."""

    def __init__(self, db: Session, key: str = "default"):
        self.db = db
        self.key = key

    def snapshot(self) -> dict:
        """Return current preferences as a plain dict."""
        row = _get_or_create(self.db, self.key)
        return {
            "preferred_llm_provider_id": row.preferred_llm_provider_id,
            "preferred_tts_provider_id": row.preferred_tts_provider_id,
            "preferred_tts_voice_id": row.preferred_tts_voice_id,
            "preferred_knowledge_base_id": row.preferred_knowledge_base_id,
            "graph_style": row.graph_style,
        }

    def update(self, preferences: dict) -> None:
        """Write preferences. Only keys present in the dict are updated."""
        row = _get_or_create(self.db, self.key)
        for attr in (
            "preferred_llm_provider_id",
            "preferred_tts_provider_id",
            "preferred_tts_voice_id",
            "preferred_knowledge_base_id",
            "graph_style",
        ):
            if attr in preferences:
                setattr(row, attr, preferences[attr])
        self.db.commit()

    def learn_from_apply(
        self,
        harness_graph: dict,
        user_final_graph: dict,
    ) -> None:
        """Compare harness draft with user's final saved graph and update preferences.

        Conservative rule: only update when user explicitly changed something.
        """
        updates: dict = {}

        # Detect LLM provider change
        harness_llm_provider = _extract_first_provider_id(harness_graph, "llm")
        user_llm_provider = _extract_first_provider_id(user_final_graph, "llm")
        if harness_llm_provider is not None and user_llm_provider is not None:
            if harness_llm_provider != user_llm_provider:
                updates["preferred_llm_provider_id"] = user_llm_provider

        # Detect TTS voice change
        harness_voice = _extract_first_config_value(harness_graph, "tts", "voice_id")
        user_voice = _extract_first_config_value(user_final_graph, "tts", "voice_id")
        if harness_voice is not None and user_voice is not None:
            if harness_voice != user_voice:
                updates["preferred_tts_voice_id"] = user_voice

        # Detect graph style shift (simple heuristic)
        harness_nodes = len(harness_graph.get("nodes", []))
        user_nodes = len(user_final_graph.get("nodes", []))
        if abs(user_nodes - harness_nodes) > 2:
            updates["graph_style"] = "verbose" if user_nodes > harness_nodes else "minimal"

        if updates:
            self.update(updates)


def _extract_first_provider_id(graph: dict, node_type: str) -> int | None:
    for node in graph.get("nodes", []):
        if node.get("type") == node_type:
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            pid = data.get("provider_id")
            if pid is not None:
                return int(pid) if isinstance(pid, (int, float, str)) else None
    return None


def _extract_first_config_value(graph: dict, node_type: str, key: str) -> str | None:
    for node in graph.get("nodes", []):
        if node.get("type") == node_type:
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            val = data.get(key)
            if val is not None:
                return str(val)
    return None
