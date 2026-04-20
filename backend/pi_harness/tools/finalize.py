from __future__ import annotations

import json
from collections.abc import Callable

from backend.harness.validators import validate_graph
from backend.pi_harness.state import WorkflowGraphDraft
from backend.pi_harness.tools.compat import CompatStructuredTool


def build_finalize_draft_tool(
    draft: WorkflowGraphDraft,
    *,
    db=None,
    on_ready: Callable[[dict], None] | None = None,
) -> CompatStructuredTool:
    def finalize_draft() -> str:
        graph = draft.snapshot()
        findings = validate_graph(graph, db=db)
        ready = not any(finding.severity == "error" for finding in findings)

        if ready and on_ready is not None:
            on_ready(graph)

        return json.dumps(
            {
                "ready": ready,
                "graph": graph,
                "findings": [finding.model_dump(mode="json") for finding in findings],
            },
            ensure_ascii=False,
        )

    async def finalize_draft_async() -> str:
        return finalize_draft()

    return CompatStructuredTool.from_function(
        finalize_draft,
        coroutine=finalize_draft_async,
        name="finalize_draft",
        description="Validate the current workflow draft and mark it ready if there are no errors.",
    )
