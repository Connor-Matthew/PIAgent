import re
from pathlib import Path

from backend.pi_harness.runtime.skills.models import Skill


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
    match = pattern.match(content.strip())
    if not match:
        return {}, content

    front_text = match.group(1)
    body = match.group(2)

    frontmatter: dict[str, str] = {}
    for line in front_text.strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            frontmatter[key.strip()] = val.strip().strip('"').strip("'")
    return frontmatter, body


def _scan_skill_dir(skill_dir: Path) -> Skill | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
        frontmatter, _ = _parse_frontmatter(content)
    except Exception:
        return None

    name = frontmatter.get("name", skill_dir.name)
    description = frontmatter.get("description", "")
    enabled = str(frontmatter.get("enabled", "true")).lower() == "true"

    if not name or not description:
        return None

    return Skill(
        name=name,
        description=description,
        enabled=enabled,
        skill_dir=skill_dir,
        skill_file=skill_file,
    )


def load_skills(skills_path: Path | str | None = None) -> list[Skill]:
    if skills_path is None:
        skills_path = Path.cwd() / "skills"
    else:
        skills_path = Path(skills_path)

    if not skills_path.exists():
        return []

    skills: list[Skill] = []
    for item in sorted(skills_path.iterdir()):
        if item.is_dir():
            skill = _scan_skill_dir(item)
            if skill:
                skills.append(skill)

    return sorted(skills, key=lambda s: s.name)


def get_skills_prompt_section(skills: list[Skill]) -> str | None:
    enabled = [s for s in skills if s.enabled]
    if not enabled:
        return None

    lines = ["<skill_system>", "  <available_skills>"]
    for skill in enabled:
        try:
            rel_path = skill.skill_file.resolve().relative_to(Path.cwd().resolve())
            rel_path = f"./{rel_path}"
        except ValueError:
            rel_path = str(skill.skill_file)
        lines.append("    <skill>")
        lines.append(f"      <name>{skill.name}</name>")
        lines.append(f"      <description>{skill.description}</description>")
        lines.append(f"      <location>{rel_path}</location>")
        lines.append("    </skill>")
    lines.append("  </available_skills>")
    lines.append("")
    lines.append("  <instructions>")
    lines.append("    - When a task matches a skill's description, load the full skill instructions by reading the file at <location>.")
    lines.append("    - Follow the skill's instructions carefully after loading it.")
    lines.append("    - Only load skills when relevant to the current task.")
    lines.append("  </instructions>")
    lines.append("</skill_system>")

    return "\n".join(lines)

