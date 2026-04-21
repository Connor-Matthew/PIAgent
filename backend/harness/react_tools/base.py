"""Shared context and utilities for ReAct authoring tools."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.harness.builder import GraphBuilder
from backend.harness.skills.loader import SkillLoader
from backend.harness.workspace import Workspace


@dataclass
class ToolContext:
    """Runtime context available to all authoring tools."""

    session_id: str
    workspace: Workspace
    builder: GraphBuilder
    db: Session
    skills: SkillLoader


def _json_compact(value: dict | list) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
