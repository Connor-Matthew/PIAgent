from __future__ import annotations

import json
from collections.abc import Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from backend.pi_harness.state import WorkflowGraphDraft

EventSink = Callable[[dict], None]


class AddNodeArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    node_type: str
    node_config: dict | None = Field(default=None, alias="config")
    node_id: str | None = None
    parent_id: str | None = None
    branch_id: str | None = None


def build_graph_op_tools(
    draft: WorkflowGraphDraft,
    *,
    event_sink: EventSink | None = None,
) -> list[StructuredTool]:
    def _emit(operation: str, **payload) -> None:
        if event_sink is None:
            return
        event_sink(
            {
                "type": "graph_update",
                "operation": operation,
                "snapshot": draft.snapshot(),
                **payload,
            }
        )

    def add_node(
        node_type: str,
        node_config: dict | None = None,
        node_id: str | None = None,
        parent_id: str | None = None,
        branch_id: str | None = None,
    ) -> str:
        node = draft.add_node(
            node_type=node_type,
            config=node_config,
            node_id=node_id,
            parent_id=parent_id,
            branch_id=branch_id,
        )
        _emit("add_node", node_id=node["id"])
        return json.dumps(
            {
                "status": "ok",
                "node_id": node["id"],
                "graph": draft.snapshot(),
            },
            ensure_ascii=False,
        )

    def connect_nodes(
        from_id: str,
        to_id: str,
        source_handle: str | None = None,
    ) -> str:
        edge = draft.connect_nodes(
            from_id=from_id,
            to_id=to_id,
            source_handle=source_handle,
        )
        _emit("connect_nodes", edge_id=edge["id"])
        return json.dumps(
            {
                "status": "ok",
                "edge_id": edge["id"],
                "graph": draft.snapshot(),
            },
            ensure_ascii=False,
        )

    def patch_node_config(node_id: str, fields: dict) -> str:
        node = draft.patch_node_config(node_id=node_id, fields=fields)
        _emit("patch_node_config", node_id=node["id"])
        return json.dumps(
            {
                "status": "ok",
                "node_id": node["id"],
                "graph": draft.snapshot(),
            },
            ensure_ascii=False,
        )

    def remove_node(node_id: str) -> str:
        draft.remove_node(node_id=node_id)
        _emit("remove_node", node_id=node_id)
        return json.dumps(
            {
                "status": "ok",
                "node_id": node_id,
                "graph": draft.snapshot(),
            },
            ensure_ascii=False,
        )

    def remove_edge(from_id: str, to_id: str) -> str:
        draft.remove_edge(from_id=from_id, to_id=to_id)
        _emit("remove_edge", edge_id=f"{from_id}-{to_id}")
        return json.dumps(
            {
                "status": "ok",
                "edge_id": f"{from_id}-{to_id}",
                "graph": draft.snapshot(),
            },
            ensure_ascii=False,
        )

    return [
        StructuredTool.from_function(
            add_node,
            name="add_node",
            description="Add a node to the workflow draft graph.",
            args_schema=AddNodeArgs,
        ),
        StructuredTool.from_function(
            connect_nodes,
            name="connect_nodes",
            description="Connect two existing nodes in the workflow draft graph.",
        ),
        StructuredTool.from_function(
            patch_node_config,
            name="patch_node_config",
            description="Patch the config or structural fields of an existing node.",
        ),
        StructuredTool.from_function(
            remove_node,
            name="remove_node",
            description="Remove a node from the workflow draft graph.",
        ),
        StructuredTool.from_function(
            remove_edge,
            name="remove_edge",
            description="Remove an edge from the workflow draft graph.",
        ),
    ]
