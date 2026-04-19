# Graph Contract + Runtime Context Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WorkflowGraph v2 the single graph contract across frontend, Harness, backend validation, compilation, and execution, then introduce a runtime context and typed event layer so workflow execution is more stable under control-flow, iteration, provider access, and SSE streaming.

**Architecture:** Normalize every graph at system boundaries with `backend/core/graph_schema.py` and `frontend/src/graph/*`, compile normalized graphs into a `CompiledWorkflow` that hides raw JSON from the engine, and pass a `RunContext` through execution instead of letting nodes open their own DB sessions. Keep the existing `ExecutionEngine` scheduling model and avoid a full runtime rewrite.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Pydantic v2, pytest, React 19, TypeScript, Vite, React Flow, Zustand.

---

## Scope

This plan implements option B from the architecture discussion:

- Contract-first graph normalization.
- Compiler and Harness validator reading the same structural rules.
- Execution engine consuming compiled metadata rather than raw `data` dicts.
- Runtime context for provider lookup, event emission, and cancellation hooks.
- Typed SSE event factories with frontend type alignment.
- Frontend store using the existing graph adapter layer instead of custom v1 serialization.

This plan does not implement a new parallel DAG scheduler, retries, resumable event logs, distributed execution, or workflow persistence migrations beyond normalizing newly saved graphs.

## Current Risk To Protect

The current repo has uncommitted work in backend files. Before executing this plan, run:

```bash
git status --short --branch
```

Expected: review the dirty files and do not revert or overwrite unrelated edits. If a task touches a dirty file, inspect `git diff -- <file>` first and layer changes on top.

---

## File Structure

Modify these backend files:

- `backend/core/graph_schema.py` — canonical graph loading, dumping, and helpers for config, parent, branch, and legacy conversion.
- `backend/core/graph_rules.py` — pure graph structural rules operating on canonical v2-compatible node accessors.
- `backend/core/compiler.py` — normalize graph input, validate against canonical graph, and produce compiled metadata.
- `backend/core/engine.py` — consume compiled metadata, pass `RunContext`, and emit typed events.
- `backend/core/state.py` — document runtime state and add optional internal iteration context type fields.
- `backend/core/template.py` — keep reference behavior but verify it works with canonical runtime outputs.
- `backend/core/run_context.py` — create runtime context for DB-backed provider lookup, provider caching, event emission, and cancellation.
- `backend/core/events.py` — create event factory helpers for SSE payloads.
- `backend/api/workflows.py` — normalize graphs on create/update/run and use `RunContext`.
- `backend/models/workflow.py` — normalize graph JSON in the property setter if it is safe with existing tests.
- `backend/harness/builder.py` — emit canonical v2 graph snapshots.
- `backend/harness/validators.py` — validate canonical v2 and legacy v1 via the same graph schema loader.
- `backend/harness/session.py` — persist/apply canonical v2 graphs.
- `backend/harness/schemas.py` — accept legacy action shapes while exposing branch metadata cleanly.
- `backend/harness/tools/validate_graph_tool.py` — validate normalized graph input.
- `backend/nodes/base.py` — accept `run_context` in node execution.
- `backend/nodes/llm_node.py` — use `RunContext` for provider/model creation.
- `backend/nodes/tts_node.py` — use `RunContext` for TTS provider creation.
- `backend/nodes/agent_node.py` — use `RunContext` for provider/model creation.
- `backend/nodes/rag_node.py` — keep retrieval behavior but accept context consistently.

Create or modify these backend tests:

- Create `backend/tests/test_graph_schema.py`.
- Create `backend/tests/test_engine_v2_contract.py`.
- Modify `backend/tests/test_compiler.py`.
- Modify `backend/tests/test_compiler_m1.py`.
- Modify `backend/tests/test_harness_v2.py`.
- Modify `backend/tests/test_harness_to_engine_e2e.py`.
- Modify `backend/tests/test_workflows_api.py`.
- Modify `backend/tests/test_nodes.py`.

Modify these frontend files:

- `frontend/src/graph/contract.ts` — keep v2 as the graph type source.
- `frontend/src/graph/adapters.ts` — keep React Flow conversion as the only graph adapter.
- `frontend/src/graph/roundtrip.test.ts` — expand round-trip coverage.
- `frontend/src/stores/workflowStore.ts` — delegate graph load/save to adapters.
- `frontend/src/types/workflow.ts` — align API graph and SSE event types with v2 and event factories.
- `frontend/src/services/api.ts` — use v2 graph type for workflow payloads.
- `frontend/package.json` — add a test script only if Vitest is already available or the execution owner agrees to add it.

---

### Task 1: Backend Graph Schema Canonical Helpers

**Files:**
- Modify: `backend/core/graph_schema.py`
- Create: `backend/tests/test_graph_schema.py`

- [ ] **Step 1: Write the failing graph schema tests**

Add `backend/tests/test_graph_schema.py`:

```python
from backend.core.graph_schema import (
    dump_graph,
    get_node_branch_id,
    get_node_config,
    get_node_parent_id,
    load_graph,
)


def test_load_graph_preserves_v2_config_and_structure():
    graph = load_graph({
        "version": 2,
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm",
                "parentId": "if_1",
                "branchId": "true",
                "label": "Writer",
                "locked": False,
                "config": {"provider_id": 7, "model": "gpt-4o"},
            }
        ],
        "edges": [],
    })

    node = graph.nodes[0]
    assert get_node_parent_id(node) == "if_1"
    assert get_node_branch_id(node) == "true"
    assert get_node_config(node) == {"provider_id": 7, "model": "gpt-4o"}


def test_load_graph_upgrades_v1_data_to_v2_config():
    graph = load_graph({
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm",
                "position": {"x": 1, "y": 2},
                "data": {
                    "label": "Writer",
                    "nodeType": "llm",
                    "parentId": "if_1",
                    "branchId": "true",
                    "provider_id": 9,
                    "model": "deepseek-chat",
                },
            }
        ],
        "edges": [{"id": "a-b", "source": "a", "target": "b", "sourceHandle": "true"}],
    })

    node = graph.nodes[0]
    assert graph.version == 2
    assert node.parentId == "if_1"
    assert node.branchId == "true"
    assert node.label == "Writer"
    assert node.config == {"provider_id": 9, "model": "deepseek-chat"}
    assert graph.edges[0].sourceHandle == "true"


def test_load_graph_merges_legacy_data_config_object():
    graph = load_graph({
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm",
                "data": {
                    "parentId": "if_1",
                    "provider_id": 1,
                    "config": {"provider_id": 2, "temperature": 0.2},
                },
            }
        ],
        "edges": [],
    })

    assert graph.nodes[0].config == {"provider_id": 2, "temperature": 0.2}


def test_dump_graph_emits_canonical_v2_without_data():
    graph = load_graph({
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
        ],
        "edges": [],
    })

    dumped = dump_graph(graph)

    assert dumped["version"] == 2
    assert dumped["nodes"][0]["config"] == {"inputs": []}
    assert "data" not in dumped["nodes"][0]
```

- [ ] **Step 2: Run the test and verify it fails for the right reason**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_graph_schema.py -v
```

Expected: FAIL because helper functions such as `get_node_config`, `get_node_parent_id`, and legacy `data.config` merge behavior are not implemented yet.

- [ ] **Step 3: Implement canonical helper functions**

Update `backend/core/graph_schema.py` with these helpers:

```python
def get_node_config(node: WorkflowNode | dict[str, Any]) -> dict[str, Any]:
    if isinstance(node, WorkflowNode):
        return dict(node.config or {})
    if isinstance(node.get("config"), dict):
        return dict(node["config"])
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if isinstance(data.get("config"), dict):
        return dict(data["config"])
    return {
        key: value
        for key, value in data.items()
        if key not in ("parentId", "branchId", "label", "locked", "nodeType")
    }


def get_node_parent_id(node: WorkflowNode | dict[str, Any]) -> str | None:
    if isinstance(node, WorkflowNode):
        return node.parentId
    if isinstance(node.get("parentId"), str):
        return node["parentId"]
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return data.get("parentId") if isinstance(data.get("parentId"), str) else None


def get_node_branch_id(node: WorkflowNode | dict[str, Any]) -> str | None:
    if isinstance(node, WorkflowNode):
        return node.branchId
    if isinstance(node.get("branchId"), str):
        return node["branchId"]
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return data.get("branchId") if isinstance(data.get("branchId"), str) else None
```

Also update `_upgrade_v1_node()` so a nested `data.config` object overrides flat legacy config keys:

```python
    nested_config = data.get("config")
    if isinstance(nested_config, dict):
        config.update(nested_config)
```

- [ ] **Step 4: Run graph schema tests again**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_graph_schema.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit this task**

Run:

```bash
git add backend/core/graph_schema.py backend/tests/test_graph_schema.py
git commit -m "refactor: add canonical workflow graph helpers"
```

Expected: commit succeeds. If the worktree contains unrelated user edits in either file, stage only this task's hunks with `git add -p`.

---

### Task 2: Compiler And Graph Rules Use Canonical Graph Metadata

**Files:**
- Modify: `backend/core/graph_rules.py`
- Modify: `backend/core/compiler.py`
- Modify: `backend/tests/test_compiler.py`
- Modify: `backend/tests/test_compiler_m1.py`

- [ ] **Step 1: Write failing compiler tests for v2 graphs**

Append to `backend/tests/test_compiler.py`:

```python
from backend.core.compiler import GraphCompiler


def test_compiler_preserves_v2_node_config():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1, "model": "gpt-4o"}},
            {
                "id": "end_1",
                "type": "end",
                "config": {
                    "outputs": [{"name": "answer", "source": "reference", "value": "{{llm_1.text}}"}],
                    "answer": "{{answer}}",
                },
            },
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }

    compiled = GraphCompiler().compile(graph)

    assert compiled.nodes["llm_1"].config["provider_id"] == 1
    assert compiled.nodes["llm_1"].config["model"] == "gpt-4o"
    assert compiled.nodes["end_1"].config["outputs"][0]["value"] == "{{llm_1.text}}"


def test_compiler_uses_v2_parent_and_branch_fields():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {"id": "if_1", "type": "if_else", "config": {"branches": [{"id": "true", "condition": None}]}},
            {"id": "child_1", "type": "llm", "parentId": "if_1", "branchId": "true", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }

    compiled = GraphCompiler().compile(graph)

    assert compiled.children_by_parent["if_1"] == ["child_1"]
    assert compiled.node_defs["child_1"]["branchId"] == "true"
```

Append to `backend/tests/test_compiler_m1.py`:

```python
def test_compiler_rejects_v2_orphan_parent_id():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "config": {}},
            {"id": "llm_1", "type": "llm", "parentId": "missing_parent", "config": {}},
            {"id": "end_1", "type": "end", "config": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    )

    compiler = GraphCompiler()
    with pytest.raises(CompilerError, match="parentId.*does not exist"):
        compiler.validate(graph_json)
```

- [ ] **Step 2: Run the compiler tests and verify red**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_compiler.py::test_compiler_preserves_v2_node_config backend/tests/test_compiler.py::test_compiler_uses_v2_parent_and_branch_fields backend/tests/test_compiler_m1.py::test_compiler_rejects_v2_orphan_parent_id -v
```

Expected: FAIL because `GraphCompiler` and `graph_rules` still read `data.parentId` and `data` config.

- [ ] **Step 3: Update graph rules to use graph schema helpers**

In `backend/core/graph_rules.py`, import:

```python
from backend.core.graph_schema import get_node_parent_id
```

Replace the private `_get_parent_id()` body with:

```python
def _get_parent_id(node_def: dict) -> str | None:
    return get_node_parent_id(node_def)
```

- [ ] **Step 4: Normalize graph input inside compiler**

In `backend/core/compiler.py`, import:

```python
from backend.core.graph_schema import dump_graph, get_node_config, get_node_parent_id, load_graph
```

Add a private normalizer:

```python
    def _normalize(self, graph_json: dict) -> dict:
        return dump_graph(load_graph(graph_json))
```

Change `validate()`, `topological_sort()`, and `compile()` so their first operation is:

```python
        graph_json = self._normalize(graph_json)
```

Change `_get_parent_id()` to:

```python
    @staticmethod
    def _get_parent_id(node_def: dict) -> str | None:
        return get_node_parent_id(node_def)
```

Change node instantiation in `compile()`:

```python
            config = {**get_node_config(node_def), "id": node_def["id"]}
```

Change End output validation and provider validation to use `get_node_config(node_def)` instead of `node_def.get("data")`.

- [ ] **Step 5: Run targeted compiler tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_compiler.py backend/tests/test_compiler_m1.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add backend/core/graph_rules.py backend/core/compiler.py backend/tests/test_compiler.py backend/tests/test_compiler_m1.py
git commit -m "refactor: compile canonical workflow graphs"
```

Expected: commit succeeds. Use `git add -p` if these files contain unrelated changes.

---

### Task 3: Harness Builder Emits Canonical WorkflowGraph v2

**Files:**
- Modify: `backend/harness/builder.py`
- Modify: `backend/harness/schemas.py`
- Modify: `backend/harness/session.py`
- Modify: `backend/harness/validators.py`
- Modify: `backend/harness/tools/validate_graph_tool.py`
- Modify: `backend/tests/test_harness_v2.py`
- Modify: `backend/tests/test_harness_to_engine_e2e.py`

- [ ] **Step 1: Write failing Harness canonical graph tests**

Append to `backend/tests/test_harness_v2.py`:

```python
def test_builder_snapshot_is_canonical_v2():
    b = GraphBuilder()
    b.apply(AddNodeAction(node_type="if_else", node_id="if_1", config={"branches": [{"id": "true"}]}))
    b.apply(
        AddNodeAction(
            node_type="llm",
            node_id="llm_true",
            parent_id="if_1",
            config={"branchId": "true", "provider_id": 1},
        )
    )

    snap = b.snapshot()
    child = next(n for n in snap["nodes"] if n["id"] == "llm_true")

    assert snap["version"] == 2
    assert child["parentId"] == "if_1"
    assert child["branchId"] == "true"
    assert child["config"] == {"provider_id": 1}
    assert "data" not in child


def test_harness_validator_accepts_v2_provider_config(db: Session):
    db.add(Provider(type="openai", name="test", api_key_encrypted="enc", enabled=True, category="llm"))
    db.commit()

    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }

    findings = validate_graph(graph, db=db)

    assert not [f for f in findings if f.severity == "error"]
```

- [ ] **Step 2: Run Harness tests and verify red**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_harness_v2.py::test_builder_snapshot_is_canonical_v2 backend/tests/test_harness_v2.py::test_harness_validator_accepts_v2_provider_config -v
```

Expected: FAIL because `GraphBuilder.snapshot()` currently returns v1 `{nodes, edges}` with node `data`.

- [ ] **Step 3: Update GraphBuilder to store and return canonical v2**

In `backend/harness/builder.py`, import:

```python
from backend.core.graph_schema import dump_graph, load_graph
```

Update `_add_node()`:

```python
        config = dict(action.config)
        branch_id = config.pop("branchId", None)
        node = {
            "id": node_id,
            "type": action.node_type,
            "position": pos,
            "config": config,
        }
        if action.parent_id:
            node["parentId"] = action.parent_id
        if isinstance(branch_id, str):
            node["branchId"] = branch_id
```

Update `_update_node_config()`:

```python
                patch = dict(action.config)
                if "parentId" in patch:
                    node["parentId"] = patch.pop("parentId")
                if "branchId" in patch:
                    node["branchId"] = patch.pop("branchId")
                node.setdefault("config", {}).update(patch)
                return
```

Update child cascade in `_delete_node()` to read top-level `parentId`:

```python
            if n.get("parentId") == action.node_id
```

Update `snapshot()`:

```python
        return dump_graph(load_graph({
            "version": 2,
            "nodes": [dict(n) for n in self._nodes],
            "edges": [dict(e) for e in self._edges],
        }))
```

Update `from_snapshot()`:

```python
        graph = dump_graph(load_graph(snapshot))
        self._nodes = [dict(n) for n in graph.get("nodes", [])]
        self._edges = [dict(e) for e in graph.get("edges", [])]
```

- [ ] **Step 4: Normalize validators and apply path**

In `backend/harness/validators.py`, normalize once at the top:

```python
from backend.core.graph_schema import dump_graph, get_node_config, load_graph

graph = dump_graph(load_graph(graph))
nodes = graph.get("nodes", [])
edges = graph.get("edges", [])
```

Replace provider checks and End output checks with `get_node_config(node)`.

In `backend/harness/tools/validate_graph_tool.py`, keep calling `validate_graph()`; no separate graph parsing logic should remain.

In `backend/harness/session.py`, keep using `self.builder.snapshot()` for graph persistence after Task 3 because it now returns v2.

- [ ] **Step 5: Update compatibility assertions that intentionally checked v1**

In `backend/tests/test_harness_v2.py`, replace old assertions such as:

```python
assert n1["data"]["parentId"] == "if1"
```

with:

```python
assert n1["parentId"] == "if1"
```

Also update any tests that expect config fields inside `data` so they expect `config`.

- [ ] **Step 6: Run Harness tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_harness_v2.py backend/tests/test_harness_to_engine_e2e.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit this task**

Run:

```bash
git add backend/harness/builder.py backend/harness/schemas.py backend/harness/session.py backend/harness/validators.py backend/harness/tools/validate_graph_tool.py backend/tests/test_harness_v2.py backend/tests/test_harness_to_engine_e2e.py
git commit -m "refactor: emit canonical graphs from harness"
```

Expected: commit succeeds. Stage hunks carefully if these files include unrelated local edits.

---

### Task 4: API And Workflow Persistence Normalize Graphs At Boundaries

**Files:**
- Modify: `backend/api/workflows.py`
- Modify: `backend/models/workflow.py`
- Modify: `backend/tests/test_workflows_api.py`

- [ ] **Step 1: Write failing API normalization tests**

Append to `backend/tests/test_workflows_api.py`:

```python
def test_create_workflow_stores_graph_as_v2(client):
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {"inputs": []}},
            {"id": "end_1", "type": "end", "data": {"outputs": [], "answer": ""}},
        ],
        "edges": [{"source": "start_1", "target": "end_1"}],
    }

    response = client.post("/api/workflows", json={"name": "v1 input", "graph": graph})

    assert response.status_code == 201
    saved = response.json()["graph"]
    assert saved["version"] == 2
    assert saved["nodes"][0]["config"] == {"inputs": []}
    assert "data" not in saved["nodes"][0]


def test_update_workflow_returns_v2_graph(client):
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [{"source": "start_1", "target": "end_1"}],
    }
    created = client.post("/api/workflows", json={"name": "x", "graph": graph}).json()

    response = client.put(
        f"/api/workflows/{created['id']}",
        json={"graph": graph},
    )

    assert response.status_code == 200
    assert response.json()["graph"]["version"] == 2
```

- [ ] **Step 2: Run targeted API tests and verify red**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_workflows_api.py::test_create_workflow_stores_graph_as_v2 backend/tests/test_workflows_api.py::test_update_workflow_returns_v2_graph -v
```

Expected: FAIL because API currently returns the same graph shape it receives.

- [ ] **Step 3: Add a local API normalizer**

In `backend/api/workflows.py`, import:

```python
from backend.core.graph_schema import dump_graph, load_graph
```

Add:

```python
def _normalize_graph_payload(graph: dict) -> dict:
    return dump_graph(load_graph(graph))
```

Use it in `create_workflow()` and `update_workflow()` before validation and persistence:

```python
    graph = _normalize_graph_payload(body.graph)
    compiler.validate(graph, db=db)
    wf.graph = graph
```

For update:

```python
    graph = _normalize_graph_payload(body.graph) if body.graph is not None else None
```

Return `wf.graph`, which should now be v2.

- [ ] **Step 4: Normalize in the Workflow model setter**

In `backend/models/workflow.py`, import:

```python
from backend.core.graph_schema import dump_graph, load_graph
```

Update the setter:

```python
    @graph.setter
    def graph(self, value: dict):
        self.graph_json = json.dumps(dump_graph(load_graph(value)), ensure_ascii=False)
```

Keep direct `graph_json=` assignments in tests valid by not changing the constructor path.

- [ ] **Step 5: Run API tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_workflows_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add backend/api/workflows.py backend/models/workflow.py backend/tests/test_workflows_api.py
git commit -m "refactor: normalize workflow graphs at api boundaries"
```

Expected: commit succeeds.

---

### Task 5: Engine Consumes Compiled Metadata Instead Of Raw Node Data

**Files:**
- Modify: `backend/core/compiler.py`
- Modify: `backend/core/engine.py`
- Create: `backend/tests/test_engine_v2_contract.py`
- Modify: `backend/tests/test_engine_if_else.py`
- Modify: `backend/tests/test_engine_iteration.py`
- Modify: `backend/tests/test_engine_iteration_concurrent.py`

- [ ] **Step 1: Write failing v2 engine contract tests**

Create `backend/tests/test_engine_v2_contract.py`:

```python
import pytest

from backend.core.engine import ExecutionEngine
from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.nodes.registry import node_registry


class EchoNode(BaseNode):
    node_type = "echo_v2"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {
            self.config.get("output_key", "text"): self.config.get("output_value", "ok")
        }
        return state


try:
    node_registry.register(EchoNode)
except KeyError:
    pass


@pytest.mark.asyncio
async def test_engine_runs_if_else_branch_from_v2_metadata():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "if_1",
                "type": "if_else",
                "config": {
                    "branches": [
                        {"id": "true", "condition": None, "outputField": "echo_true.text"}
                    ]
                },
            },
            {
                "id": "echo_true",
                "type": "echo_v2",
                "parentId": "if_1",
                "branchId": "true",
                "config": {"output_key": "text", "output_value": "yes"},
            },
            {"id": "end_1", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "if_1"},
            {"source": "if_1", "target": "end_1"},
        ],
    }

    state = await ExecutionEngine().run(graph, user_input="go")

    assert state["node_outputs"]["if_1"]["branchTaken"] == "true"
    assert state["node_outputs"]["if_1"]["result"] == "yes"


@pytest.mark.asyncio
async def test_engine_runs_iteration_from_v2_metadata():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": [{"name": "items", "type": "text"}]}},
            {
                "id": "iter_1",
                "type": "iteration",
                "config": {
                    "inputRef": "{{start_1.items}}",
                    "itemVar": "item",
                    "outputField": "echo_body.text",
                    "maxConcurrency": 1,
                },
            },
            {
                "id": "echo_body",
                "type": "echo_v2",
                "parentId": "iter_1",
                "config": {"output_key": "text", "output_value": "item-output"},
            },
            {"id": "end_1", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "iter_1"},
            {"source": "iter_1", "target": "end_1"},
        ],
    }

    state = await ExecutionEngine().run(graph, inputs={"items": ["a", "b"]})

    assert state["node_outputs"]["iter_1"]["results"] == ["item-output", "item-output"]
```

- [ ] **Step 2: Run engine v2 tests and verify red**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_engine_v2_contract.py -v
```

Expected: FAIL because engine branch and iteration logic still reads `node_def.get("data")`.

- [ ] **Step 3: Add compiled metadata accessors**

In `backend/core/compiler.py`, extend `CompiledWorkflow`:

```python
    node_configs: dict[str, dict]
    parent_by_node: dict[str, str | None]
    branch_by_node: dict[str, str | None]
```

Populate these maps in `compile()`:

```python
        node_configs = {node_id: get_node_config(node_def) for node_id, node_def in node_map.items()}
        parent_by_node = {node_id: self._get_parent_id(node_def) for node_id, node_def in node_map.items()}
        branch_by_node = {
            node_id: node_def.get("branchId") if isinstance(node_def.get("branchId"), str) else None
            for node_id, node_def in node_map.items()
        }
```

Pass them into `CompiledWorkflow(...)`.

- [ ] **Step 4: Update engine to use compiled config maps**

In `backend/core/engine.py`, replace:

```python
branches = (node_def.get("data") or {}).get("branches", [])
```

with:

```python
branches = compiled.node_configs.get(if_else_id, {}).get("branches", [])
```

Replace branch child filtering:

```python
if compiled.branch_by_node.get(cid) == branch_id
```

Replace iteration data lookup:

```python
data = compiled.node_configs.get(iter_id, {})
```

Keep `compiled.node_defs[node_id]["type"]` until a later task because type lookup is stable.

- [ ] **Step 5: Run engine tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_engine_v2_contract.py backend/tests/test_engine_if_else.py backend/tests/test_engine_iteration.py backend/tests/test_engine_iteration_concurrent.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add backend/core/compiler.py backend/core/engine.py backend/tests/test_engine_v2_contract.py backend/tests/test_engine_if_else.py backend/tests/test_engine_iteration.py backend/tests/test_engine_iteration_concurrent.py
git commit -m "refactor: execute workflows from compiled graph metadata"
```

Expected: commit succeeds.

---

### Task 6: Add RunContext For Provider Lookup And Event Emission

**Files:**
- Create: `backend/core/run_context.py`
- Modify: `backend/core/engine.py`
- Modify: `backend/nodes/base.py`
- Modify: `backend/nodes/llm_node.py`
- Modify: `backend/nodes/tts_node.py`
- Modify: `backend/nodes/agent_node.py`
- Modify: `backend/nodes/rag_node.py`
- Modify: `backend/tests/test_nodes.py`
- Create: `backend/tests/test_run_context.py`

- [ ] **Step 1: Write failing RunContext tests**

Create `backend/tests/test_run_context.py`:

```python
import pytest

from backend.core.run_context import RunContext
from backend.models.provider import Provider


def test_run_context_reuses_built_llm_provider(db, monkeypatch):
    row = Provider(
        id=11,
        type="openai",
        name="test",
        api_key_encrypted="enc",
        enabled=True,
        category="llm",
    )
    db.add(row)
    db.commit()

    calls = []

    class BuiltProvider:
        pass

    def fake_build_provider(provider_row):
        calls.append(provider_row.id)
        return BuiltProvider()

    monkeypatch.setattr("backend.core.run_context.build_provider", fake_build_provider)

    ctx = RunContext(db_factory=lambda: db)

    first = ctx.get_llm_provider(11)
    second = ctx.get_llm_provider(11)

    assert first is second
    assert calls == [11]


@pytest.mark.asyncio
async def test_run_context_emit_forwards_event():
    events = []

    async def on_event(event):
        events.append(event)

    ctx = RunContext(on_event=on_event)

    await ctx.emit({"type": "workflow_start"})

    assert events == [{"type": "workflow_start"}]
```

- [ ] **Step 2: Run RunContext tests and verify red**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_run_context.py -v
```

Expected: FAIL because `backend/core/run_context.py` does not exist yet.

- [ ] **Step 3: Implement RunContext**

Create `backend/core/run_context.py`:

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.provider import Provider
from backend.providers import build_provider
from backend.tts import build_tts_provider

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class RunContext:
    db_factory: Callable[[], Session] = SessionLocal
    on_event: EventCallback | None = None
    cancel_event: asyncio.Event | None = None
    run_id: str | None = None
    _llm_providers: dict[int, Any] = field(default_factory=dict)
    _tts_providers: dict[int, Any] = field(default_factory=dict)

    async def emit(self, event: dict[str, Any]) -> None:
        if self.on_event is not None:
            await self.on_event(event)

    def _load_provider_row(self, provider_id: int, expected_category: str | None = None) -> Provider:
        db = self.db_factory()
        should_close = db is not None and db.__class__.__name__ != "Session"
        try:
            row = db.query(Provider).filter(Provider.id == provider_id).first()
            if not row:
                raise ValueError(f"Provider not found: {provider_id}")
            if not row.enabled:
                raise ValueError(f"Provider is disabled: {provider_id}")
            if expected_category and row.category != expected_category:
                raise ValueError(
                    f"Provider {provider_id} has category {row.category}, expected {expected_category}"
                )
            return row
        finally:
            if should_close:
                db.close()

    def get_llm_provider(self, provider_id: int) -> Any:
        if provider_id not in self._llm_providers:
            self._llm_providers[provider_id] = build_provider(
                self._load_provider_row(provider_id, expected_category="llm")
            )
        return self._llm_providers[provider_id]

    def get_tts_provider(self, provider_id: int) -> Any:
        if provider_id not in self._tts_providers:
            self._tts_providers[provider_id] = build_tts_provider(
                self._load_provider_row(provider_id, expected_category="tts")
            )
        return self._tts_providers[provider_id]
```

If the `should_close` heuristic is awkward in implementation, replace it with an explicit `owns_db_session: bool = True` field and pass `owns_db_session=False` from tests that inject a fixture session.

- [ ] **Step 4: Pass RunContext from ExecutionEngine**

In `backend/core/engine.py`, import `RunContext` and create it at the start of `run()`:

```python
        run_context = RunContext(on_event=on_event)
```

Pass it through `_run_scope()`, `_run_single()`, `_run_if_else()`, `_run_iteration()`, and `_run_iter_item()`.

Change node execution:

```python
state = await node.execute(
    state,
    user_input=self._user_input,
    on_event=on_event,
    run_context=run_context,
)
```

- [ ] **Step 5: Update nodes to prefer RunContext and keep backward compatibility**

In `backend/nodes/llm_node.py`, change `_get_chat_model()` to accept an optional context:

```python
    def _get_chat_model(self, run_context=None):
        provider_id = self.config.get("provider_id")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)
        streaming = self.config.get("streaming", True)

        if not provider_id:
            raise ValueError("provider_id is required for LLM node")

        if run_context is not None:
            provider = run_context.get_llm_provider(int(provider_id))
        else:
            provider = self._get_provider_legacy(provider_id)

        return provider.create_chat_model(
            model=model_name,
            temperature=temperature,
            streaming=streaming,
        )
```

Extract the existing DB lookup into `_get_provider_legacy()` so current node unit tests can still instantiate nodes directly.

In `execute()`, call:

```python
chat_model = self._get_chat_model(kwargs.get("run_context"))
```

Apply the same pattern to:

- `backend/nodes/tts_node.py` with `run_context.get_tts_provider(int(provider_id))`.
- `backend/nodes/agent_node.py` with `run_context.get_llm_provider(int(provider_id))`.
- `backend/nodes/rag_node.py` by accepting the argument and not using it yet.

- [ ] **Step 6: Run node and context tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_run_context.py backend/tests/test_nodes.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit this task**

Run:

```bash
git add backend/core/run_context.py backend/core/engine.py backend/nodes/base.py backend/nodes/llm_node.py backend/nodes/tts_node.py backend/nodes/agent_node.py backend/nodes/rag_node.py backend/tests/test_run_context.py backend/tests/test_nodes.py
git commit -m "refactor: introduce workflow run context"
```

Expected: commit succeeds.

---

### Task 7: Typed SSE Event Factories And Scope Metadata

**Files:**
- Create: `backend/core/events.py`
- Modify: `backend/core/engine.py`
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/stores/debugStore.ts`
- Modify: `frontend/src/hooks/useSSE.ts`
- Create: `backend/tests/test_events.py`
- Modify: `backend/tests/test_engine_v2_contract.py`

- [ ] **Step 1: Write failing event factory tests**

Create `backend/tests/test_events.py`:

```python
from backend.core import events


def test_node_start_event_has_stable_shape():
    event = events.node_start(
        node_id="llm_1",
        node_type="llm",
        scope_id="iter_1",
        iteration_index=2,
    )

    assert event == {
        "type": "node_start",
        "node_id": "llm_1",
        "node_type": "llm",
        "status": "running",
        "scope_id": "iter_1",
        "iteration_index": 2,
    }


def test_workflow_end_completed_event_has_outputs():
    event = events.workflow_end(
        status="completed",
        duration=1.2,
        answer="done",
        outputs={"answer": "done"},
    )

    assert event["type"] == "workflow_end"
    assert event["status"] == "completed"
    assert event["outputs"] == {"answer": "done"}
```

- [ ] **Step 2: Run event tests and verify red**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_events.py -v
```

Expected: FAIL because `backend/core/events.py` does not exist.

- [ ] **Step 3: Implement backend event factories**

Create `backend/core/events.py`:

```python
from __future__ import annotations

from typing import Any, Literal


def _with_scope(
    event: dict[str, Any],
    *,
    scope_id: str | None = None,
    iteration_index: int | None = None,
) -> dict[str, Any]:
    if scope_id is not None:
        event["scope_id"] = scope_id
    if iteration_index is not None:
        event["iteration_index"] = iteration_index
    return event


def workflow_start() -> dict[str, Any]:
    return {"type": "workflow_start"}


def node_start(
    *,
    node_id: str,
    node_type: str,
    scope_id: str | None = None,
    iteration_index: int | None = None,
) -> dict[str, Any]:
    return _with_scope(
        {
            "type": "node_start",
            "node_id": node_id,
            "node_type": node_type,
            "status": "running",
        },
        scope_id=scope_id,
        iteration_index=iteration_index,
    )


def node_end(
    *,
    node_id: str,
    node_type: str,
    status: Literal["completed", "failed"],
    duration: float | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    scope_id: str | None = None,
    iteration_index: int | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "node_end",
        "node_id": node_id,
        "node_type": node_type,
        "status": status,
    }
    if duration is not None:
        event["duration"] = duration
    if output is not None:
        event["output"] = output
    if error is not None:
        event["error"] = error
    return _with_scope(event, scope_id=scope_id, iteration_index=iteration_index)


def workflow_end(
    *,
    status: Literal["completed", "failed", "cancelled"],
    duration: float,
    answer: str = "",
    outputs: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "workflow_end",
        "status": status,
        "duration": duration,
        "answer": answer,
        "outputs": outputs or {},
    }
    if message:
        event["message"] = message
    return event
```

Add factories for existing control-flow events as engine code is migrated:

```python
def branch_taken(*, node_id: str, branch_id: str | None, condition_result: bool) -> dict[str, Any]:
    return {
        "type": "branch_taken",
        "node_id": node_id,
        "branch_id": branch_id,
        "condition_result": condition_result,
    }
```

- [ ] **Step 4: Migrate engine event construction**

In `backend/core/engine.py`, import:

```python
from backend.core import events
```

Replace inline workflow and node event dicts with `events.workflow_start()`, `events.node_start(...)`, `events.node_end(...)`, and `events.workflow_end(...)`.

Use `parent_id` as `scope_id` when executing child nodes:

```python
await self._run_single(
    node,
    node_id,
    node_type,
    state,
    on_event,
    run_context,
    scope_id=parent_id,
    iteration_index=iteration_index,
)
```

- [ ] **Step 5: Align frontend event types**

In `frontend/src/types/workflow.ts`, add optional fields to `SSEEvent`:

```ts
  scope_id?: string
```

Keep `iteration_index?: number` because it already exists.

In `frontend/src/stores/debugStore.ts`, update `compositeKey()` so scope participates in identity:

```ts
function compositeKey(nodeId: string, iterationIndex?: number | null, scopeId?: string | null): string {
  const scope = scopeId ?? 'root'
  const iter = iterationIndex != null ? iterationIndex : 0
  return `${scope}:${nodeId}#${iter}`
}
```

Update each call site from:

```ts
compositeKey(event.node_id, event.iteration_index)
```

to:

```ts
compositeKey(event.node_id, event.iteration_index, event.scope_id)
```

- [ ] **Step 6: Run backend event and engine tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_events.py backend/tests/test_engine.py backend/tests/test_engine_v2_contract.py backend/tests/test_engine_if_else.py backend/tests/test_engine_iteration.py -v
```

Expected: PASS.

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit this task**

Run:

```bash
git add backend/core/events.py backend/core/engine.py backend/tests/test_events.py backend/tests/test_engine_v2_contract.py frontend/src/types/workflow.ts frontend/src/stores/debugStore.ts frontend/src/hooks/useSSE.ts
git commit -m "refactor: type workflow execution events"
```

Expected: commit succeeds.

---

### Task 8: Frontend Store Uses Graph Adapter For Load And Save

**Files:**
- Modify: `frontend/src/graph/contract.ts`
- Modify: `frontend/src/graph/adapters.ts`
- Modify: `frontend/src/graph/roundtrip.test.ts`
- Modify: `frontend/src/stores/workflowStore.ts`
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/package.json` only if a test runner is added.

- [ ] **Step 1: Write frontend graph store test or expand adapter test**

If Vitest is already installed in `node_modules`, add this to `frontend/src/graph/roundtrip.test.ts`:

```ts
it('saves React Flow state as canonical v2 graph', () => {
  const original = loadGraph({
    nodes: [
      { id: 'start_1', type: 'start', data: { inputs: [] } },
      {
        id: 'llm_true',
        type: 'llm',
        position: { x: 100, y: 100 },
        data: { parentId: 'if_1', branchId: 'true', provider_id: 1 },
      },
    ],
    edges: [],
  })

  const { nodes, edges } = graphToReactFlow(original)
  const saved = reactFlowToGraph(nodes, edges)

  expect(saved.version).toBe(2)
  expect(saved.nodes[1]).toMatchObject({
    id: 'llm_true',
    parentId: 'if_1',
    branchId: 'true',
    config: { provider_id: 1 },
  })
  expect('data' in saved.nodes[1]).toBe(false)
})
```

If Vitest is not installed, add a test script only after adding `vitest` to dev dependencies:

```json
"test": "vitest run"
```

- [ ] **Step 2: Run frontend test/build and verify current failure**

If Vitest is available:

```bash
cd frontend && npm run test -- --run src/graph/roundtrip.test.ts
```

Expected: FAIL if current adapters do not preserve the newly asserted shape.

If Vitest is not available and dependency installation is not approved, run:

```bash
cd frontend && npm run build
```

Expected: build may pass; continue with adapter integration and use backend tests as the main red-green guard.

- [ ] **Step 3: Update WorkflowGraph types**

In `frontend/src/types/workflow.ts`, import or mirror v2:

```ts
export type {
  WorkflowGraphV2 as WorkflowGraph,
  WorkflowNodeV2 as WorkflowGraphNode,
  WorkflowEdgeV2 as WorkflowGraphEdge,
} from '../graph/contract'
```

Keep execution event types in this file unless a separate `types/events.ts` is introduced.

- [ ] **Step 4: Delegate store graph loading/saving to adapters**

In `frontend/src/stores/workflowStore.ts`, import:

```ts
import { graphToReactFlow, reactFlowToGraph } from '../graph/adapters'
import { loadGraph } from '../graph/contract'
```

Update `setWorkflow()`:

```ts
  setWorkflow: (id, name, graphNodes, edges) => {
    const graph = loadGraph({ nodes: graphNodes, edges })
    const converted = graphToReactFlow(graph)
    set({
      workflowId: id,
      workflowName: name,
      nodes: normalizeGraphNodes(converted.nodes),
      edges: normalizeGraphEdges(converted.edges),
      isDraft: false,
    })
  },
```

Update `setDraftSnapshot()` and `setDraftWorkflow()` the same way.

Update `toGraphJSON()`:

```ts
  toGraphJSON: () => {
    const { nodes, edges } = get()
    return reactFlowToGraph(nodes, edges)
  },
```

After this change, delete or shrink custom v1 serialization code inside `toGraphJSON()`.

- [ ] **Step 5: Ensure default graph creation returns v2**

In `frontend/src/App.tsx`, update `createDefaultGraph()` so it returns:

```ts
return {
  version: 2,
  nodes: [
    {
      id: 'start_1',
      type: 'start',
      position: defaultStartNode.position,
      label: defaultStartNode.data.label,
      locked: true,
      config: defaultStartNode.data.config,
    },
    {
      id: 'end_1',
      type: 'end',
      position: defaultEndNode.position,
      label: defaultEndNode.data.label,
      locked: true,
      config: defaultEndNode.data.config,
    },
  ],
  edges: [],
}
```

- [ ] **Step 6: Run frontend verification**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

If Vitest was configured, also run:

```bash
cd frontend && npm run test -- --run src/graph/roundtrip.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit this task**

Run:

```bash
git add frontend/src/graph/contract.ts frontend/src/graph/adapters.ts frontend/src/graph/roundtrip.test.ts frontend/src/stores/workflowStore.ts frontend/src/types/workflow.ts frontend/src/services/api.ts frontend/src/App.tsx frontend/package.json
git commit -m "refactor: save frontend workflows as graph v2"
```

Expected: commit succeeds. Do not stage `frontend/package.json` if no script or dependency changed.

---

### Task 9: End-To-End Contract Verification

**Files:**
- Modify: `backend/tests/test_harness_to_engine_e2e.py`
- Modify: `backend/tests/test_workflows_api.py`
- Modify: `frontend/src/graph/roundtrip.test.ts`

- [ ] **Step 1: Add an E2E guard from Harness to Engine with canonical v2**

In `backend/tests/test_harness_to_engine_e2e.py`, after applying a Harness session, assert:

```python
assert graph_json["version"] == 2
assert all("config" in node for node in graph_json["nodes"])
assert all("data" not in node for node in graph_json["nodes"])
```

In the if-else E2E test, assert branch children use top-level fields:

```python
true_child = next(n for n in graph_json["nodes"] if n["id"] == "llm_true")
assert true_child["parentId"] == "if_1"
assert true_child["branchId"] == "true"
assert true_child["config"]["provider_id"] == 1
```

- [ ] **Step 2: Add API create-update-run contract coverage**

In `backend/tests/test_workflows_api.py`, add a test that creates a v1 graph, fetches it, updates it, and verifies every response is v2:

```python
def test_workflow_api_roundtrips_graph_v2(client):
    graph = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [{"source": "start_1", "target": "end_1"}],
    }

    created = client.post("/api/workflows", json={"name": "roundtrip", "graph": graph}).json()
    fetched = client.get(f"/api/workflows/{created['id']}").json()
    updated = client.put(f"/api/workflows/{created['id']}", json={"graph": fetched["graph"]}).json()

    assert created["graph"]["version"] == 2
    assert fetched["graph"]["version"] == 2
    assert updated["graph"]["version"] == 2
```

- [ ] **Step 3: Run backend contract suite**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_graph_schema.py backend/tests/test_compiler.py backend/tests/test_compiler_m1.py backend/tests/test_harness_v2.py backend/tests/test_harness_to_engine_e2e.py backend/tests/test_workflows_api.py backend/tests/test_engine_v2_contract.py -v
```

Expected: PASS.

- [ ] **Step 4: Run full backend tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/
```

Expected: PASS. Existing deprecation warnings from third-party packages are acceptable if no tests fail.

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit contract verification**

Run:

```bash
git add backend/tests/test_harness_to_engine_e2e.py backend/tests/test_workflows_api.py frontend/src/graph/roundtrip.test.ts
git commit -m "test: cover graph contract across harness api and engine"
```

Expected: commit succeeds.

---

### Task 10: Documentation And Cleanup

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-04-19-graph-contract-architecture-reset-design.md`
- Optional modify: `frontend/README.md`

- [ ] **Step 1: Update architecture docs**

In `CLAUDE.md`, update the backend architecture section so it says:

```markdown
**Execution pipeline:** Workflow JSON is loaded through `backend/core/graph_schema.py` and normalized to WorkflowGraph v2. `GraphCompiler` validates the canonical graph and builds a `CompiledWorkflow` with execution order, node configs, parent scopes, and branch metadata. `ExecutionEngine` consumes the compiled workflow, passes a `RunContext` to nodes, and emits typed SSE events.
```

Add:

```markdown
**Graph contract:** New saves use WorkflowGraph v2: node structural fields (`parentId`, `branchId`) are top-level, node business fields live under `config`, and `sourceHandle` is UI metadata only. Legacy v1 graphs with `data` are accepted at boundaries and normalized before validation or execution.
```

- [ ] **Step 2: Update the graph architecture spec status**

In `docs/superpowers/specs/2026-04-19-graph-contract-architecture-reset-design.md`, change the status from recommendation to implemented plan reference:

```markdown
> **状态：** 已转为执行计划
> **执行计划：** `docs/superpowers/plans/2026-04-19-graph-contract-runtime-context-refactor.md`
```

- [ ] **Step 3: Remove stale imports and dead comments**

Search:

```bash
rg -n "StateGraph|LangGraph CompiledGraph|data\\.parentId|data\\.branchId|data\\.provider_id|node_def\\.get\\(\"data\"\\)" backend frontend/src CLAUDE.md docs/superpowers
```

Expected: only compatibility tests, migration comments, or legacy-normalization code should remain. Remove unused imports such as `StateGraph` from `backend/core/compiler.py` if no code uses them.

- [ ] **Step 4: Run final verification**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/
```

Expected: PASS.

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit docs and cleanup**

Run:

```bash
git add CLAUDE.md docs/superpowers/specs/2026-04-19-graph-contract-architecture-reset-design.md backend/core/compiler.py
git commit -m "docs: describe canonical graph runtime architecture"
```

Expected: commit succeeds. Do not stage `backend/core/compiler.py` if it did not change in this cleanup task.

---

## Final Verification Checklist

Run the full backend test suite:

```bash
backend/.venv/bin/python -m pytest backend/tests/
```

Expected: all tests pass.

Run the frontend build:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite build pass.

Run a graph contract grep:

```bash
rg -n "node_def\\.get\\(\"data\"\\)|data\\.parentId|data\\.branchId|data\\.provider_id" backend frontend/src
```

Expected: no runtime code relies on those legacy paths. Matches inside legacy upgrade helpers or explicit compatibility tests are acceptable.

Run git status:

```bash
git status --short --branch
```

Expected: clean working tree except for intentional user changes that were present before execution.

---

## Self-Review

**Spec coverage:** This plan covers graph v2 as a first-class contract, frontend adapter usage, backend schema normalization, Harness as a graph producer, compiler/engine separation, runtime provider access, and scoped event metadata.

**Placeholder scan:** No step requires an unspecified implementation. Each task names concrete files, tests, commands, expected outcomes, and the minimal production code shape.

**Type consistency:** The plan consistently uses `version`, `nodes`, `edges`, `config`, `parentId`, `branchId`, `sourceHandle`, `CompiledWorkflow`, `RunContext`, and `SSEEvent` across backend and frontend tasks.

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-04-19-graph-contract-runtime-context-refactor.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh agent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session using executing-plans, batching with checkpoints.
