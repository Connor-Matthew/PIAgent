from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = Field(default=None)
