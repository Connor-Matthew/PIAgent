"""PIAgent Harness v2 — LeadAgent: the sole agent with a loop, tools, and skill loader.

The actual orchestration loop lives in HarnessSession (session.py).
LeadAgent is responsible only for the `decide()` call.
"""

from __future__ import annotations

from backend.harness.llm_client import HarnessLLMClient
from backend.harness.prompts import render_observation, render_system_prompt
from backend.harness.schemas import Decision, validate_decision_payload
from backend.harness.tools.base import ToolRegistry
from backend.harness.workspace import Workspace


class LeadAgent:
    """Emits a Decision based on the current workspace observation."""

    def __init__(
        self,
        db,
        tool_registry: ToolRegistry,
        skill_catalog: list[dict],
        preferences: dict | None = None,
    ):
        self.llm = HarnessLLMClient(db)
        self.tool_registry = tool_registry
        self.skill_catalog = skill_catalog
        self.preferences = preferences or {}

    def decide(
        self,
        workspace: Workspace,
    ) -> Decision:
        """Render observation, call LLM, return a validated Decision.

        This is a **synchronous** call wrapped in asyncio.to_thread by the caller
        (HarnessSession) so that the loop stays async-friendly.
        """
        system = render_system_prompt(
            tool_registry=self.tool_registry,
            skill_catalog=self.skill_catalog,
            preferences=self.preferences,
        )
        user = render_observation(workspace.observation())
        raw_decision = self.llm.structured_invoke(
            schema=dict,
            system_prompt=system,
            user_prompt=user,
        )
        return validate_decision_payload(raw_decision)
