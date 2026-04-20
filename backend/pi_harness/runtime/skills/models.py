from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    enabled: bool
    skill_dir: Path
    skill_file: Path

