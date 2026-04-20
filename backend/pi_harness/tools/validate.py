from __future__ import annotations

import json

from backend.pi_harness.validators import validate_graph
from backend.pi_harness.state import WorkflowGraphDraft
from backend.pi_harness.tools.compat import CompatStructuredTool


def build_validate_graph_tool(
    draft: WorkflowGraphDraft,
    *,
    db=None,
) -> CompatStructuredTool:
    def validate_current_graph() -> str:
        findings = validate_graph(draft.snapshot(), db=db)
        return json.dumps(
            {
                "status": "ok",
                "findings": [finding.model_dump(mode="json") for finding in findings],
            },
            ensure_ascii=False,
        )

    async def validate_current_graph_async() -> str:
        return validate_current_graph()

    return CompatStructuredTool.from_function(
        validate_current_graph,
        coroutine=validate_current_graph_async,
        name="validate_graph",
        description="Validate the current workflow draft graph and return findings.",
    )
