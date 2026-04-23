# Workflow Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only, canvas-bound Workflow Assistant that answers questions about the current workflow through mini-harness ReAct tool calling and SSE streaming.

**Architecture:** mini-harness remains the reusable agent runtime, but PIAgent must pass request-scoped read-only tool instances directly instead of mutating mini-harness's global registry. PIAgent owns workflow/session persistence, assistant domain tools, SSE event translation, and the canvas chat UI. The assistant never registers mutation tools and never emits graph diffs.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Pydantic v2, LangGraph/mini-harness, pytest, React 19, TypeScript, Vite, Zustand.

---

## Scope

This plan implements the active source of truth: `docs/superpowers/specs/2026-04-23-workflow-assistant.md`.

It intentionally keeps v1 read-only:

- No graph mutation tools.
- No apply buttons.
- No generated graph diffs.
- No multi-session branching.
- No voice, image, or file input.

## Reality Adjustments From Local Review

The spec's product direction is unchanged, but the implementation plan makes four concrete corrections based on `/Users/mac/Desktop/mini-harness` and current PIAgent code:

- mini-harness config and registry are global singletons, so PIAgent must use explicit request-scoped tool instances rather than registering workflow-specific closures globally.
- mini-harness skills currently require `read_file` to load full skill bodies. PIAgent v1 will inline the assistant context into the system prompt instead of registering `read_file`.
- mini-harness summarization can compress system messages. PIAgent v1 will disable summarization until mini-harness preserves hard policy messages.
- PIAgent currently does not persist full run event history. v1 will add a `workflow_run_events` table so `get_run_events` has real data for new runs.

## File Structure

Modify `/Users/mac/Desktop/mini-harness`:

- `mini_harness/config/loader.py` — add `set_app_config()` and clear cached registry when config changes.
- `mini_harness/config/__init__.py` — export `set_app_config`.
- `mini_harness/tools/registry.py` — add `reset_tool_registry()`.
- `mini_harness/tools/__init__.py` — export `reset_tool_registry`.
- `mini_harness/agent/graph.py` — allow `create_agent(..., tool_instances=[...])`.
- `mini_harness/memory/summarizer.py` — preserve leading system messages if summarization remains enabled later.
- `tests/test_piagent_embedding.py` — cover config override, registry reset, explicit tools, and system prompt preservation.
- `pyproject.toml`, `mini_harness/__init__.py` — bump to `0.1.1`.

Modify PIAgent backend:

- `backend/requirements.txt` — add `mini-harness @ file:///Users/mac/Desktop/mini-harness`.
- `backend/models/assistant_session.py` — one assistant conversation per workflow.
- `backend/models/run_event.py` — persisted workflow SSE events for assistant inspection.
- `backend/models/__init__.py` — import new models.
- `backend/api/workflows.py` — persist workflow run events as they stream.
- `backend/assistant/__init__.py` — package marker.
- `backend/assistant/mini_harness.yaml` — PIAgent mini-harness config with no built-in tools and summarization disabled.
- `backend/assistant/prompt.py` — Chinese read-only system prompt with inlined workflow context.
- `backend/assistant/tools.py` — eight read-only domain tools.
- `backend/assistant/session.py` — session load/save helpers.
- `backend/assistant/agent.py` — request-scoped agent factory.
- `backend/assistant/routes.py` — `/api/assistant/sessions/{workflow_id}/stream`.
- `backend/main.py` — configure mini-harness and include assistant router.

Create/modify PIAgent backend tests:

- `backend/tests/test_assistant_models.py`
- `backend/tests/test_assistant_tools.py`
- `backend/tests/test_assistant_routes.py`
- `backend/tests/test_run_event_persistence.py`

Modify PIAgent frontend:

- `frontend/src/types/workflow.ts` — assistant event/message types.
- `frontend/src/services/assistantApi.ts` — fetch-based SSE streaming client.
- `frontend/src/stores/assistantStore.ts` — per-workflow chat/session state.
- `frontend/src/components/assistant/ChatPanel.tsx` — slide-out chat panel with collapsible tool traces.
- `frontend/src/components/canvas/WorkflowCanvas.tsx` — lower-right assistant bubble and panel mount.
- `frontend/src/index.css` — minimal assistant panel styling only if existing utilities are insufficient.

## Task 1: Harden mini-harness For Embedded Request-Scoped Use

**Files:**
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/config/loader.py`
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/config/__init__.py`
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/tools/registry.py`
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/tools/__init__.py`
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/agent/graph.py`
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/memory/summarizer.py`
- Modify: `/Users/mac/Desktop/mini-harness/pyproject.toml`
- Modify: `/Users/mac/Desktop/mini-harness/mini_harness/__init__.py`
- Create: `/Users/mac/Desktop/mini-harness/tests/test_piagent_embedding.py`

- [x] **Step 1: Write failing mini-harness embedding tests**

Create `tests/test_piagent_embedding.py` with tests for:

```python
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from mini_harness.config import AppConfig, ToolConfig, get_app_config, set_app_config
from mini_harness.memory.summarizer import Summarizer
from mini_harness.tools.registry import get_tool_registry


class EchoTool(BaseTool):
    name: str = "echo"
    description: str = "Echo input"

    def _run(self, text: str = ""):
        return text


def test_set_app_config_replaces_config_and_resets_registry():
    set_app_config(AppConfig(config_version=1, tools=[ToolConfig(name="missing", use="nope:Nope")]))
    assert get_app_config().tools[0].name == "missing"

    set_app_config(AppConfig(config_version=1, tools=[]))

    assert get_app_config().tools == []
    assert get_tool_registry().list_tools() == []


def test_create_agent_accepts_explicit_tool_instances(monkeypatch):
    captured = {}

    def fake_model(name=None):
        return SimpleNamespace()

    def fake_create_react_agent(*, model, tools, prompt):
        captured["tools"] = tools
        return "agent"

    import mini_harness.agent.graph as graph_mod

    monkeypatch.setattr(graph_mod, "create_chat_model", fake_model)
    monkeypatch.setattr(graph_mod, "create_react_agent", fake_create_react_agent)
    set_app_config(AppConfig(config_version=1, models=[{"name": "default", "model": "dummy"}], tools=[]))

    agent = graph_mod.create_agent(tool_instances=[EchoTool()])

    assert agent == "agent"
    assert [tool.name for tool in captured["tools"]] == ["echo"]


def test_summarizer_preserves_leading_system_messages():
    model = SimpleNamespace(invoke=lambda messages: SimpleNamespace(content="summary"))
    summarizer = Summarizer(model=model, trigger_messages=2, keep_messages=1)

    messages = [
        SystemMessage(content="hard policy"),
        HumanMessage(content="old one"),
        HumanMessage(content="old two"),
        HumanMessage(content="latest"),
    ]

    compressed = summarizer.compress(messages)

    assert compressed[0].content == "hard policy"
    assert compressed[1].content.startswith("[Previous conversation summary]")
    assert compressed[-1].content == "latest"
```

- [x] **Step 2: Run mini-harness tests and verify red**

Run:

```bash
cd /Users/mac/Desktop/mini-harness && .venv/bin/python -m pytest tests/test_piagent_embedding.py -v
```

Expected: FAIL because `set_app_config` and `tool_instances` do not exist and summarizer does not preserve system messages.

- [x] **Step 3: Implement mini-harness embedded APIs**

Implement:

```python
# mini_harness/config/loader.py
def set_app_config(cfg: AppConfig) -> None:
    global _config_instance
    _config_instance = cfg
    from mini_harness.tools.registry import reset_tool_registry
    reset_tool_registry()
```

```python
# mini_harness/tools/registry.py
def reset_tool_registry() -> None:
    global _tool_registry_instance
    _tool_registry_instance = None
```

```python
# mini_harness/agent/graph.py
def create_agent(model_name=None, tools=None, system_prompt=None, tool_instances=None):
    model = create_chat_model(model_name)
    if tool_instances is None:
        registry = get_tool_registry()
        resolved_tools = registry.get_tools(tools)
    else:
        resolved_tools = list(tool_instances)
    ...
```

Update exports and bump mini-harness version to `0.1.1`.

- [x] **Step 4: Preserve leading system messages in summarizer**

Update `Summarizer.compress()` so it peels off leading `SystemMessage` instances, compresses only the remaining conversation, then prepends the preserved system messages before the summary and recent messages.

- [x] **Step 5: Run mini-harness targeted tests**

Run:

```bash
cd /Users/mac/Desktop/mini-harness && .venv/bin/python -m pytest tests/test_piagent_embedding.py tests/test_tools.py tests/test_summarizer.py -v
```

Expected: PASS.

## Task 2: Add Assistant And Run Event Persistence

**Files:**
- Create: `backend/models/assistant_session.py`
- Create: `backend/models/run_event.py`
- Modify: `backend/models/__init__.py`
- Modify: `backend/api/workflows.py`
- Create: `backend/tests/test_assistant_models.py`
- Create: `backend/tests/test_run_event_persistence.py`

- [x] **Step 1: Write failing model tests**

Add tests proving:

- `AssistantSession.workflow_id` stores the existing string workflow UUID.
- `AssistantSession.messages` round-trips a list of role/content dicts.
- `WorkflowRunEvent.event` round-trips arbitrary JSON.

- [x] **Step 2: Implement models**

Implement `AssistantSession` with `workflow_id: String(FK workflows.id)`, `messages_json`, `updated_at`, and `messages` property.

Implement `WorkflowRunEvent` with `id`, `workflow_id`, `run_id`, `seq`, `event_type`, `event_json`, `created_at`, and `event` property.

- [x] **Step 3: Persist workflow events**

In `backend/api/workflows.py`, when `on_event(event)` receives a workflow execution event, insert a `WorkflowRunEvent` row with increasing `seq`, `event_type=event["type"]`, and the JSON payload.

- [x] **Step 4: Run persistence tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_models.py backend/tests/test_run_event_persistence.py -v
```

Expected: PASS.

## Task 3: Implement Read-Only Assistant Domain Tools

**Files:**
- Create: `backend/assistant/__init__.py`
- Create: `backend/assistant/tools.py`
- Create: `backend/tests/test_assistant_tools.py`

- [x] **Step 1: Write failing tool tests**

Add tests for these read-only behaviors:

- `get_current_graph` returns the workflow graph.
- `get_node_config` returns only the requested node's config.
- `list_node_types` returns node contracts from `backend.nodes.contracts`.
- `list_providers` redacts API keys.
- `list_knowledge_bases` returns KB metadata.
- `peek_knowledge_base` returns retrieved chunks when `query` is supplied.
- `get_recent_runs` returns newest runs first.
- `get_run_events` returns persisted event payloads in `seq` order.
- `build_readonly_tools()` does not include mutation names such as `update_node`, `add_node`, `delete_node`, or `apply_graph`.

- [x] **Step 2: Implement tool classes**

Create one `BaseTool` subclass per tool with Pydantic arg schemas where needed. Each tool captures a SQLAlchemy session and `workflow_id` at construction time, but only performs SELECT/read operations.

- [x] **Step 3: Run assistant tool tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_tools.py -v
```

Expected: PASS.

## Task 4: Build Assistant Agent Factory And Backend Routes

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/assistant/mini_harness.yaml`
- Create: `backend/assistant/prompt.py`
- Create: `backend/assistant/session.py`
- Create: `backend/assistant/agent.py`
- Create: `backend/assistant/routes.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_assistant_routes.py`

- [x] **Step 1: Install local mini-harness dependency**

Add to `backend/requirements.txt`:

```text
mini-harness @ file:///Users/mac/Desktop/mini-harness
```

Then run:

```bash
backend/.venv/bin/python -m pip install -e /Users/mac/Desktop/mini-harness
```

Expected: `backend/.venv/bin/python -c "import mini_harness; print(mini_harness.__version__)"` prints `0.1.1`.

- [x] **Step 2: Write failing route tests**

Add tests proving:

- `POST /api/assistant/sessions/{workflow_id}/stream` returns `404` for a missing workflow.
- The route loads or creates one `AssistantSession` per workflow.
- A mocked mini-harness agent stream is translated into `session.started`, `message.delta`, `tool.call`, `tool.result`, and `message.done` SSE events.
- The stored session contains the user message and final assistant text.

- [x] **Step 3: Implement prompt and config**

Create `mini_harness.yaml` with `tools: []`, `skills.enabled: false`, `allow_bash: false`, `summarization.enabled: false`, `clarification.enabled: false`, and token usage enabled.

Create `ASSISTANT_SYSTEM_PROMPT` in Chinese. Inline the node-type and template context directly in the prompt.

- [x] **Step 4: Implement route and agent factory**

`build_assistant_agent(db, workflow_id)` must call mini-harness `create_agent(system_prompt=ASSISTANT_SYSTEM_PROMPT, tool_instances=build_readonly_tools(db, workflow_id))`.

`routes.py` must use fetch-compatible SSE over `StreamingResponse`, translate mini-harness message stream into PIAgent assistant event names, and never expose full raw API keys.

- [x] **Step 5: Register router and startup config**

In `backend/main.py`, import `set_app_config` / `load_config` from mini-harness in lifespan and load `backend/assistant/mini_harness.yaml`. Include the assistant router after existing API routers.

- [x] **Step 6: Run backend assistant tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_models.py backend/tests/test_assistant_tools.py backend/tests/test_assistant_routes.py backend/tests/test_run_event_persistence.py -v
```

Expected: PASS.

## Task 5: Add Frontend Assistant Panel

**Files:**
- Modify: `frontend/src/types/workflow.ts`
- Create: `frontend/src/services/assistantApi.ts`
- Create: `frontend/src/stores/assistantStore.ts`
- Create: `frontend/src/components/assistant/ChatPanel.tsx`
- Modify: `frontend/src/components/canvas/WorkflowCanvas.tsx`

- [x] **Step 1: Add assistant types**

Add types for `AssistantMessage`, `AssistantToolTrace`, and assistant SSE events.

- [x] **Step 2: Implement fetch streaming client**

Create `assistantApi.streamMessage(workflowId, message, handlers)` using `fetch()` and a `ReadableStream` parser. Do not use native `EventSource` because the route is POST-based.

- [x] **Step 3: Implement Zustand assistant store**

Store panel open/closed state, messages keyed by workflow id, streaming status, and tool traces. The store must keep chat history when the panel closes.

- [x] **Step 4: Implement ChatPanel**

Build a 400px right slide-out panel with message list, streaming assistant text, collapsible tool traces, and a textarea/send button. Use concise Chinese UI labels.

- [x] **Step 5: Mount bubble and panel on canvas**

Add a lower-right assistant icon button in `WorkflowCanvas.tsx`. Toggle the panel without resizing the React Flow canvas.

- [x] **Step 6: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

## Task 6: End-To-End Verification And Demo Fixtures

**Files:**
- Create: `backend/tests/test_assistant_e2e.py`
- Optional create: `docs/superpowers/evals/workflow-assistant-fixtures.md`

- [x] **Step 1: Add backend e2e test**

Create one test that seeds a workflow with an LLM node whose prompt references a missing upstream node, mocks the assistant model stream, calls the assistant endpoint, and verifies that the current graph tool can expose the problem context.

- [x] **Step 2: Create first 10 manual eval prompts**

Document 10 workflow questions covering RAG without KB, missing template refs, disabled providers, TTS text mismatch, and failed runs.

- [x] **Step 3: Run final verification**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/
cd frontend && npm run build
```

Expected: backend tests and frontend build pass.

## Self-Review

**Spec coverage:** Covers the assistant bubble/panel, one workflow-one session, read-only tool surface, mini-harness dependency, request-scoped tools, SSE translation, provider/KB/run history inspection, and evaluation fixtures.

**Known deferrals:** Apply buttons, graph diffs, multi-session branching, file upload, voice input, image input, and autonomous graph modification remain out of scope by design.

**Type consistency:** `workflow_id` is string everywhere because `Workflow.id` is a UUID string. Assistant SSE event names match the active spec: `session.started`, `message.delta`, `tool.call`, `tool.result`, `message.done`, and `error`.

**Execution choice:** Inline execution in this branch, because the user explicitly asked to start implementation in this session and subagent spawning was not requested.
