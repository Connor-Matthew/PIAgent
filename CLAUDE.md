# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is PIAgent

A visual AI agent workflow orchestration platform. Users drag-and-drop nodes (Start, LLM, RAG, TTS, Agent, End) on a canvas to build multi-step AI pipelines, then execute them with real-time SSE streaming.

## Commands

### Dev servers
```bash
# Both services (from repo root):
./scripts/start-dev.sh

# Backend only (must run from repo root for package resolution):
source backend/.venv/bin/activate && uvicorn backend.main:app --reload --port 8000

# Frontend only:
cd frontend && npm run dev
```

### Tests
```bash
# All backend tests:
source backend/.venv/bin/activate && python -m pytest backend/tests/

# Single test file:
python -m pytest backend/tests/test_compiler.py

# Single test:
python -m pytest backend/tests/test_compiler.py::test_compiler_detects_cycle -v

# Frontend lint:
cd frontend && npx eslint .
```

### Build
```bash
cd frontend && npm run build   # runs tsc -b then vite build
```

## Architecture

### Backend (Python / FastAPI)

**Execution pipeline:** Workflow JSON → `GraphCompiler` validates DAG (Kahn's algorithm) & topological sort → `ExecutionEngine` runs nodes sequentially → SSE events streamed to frontend.

Key flow: `api/workflows.py` receives run request → creates `WorkflowRun` record → opens SSE endpoint → `ExecutionEngine.run()` iterates nodes in topological order, calling `node.execute(state)` and emitting events via callback queue.

**Node system:** All nodes extend `BaseNode` (in `nodes/base.py`) with a class-level `node_type` string and `async execute(state, **kwargs) -> WorkflowState`. Nodes are registered at import time in `compiler.py` via `node_registry`. `WorkflowState` is a TypedDict; nodes read from `state["inputs"]` / `state["node_outputs"]` and write their output back into `state["node_outputs"][self.node_id]`.

**Template system:** `core/template.py` resolves `{nodeId.fieldName}` references in node configs, allowing nodes to reference upstream outputs.

**Provider system:** LLM providers (OpenAI, Anthropic, Google, DeepSeek) stored in DB as `Provider` model with encrypted API keys (`core/crypto.py` uses Fernet). Provider CRUD at `api/providers.py`. LLM nodes resolve their provider at execution time.

**Agent mode:** `backend/agent/` implements a conversational workflow builder. The `AgentPanel` collects user intent → `clarifier.py` asks follow-up questions → `planner.py` generates a `RecipeIR` → `adapter.py` converts IR to workflow graph JSON. This lets users describe what they want in natural language and get a runnable workflow.

**API routes:** All under `/api/` prefix — `workflows`, `knowledge`, `providers`, `agent`.

### Frontend (React / TypeScript / Vite)

**State:** Zustand stores — `workflowStore` (nodes, edges, canvas state), `debugStore` (SSE events, execution state), `agentStore` (agent session).

**Layout:** `App.tsx` has two routes: `/` (workflow editor) and `/providers` (provider management). The workflow editor is a 3-column layout: NodeLibrary (left) | Canvas + AgentPanel + DebugDrawer (center) | NodeConfig (right).

**Canvas:** `WorkflowCanvas` uses React Flow. Custom node components live in `components/nodes/`.

**API layer:** `services/api.ts` (workflow CRUD + SSE execution), `services/agentApi.ts` (agent session endpoints).

### Database

SQLite via SQLAlchemy. Models in `backend/models/`: `Workflow`, `WorkflowRun`, `Provider`, `AgentSession`, `KnowledgeBase`. Schema auto-created on startup. Tests use in-memory SQLite with `conftest.py` fixtures that override `get_db`.

## Environment

- Backend requires a `.env` file at repo root with API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.). SECRET_KEY is auto-generated in dev.
- Backend venv at `backend/.venv/` (Python 3.14).
- Frontend dev server runs on port 5173, backend on port 8000. CORS configured for localhost:5173.
- The UI is in Chinese (zh-CN). Keep Chinese strings in the frontend as-is unless told otherwise.
