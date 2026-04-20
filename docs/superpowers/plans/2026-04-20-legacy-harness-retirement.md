# Legacy Harness Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy `backend/harness/` implementation without losing graph validation, engine parity coverage, or the current `/api/harness` product behavior.

**Architecture:** First extract the last still-live shared primitive from `backend/harness/` into `backend/pi_harness/` so the new runtime is self-contained. Then replace or delete tests that only exist to cover the retired LeadAgent stack. Only after there are no runtime or test imports of `backend.harness` should we delete the legacy directory. Because the current worktree contains user edits inside `backend/harness/validators.py` and `backend/harness/skills/*.md`, the delete step is guarded by an explicit checkpoint.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, LangGraph/LangChain, pytest, React/Vite, ripgrep, git

---

## File Map

**Create**
- `backend/pi_harness/schemas.py`
- `backend/pi_harness/validators.py`
- `backend/tests/test_pi_harness_validators.py`
- `backend/tests/test_pi_harness_to_engine_e2e.py`

**Modify**
- `backend/pi_harness/tools/validate.py`
- `backend/pi_harness/tools/finalize.py`
- `CLAUDE.md`
- `docs/PI_HARNESS_MIGRATION_PLAN.md`

**Delete**
- `backend/tests/test_harness_v2.py`
- `backend/tests/test_harness_to_engine_e2e.py`
- `backend/tests/test_harness_decision_compat.py`
- `backend/tests/test_harness_llm_client.py`
- `backend/harness/` (only after the dirty-file checkpoint passes)

**Do Not Touch**
- `backend/api/providers.py`
- `backend/core/crypto.py`
- `backend/main.py`
- `backend/tests/conftest.py`
- `backend/tests/test_crypto.py`
- `backend/tests/test_providers_api.py`
- `frontend/src/pages/Providers.tsx`
- `docs/superpowers/specs/2026-04-20-piagent-harness-v3.md`

### Task 1: Extract Graph Validation Into `pi_harness`

**Files:**
- Create: `backend/pi_harness/schemas.py`
- Create: `backend/pi_harness/validators.py`
- Create: `backend/tests/test_pi_harness_validators.py`
- Modify: `backend/pi_harness/tools/validate.py`
- Modify: `backend/pi_harness/tools/finalize.py`

- [ ] **Step 1: Write the failing validator ownership tests**

```python
# backend/tests/test_pi_harness_validators.py
from backend.pi_harness.schemas import Finding
from backend.pi_harness.validators import validate_graph


def test_validate_graph_returns_pi_harness_findings():
    findings = validate_graph({"version": 2, "nodes": [], "edges": []})

    assert findings
    assert all(isinstance(item, Finding) for item in findings)
    assert {item.code for item in findings} >= {"missing_start", "missing_end"}


def test_validate_graph_matches_legacy_output_for_simple_linear_graph():
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start", "type": "start", "config": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1}},
            {"id": "end", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"id": "start-llm_1", "source": "start", "target": "llm_1"},
            {"id": "llm_1-end", "source": "llm_1", "target": "end"},
        ],
    }

    new_findings = [item.model_dump(mode="json") for item in validate_graph(graph)]
    from backend.harness.validators import validate_graph as legacy_validate_graph
    old_findings = [item.model_dump(mode="json") for item in legacy_validate_graph(graph)]

    assert new_findings == old_findings
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_validators.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.pi_harness.validators'` or `No module named 'backend.pi_harness.schemas'`

- [ ] **Step 3: Add the `Finding` model to `pi_harness`**

```python
# backend/pi_harness/schemas.py
from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = Field(default=None)
```

- [ ] **Step 4: Copy the validator implementation into `pi_harness`**

```python
# backend/pi_harness/validators.py
from backend.core import graph_rules
from backend.core.graph_schema import dump_graph, get_node_config, load_graph
from backend.core.template import REF_RE
from backend.pi_harness.schemas import Finding


_STATIC_NODE_FIELDS = {
    "llm": ["text"],
    "rag": ["context", "documents"],
    "tts": ["audio_url", "duration"],
    "agent": ["text", "steps"],
}
```

Implementation note:
- Copy `_collect_available_refs`, `_format_refs_hint`, and the full `validate_graph()` body from `backend/harness/validators.py`
- Change only the `Finding` import so parity stays exact on the first pass

- [ ] **Step 5: Repoint the tool wrappers to the new validator**

```python
# backend/pi_harness/tools/validate.py
from backend.pi_harness.validators import validate_graph


# backend/pi_harness/tools/finalize.py
from backend.pi_harness.validators import validate_graph
```

- [ ] **Step 6: Run the validator-focused regression suite**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_validators.py backend/tests/test_pi_harness_draft.py backend/tests/test_pi_harness_api.py -q`

Expected: PASS

- [ ] **Step 7: Commit the extraction checkpoint**

```bash
git add backend/pi_harness/schemas.py backend/pi_harness/validators.py backend/pi_harness/tools/validate.py backend/pi_harness/tools/finalize.py backend/tests/test_pi_harness_validators.py
git commit -m "refactor: move graph validation into pi_harness"
```

### Task 2: Port Engine Parity Coverage Off The Legacy Session

**Files:**
- Create: `backend/tests/test_pi_harness_to_engine_e2e.py`
- Delete: `backend/tests/test_harness_to_engine_e2e.py`

- [ ] **Step 1: Write the new end-to-end regression tests against `pi_harness`**

```python
# backend/tests/test_pi_harness_to_engine_e2e.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.engine import ExecutionEngine
from backend.pi_harness.session import create_harness_session


async def _apply_ready_graph(db, graph: dict) -> tuple[str, dict]:
    session = create_harness_session(db, goal="engine parity")
    session.draft.load_snapshot(graph)
    session._status = "ready"
    result = await session.apply()
    return result["workflow_id"], result["graph"]


@pytest.mark.asyncio
async def test_pi_harness_to_engine_linear_workflow(db):
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": []}},
            {"id": "llm_1", "type": "llm", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"id": "start_1-llm_1", "source": "start_1", "target": "llm_1"},
            {"id": "llm_1-end_1", "source": "llm_1", "target": "end_1"},
        ],
    }

    _, persisted_graph = await _apply_ready_graph(db, graph)

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_llm:
        model = AsyncMock()
        response = MagicMock()
        response.content = "Hello from mocked LLM"
        model.ainvoke.return_value = response
        mock_llm.return_value = model

        engine = ExecutionEngine()
        final_state = await engine.run(persisted_graph, user_input="hi", on_event=lambda _: None)

    assert final_state["node_outputs"]["llm_1"]["text"] == "Hello from mocked LLM"
```

- [ ] **Step 2: Add the branching parity case**

```python
@pytest.mark.asyncio
async def test_pi_harness_to_engine_if_else_subgraph(db):
    graph = {
        "version": 2,
        "nodes": [
            {"id": "start_1", "type": "start", "config": {"inputs": []}},
            {
                "id": "if_1",
                "type": "if_else",
                "config": {
                    "branches": [
                        {"id": "true", "condition": {"left": "{{start_1.input}}", "op": "eq", "right": "test"}, "outputField": "llm_true.text"},
                        {"id": "false", "condition": None, "outputField": "llm_false.text"},
                    ]
                },
            },
            {"id": "llm_true", "type": "llm", "parentId": "if_1", "branchId": "true", "config": {"provider_id": 1}},
            {"id": "llm_false", "type": "llm", "parentId": "if_1", "branchId": "false", "config": {"provider_id": 1}},
            {"id": "end_1", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"id": "start_1-if_1", "source": "start_1", "target": "if_1"},
            {"id": "if_1-end_1", "source": "if_1", "target": "end_1"},
        ],
    }

    _, persisted_graph = await _apply_ready_graph(db, graph)
    engine = ExecutionEngine()
    final_state = await engine.run(persisted_graph, user_input="test", on_event=lambda _: None)

    assert "node_outputs" in final_state
```

- [ ] **Step 3: Run the new parity tests**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_to_engine_e2e.py -q`

Expected: PASS. If either test fails, fix the graph fixture or the `session.apply()` setup before deleting the legacy file.

- [ ] **Step 4: Delete the legacy engine-parity test file**

```diff
*** Delete File: backend/tests/test_harness_to_engine_e2e.py
```

- [ ] **Step 5: Re-run the parity suite after deletion**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_to_engine_e2e.py backend/tests/test_pi_harness_api.py backend/tests/test_pi_harness_runtime.py -q`

Expected: PASS

- [ ] **Step 6: Commit the parity migration**

```bash
git add backend/tests/test_pi_harness_to_engine_e2e.py backend/tests/test_harness_to_engine_e2e.py
git commit -m "test: move engine parity coverage to pi_harness"
```

### Task 3: Retire Legacy-Only Tests And Replace The Remaining Coverage

**Files:**
- Delete: `backend/tests/test_harness_v2.py`
- Delete: `backend/tests/test_harness_decision_compat.py`
- Delete: `backend/tests/test_harness_llm_client.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Confirm replacement coverage exists before deleting old tests**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_runtime.py backend/tests/test_pi_harness_draft.py backend/tests/test_pi_harness_context_tools.py backend/tests/test_pi_harness_api.py backend/tests/test_pi_harness_validators.py backend/tests/test_pi_harness_to_engine_e2e.py -q`

Expected: PASS

Replacement map:
- `test_harness_v2.py` builder + draft coverage → `test_pi_harness_draft.py`
- `test_harness_v2.py` API/session coverage → `test_pi_harness_api.py`
- `test_harness_v2.py` validator coverage → `test_pi_harness_validators.py`
- `test_harness_to_engine_e2e.py` → `test_pi_harness_to_engine_e2e.py`
- `test_harness_llm_client.py` provider resolution coverage → `test_pi_harness_runtime.py::test_db_model_resolver_builds_chat_model_from_provider_row`
- `test_harness_decision_compat.py` legacy `LeadAgent` payload normalization → intentionally dropped because the LeadAgent path is no longer a supported runtime surface

- [ ] **Step 2: Delete the obsolete legacy-only test files**

```diff
*** Delete File: backend/tests/test_harness_v2.py
*** Delete File: backend/tests/test_harness_decision_compat.py
*** Delete File: backend/tests/test_harness_llm_client.py
```

- [ ] **Step 3: Update the architecture note in `CLAUDE.md`**

```markdown
**Harness mode:** `backend/pi_harness/` implements the natural-language workflow builder. The `AgentPanel` collects a user goal → `/api/harness/sessions` creates a `pi_harness` session → the SSE stream drives the vendored mini-harness ReAct runtime → tools and skills gather facts → `WorkflowGraphDraft` emits graph updates → `finalize_draft` validates the draft → `apply` persists the workflow. `/api/pi_harness/*` remains as a compatibility alias during migration.
```

- [ ] **Step 4: Run the reduced suite with the legacy-only tests gone**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_runtime.py backend/tests/test_pi_harness_draft.py backend/tests/test_pi_harness_context_tools.py backend/tests/test_pi_harness_validators.py backend/tests/test_pi_harness_to_engine_e2e.py backend/tests/test_pi_harness_api.py -q`

Expected: PASS

- [ ] **Step 5: Commit the test and doc retirement**

```bash
git add CLAUDE.md backend/tests/test_harness_v2.py backend/tests/test_harness_decision_compat.py backend/tests/test_harness_llm_client.py
git commit -m "chore: retire legacy harness test surface"
```

### Task 4: Resolve Dirty Legacy Files Before Deletion

**Files:**
- Modify: `backend/pi_harness/skills/agent_node/SKILL.md` (only if porting content)
- Modify: `backend/pi_harness/skills/io_contract/SKILL.md` (only if porting content)
- Modify: `backend/pi_harness/skills/llm_basic/SKILL.md` (only if porting content)
- Modify: `backend/pi_harness/skills/rag_qa/SKILL.md` (only if porting content)
- Modify: `backend/pi_harness/skills/simple_pipeline/SKILL.md` (only if porting content)
- Modify: `backend/pi_harness/skills/tts_podcast/SKILL.md` (only if porting content)
- Modify: `backend/pi_harness/validators.py` (only if `backend/harness/validators.py` contains user changes that must survive)

- [ ] **Step 1: Inspect the legacy dirty state**

Run: `git status --short backend/harness backend/harness/skills backend/harness/validators.py`

Expected: See the current user-owned modifications, not a clean tree

- [ ] **Step 2: Capture the actual diff that blocks deletion**

Run: `git diff -- backend/harness/validators.py backend/harness/skills/io_contract.md backend/harness/skills/llm_basic.md backend/harness/skills/rag_qa.md backend/harness/skills/simple_pipeline.md backend/harness/skills/tts_podcast.md`

Expected: Non-empty diff output

- [ ] **Step 3: Hard checkpoint — ask the user how to handle those edits**

Use this exact question:

```text
`backend/harness/validators.py` and `backend/harness/skills/*.md` still contain uncommitted edits in this worktree. Do you want me to port those changes into `backend/pi_harness/` before deleting the legacy directory, or should we leave the old directory in place for now?`
```

- [ ] **Step 4: If the user says “port them”, copy the deltas into `pi_harness` equivalents**

Run these exact commands in order:

```bash
git diff -- backend/harness/validators.py > /tmp/legacy-validator.diff
git diff -- backend/harness/skills/io_contract.md > /tmp/io-contract.diff
git diff -- backend/harness/skills/llm_basic.md > /tmp/llm-basic.diff
git diff -- backend/harness/skills/rag_qa.md > /tmp/rag-qa.diff
git diff -- backend/harness/skills/simple_pipeline.md > /tmp/simple-pipeline.diff
git diff -- backend/harness/skills/tts_podcast.md > /tmp/tts-podcast.diff
```

Then mirror each diff into the matching `backend/pi_harness/validators.py` or `backend/pi_harness/skills/*/SKILL.md` file by hand with `apply_patch`, preserving the same semantic change but leaving the legacy file untouched until the delete step.

- [ ] **Step 5: If the user says “do not port”, stop here and do not delete `backend/harness/`**

Run: `git status --short backend/harness`

Expected: Still dirty. No `git rm`, no `rm -rf`, no revert.

### Task 5: Delete `backend/harness/` And Verify The Repo Is Clean Of Runtime Imports

**Files:**
- Delete: `backend/harness/`
- Modify: `docs/PI_HARNESS_MIGRATION_PLAN.md`

- [ ] **Step 1: Verify the dirty-file checkpoint is resolved**

Run: `git status --short backend/harness`

Expected: No output

- [ ] **Step 2: Delete the legacy implementation**

```diff
*** Delete File: backend/harness/__init__.py
*** Delete File: backend/harness/actions.py
*** Delete File: backend/harness/builder.py
*** Delete File: backend/harness/lead_agent.py
*** Delete File: backend/harness/llm_client.py
*** Delete File: backend/harness/memory.py
*** Delete File: backend/harness/preferences.py
*** Delete File: backend/harness/prompts.py
*** Delete File: backend/harness/schemas.py
*** Delete File: backend/harness/session.py
*** Delete File: backend/harness/tools/__init__.py
*** Delete File: backend/harness/tools/base.py
*** Delete File: backend/harness/tools/list_knowledge_bases.py
*** Delete File: backend/harness/tools/list_node_types.py
*** Delete File: backend/harness/tools/list_providers.py
*** Delete File: backend/harness/tools/list_skills.py
*** Delete File: backend/harness/tools/peek_knowledge_base.py
*** Delete File: backend/harness/tools/recall_preference.py
*** Delete File: backend/harness/tools/validate_graph_tool.py
*** Delete File: backend/harness/validators.py
*** Delete File: backend/harness/workspace.py
*** Delete File: backend/harness/skills/__init__.py
*** Delete File: backend/harness/skills/agent_node.md
*** Delete File: backend/harness/skills/io_contract.md
*** Delete File: backend/harness/skills/llm_basic.md
*** Delete File: backend/harness/skills/loader.py
*** Delete File: backend/harness/skills/rag_qa.md
*** Delete File: backend/harness/skills/simple_pipeline.md
*** Delete File: backend/harness/skills/tts_podcast.md
```

- [ ] **Step 3: Mark the migration plan complete**

```markdown
<!-- docs/PI_HARNESS_MIGRATION_PLAN.md -->
- [x] 删除 `backend/harness/`
- [x] 更新 `CLAUDE.md` / 相关文档里的 harness 段落
```

- [ ] **Step 4: Run the no-legacy-import audit**

Run: `rg -n "backend\\.harness|from backend.harness|import backend.harness" backend frontend CLAUDE.md -g '!docs/**'`

Expected: No output

- [ ] **Step 5: Run final verification**

Run: `backend/.venv/bin/pytest backend/tests/test_pi_harness_runtime.py backend/tests/test_pi_harness_draft.py backend/tests/test_pi_harness_context_tools.py backend/tests/test_pi_harness_validators.py backend/tests/test_pi_harness_to_engine_e2e.py backend/tests/test_pi_harness_api.py -q`

Expected: PASS

Run: `npm run build`

Expected: Frontend build succeeds

- [ ] **Step 6: Commit the final removal**

```bash
git add CLAUDE.md docs/PI_HARNESS_MIGRATION_PLAN.md backend/pi_harness backend/tests frontend/src/services/harnessApi.ts
git add -u backend/harness
git commit -m "chore: remove legacy harness implementation"
```

## Self-Review

**Spec coverage**
- Removes the last production dependency on `backend/harness` by moving validators into `pi_harness`
- Preserves engine parity coverage by re-creating the two E2E scenarios against the new session/apply path
- Deletes legacy-only runtime and test surfaces only after replacement coverage exists
- Adds an explicit stop-the-line checkpoint for user-owned dirty files before any destructive delete
- Updates `CLAUDE.md` and the migration plan after the final delete

**Placeholder scan**
- No `TODO`, `TBD`, or “implement later”
- Every task lists exact files, commands, and expected outcomes
- The dirty-file checkpoint includes the exact question to ask the user before deletion

**Type consistency**
- New validation types live in `backend.pi_harness.schemas.Finding`
- New validator function lives in `backend.pi_harness.validators.validate_graph`
- Runtime wrappers (`tools/validate.py`, `tools/finalize.py`) import only from `backend.pi_harness.validators`
