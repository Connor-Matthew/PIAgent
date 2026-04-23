# PIAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AI Agent workflow orchestration platform with visual drag-and-drop canvas, LangGraph execution engine, RAG knowledge retrieval, ReAct Agent, TTS audio synthesis, and real-time SSE debugging.

**Architecture:** React Flow frontend submits workflow graph JSON to FastAPI backend. Graph Compiler converts it to a LangGraph StateGraph. Execution Engine runs the graph node-by-node, pushing real-time status via SSE. Nodes include LLM (multi-provider), RAG (Chroma), ReAct Agent, and TTS.

**Tech Stack:** React 18 + TypeScript + React Flow + Zustand + Vite + TailwindCSS | Python 3.12 + FastAPI + LangChain + LangGraph + SQLAlchemy + SQLite + Chroma

---

## File Structure

### Backend `backend/`

```
backend/
├── main.py                     — FastAPI app entry, CORS, router mounting
├── config.py                   — Settings via pydantic-settings
├── database.py                 — SQLite engine + session factory
├── api/
│   ├── __init__.py
│   ├── workflows.py            — Workflow CRUD + run + SSE endpoints
│   ├── knowledge.py            — Knowledge base CRUD + upload + query
│   └── providers.py            — LLM provider list + model list + test
├── core/
│   ├── __init__.py
│   ├── state.py                — WorkflowState TypedDict
│   ├── compiler.py             — Graph Compiler: JSON → LangGraph StateGraph
│   └── engine.py               — Execution Engine: run graph + emit SSE events
├── nodes/
│   ├── __init__.py
│   ├── base.py                 — BaseNode ABC
│   ├── registry.py             — NodeRegistry: type string → node class
│   ├── start_node.py           — Writes user input to state
│   ├── end_node.py             — Collects final output
│   ├── llm_node.py             — LangChain ChatModel invocation
│   ├── rag_node.py             — Retriever + context injection
│   ├── agent_node.py           — ReAct Agent with tool calling
│   └── tts_node.py             — TTS tool invocation
├── providers/
│   ├── __init__.py
│   ├── base.py                 — BaseLLMProvider ABC
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   ├── google_provider.py
│   └── deepseek_provider.py
├── tts/
│   ├── __init__.py
│   ├── base.py                 — BaseTTSProvider ABC
│   └── fish_audio.py
├── rag/
│   ├── __init__.py
│   ├── embeddings.py           — Embedding model wrapper
│   ├── vectorstore.py          — Chroma collection manager
│   └── loader.py               — Document loading + chunking
├── models/
│   ├── __init__.py
│   ├── workflow.py             — Workflow SQLAlchemy model
│   ├── run.py                  — WorkflowRun model
│   └── knowledge_base.py       — KnowledgeBase model
├── requirements.txt
└── tests/
    ├── __init__.py
    ├── test_compiler.py
    ├── test_engine.py
    ├── test_nodes.py
    ├── test_workflows_api.py
    └── conftest.py             — Shared fixtures (test DB, client)
```

### Frontend `frontend/`

```
frontend/
├── src/
│   ├── App.tsx                 — Root layout: 3-column + debug drawer
│   ├── main.tsx                — Vite entry
│   ├── index.css               — TailwindCSS imports
│   ├── components/
│   │   ├── canvas/
│   │   │   ├── WorkflowCanvas.tsx   — React Flow wrapper
│   │   │   └── CanvasToolbar.tsx    — Zoom, undo/redo, debug button
│   │   ├── nodes/
│   │   │   ├── StartNode.tsx
│   │   │   ├── LLMNode.tsx
│   │   │   ├── RAGNode.tsx
│   │   │   ├── AgentNode.tsx
│   │   │   ├── TTSNode.tsx
│   │   │   ├── EndNode.tsx
│   │   │   └── index.ts            — nodeTypes registry
│   │   ├── panels/
│   │   │   ├── NodeLibrary.tsx      — Left sidebar, draggable items
│   │   │   └── NodeConfig.tsx       — Right sidebar, selected node config
│   │   └── debug/
│   │       ├── DebugDrawer.tsx      — Bottom drawer container
│   │       ├── ExecutionTimeline.tsx — Node status cards list
│   │       ├── NodeStatusCard.tsx   — Single node execution status
│   │       └── AudioPlayer.tsx      — Podcast audio player
│   ├── stores/
│   │   ├── workflowStore.ts         — Zustand: nodes, edges, selected
│   │   └── debugStore.ts            — Zustand: run state, node statuses
│   ├── hooks/
│   │   ├── useSSE.ts                — SSE EventSource hook
│   │   └── useDnD.ts                — Drag-and-drop from library to canvas
│   ├── services/
│   │   └── api.ts                   — Axios/fetch API client
│   └── types/
│       └── workflow.ts              — Shared TypeScript types
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
└── postcss.config.js
```

---

## Task 1: Backend Project Setup

**Files:**
- Create: `backend/main.py`, `backend/config.py`, `backend/database.py`, `backend/requirements.txt`
- Create: `backend/models/__init__.py`, `backend/models/workflow.py`, `backend/models/run.py`, `backend/models/knowledge_base.py`
- Create: `backend/api/__init__.py`
- Test: `backend/tests/conftest.py`, `backend/tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
pydantic-settings==2.5.0
langchain==0.3.7
langchain-openai==0.2.9
langchain-anthropic==0.3.0
langchain-google-genai==2.0.4
langgraph==0.2.53
chromadb==0.5.20
python-multipart==0.0.12
httpx==0.27.0
pytest==8.3.0
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./piagent.db"
    audio_dir: str = "./audio_files"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Create SQLAlchemy models**

`backend/models/__init__.py`:
```python
from backend.models.workflow import Workflow
from backend.models.run import WorkflowRun
from backend.models.knowledge_base import KnowledgeBase
```

`backend/models/workflow.py`:
```python
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from backend.database import Base
import uuid

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    graph_json = Column(Text, nullable=False)  # {nodes: [...], edges: [...]}
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def graph(self) -> dict:
        return json.loads(self.graph_json)

    @graph.setter
    def graph(self, value: dict):
        self.graph_json = json.dumps(value)
```

`backend/models/run.py`:
```python
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from backend.database import Base
import uuid

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending/running/completed/failed
    input_text = Column(Text, default="")
    output_json = Column(Text, default="{}")
    duration = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def output(self) -> dict:
        return json.loads(self.output_json)

    @output.setter
    def output(self, value: dict):
        self.output_json = json.dumps(value, ensure_ascii=False)
```

`backend/models/knowledge_base.py`:
```python
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime
from backend.database import Base
import uuid

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    doc_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 5: Create main.py**

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import engine, Base

app = FastAPI(title="PIAgent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=settings.audio_dir), name="audio")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Create test fixtures**

`backend/tests/__init__.py`: empty file

`backend/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import app

TEST_DB_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 7: Verify setup**

Run:
```bash
cd backend && pip install -r requirements.txt
python -c "from backend.main import app; print('OK')"
pytest tests/ -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: backend project setup with FastAPI, SQLAlchemy, models"
```

---

## Task 2: WorkflowState + BaseNode + Node Registry

**Files:**
- Create: `backend/core/__init__.py`, `backend/core/state.py`
- Create: `backend/nodes/__init__.py`, `backend/nodes/base.py`, `backend/nodes/registry.py`
- Test: `backend/tests/test_nodes.py`

- [ ] **Step 1: Write failing test for node registry**

`backend/tests/test_nodes.py`:
```python
from backend.core.state import WorkflowState
from backend.nodes.registry import NodeRegistry
from backend.nodes.base import BaseNode

def test_workflow_state_has_required_fields():
    state: WorkflowState = {
        "input": "",
        "messages": [],
        "context": "",
        "llm_output": "",
        "audio_url": "",
        "node_outputs": {},
    }
    assert state["input"] == ""

def test_node_registry_register_and_get():
    class FakeNode(BaseNode):
        node_type = "fake"
        async def execute(self, state: WorkflowState) -> WorkflowState:
            return state

    registry = NodeRegistry()
    registry.register(FakeNode)
    node_cls = registry.get("fake")
    assert node_cls is FakeNode

def test_node_registry_get_unknown_raises():
    registry = NodeRegistry()
    import pytest
    with pytest.raises(KeyError):
        registry.get("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Implement state.py**

`backend/core/__init__.py`: empty file

`backend/core/state.py`:
```python
from typing import TypedDict
from langchain_core.messages import BaseMessage

class WorkflowState(TypedDict):
    input: str
    messages: list[BaseMessage]
    context: str
    llm_output: str
    audio_url: str
    node_outputs: dict
```

- [ ] **Step 4: Implement base.py and registry.py**

`backend/nodes/__init__.py`: empty file

`backend/nodes/base.py`:
```python
from abc import ABC, abstractmethod
from backend.core.state import WorkflowState

class BaseNode(ABC):
    node_type: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, state: WorkflowState) -> WorkflowState:
        ...
```

`backend/nodes/registry.py`:
```python
from backend.nodes.base import BaseNode

class NodeRegistry:
    def __init__(self):
        self._registry: dict[str, type[BaseNode]] = {}

    def register(self, node_cls: type[BaseNode]):
        self._registry[node_cls.node_type] = node_cls

    def get(self, node_type: str) -> type[BaseNode]:
        if node_type not in self._registry:
            raise KeyError(f"Unknown node type: {node_type}")
        return self._registry[node_type]

    def list_types(self) -> list[str]:
        return list(self._registry.keys())

# Global registry instance
node_registry = NodeRegistry()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/ backend/nodes/ backend/tests/test_nodes.py
git commit -m "feat: WorkflowState, BaseNode, NodeRegistry"
```

---

## Task 3: Start Node + End Node

**Files:**
- Create: `backend/nodes/start_node.py`, `backend/nodes/end_node.py`
- Modify: `backend/tests/test_nodes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_nodes.py`:
```python
import pytest

@pytest.mark.asyncio
async def test_start_node_writes_input():
    from backend.nodes.start_node import StartNode
    node = StartNode(config={})
    state: WorkflowState = {
        "input": "", "messages": [], "context": "",
        "llm_output": "", "audio_url": "", "node_outputs": {},
    }
    result = await node.execute(state, user_input="你好世界")
    assert result["input"] == "你好世界"
    assert "start" in result["node_outputs"]

@pytest.mark.asyncio
async def test_end_node_collects_output():
    from backend.nodes.end_node import EndNode
    node = EndNode(config={})
    state: WorkflowState = {
        "input": "test", "messages": [], "context": "",
        "llm_output": "generated text", "audio_url": "/audio/test.mp3",
        "node_outputs": {},
    }
    result = await node.execute(state)
    assert result["node_outputs"]["end"]["llm_output"] == "generated text"
    assert result["node_outputs"]["end"]["audio_url"] == "/audio/test.mp3"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && pytest tests/test_nodes.py::test_start_node_writes_input tests/test_nodes.py::test_end_node_collects_output -v`
Expected: FAIL

- [ ] **Step 3: Implement start_node.py**

```python
from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState

class StartNode(BaseNode):
    node_type = "start"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        user_input = kwargs.get("user_input", state.get("input", ""))
        state["input"] = user_input
        state["node_outputs"]["start"] = {"input": user_input}
        return state
```

- [ ] **Step 4: Implement end_node.py**

```python
from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState

class EndNode(BaseNode):
    node_type = "end"

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        state["node_outputs"]["end"] = {
            "llm_output": state.get("llm_output", ""),
            "audio_url": state.get("audio_url", ""),
        }
        return state
```

- [ ] **Step 5: Update BaseNode.execute signature to accept kwargs**

`backend/nodes/base.py`:
```python
from abc import ABC, abstractmethod
from backend.core.state import WorkflowState

class BaseNode(ABC):
    node_type: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        ...
```

Update the `FakeNode` in test accordingly (add `**kwargs`).

- [ ] **Step 6: Run tests**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/nodes/ backend/tests/test_nodes.py
git commit -m "feat: StartNode and EndNode implementations"
```

---

## Task 4: Graph Compiler

**Files:**
- Create: `backend/core/compiler.py`
- Test: `backend/tests/test_compiler.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_compiler.py`:
```python
import pytest
from backend.core.compiler import GraphCompiler, CycleDetectedError

def make_graph_json(nodes, edges):
    return {"nodes": nodes, "edges": edges}

def test_compiler_detects_cycle():
    graph_json = make_graph_json(
        nodes=[
            {"id": "a", "type": "start", "data": {}},
            {"id": "b", "type": "llm", "data": {}},
        ],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ],
    )
    compiler = GraphCompiler()
    with pytest.raises(CycleDetectedError):
        compiler.validate(graph_json)

def test_compiler_topological_sort():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "llm_1", "type": "llm", "data": {}},
            {"id": "tts_1", "type": "tts", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "tts_1"},
            {"source": "tts_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    order = compiler.topological_sort(graph_json)
    assert order == ["start_1", "llm_1", "tts_1", "end_1"]

def test_compiler_compile_returns_langgraph():
    graph_json = make_graph_json(
        nodes=[
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        edges=[
            {"source": "start_1", "target": "end_1"},
        ],
    )
    compiler = GraphCompiler()
    compiled = compiler.compile(graph_json)
    # compiled should be a LangGraph CompiledGraph
    assert compiled is not None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && pytest tests/test_compiler.py -v`
Expected: FAIL

- [ ] **Step 3: Implement compiler.py**

```python
from collections import defaultdict, deque
from langgraph.graph import StateGraph, END

from backend.core.state import WorkflowState
from backend.nodes.registry import node_registry
from backend.nodes.start_node import StartNode
from backend.nodes.end_node import EndNode

# Register built-in nodes
node_registry.register(StartNode)
node_registry.register(EndNode)


class CycleDetectedError(Exception):
    pass


class GraphCompiler:
    def validate(self, graph_json: dict):
        """Validate DAG: detect cycles using Kahn's algorithm."""
        nodes = {n["id"] for n in graph_json["nodes"]}
        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        queue = deque(n for n in nodes if in_degree[n] == 0)
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(nodes):
            raise CycleDetectedError("Workflow graph contains a cycle")

    def topological_sort(self, graph_json: dict) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm."""
        self.validate(graph_json)

        nodes = {n["id"] for n in graph_json["nodes"]}
        in_degree = defaultdict(int)
        adj = defaultdict(list)

        for edge in graph_json["edges"]:
            adj[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        queue = deque(n for n in nodes if in_degree[n] == 0)
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return order

    def compile(self, graph_json: dict):
        """Compile workflow JSON into a LangGraph CompiledGraph."""
        self.validate(graph_json)

        graph = StateGraph(WorkflowState)
        node_map = {n["id"]: n for n in graph_json["nodes"]}

        # Add nodes
        for node_def in graph_json["nodes"]:
            node_cls = node_registry.get(node_def["type"])
            node_instance = node_cls(config=node_def.get("data", {}))

            async def make_handler(inst, state):
                return await inst.execute(state)

            # Closure to capture node_instance
            handler = (lambda inst: (lambda state: inst.execute(state)))(node_instance)
            graph.add_node(node_def["id"], handler)

        # Find start node and set entry point
        order = self.topological_sort(graph_json)
        graph.set_entry_point(order[0])

        # Add edges
        for edge in graph_json["edges"]:
            target = edge["target"]
            # Check if target is an end-type node with no outgoing edges
            has_outgoing = any(e["source"] == target for e in graph_json["edges"])
            if not has_outgoing and node_map[target]["type"] == "end":
                graph.add_edge(edge["source"], target)
            else:
                graph.add_edge(edge["source"], target)

        # Set finish point to the last node in topological order
        graph.set_finish_point(order[-1])

        return graph.compile()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_compiler.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/compiler.py backend/tests/test_compiler.py
git commit -m "feat: Graph Compiler with DAG validation, topological sort, LangGraph compilation"
```

---

## Task 5: Execution Engine + SSE

**Files:**
- Create: `backend/core/engine.py`
- Test: `backend/tests/test_engine.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_engine.py`:
```python
import pytest
from backend.core.engine import ExecutionEngine
from backend.core.state import WorkflowState

@pytest.mark.asyncio
async def test_engine_executes_simple_workflow():
    graph_json = {
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}},
            {"id": "end_1", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "end_1"},
        ],
    }

    events = []
    async def on_event(event):
        events.append(event)

    engine = ExecutionEngine()
    result = await engine.run(graph_json, user_input="hello", on_event=on_event)

    assert result["input"] == "hello"
    # Should have node_start and node_end events
    event_types = [e["type"] for e in events]
    assert "node_start" in event_types
    assert "node_end" in event_types
    assert "workflow_end" in event_types
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && pytest tests/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement engine.py**

```python
import time
from typing import Callable, Awaitable
from backend.core.compiler import GraphCompiler
from backend.core.state import WorkflowState

class ExecutionEngine:
    def __init__(self):
        self.compiler = GraphCompiler()

    async def run(
        self,
        graph_json: dict,
        user_input: str,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> WorkflowState:
        """Execute a workflow graph and emit events for each node."""

        order = self.compiler.topological_sort(graph_json)
        node_map = {n["id"]: n for n in graph_json["nodes"]}

        # Initialize state
        state: WorkflowState = {
            "input": user_input,
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }

        workflow_start = time.time()

        # Import node registry to get handlers
        from backend.nodes.registry import node_registry

        for node_id in order:
            node_def = node_map[node_id]
            node_cls = node_registry.get(node_def["type"])
            node_instance = node_cls(config=node_def.get("data", {}))

            # Emit node_start
            if on_event:
                await on_event({
                    "type": "node_start",
                    "node_id": node_id,
                    "node_type": node_def["type"],
                    "status": "running",
                })

            node_start = time.time()

            # Execute node
            if node_def["type"] == "start":
                state = await node_instance.execute(state, user_input=user_input)
            else:
                state = await node_instance.execute(state)

            duration = round(time.time() - node_start, 3)

            # Emit node_end
            if on_event:
                await on_event({
                    "type": "node_end",
                    "node_id": node_id,
                    "node_type": node_def["type"],
                    "status": "completed",
                    "duration": duration,
                    "output": state.get("node_outputs", {}).get(node_id, {}),
                })

        total_duration = round(time.time() - workflow_start, 3)

        if on_event:
            await on_event({
                "type": "workflow_end",
                "status": "completed",
                "duration": total_duration,
            })

        return state
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/engine.py backend/tests/test_engine.py
git commit -m "feat: ExecutionEngine with event emission for SSE"
```

---

## Task 6: Workflow CRUD + Run API

**Files:**
- Create: `backend/api/workflows.py`
- Modify: `backend/main.py` — mount router
- Test: `backend/tests/test_workflows_api.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_workflows_api.py`:
```python
SAMPLE_GRAPH = {
    "nodes": [
        {"id": "start_1", "type": "start", "data": {}},
        {"id": "end_1", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "start_1", "target": "end_1"},
    ],
}

def test_create_workflow(client):
    resp = client.post("/api/workflows", json={
        "name": "Test Flow",
        "description": "A test",
        "graph": SAMPLE_GRAPH,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Flow"
    assert "id" in data

def test_list_workflows(client):
    client.post("/api/workflows", json={"name": "Flow 1", "graph": SAMPLE_GRAPH})
    client.post("/api/workflows", json={"name": "Flow 2", "graph": SAMPLE_GRAPH})
    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

def test_get_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "My Flow", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Flow"

def test_update_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "Old Name", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.put(f"/api/workflows/{wf_id}", json={"name": "New Name", "graph": SAMPLE_GRAPH})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"

def test_delete_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "To Delete", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.delete(f"/api/workflows/{wf_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 404

def test_run_workflow(client):
    create_resp = client.post("/api/workflows", json={"name": "Run Test", "graph": SAMPLE_GRAPH})
    wf_id = create_resp.json()["id"]
    resp = client.post(f"/api/workflows/{wf_id}/run", json={"input": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "run_id" in data
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && pytest tests/test_workflows_api.py -v`
Expected: FAIL — 404 on all routes

- [ ] **Step 3: Implement workflows.py**

```python
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models.workflow import Workflow
from backend.models.run import WorkflowRun
from backend.core.engine import ExecutionEngine

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    graph: dict

class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: dict | None = None

class RunCreate(BaseModel):
    input: str

# --- CRUD ---

@router.post("", status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db)):
    wf = Workflow(name=body.name, description=body.description)
    wf.graph = body.graph
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return {"id": wf.id, "name": wf.name, "description": wf.description, "graph": wf.graph, "created_at": str(wf.created_at)}

@router.get("")
def list_workflows(db: Session = Depends(get_db)):
    workflows = db.query(Workflow).all()
    return [{"id": w.id, "name": w.name, "description": w.description, "created_at": str(w.created_at)} for w in workflows]

@router.get("/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"id": wf.id, "name": wf.name, "description": wf.description, "graph": wf.graph, "created_at": str(wf.created_at)}

@router.put("/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowUpdate, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.graph is not None:
        wf.graph = body.graph
    db.commit()
    db.refresh(wf)
    return {"id": wf.id, "name": wf.name, "description": wf.description, "graph": wf.graph}

@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(wf)
    db.commit()
    return Response(status_code=204)

# --- Execution ---

@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: RunCreate, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = WorkflowRun(workflow_id=wf.id, input_text=body.input, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    engine = ExecutionEngine()
    result = await engine.run(wf.graph, user_input=body.input)

    run.status = "completed"
    run.output = result
    run.duration = result.get("node_outputs", {}).get("end", {}).get("duration", 0)
    db.commit()

    return {"run_id": run.id, "status": "completed", "output": result}

@router.get("/{workflow_id}/runs/{run_id}/events")
async def stream_run_events(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    """SSE endpoint for real-time workflow execution events."""
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event):
            await queue.put(event)

        engine = ExecutionEngine()

        async def execute():
            result = await engine.run(wf.graph, user_input=run.input_text, on_event=on_event)
            await queue.put(None)  # Signal completion

        task = asyncio.create_task(execute())

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/{workflow_id}/runs")
def list_runs(workflow_id: str, db: Session = Depends(get_db)):
    runs = db.query(WorkflowRun).filter(WorkflowRun.workflow_id == workflow_id).all()
    return [{"id": r.id, "status": r.status, "duration": r.duration, "created_at": str(r.created_at)} for r in runs]
```

- [ ] **Step 4: Mount router in main.py**

Add to `backend/main.py` after the middleware setup:
```python
from backend.api.workflows import router as workflows_router
app.include_router(workflows_router)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_workflows_api.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/ backend/main.py backend/tests/test_workflows_api.py
git commit -m "feat: Workflow CRUD + Run + SSE execution API"
```

---

## Task 7: LLM Provider Abstraction + OpenAI Provider

**Files:**
- Create: `backend/providers/__init__.py`, `backend/providers/base.py`, `backend/providers/openai_provider.py`
- Create: `backend/providers/anthropic_provider.py`, `backend/providers/google_provider.py`, `backend/providers/deepseek_provider.py`

- [ ] **Step 1: Implement base.py**

`backend/providers/__init__.py`: empty file

`backend/providers/base.py`:
```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from langchain_core.messages import BaseMessage

class BaseLLMProvider(ABC):
    name: str = ""

    @abstractmethod
    def get_chat_model(self, model: str, temperature: float = 0.7, streaming: bool = True):
        """Return a LangChain ChatModel instance."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return available model names."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the provider API key is valid."""
        ...
```

- [ ] **Step 2: Implement openai_provider.py**

```python
from langchain_openai import ChatOpenAI
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def get_chat_model(self, model: str = "gpt-4o", temperature: float = 0.7, streaming: bool = True):
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.openai_api_key,
        )

    def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
```

- [ ] **Step 3: Implement anthropic, google, deepseek providers**

`backend/providers/anthropic_provider.py`:
```python
from langchain_anthropic import ChatAnthropic
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def get_chat_model(self, model: str = "claude-sonnet-4-20250514", temperature: float = 0.7, streaming: bool = True):
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.anthropic_api_key,
        )

    def list_models(self) -> list[str]:
        return ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
```

`backend/providers/google_provider.py`:
```python
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class GoogleProvider(BaseLLMProvider):
    name = "google"

    def get_chat_model(self, model: str = "gemini-2.0-flash", temperature: float = 0.7, streaming: bool = True):
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            google_api_key=settings.google_api_key,
        )

    def list_models(self) -> list[str]:
        return ["gemini-2.0-flash", "gemini-2.0-pro"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
```

`backend/providers/deepseek_provider.py`:
```python
from langchain_openai import ChatOpenAI
from backend.providers.base import BaseLLMProvider
from backend.config import settings

class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"

    def get_chat_model(self, model: str = "deepseek-chat", temperature: float = 0.7, streaming: bool = True):
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
        )

    def list_models(self) -> list[str]:
        return ["deepseek-chat", "deepseek-reasoner"]

    async def test_connection(self) -> bool:
        try:
            model = self.get_chat_model(streaming=False)
            await model.ainvoke("hi")
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Commit**

```bash
git add backend/providers/
git commit -m "feat: LLM provider abstraction with OpenAI, Anthropic, Google, DeepSeek"
```

---

## Task 8: LLM Node

**Files:**
- Create: `backend/nodes/llm_node.py`
- Modify: `backend/core/compiler.py` — register node
- Modify: `backend/tests/test_nodes.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_nodes.py`:
```python
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_llm_node_generates_output():
    from backend.nodes.llm_node import LLMNode

    mock_response = MagicMock()
    mock_response.content = "Generated podcast script about AI."

    with patch("backend.nodes.llm_node.LLMNode._get_chat_model") as mock_get:
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        mock_get.return_value = mock_model

        node = LLMNode(config={
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "system_prompt": "You are a podcast writer.",
        })
        state: WorkflowState = {
            "input": "AI in education",
            "messages": [],
            "context": "",
            "llm_output": "",
            "audio_url": "",
            "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["llm_output"] == "Generated podcast script about AI."
        assert len(result["messages"]) > 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && pytest tests/test_nodes.py::test_llm_node_generates_output -v`
Expected: FAIL

- [ ] **Step 3: Implement llm_node.py**

```python
from langchain_core.messages import HumanMessage, SystemMessage

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.google_provider import GoogleProvider
from backend.providers.deepseek_provider import DeepSeekProvider

PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "deepseek": DeepSeekProvider(),
}

class LLMNode(BaseNode):
    node_type = "llm"

    def _get_chat_model(self):
        provider_name = self.config.get("provider", "openai")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)
        streaming = self.config.get("streaming", True)

        provider = PROVIDERS.get(provider_name)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")

        return provider.get_chat_model(
            model=model_name,
            temperature=temperature,
            streaming=streaming,
        )

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        chat_model = self._get_chat_model()

        messages = []
        system_prompt = self.config.get("system_prompt", "")
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        # Include RAG context if available
        user_content = state["input"]
        if state.get("context"):
            user_content = f"Reference context:\n{state['context']}\n\nUser input:\n{state['input']}"

        messages.append(HumanMessage(content=user_content))

        response = await chat_model.ainvoke(messages)

        state["llm_output"] = response.content
        state["messages"] = messages + [response]
        state["node_outputs"][self.config.get("node_id", "llm")] = {
            "output": response.content,
        }

        return state
```

- [ ] **Step 4: Register LLM node in compiler.py**

Add to imports in `backend/core/compiler.py`:
```python
from backend.nodes.llm_node import LLMNode
node_registry.register(LLMNode)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nodes/llm_node.py backend/core/compiler.py backend/tests/test_nodes.py
git commit -m "feat: LLM Node with multi-provider support via LangChain"
```

---

## Task 9: TTS Abstraction + TTS Node

**Files:**
- Create: `backend/tts/__init__.py`, `backend/tts/base.py`, `backend/tts/fish_audio.py`
- Create: `backend/nodes/tts_node.py`
- Modify: `backend/core/compiler.py` — register node
- Modify: `backend/tests/test_nodes.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_nodes.py`:
```python
@pytest.mark.asyncio
async def test_tts_node_generates_audio_url():
    from backend.nodes.tts_node import TTSNode

    with patch("backend.nodes.tts_node.TTSNode._get_tts_provider") as mock_get:
        mock_provider = AsyncMock()
        mock_provider.synthesize.return_value = "/audio/test123.mp3"
        mock_get.return_value = mock_provider

        node = TTSNode(config={"provider": "fish_audio", "voice": "default"})
        state: WorkflowState = {
            "input": "test", "messages": [], "context": "",
            "llm_output": "Hello, welcome to the podcast.",
            "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["audio_url"].endswith(".mp3")
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && pytest tests/test_nodes.py::test_tts_node_generates_audio_url -v`
Expected: FAIL

- [ ] **Step 3: Implement TTS base + fish_audio**

`backend/tts/__init__.py`: empty file

`backend/tts/base.py`:
```python
from abc import ABC, abstractmethod

class BaseTTSProvider(ABC):
    name: str = ""

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "default", output_dir: str = "./audio_files") -> str:
        """Synthesize text to audio. Returns the file path relative to audio serving."""
        ...
```

`backend/tts/fish_audio.py`:
```python
import os
import uuid
import httpx

from backend.tts.base import BaseTTSProvider

class FishAudioProvider(BaseTTSProvider):
    name = "fish_audio"

    def __init__(self, api_key: str = "", base_url: str = "https://api.fish.audio"):
        self.api_key = api_key
        self.base_url = base_url

    async def synthesize(self, text: str, voice: str = "default", output_dir: str = "./audio_files") -> str:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(output_dir, filename)

        # Fish Audio TTS API call
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/tts",
                json={"text": text, "reference_id": voice},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)

        return f"/audio/{filename}"
```

- [ ] **Step 4: Implement tts_node.py**

```python
from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.tts.base import BaseTTSProvider
from backend.tts.fish_audio import FishAudioProvider
from backend.config import settings

TTS_PROVIDERS: dict[str, BaseTTSProvider] = {
    "fish_audio": FishAudioProvider(),
}

class TTSNode(BaseNode):
    node_type = "tts"

    def _get_tts_provider(self) -> BaseTTSProvider:
        provider_name = self.config.get("provider", "fish_audio")
        provider = TTS_PROVIDERS.get(provider_name)
        if not provider:
            raise ValueError(f"Unknown TTS provider: {provider_name}")
        return provider

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        text = state.get("llm_output", "")
        if not text:
            text = state.get("input", "")

        provider = self._get_tts_provider()
        voice = self.config.get("voice", "default")

        audio_url = await provider.synthesize(
            text=text,
            voice=voice,
            output_dir=settings.audio_dir,
        )

        state["audio_url"] = audio_url
        state["node_outputs"][self.config.get("node_id", "tts")] = {
            "audio_url": audio_url,
        }

        return state
```

- [ ] **Step 5: Register TTS node in compiler.py**

Add to `backend/core/compiler.py`:
```python
from backend.nodes.tts_node import TTSNode
node_registry.register(TTSNode)
```

- [ ] **Step 6: Run tests**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tts/ backend/nodes/tts_node.py backend/core/compiler.py backend/tests/test_nodes.py
git commit -m "feat: TTS abstraction layer + TTSNode with Fish Audio provider"
```

---

## Task 10: RAG Components + RAG Node

**Files:**
- Create: `backend/rag/__init__.py`, `backend/rag/embeddings.py`, `backend/rag/vectorstore.py`, `backend/rag/loader.py`
- Create: `backend/nodes/rag_node.py`
- Modify: `backend/core/compiler.py` — register node
- Modify: `backend/tests/test_nodes.py`

- [ ] **Step 1: Implement RAG components**

`backend/rag/__init__.py`: empty file

`backend/rag/embeddings.py`:
```python
from langchain_openai import OpenAIEmbeddings
from backend.config import settings

def get_embedding_model(provider: str = "openai"):
    if provider == "openai":
        return OpenAIEmbeddings(api_key=settings.openai_api_key)
    raise ValueError(f"Unknown embedding provider: {provider}")
```

`backend/rag/vectorstore.py`:
```python
from langchain_chroma import Chroma
from backend.rag.embeddings import get_embedding_model

CHROMA_DIR = "./chroma_data"

def get_vectorstore(collection_name: str, embedding_provider: str = "openai") -> Chroma:
    embedding = get_embedding_model(embedding_provider)
    return Chroma(
        collection_name=collection_name,
        embedding_function=embedding,
        persist_directory=CHROMA_DIR,
    )
```

`backend/rag/loader.py`:
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader

def load_and_split(file_path: str, chunk_size: int = 1000, chunk_overlap: int = 200):
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    else:
        loader = TextLoader(file_path, encoding="utf-8")

    documents = loader.load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_documents(documents)
```

- [ ] **Step 2: Write failing test for RAG node**

Append to `backend/tests/test_nodes.py`:
```python
@pytest.mark.asyncio
async def test_rag_node_retrieves_context():
    from backend.nodes.rag_node import RAGNode

    with patch("backend.nodes.rag_node.RAGNode._get_retriever") as mock_get:
        from langchain_core.documents import Document
        mock_retriever = AsyncMock()
        mock_retriever.ainvoke.return_value = [
            Document(page_content="AI is transforming education worldwide."),
            Document(page_content="Personalized learning is a key benefit."),
        ]
        mock_get.return_value = mock_retriever

        node = RAGNode(config={"knowledge_base_id": "kb1", "top_k": 3})
        state: WorkflowState = {
            "input": "AI in education", "messages": [], "context": "",
            "llm_output": "", "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert "AI is transforming" in result["context"]
        assert "Personalized learning" in result["context"]
```

- [ ] **Step 3: Implement rag_node.py**

```python
from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.rag.vectorstore import get_vectorstore

class RAGNode(BaseNode):
    node_type = "rag"

    def _get_retriever(self):
        kb_id = self.config.get("knowledge_base_id", "default")
        top_k = self.config.get("top_k", 3)
        vectorstore = get_vectorstore(collection_name=kb_id)
        return vectorstore.as_retriever(search_kwargs={"k": top_k})

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        query = state.get("input", "")
        retriever = self._get_retriever()

        docs = await retriever.ainvoke(query)
        context = "\n\n".join(doc.page_content for doc in docs)

        state["context"] = context
        state["node_outputs"][self.config.get("node_id", "rag")] = {
            "retrieved_docs": len(docs),
            "context_preview": context[:200],
        }

        return state
```

- [ ] **Step 4: Register RAG node in compiler.py**

Add to `backend/core/compiler.py`:
```python
from backend.nodes.rag_node import RAGNode
node_registry.register(RAGNode)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/rag/ backend/nodes/rag_node.py backend/core/compiler.py backend/tests/test_nodes.py
git commit -m "feat: RAG components (Chroma vectorstore, loader) + RAGNode"
```

---

## Task 11: Knowledge Base API

**Files:**
- Create: `backend/api/knowledge.py`
- Modify: `backend/main.py` — mount router

- [ ] **Step 1: Implement knowledge.py**

```python
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models.knowledge_base import KnowledgeBase
from backend.rag.loader import load_and_split
from backend.rag.vectorstore import get_vectorstore

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])

UPLOAD_DIR = "./uploads"

class KBCreate(BaseModel):
    name: str
    description: str = ""

class KBQuery(BaseModel):
    query: str
    top_k: int = 3

@router.post("", status_code=201)
def create_kb(body: KBCreate, db: Session = Depends(get_db)):
    kb = KnowledgeBase(name=body.name, description=body.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {"id": kb.id, "name": kb.name, "description": kb.description, "doc_count": kb.doc_count}

@router.get("/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"id": kb.id, "name": kb.name, "description": kb.description, "doc_count": kb.doc_count}

@router.post("/{kb_id}/upload")
async def upload_doc(kb_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    docs = load_and_split(file_path)
    vectorstore = get_vectorstore(collection_name=kb_id)
    vectorstore.add_documents(docs)

    kb.doc_count += len(docs)
    db.commit()

    return {"chunks": len(docs), "doc_count": kb.doc_count}

@router.post("/{kb_id}/query")
async def query_kb(kb_id: str, body: KBQuery, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    vectorstore = get_vectorstore(collection_name=kb_id)
    retriever = vectorstore.as_retriever(search_kwargs={"k": body.top_k})
    docs = await retriever.ainvoke(body.query)

    return {"results": [{"content": d.page_content, "metadata": d.metadata} for d in docs]}
```

- [ ] **Step 2: Mount router in main.py**

Add to `backend/main.py`:
```python
from backend.api.knowledge import router as knowledge_router
app.include_router(knowledge_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/knowledge.py backend/main.py
git commit -m "feat: Knowledge base API with document upload and query"
```

---

## Task 12: ReAct Agent Node

**Files:**
- Create: `backend/nodes/agent_node.py`
- Modify: `backend/core/compiler.py` — register node
- Modify: `backend/tests/test_nodes.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_nodes.py`:
```python
@pytest.mark.asyncio
async def test_agent_node_executes():
    from backend.nodes.agent_node import AgentNode

    with patch("backend.nodes.agent_node.AgentNode._build_agent") as mock_build:
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [MagicMock(content="Agent completed the task. Here's the podcast script.")]
        }
        mock_build.return_value = mock_agent

        node = AgentNode(config={
            "provider": "openai",
            "model": "gpt-4o",
            "system_prompt": "You are a helpful agent.",
            "tools": ["rag", "tts"],
        })
        state: WorkflowState = {
            "input": "Make a podcast about AI", "messages": [], "context": "",
            "llm_output": "", "audio_url": "", "node_outputs": {},
        }
        result = await node.execute(state)
        assert result["llm_output"] != ""
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && pytest tests/test_nodes.py::test_agent_node_executes -v`
Expected: FAIL

- [ ] **Step 3: Implement agent_node.py**

```python
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.nodes.llm_node import PROVIDERS

@tool
def search_knowledge(query: str) -> str:
    """Search the knowledge base for relevant information."""
    # In real usage, this would call the RAG vectorstore
    # Placeholder for tool definition — actual retrieval injected at runtime
    return f"Knowledge base results for: {query}"

@tool
def synthesize_audio(text: str) -> str:
    """Convert text to audio using TTS service."""
    # Placeholder — actual TTS call injected at runtime
    return f"Audio synthesized for text of length {len(text)}"

AVAILABLE_TOOLS = {
    "rag": search_knowledge,
    "tts": synthesize_audio,
}

class AgentNode(BaseNode):
    node_type = "agent"

    def _build_agent(self):
        provider_name = self.config.get("provider", "openai")
        model_name = self.config.get("model", "gpt-4o")
        temperature = self.config.get("temperature", 0.7)

        provider = PROVIDERS.get(provider_name)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")

        llm = provider.get_chat_model(model=model_name, temperature=temperature, streaming=True)

        tool_names = self.config.get("tools", [])
        tools = [AVAILABLE_TOOLS[t] for t in tool_names if t in AVAILABLE_TOOLS]

        system_prompt = self.config.get("system_prompt", "You are a helpful AI agent.")

        return create_react_agent(llm, tools, prompt=system_prompt)

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        agent = self._build_agent()

        input_messages = [HumanMessage(content=state["input"])]
        if state.get("context"):
            input_messages.insert(0, SystemMessage(content=f"Context:\n{state['context']}"))

        result = await agent.ainvoke({"messages": input_messages})

        # Extract the last AI message as output
        last_message = result["messages"][-1]
        state["llm_output"] = last_message.content
        state["messages"] = result["messages"]
        state["node_outputs"][self.config.get("node_id", "agent")] = {
            "output": last_message.content,
            "total_messages": len(result["messages"]),
        }

        return state
```

- [ ] **Step 4: Register agent node in compiler.py**

Add to `backend/core/compiler.py`:
```python
from backend.nodes.agent_node import AgentNode
node_registry.register(AgentNode)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_nodes.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nodes/agent_node.py backend/core/compiler.py backend/tests/test_nodes.py
git commit -m "feat: ReAct Agent node with LangGraph create_react_agent"
```

---

## Task 13: Providers API

**Files:**
- Create: `backend/api/providers.py`
- Modify: `backend/main.py` — mount router

- [ ] **Step 1: Implement providers.py**

```python
from fastapi import APIRouter
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.google_provider import GoogleProvider
from backend.providers.deepseek_provider import DeepSeekProvider

router = APIRouter(prefix="/api/providers", tags=["providers"])

ALL_PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "deepseek": DeepSeekProvider(),
}

@router.get("")
def list_providers():
    return [{"name": p.name, "models": p.list_models()} for p in ALL_PROVIDERS.values()]

@router.get("/{provider_name}/models")
def get_models(provider_name: str):
    provider = ALL_PROVIDERS.get(provider_name)
    if not provider:
        return {"error": f"Unknown provider: {provider_name}"}
    return {"provider": provider_name, "models": provider.list_models()}

@router.post("/{provider_name}/test")
async def test_provider(provider_name: str):
    provider = ALL_PROVIDERS.get(provider_name)
    if not provider:
        return {"success": False, "error": f"Unknown provider: {provider_name}"}
    success = await provider.test_connection()
    return {"success": success, "provider": provider_name}
```

- [ ] **Step 2: Mount router in main.py**

Add to `backend/main.py`:
```python
from backend.api.providers import router as providers_router
app.include_router(providers_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/providers.py backend/main.py
git commit -m "feat: Providers API for listing models and testing connections"
```

---

## Task 14: Frontend Project Setup

**Files:**
- Create: `frontend/` — entire Vite + React + TypeScript project
- Create: `frontend/src/types/workflow.ts`

- [ ] **Step 1: Scaffold Vite project**

```bash
cd /Users/mac/Desktop/PIAgent
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install reactflow zustand tailwindcss @tailwindcss/vite axios
```

- [ ] **Step 2: Configure TailwindCSS**

`frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/audio': 'http://localhost:8000',
    },
  },
})
```

`frontend/src/index.css`:
```css
@import "tailwindcss";

body {
  margin: 0;
  background: #0a0f1a;
  color: #e2e8f0;
  font-family: Inter, system-ui, sans-serif;
}

.react-flow__node {
  font-size: 14px;
}
```

- [ ] **Step 3: Create TypeScript types**

`frontend/src/types/workflow.ts`:
```typescript
export type NodeType = 'start' | 'llm' | 'rag' | 'agent' | 'tts' | 'end'

export interface WorkflowNodeData {
  label: string
  nodeType: NodeType
  config: Record<string, unknown>
}

export interface WorkflowGraph {
  nodes: Array<{
    id: string
    type: string
    data: Record<string, unknown>
  }>
  edges: Array<{
    source: string
    target: string
  }>
}

export interface Workflow {
  id: string
  name: string
  description: string
  graph: WorkflowGraph
  created_at: string
}

export type NodeStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface NodeExecutionState {
  nodeId: string
  status: NodeStatus
  duration?: number
  output?: string
  chunks: string[]  // for streaming LLM output
}

export interface SSEEvent {
  type: 'node_start' | 'node_stream' | 'node_end' | 'workflow_end'
  node_id?: string
  node_type?: string
  status?: string
  chunk?: string
  duration?: number
  output?: Record<string, unknown>
}
```

- [ ] **Step 4: Create API service**

`frontend/src/services/api.ts`:
```typescript
import axios from 'axios'
import type { Workflow, WorkflowGraph } from '../types/workflow'

const api = axios.create({ baseURL: '/api' })

export const workflowApi = {
  list: () => api.get<Workflow[]>('/workflows').then(r => r.data),
  get: (id: string) => api.get<Workflow>(`/workflows/${id}`).then(r => r.data),
  create: (data: { name: string; description?: string; graph: WorkflowGraph }) =>
    api.post<Workflow>('/workflows', data).then(r => r.data),
  update: (id: string, data: Partial<Workflow>) =>
    api.put<Workflow>(`/workflows/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/workflows/${id}`),
  run: (id: string, input: string) =>
    api.post<{ run_id: string; status: string; output: unknown }>(`/workflows/${id}/run`, { input }).then(r => r.data),
}

export const providerApi = {
  list: () => api.get('/providers').then(r => r.data),
  models: (name: string) => api.get(`/providers/${name}/models`).then(r => r.data),
  test: (name: string) => api.post(`/providers/${name}/test`).then(r => r.data),
}

export const knowledgeApi = {
  create: (data: { name: string; description?: string }) =>
    api.post('/knowledge-bases', data).then(r => r.data),
  get: (id: string) => api.get(`/knowledge-bases/${id}`).then(r => r.data),
  upload: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/knowledge-bases/${id}/upload`, form).then(r => r.data)
  },
  query: (id: string, query: string, topK = 3) =>
    api.post(`/knowledge-bases/${id}/query`, { query, top_k: topK }).then(r => r.data),
}
```

- [ ] **Step 5: Verify frontend starts**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173 — should see default Vite page.

- [ ] **Step 6: Commit**

```bash
git add frontend/
echo "node_modules" >> frontend/.gitignore
git commit -m "feat: frontend project setup with Vite, React, TypeScript, TailwindCSS"
```

---

## Task 15: Zustand Stores

**Files:**
- Create: `frontend/src/stores/workflowStore.ts`, `frontend/src/stores/debugStore.ts`

- [ ] **Step 1: Implement workflowStore.ts**

```typescript
import { create } from 'zustand'
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from 'reactflow'
import type { WorkflowNodeData } from '../types/workflow'

interface WorkflowState {
  nodes: Node<WorkflowNodeData>[]
  edges: Edge[]
  selectedNodeId: string | null
  workflowId: string | null
  workflowName: string

  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: OnConnect
  addNode: (node: Node<WorkflowNodeData>) => void
  setSelectedNode: (id: string | null) => void
  updateNodeData: (id: string, data: Partial<WorkflowNodeData>) => void
  setWorkflow: (id: string, name: string, nodes: Node<WorkflowNodeData>[], edges: Edge[]) => void
  toGraphJSON: () => { nodes: unknown[]; edges: unknown[] }
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  workflowId: null,
  workflowName: 'Untitled Workflow',

  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) }),

  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),

  onConnect: (connection) =>
    set({ edges: addEdge(connection, get().edges) }),

  addNode: (node) =>
    set({ nodes: [...get().nodes, node] }),

  setSelectedNode: (id) =>
    set({ selectedNodeId: id }),

  updateNodeData: (id, data) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...data } } : n
      ),
    }),

  setWorkflow: (id, name, nodes, edges) =>
    set({ workflowId: id, workflowName: name, nodes, edges }),

  toGraphJSON: () => {
    const { nodes, edges } = get()
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.data.nodeType,
        data: n.data.config,
      })),
      edges: edges.map((e) => ({
        source: e.source,
        target: e.target,
      })),
    }
  },
}))
```

- [ ] **Step 2: Implement debugStore.ts**

```typescript
import { create } from 'zustand'
import type { NodeExecutionState, SSEEvent } from '../types/workflow'

type DebugMode = 'simple' | 'detailed'

interface DebugState {
  isOpen: boolean
  mode: DebugMode
  isRunning: boolean
  inputText: string
  nodeStates: Map<string, NodeExecutionState>
  audioUrl: string | null
  totalDuration: number | null

  toggleDrawer: () => void
  setMode: (mode: DebugMode) => void
  setInputText: (text: string) => void
  startRun: () => void
  handleSSEEvent: (event: SSEEvent) => void
  reset: () => void
}

export const useDebugStore = create<DebugState>((set, get) => ({
  isOpen: false,
  mode: 'detailed',
  isRunning: false,
  inputText: '',
  nodeStates: new Map(),
  audioUrl: null,
  totalDuration: null,

  toggleDrawer: () => set({ isOpen: !get().isOpen }),

  setMode: (mode) => set({ mode }),

  setInputText: (text) => set({ inputText: text }),

  startRun: () =>
    set({ isRunning: true, nodeStates: new Map(), audioUrl: null, totalDuration: null }),

  handleSSEEvent: (event) => {
    const states = new Map(get().nodeStates)

    if (event.type === 'node_start' && event.node_id) {
      states.set(event.node_id, {
        nodeId: event.node_id,
        status: 'running',
        chunks: [],
      })
      set({ nodeStates: states })
    }

    if (event.type === 'node_stream' && event.node_id) {
      const existing = states.get(event.node_id)
      if (existing && event.chunk) {
        existing.chunks.push(event.chunk)
        states.set(event.node_id, { ...existing })
        set({ nodeStates: states })
      }
    }

    if (event.type === 'node_end' && event.node_id) {
      const existing = states.get(event.node_id)
      if (existing) {
        existing.status = 'completed'
        existing.duration = event.duration
        if (event.output?.audio_url) {
          set({ audioUrl: event.output.audio_url as string })
        }
        states.set(event.node_id, { ...existing })
        set({ nodeStates: states })
      }
    }

    if (event.type === 'workflow_end') {
      set({ isRunning: false, totalDuration: event.duration ?? null })
    }
  },

  reset: () =>
    set({ isRunning: false, nodeStates: new Map(), audioUrl: null, totalDuration: null }),
}))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/
git commit -m "feat: Zustand stores for workflow canvas and debug state"
```

---

## Task 16: Custom Nodes + Node Registry

**Files:**
- Create: all files in `frontend/src/components/nodes/`

- [ ] **Step 1: Create shared node wrapper style**

Each custom node follows the same pattern: colored border, icon, label, handles. Create all six nodes.

`frontend/src/components/nodes/StartNode.tsx`:
```tsx
import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function StartNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[160px] ${selected ? 'border-blue-400' : 'border-blue-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-blue-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">入</span>
        <span className="text-slate-100 text-sm font-semibold">用户输入</span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-blue-500 !w-3 !h-3" />
    </div>
  )
}
```

`frontend/src/components/nodes/LLMNode.tsx`:
```tsx
import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function LLMNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[180px] ${selected ? 'border-purple-400' : 'border-purple-500'}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="bg-purple-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">🧠</span>
        <span className="text-slate-100 text-sm font-semibold">LLM 对话</span>
      </div>
      <div className="text-xs text-slate-400">
        {(data.config?.provider as string) || 'openai'} / {(data.config?.model as string) || 'gpt-4o'}
      </div>
      <Handle type="target" position={Position.Left} className="!bg-purple-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} className="!bg-purple-500 !w-3 !h-3" />
    </div>
  )
}
```

`frontend/src/components/nodes/RAGNode.tsx`:
```tsx
import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function RAGNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[170px] ${selected ? 'border-green-400' : 'border-green-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-green-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">📚</span>
        <span className="text-slate-100 text-sm font-semibold">RAG 知识检索</span>
      </div>
      <Handle type="target" position={Position.Left} className="!bg-green-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} className="!bg-green-500 !w-3 !h-3" />
    </div>
  )
}
```

`frontend/src/components/nodes/AgentNode.tsx`:
```tsx
import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function AgentNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[170px] ${selected ? 'border-pink-400' : 'border-pink-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-pink-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">🤖</span>
        <span className="text-slate-100 text-sm font-semibold">ReAct Agent</span>
      </div>
      <Handle type="target" position={Position.Left} className="!bg-pink-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} className="!bg-pink-500 !w-3 !h-3" />
    </div>
  )
}
```

`frontend/src/components/nodes/TTSNode.tsx`:
```tsx
import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function TTSNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[170px] ${selected ? 'border-yellow-400' : 'border-yellow-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-yellow-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">🎙</span>
        <span className="text-slate-100 text-sm font-semibold">TTS 音频合成</span>
      </div>
      <Handle type="target" position={Position.Left} className="!bg-yellow-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} className="!bg-yellow-500 !w-3 !h-3" />
    </div>
  )
}
```

`frontend/src/components/nodes/EndNode.tsx`:
```tsx
import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function EndNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 ${selected ? 'border-slate-400' : 'border-slate-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-slate-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">⏹</span>
        <span className="text-slate-100 text-sm font-semibold">结束</span>
      </div>
      <Handle type="target" position={Position.Left} className="!bg-slate-500 !w-3 !h-3" />
    </div>
  )
}
```

`frontend/src/components/nodes/index.ts`:
```typescript
import { StartNode } from './StartNode'
import { LLMNode } from './LLMNode'
import { RAGNode } from './RAGNode'
import { AgentNode } from './AgentNode'
import { TTSNode } from './TTSNode'
import { EndNode } from './EndNode'

export const nodeTypes = {
  start: StartNode,
  llm: LLMNode,
  rag: RAGNode,
  agent: AgentNode,
  tts: TTSNode,
  end: EndNode,
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/nodes/
git commit -m "feat: custom React Flow node components for all 6 node types"
```

---

## Task 17: Canvas + Node Library + Node Config

**Files:**
- Create: `frontend/src/components/canvas/WorkflowCanvas.tsx`, `frontend/src/components/canvas/CanvasToolbar.tsx`
- Create: `frontend/src/components/panels/NodeLibrary.tsx`, `frontend/src/components/panels/NodeConfig.tsx`
- Create: `frontend/src/hooks/useDnD.ts`

- [ ] **Step 1: Implement useDnD hook**

`frontend/src/hooks/useDnD.ts`:
```typescript
import { useCallback, useRef } from 'react'
import type { ReactFlowInstance } from 'reactflow'
import type { NodeType, WorkflowNodeData } from '../types/workflow'
import { useWorkflowStore } from '../stores/workflowStore'

let nodeId = 0
const getId = () => `node_${++nodeId}`

export function useDnD() {
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null)
  const addNode = useWorkflowStore((s) => s.addNode)

  const onInit = useCallback((instance: ReactFlowInstance) => {
    reactFlowInstance.current = instance
  }, [])

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      const nodeType = event.dataTransfer.getData('application/piagent-node') as NodeType
      if (!nodeType || !reactFlowInstance.current) return

      const position = reactFlowInstance.current.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const labels: Record<NodeType, string> = {
        start: '用户输入',
        llm: 'LLM 对话',
        rag: 'RAG 知识检索',
        agent: 'ReAct Agent',
        tts: 'TTS 音频合成',
        end: '结束',
      }

      addNode({
        id: getId(),
        type: nodeType,
        position,
        data: {
          label: labels[nodeType],
          nodeType,
          config: {},
        } satisfies WorkflowNodeData,
      })
    },
    [addNode]
  )

  return { onInit, onDragOver, onDrop }
}
```

- [ ] **Step 2: Implement WorkflowCanvas**

`frontend/src/components/canvas/WorkflowCanvas.tsx`:
```tsx
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow'
import 'reactflow/dist/style.css'
import { useWorkflowStore } from '../../stores/workflowStore'
import { nodeTypes } from '../nodes'
import { useDnD } from '../../hooks/useDnD'
import { CanvasToolbar } from './CanvasToolbar'

export function WorkflowCanvas() {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, setSelectedNode } = useWorkflowStore()
  const { onInit, onDragOver, onDrop } = useDnD()

  return (
    <div className="flex-1 relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={onInit}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onNodeClick={(_, node) => setSelectedNode(node.id)}
        onPaneClick={() => setSelectedNode(null)}
        nodeTypes={nodeTypes}
        fitView
        className="bg-[#0a0f1a]"
      >
        <Background color="#1e293b" gap={24} size={1} />
        <Controls className="!bg-slate-800 !border-slate-700" />
        <MiniMap className="!bg-slate-900" nodeColor="#334155" />
      </ReactFlow>
      <CanvasToolbar />
    </div>
  )
}
```

`frontend/src/components/canvas/CanvasToolbar.tsx`:
```tsx
import { useDebugStore } from '../../stores/debugStore'

export function CanvasToolbar() {
  const toggleDrawer = useDebugStore((s) => s.toggleDrawer)

  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2 flex gap-4 items-center z-10">
      <button
        onClick={toggleDrawer}
        className="bg-blue-500 text-white text-sm px-3 py-1 rounded-md hover:bg-blue-600"
      >
        ▶ 调试
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Implement NodeLibrary**

`frontend/src/components/panels/NodeLibrary.tsx`:
```tsx
import type { NodeType } from '../../types/workflow'

const NODE_GROUPS = [
  {
    label: '基础节点',
    items: [
      { type: 'start' as NodeType, icon: '入', label: '用户输入', color: 'bg-blue-500' },
      { type: 'end' as NodeType, icon: '⏹', label: '结束', color: 'bg-slate-500' },
    ],
  },
  {
    label: '大模型',
    items: [
      { type: 'llm' as NodeType, icon: '🧠', label: 'LLM 对话', color: 'bg-purple-500' },
      { type: 'agent' as NodeType, icon: '🤖', label: 'ReAct Agent', color: 'bg-pink-500' },
    ],
  },
  {
    label: '工具',
    items: [
      { type: 'rag' as NodeType, icon: '📚', label: 'RAG 知识检索', color: 'bg-green-500' },
      { type: 'tts' as NodeType, icon: '🎙', label: 'TTS 音频合成', color: 'bg-yellow-500' },
    ],
  },
]

export function NodeLibrary() {
  const onDragStart = (event: React.DragEvent, nodeType: NodeType) => {
    event.dataTransfer.setData('application/piagent-node', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="w-[220px] bg-slate-900 border-r border-slate-800 p-4 overflow-y-auto shrink-0">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">节点库</div>
      {NODE_GROUPS.map((group) => (
        <div key={group.label} className="mb-4">
          <div className="text-xs text-slate-600 mb-1.5">{group.label}</div>
          {group.items.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => onDragStart(e, item.type)}
              className="bg-slate-800 border border-slate-700 rounded-lg p-2.5 mb-1.5 flex items-center gap-2 cursor-grab active:cursor-grabbing hover:border-slate-600"
            >
              <span className={`${item.color} text-white w-6 h-6 rounded flex items-center justify-center text-xs`}>
                {item.icon}
              </span>
              <span className="text-slate-200 text-sm">{item.label}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Implement NodeConfig**

`frontend/src/components/panels/NodeConfig.tsx`:
```tsx
import { useWorkflowStore } from '../../stores/workflowStore'

export function NodeConfig() {
  const { nodes, selectedNodeId, updateNodeData } = useWorkflowStore()
  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

  if (!selectedNode) {
    return (
      <div className="w-[260px] bg-slate-900 border-l border-slate-800 p-4 shrink-0">
        <div className="text-xs text-slate-500 uppercase tracking-wider mb-4">节点配置</div>
        <div className="text-sm text-slate-600 text-center mt-8">选择一个节点查看配置</div>
      </div>
    )
  }

  const { data } = selectedNode
  const config = data.config as Record<string, unknown>

  const updateConfig = (key: string, value: unknown) => {
    updateNodeData(selectedNode.id, {
      config: { ...config, [key]: value },
    })
  }

  return (
    <div className="w-[260px] bg-slate-900 border-l border-slate-800 p-4 shrink-0 overflow-y-auto">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-4">节点配置</div>
      <div className="text-sm text-slate-200 font-semibold mb-4">{data.label}</div>

      {data.nodeType === 'llm' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">模型提供商</span>
            <select
              value={(config.provider as string) || 'openai'}
              onChange={(e) => updateConfig('provider', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google</option>
              <option value="deepseek">DeepSeek</option>
            </select>
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">模型</span>
            <input
              value={(config.model as string) || 'gpt-4o'}
              onChange={(e) => updateConfig('model', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">Temperature: {(config.temperature as number) ?? 0.7}</span>
            <input
              type="range" min="0" max="1" step="0.1"
              value={(config.temperature as number) ?? 0.7}
              onChange={(e) => updateConfig('temperature', parseFloat(e.target.value))}
              className="w-full"
            />
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">System Prompt</span>
            <textarea
              value={(config.system_prompt as string) || ''}
              onChange={(e) => updateConfig('system_prompt', e.target.value)}
              rows={4}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 resize-none"
            />
          </label>
        </>
      )}

      {data.nodeType === 'rag' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">知识库 ID</span>
            <input
              value={(config.knowledge_base_id as string) || ''}
              onChange={(e) => updateConfig('knowledge_base_id', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">Top-K: {(config.top_k as number) ?? 3}</span>
            <input
              type="range" min="1" max="10" step="1"
              value={(config.top_k as number) ?? 3}
              onChange={(e) => updateConfig('top_k', parseInt(e.target.value))}
              className="w-full"
            />
          </label>
        </>
      )}

      {data.nodeType === 'tts' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">TTS 提供商</span>
            <select
              value={(config.provider as string) || 'fish_audio'}
              onChange={(e) => updateConfig('provider', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              <option value="fish_audio">Fish Audio</option>
            </select>
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">音色 ID</span>
            <input
              value={(config.voice as string) || 'default'}
              onChange={(e) => updateConfig('voice', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
        </>
      )}

      {data.nodeType === 'agent' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">模型提供商</span>
            <select
              value={(config.provider as string) || 'openai'}
              onChange={(e) => updateConfig('provider', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google</option>
              <option value="deepseek">DeepSeek</option>
            </select>
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">System Prompt</span>
            <textarea
              value={(config.system_prompt as string) || ''}
              onChange={(e) => updateConfig('system_prompt', e.target.value)}
              rows={4}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 resize-none"
            />
          </label>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/canvas/ frontend/src/components/panels/ frontend/src/hooks/
git commit -m "feat: WorkflowCanvas, NodeLibrary, NodeConfig, drag-and-drop"
```

---

## Task 18: SSE Hook

**Files:**
- Create: `frontend/src/hooks/useSSE.ts`

- [ ] **Step 1: Implement useSSE**

`frontend/src/hooks/useSSE.ts`:
```typescript
import { useCallback, useRef } from 'react'
import { useDebugStore } from '../stores/debugStore'
import type { SSEEvent } from '../types/workflow'

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const handleEvent = useDebugStore((s) => s.handleSSEEvent)

  const connect = useCallback(
    (workflowId: string, runId: string) => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }

      const url = `/api/workflows/${workflowId}/runs/${runId}/events`
      const es = new EventSource(url)
      eventSourceRef.current = es

      const handleMessage = (eventType: string) => (event: MessageEvent) => {
        const data: SSEEvent = JSON.parse(event.data)
        handleEvent(data)
      }

      es.addEventListener('node_start', handleMessage('node_start'))
      es.addEventListener('node_stream', handleMessage('node_stream'))
      es.addEventListener('node_end', handleMessage('node_end'))
      es.addEventListener('workflow_end', (event) => {
        const data: SSEEvent = JSON.parse(event.data)
        handleEvent(data)
        es.close()
      })

      es.onerror = () => {
        es.close()
      }
    },
    [handleEvent]
  )

  const disconnect = useCallback(() => {
    eventSourceRef.current?.close()
    eventSourceRef.current = null
  }, [])

  return { connect, disconnect }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useSSE.ts
git commit -m "feat: useSSE hook for real-time workflow execution events"
```

---

## Task 19: Debug Drawer + Audio Player

**Files:**
- Create: `frontend/src/components/debug/DebugDrawer.tsx`, `frontend/src/components/debug/ExecutionTimeline.tsx`, `frontend/src/components/debug/NodeStatusCard.tsx`, `frontend/src/components/debug/AudioPlayer.tsx`

- [ ] **Step 1: Implement NodeStatusCard**

`frontend/src/components/debug/NodeStatusCard.tsx`:
```tsx
import type { NodeExecutionState } from '../../types/workflow'

export function NodeStatusCard({ state }: { state: NodeExecutionState }) {
  const statusIcon = {
    pending: '○',
    running: '⟳',
    completed: '✓',
    failed: '✗',
  }[state.status]

  const statusColor = {
    pending: 'text-slate-500',
    running: 'text-purple-400',
    completed: 'text-green-400',
    failed: 'text-red-400',
  }[state.status]

  const borderColor = {
    pending: 'border-slate-800',
    running: 'border-purple-500/30',
    completed: 'border-green-500/30',
    failed: 'border-red-500/30',
  }[state.status]

  return (
    <div className={`bg-slate-950 border ${borderColor} rounded-lg p-3 mb-2`}>
      <div className="flex justify-between items-center mb-1">
        <div className="flex items-center gap-2">
          <span className={`${statusColor} ${state.status === 'running' ? 'animate-spin' : ''}`}>
            {statusIcon}
          </span>
          <span className="text-slate-200 text-sm font-medium">{state.nodeId}</span>
          {state.status === 'running' && state.chunks.length > 0 && (
            <span className="bg-purple-500/20 text-purple-400 text-[10px] px-1.5 py-0.5 rounded">
              streaming
            </span>
          )}
        </div>
        {state.duration && (
          <span className="text-slate-600 text-xs">{state.duration}s</span>
        )}
      </div>
      {state.chunks.length > 0 && (
        <div className="text-xs text-purple-300 bg-slate-800 rounded p-2 mt-1 max-h-16 overflow-hidden">
          {state.chunks.join('')}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Implement ExecutionTimeline**

`frontend/src/components/debug/ExecutionTimeline.tsx`:
```tsx
import { useDebugStore } from '../../stores/debugStore'
import { NodeStatusCard } from './NodeStatusCard'

export function ExecutionTimeline() {
  const nodeStates = useDebugStore((s) => s.nodeStates)

  return (
    <div className="flex-1 p-4 overflow-y-auto">
      <div className="text-xs text-slate-400 mb-3">执行链路</div>
      {Array.from(nodeStates.values()).map((state) => (
        <NodeStatusCard key={state.nodeId} state={state} />
      ))}
      {nodeStates.size === 0 && (
        <div className="text-sm text-slate-600 text-center mt-8">等待运行...</div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Implement AudioPlayer**

`frontend/src/components/debug/AudioPlayer.tsx`:
```tsx
import { useRef, useState, useEffect } from 'react'
import { useDebugStore } from '../../stores/debugStore'

export function AudioPlayer() {
  const audioUrl = useDebugStore((s) => s.audioUrl)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    if (audioUrl && audioRef.current) {
      audioRef.current.load()
    }
  }, [audioUrl])

  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play()
    }
    setIsPlaying(!isPlaying)
  }

  const formatTime = (t: number) => {
    const m = Math.floor(t / 60)
    const s = Math.floor(t % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="w-[280px] p-4 border-l border-slate-800">
      <div className="text-xs text-slate-400 mb-3">最终输出</div>
      <div className={`bg-slate-950 border border-slate-700 rounded-xl p-4 ${!audioUrl ? 'opacity-40' : ''}`}>
        <div className="text-sm text-slate-400 mb-3">🎧 AI 播客播放器</div>
        <audio
          ref={audioRef}
          src={audioUrl || undefined}
          onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime ?? 0)}
          onLoadedMetadata={() => setDuration(audioRef.current?.duration ?? 0)}
          onEnded={() => setIsPlaying(false)}
        />
        <div className="bg-slate-800 rounded-full h-1 mb-3 cursor-pointer"
          onClick={(e) => {
            if (!audioRef.current || !duration) return
            const rect = e.currentTarget.getBoundingClientRect()
            const ratio = (e.clientX - rect.left) / rect.width
            audioRef.current.currentTime = ratio * duration
          }}
        >
          <div
            className="bg-blue-500 rounded-full h-full"
            style={{ width: duration ? `${(currentTime / duration) * 100}%` : '0%' }}
          />
        </div>
        <div className="flex justify-between items-center">
          <span className="text-slate-600 text-xs">{formatTime(currentTime)}</span>
          <button
            onClick={togglePlay}
            disabled={!audioUrl}
            className="bg-blue-500 text-white w-8 h-8 rounded-full flex items-center justify-center disabled:opacity-50"
          >
            {isPlaying ? '⏸' : '▶'}
          </button>
          <span className="text-slate-600 text-xs">{duration ? formatTime(duration) : '--:--'}</span>
        </div>
      </div>
      {!audioUrl && (
        <div className="text-xs text-slate-600 text-center mt-3">等待工作流执行完成...</div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Implement DebugDrawer**

`frontend/src/components/debug/DebugDrawer.tsx`:
```tsx
import { useDebugStore } from '../../stores/debugStore'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useSSE } from '../../hooks/useSSE'
import { workflowApi } from '../../services/api'
import { ExecutionTimeline } from './ExecutionTimeline'
import { AudioPlayer } from './AudioPlayer'

export function DebugDrawer() {
  const {
    isOpen, mode, isRunning, inputText,
    toggleDrawer, setMode, setInputText, startRun,
  } = useDebugStore()
  const { workflowId, toGraphJSON } = useWorkflowStore()
  const { connect } = useSSE()

  if (!isOpen) return null

  const handleRun = async () => {
    if (!workflowId || !inputText.trim()) return
    startRun()

    const result = await workflowApi.run(workflowId, inputText)
    connect(workflowId, result.run_id)
  }

  return (
    <div className="border-t border-slate-700 bg-slate-900" style={{ height: '40vh' }}>
      {/* Header */}
      <div className="bg-slate-800 px-5 py-3 flex justify-between items-center border-b border-slate-700">
        <div className="flex items-center gap-3">
          <span className="text-slate-100 text-sm font-semibold">调试运行</span>
          <div className="flex gap-1">
            <button
              onClick={() => setMode('simple')}
              className={`text-xs px-2.5 py-1 rounded ${mode === 'simple' ? 'bg-blue-500 text-white' : 'bg-slate-900 text-slate-400'}`}
            >
              简洁
            </button>
            <button
              onClick={() => setMode('detailed')}
              className={`text-xs px-2.5 py-1 rounded ${mode === 'detailed' ? 'bg-blue-500 text-white' : 'bg-slate-900 text-slate-400'}`}
            >
              详细
            </button>
          </div>
        </div>
        <button onClick={toggleDrawer} className="text-slate-500 hover:text-slate-300 text-lg">✕</button>
      </div>

      {/* Body */}
      <div className="flex h-[calc(100%-48px)]">
        {/* Input */}
        <div className="w-[300px] p-4 border-r border-slate-800">
          <div className="text-xs text-slate-400 mb-2">输入文本</div>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="请输入播客主题..."
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm text-slate-200 resize-none h-24"
          />
          <button
            onClick={handleRun}
            disabled={isRunning || !inputText.trim()}
            className="w-full mt-3 bg-blue-500 text-white rounded-lg py-2 text-sm hover:bg-blue-600 disabled:opacity-50"
          >
            {isRunning ? '运行中...' : '▶ 开始运行'}
          </button>
        </div>

        {/* Timeline (detailed mode only) */}
        {mode === 'detailed' && <ExecutionTimeline />}

        {/* Audio output */}
        <AudioPlayer />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/debug/
git commit -m "feat: DebugDrawer with ExecutionTimeline, NodeStatusCard, AudioPlayer"
```

---

## Task 20: App Layout + Integration

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Wire everything together in App.tsx**

```tsx
import { ReactFlowProvider } from 'reactflow'
import { NodeLibrary } from './components/panels/NodeLibrary'
import { WorkflowCanvas } from './components/canvas/WorkflowCanvas'
import { NodeConfig } from './components/panels/NodeConfig'
import { DebugDrawer } from './components/debug/DebugDrawer'

export default function App() {
  return (
    <ReactFlowProvider>
      <div className="h-screen flex flex-col">
        {/* Header */}
        <header className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center gap-3 shrink-0">
          <span className="text-blue-400 font-bold text-lg">PIAgent</span>
          <span className="text-slate-500 text-sm">AI Agent 工作流编排平台</span>
        </header>

        {/* Main content: 3-column layout */}
        <div className="flex flex-1 overflow-hidden">
          <NodeLibrary />
          <WorkflowCanvas />
          <NodeConfig />
        </div>

        {/* Debug drawer */}
        <DebugDrawer />
      </div>
    </ReactFlowProvider>
  )
}
```

- [ ] **Step 2: Verify frontend renders**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173 — should see:
- Header with "PIAgent"
- Left sidebar with draggable node library
- Center canvas (empty, with grid background)
- Right sidebar (showing "选择一个节点查看配置")
- Debug button in canvas toolbar

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: App layout with 3-column design and debug drawer"
```

---

## Task 21: End-to-End Smoke Test

**Files:**
- No new files — manual verification

- [ ] **Step 1: Start backend**

```bash
cd backend && uvicorn backend.main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Verify health endpoint**

```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Create a workflow via API**

```bash
curl -X POST http://localhost:8000/api/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI Podcast Demo",
    "graph": {
      "nodes": [
        {"id": "start_1", "type": "start", "data": {}},
        {"id": "llm_1", "type": "llm", "data": {"provider": "openai", "model": "gpt-4o", "system_prompt": "Generate a podcast script."}},
        {"id": "tts_1", "type": "tts", "data": {"provider": "fish_audio"}},
        {"id": "end_1", "type": "end", "data": {}}
      ],
      "edges": [
        {"source": "start_1", "target": "llm_1"},
        {"source": "llm_1", "target": "tts_1"},
        {"source": "tts_1", "target": "end_1"}
      ]
    }
  }'
```

- [ ] **Step 5: Test drag-and-drop in browser**

Open http://localhost:5173:
1. Drag "用户输入" node onto canvas
2. Drag "LLM 对话" node onto canvas
3. Connect them by dragging from right handle to left handle
4. Click on LLM node — verify config panel shows on right
5. Click "调试" button — verify drawer opens at bottom

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat: PIAgent v1 — AI Agent workflow orchestration platform"
```
