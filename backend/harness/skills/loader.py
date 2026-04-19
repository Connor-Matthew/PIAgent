"""PIAgent Harness v2 — SkillLoader: on-demand disk reads + frontmatter parsing.

Skills are Markdown files with YAML frontmatter. The loader caches content
per-process and prevents duplicate loads within a single session.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


_SKILL_DIR = Path(__file__).parent

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class SkillInfo:
    def __init__(self, name: str, description: str, applies_when: str, meta: dict):
        self.name = name
        self.description = description
        self.applies_when = applies_when
        self.meta = meta

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "applies_when": self.applies_when,
            "nodes": self.meta.get("nodes", []),
            "requires": self.meta.get("requires", []),
        }


class SkillLoader:
    """Loads skills from disk. Maintains a catalog without loading full content."""

    def __init__(self, skill_dir: Path | None = None) -> None:
        self._skill_dir = skill_dir or _SKILL_DIR
        self._catalog: list[SkillInfo] | None = None
        self._cache: dict[str, str] = {}  # name -> full markdown

    def catalog(self) -> list[dict]:
        """Return skill catalog (name + description + applies_when) without loading content."""
        if self._catalog is None:
            self._catalog = self._scan()
        return [s.to_dict() for s in self._catalog]

    def load(self, name: str) -> str:
        """Load full skill markdown. Cached per-process; idempotent."""
        if name in self._cache:
            return self._cache[name]

        path = self._skill_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Skill not found: {name}")

        content = path.read_text(encoding="utf-8")
        self._cache[name] = content
        return content

    def _scan(self) -> list[SkillInfo]:
        skills: list[SkillInfo] = []
        for path in sorted(self._skill_dir.glob("*.md")):
            if path.name.startswith("_"):
                continue
            meta, _ = _parse_skill(path.read_text(encoding="utf-8"))
            name = meta.get("name", path.stem)
            skills.append(
                SkillInfo(
                    name=name,
                    description=meta.get("description", ""),
                    applies_when=meta.get("applies_when", ""),
                    meta=meta,
                )
            )
        return skills


def _parse_skill(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and Markdown body from skill text."""
    match = _FRONTMATTER_RE.match(text)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        body = match.group(2).strip()
        return meta, body
    return {}, text.strip()
