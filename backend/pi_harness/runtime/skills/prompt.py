from pathlib import Path

from langchain_core.messages import SystemMessage

from backend.pi_harness.runtime.skills.loader import (
    get_skills_prompt_section,
    load_skills,
)


def build_skills_state_modifier(skills_path: str | Path | None = None):
    skills = load_skills(skills_path)
    skills_section = get_skills_prompt_section(skills)

    if not skills_section:
        return None

    def state_modifier(state):
        return [SystemMessage(content=skills_section)] + list(state["messages"])

    return state_modifier

