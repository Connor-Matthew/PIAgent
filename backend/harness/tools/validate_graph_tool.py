from __future__ import annotations

from pydantic import BaseModel

from backend.harness.tools.base import HarnessContext, Tool
from backend.harness.validators import validate_graph


class ValidateGraphInput(BaseModel):
    graph: dict


class ValidateGraphOutput(BaseModel):
    ok: bool
    findings: list[dict]


class ValidateGraphTool:
    name = "validate_graph"
    description = (
        "Validate a workflow graph and return any errors or warnings. "
        "This is the same validation run automatically at Finalize."
    )
    input_schema = ValidateGraphInput
    output_schema = ValidateGraphOutput
    side_effects = False

    async def run(
        self, args: ValidateGraphInput, ctx: HarnessContext
    ) -> ValidateGraphOutput:
        findings = validate_graph(args.graph, db=ctx.db)
        return ValidateGraphOutput(
            ok=not any(f.severity == "error" for f in findings),
            findings=[f.model_dump(mode="json") for f in findings],
        )
