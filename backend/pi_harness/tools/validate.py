from __future__ import annotations

import json

from langchain_core.tools import StructuredTool

from backend.harness.validators import validate_graph
from backend.pi_harness.state import WorkflowGraphDraft


def build_validate_graph_tool(
    draft: WorkflowGraphDraft,
    *,
    db=None,
) -> StructuredTool:
    def validate_current_graph() -> str:
        findings = validate_graph(draft.snapshot(), db=db)
        return json.dumps(
            {
                "status": "ok",
                "findings": [finding.model_dump(mode="json") for finding in findings],
            },
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        validate_current_graph,
        name="validate_graph",
        description="Validate the current workflow draft graph and return findings.",
    )
