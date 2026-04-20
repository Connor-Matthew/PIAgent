from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from backend.pi_harness.state import WorkflowGraphDraft
from backend.pi_harness.tools.compat import CompatStructuredTool

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
) -> list[CompatStructuredTool]:
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

    async def add_node_async(
        node_type: str,
        node_config: dict | None = None,
        node_id: str | None = None,
        parent_id: str | None = None,
        branch_id: str | None = None,
    ) -> str:
        return add_node(
            node_type=node_type,
            node_config=node_config,
            node_id=node_id,
            parent_id=parent_id,
            branch_id=branch_id,
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

    async def connect_nodes_async(
        from_id: str,
        to_id: str,
        source_handle: str | None = None,
    ) -> str:
        return connect_nodes(
            from_id=from_id,
            to_id=to_id,
            source_handle=source_handle,
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

    async def patch_node_config_async(node_id: str, fields: dict) -> str:
        return patch_node_config(node_id=node_id, fields=fields)

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

    async def remove_node_async(node_id: str) -> str:
        return remove_node(node_id=node_id)

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

    async def remove_edge_async(from_id: str, to_id: str) -> str:
        return remove_edge(from_id=from_id, to_id=to_id)

    return [
        CompatStructuredTool.from_function(
            add_node,
            coroutine=add_node_async,
            name="add_node",
            description="Add a node to the workflow draft graph.",
            args_schema=AddNodeArgs,
        ),
        CompatStructuredTool.from_function(
            connect_nodes,
            coroutine=connect_nodes_async,
            name="connect_nodes",
            description="Connect two existing nodes in the workflow draft graph.",
        ),
        CompatStructuredTool.from_function(
            patch_node_config,
            coroutine=patch_node_config_async,
            name="patch_node_config",
            description="Patch the config or structural fields of an existing node.",
        ),
        CompatStructuredTool.from_function(
            remove_node,
            coroutine=remove_node_async,
            name="remove_node",
            description="Remove a node from the workflow draft graph.",
        ),
        CompatStructuredTool.from_function(
            remove_edge,
            coroutine=remove_edge_async,
            name="remove_edge",
            description="Remove an edge from the workflow draft graph.",
        ),
    ]
