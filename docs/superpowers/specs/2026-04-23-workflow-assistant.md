# Workflow Assistant Spec

**Date**: 2026-04-23
**Status**: Design approved, not yet implemented
**Supersedes**: the ReAct graph-builder harness (to be removed on branch `codex/remove-harness`)

## Context

Previous work attempted a full ReAct agent that generated valid WorkflowGraph v2 diffs with self-validation loops. That approach hit a complexity wall: producing structurally valid graphs with reliable self-correction is a frontier problem, and the cost of failure (a broken graph) was high.

The `mini-harness` library at `/Users/mac/Desktop/mini-harness` was extracted during that effort. It is a clean, reusable ReAct agent runtime built on LangGraph's `create_react_agent`, with config-driven tool registry, skills-as-prompt mechanism, loop detection, summarization, and SSE streaming. It remains an independent repo and will be consumed by PIAgent as a library dependency.

## Goal

A read-only conversational assistant, anchored to the canvas, that observes the current workflow and answers user questions or offers textual suggestions. The assistant **never** modifies the graph.

## Hard scope rules

- Assistant observes the current graph, node configs, providers, knowledge bases, and run history
- Assistant answers questions and offers textual suggestions / hints
- Assistant **NEVER** modifies the graph — no apply-diff, no one-click-fix, no structured mutation output
- Suggestions are plain prose; the user reads and manually applies
- Out-of-scope questions (general coding, unrelated knowledge) are politely refused

Rationale: the hard problem in the previous iteration was generating valid structured graph diffs with self-validation. Read-only mode eliminates that entire failure class while still showcasing ReAct + tool calling + streaming + context-aware agents.

## Product shape

- **Entry point**: a bubble icon docked to the lower-right of the canvas, always visible. Click to slide out a ~400px right panel. Does not occupy main canvas space; user can toggle open/closed at any time.
- **Interaction**: pure chat. User types, presses Enter, sees streaming reply.
- **Inline tool-call traces**: the assistant's reply interleaves lightweight one-liners for each tool invocation, e.g. `📖 读取了 graph` / `🔍 查看了 llm_1 的配置`. Each trace line is collapsible — click to expand full tool args and result. Keeps the conversation compact by default while preserving full transparency on demand.
- **Session binding**: one workflow = one session. Switching workflow swaps sessions automatically. Closing the panel does not destroy the session; reopening resumes the conversation.
- **Explicitly excluded from v1 UI**: apply-suggestion buttons, any diff-generation entry, multi-session list / history branching, file upload, voice input, image input.

## Architecture

```
mini-harness (independent repo, LangGraph + ReAct runtime)
     |
     | imported as local editable dependency
     v
PIAgent backend/assistant/ (registers domain tools, system prompt, skills)
     |
     | exposed over /api/assistant/sessions/{workflow_id}/stream (SSE)
     v
frontend ChatPanel (right-side slide-out on canvas)
```

## Mini-harness integration

### Required mini-harness change (one small API)

mini-harness's `get_app_config()` is a singleton loaded from its package root `config.yaml`. PIAgent needs its own config. Add:

```python
# mini_harness/config/__init__.py
def set_app_config(cfg: AppConfig) -> None:
    global _config_instance
    _config_instance = cfg
```

PIAgent calls `set_app_config(load_config("backend/assistant/mini_harness.yaml"))` at FastAPI startup.

### How PIAgent injects its tools

mini-harness's `ToolRegistry.register(tool_instance)` (registry.py:15) already supports direct instance registration. PIAgent builds tool instances with DB session + workflow_id captured in closures, then registers them before calling `create_agent()`. No mini-harness change needed here.

### Builtin tools NOT exposed to assistant

mini-harness ships `bash`, `python`, `read_file`, `write_file` (for coding-agent use cases). These must not be registered for the PIAgent assistant — the config has `tools: []` and PIAgent injects only its own read-only tools at runtime.

## PIAgent file layout

```
backend/assistant/
├── __init__.py
├── mini_harness.yaml           # PIAgent-specific mini-harness config
├── skills/
│   └── piagent_context.md      # Minimal skill: node types, template syntax, common pitfalls
├── tools.py                    # 8 read-only domain tools (BaseTool subclasses)
├── prompt.py                   # ASSISTANT_SYSTEM_PROMPT constant
├── session.py                  # Per-workflow session state (reuses AssistantSession model)
├── agent.py                    # build_assistant_agent(db, workflow_id) factory
└── routes.py                   # FastAPI router + SSE event translation
```

### `mini_harness.yaml`

```yaml
config_version: 1
models:
  - name: default
    model: gpt-4o-mini
    api_key: ${OPENAI_API_KEY}
tools: []                       # Intentionally empty; PIAgent injects at runtime
skills:
  enabled: true
  directory: backend/assistant/skills
sandbox:
  use: mini_harness.sandbox.local:LocalSandboxProvider
  work_dir: ./workspace
  allow_bash: false
loop_detection:
  enabled: true
  warn_threshold: 3
  hard_limit: 5
summarization:
  enabled: true
  trigger_messages: 30
  keep_messages: 10
clarification:
  enabled: false                # Assistant asks in prose, not via dedicated tool
token_usage:
  enabled: true
```

### Tool surface (all read-only)

| Tool | Input | Returns | Purpose |
|---|---|---|---|
| `get_current_graph` | — | Full v2 graph (nodes, edges, configs) | Explain workflow, find issues |
| `get_node_config` | `node_id` | Single node's full config | Deep-dive on a node |
| `list_node_types` | — | All node types + schemas from `node_registry` | "Which node should I use?" |
| `list_providers` | — | Configured providers (API keys redacted) | Diagnose LLM/embedding config |
| `list_knowledge_bases` | — | KB list | "Can I do RAG here?" |
| `peek_knowledge_base` | `kb_id, query?` | Sample chunks | Judge KB coverage |
| `get_recent_runs` | `workflow_id, limit` | Recent WorkflowRun summaries | "Why did yesterday's run fail?" |
| `get_run_events` | `run_id` | SSE event sequence of that run | Pinpoint failing node |

Each tool is a factory: `make_tool(db_session, workflow_id) -> BaseTool`. The closure captures request context so tools stay stateless from mini-harness's perspective.

**Explicitly forbidden**: any tool that mutates the graph (`update_node`, `add_node`, `delete_node`, `apply_graph`, `validate_graph_as_final`). Adding one breaks the scope rule.

### System prompt skeleton

```
你是 PIAgent 画布上的工作流助手。用户正在编辑一个可视化 AI 工作流。

你的职责：
1. 观察当前 workflow 的结构和配置（通过工具调用）
2. 回答用户关于这个 workflow 的问题
3. 指出潜在问题、解释节点行为、建议改进方向

硬约束：
- 你只做观察和建议，不修改 graph
- 当用户说"帮我改一下"，你应回复"我不能直接改，但你可以这样改：……（描述步骤）"
- 只回答与当前 workflow、节点、provider、知识库、运行记录相关的问题
- 其他问题（写代码、闲聊、通用知识）礼貌拒答并建议用 ChatGPT
- 回答用中文，简洁，默认用户是开发者

工具使用原则：
- 用户问题涉及具体节点/运行时，先调用工具拿到事实，再回答
- 别问用户要信息，工具能查到的自己查
```

### `skills/piagent_context.md` (minimal v1)

```markdown
# PIAgent Workflow Assistant Context

你正在协助用户编辑 PIAgent 可视化工作流。

## 可用节点类型
- Start：工作流入口，定义输入变量
- LLM：调用语言模型，支持多 provider
- RAG：从知识库检索 + 生成
- TTS：文本转语音
- If-Else：条件分支
- Iteration：循环遍历列表
- End：工作流终点，输出结果

## 模板语法
节点 config 里可以用 {{nodeId.fieldName}} 引用上游节点输出。

## 常见陷阱
- RAG 节点未绑定 KB → 查询无结果
- LLM 节点 prompt 引用不存在的上游 → 运行时报错
- TTS 输入必须是纯文本字符串，不能是 JSON 对象
```

### Session model

Reuse or reintroduce `AssistantSession` (SQLAlchemy model):
- `id: int`
- `workflow_id: int` (FK)
- `messages_json: str` (serialized conversation history)
- `updated_at: datetime`

One row per workflow. No multi-session support in v1.

### SSE event types (backend → frontend)

- `session.started` — session init
- `message.delta` — streaming text chunk from assistant
- `tool.call` — `{ tool, args, call_id }`
- `tool.result` — `{ call_id, summary }` (full body not inlined; frontend can fetch on demand later)
- `message.done` — turn complete
- `error` — error state

Reuse mini-harness's existing event structure where possible; translate at the route layer.

## Frontend changes

```
frontend/src/components/assistant/
└── ChatPanel.tsx              # Right-side slide-out, message list, input box

frontend/src/services/
└── assistantApi.ts            # POST /api/assistant/sessions/{id}/stream + SSE client

frontend/src/stores/
└── assistantStore.ts          # Messages, streaming state, panel open/closed

frontend/src/components/canvas/WorkflowCanvas.tsx  # Add bubble button in lower-right corner
```

## Other backend changes

- `backend/main.py`: on startup, `set_app_config(load_config(...))`; `include_router(assistant.router)`
- `backend/requirements.txt` (or pyproject): add `mini-harness @ file:///Users/mac/Desktop/mini-harness` (local editable; switch to git URL once pushed)
- `backend/models/__init__.py`: add `AssistantSession` (new or restored from removed `AgentSession`)

## Evaluation

Build a fixture set: 20 hand-crafted workflows + typical questions. Examples:
- RAG node with no KB bound → "Why no results?"
- LLM node prompt references `{{llm_2.output}}` but `llm_2` doesn't exist → "Why does this error?"
- TTS node reads from a JSON-returning LLM → "Will this run?"

Manual scoring: 0 (wrong) / 1 (partially correct) / 2 (accurate). Target metric for resume/interview: accuracy rate on the 20-question set.

## Implementation order

1. **mini-harness**: add `set_app_config()` + one unit test. Bump to 0.1.1.
2. **PIAgent backend skeleton**: all files under `backend/assistant/`, tools return mock data. End-to-end: route accepts POST, SSE stream flows, dummy response returns.
3. **Tools real data**: fill in 8 tools one by one, each with a unit test against the in-memory SQLite fixture.
4. **Frontend**: ChatPanel + store + bubble trigger.
5. **Eval set**: 10 fixtures first, scale to 20.
6. **Polish**: expand skills, tune loop detection thresholds, optional token usage display.

Target for v1: within two weeks, a demo-able assistant conversation that shows multi-turn tool calling on a real workflow.

## Interview narrative

> "I extracted a reusable agent runtime library (mini-harness) built on LangGraph, then consumed it from PIAgent as a dependency. PIAgent registers domain-specific read-only tools with mini-harness's registry and exposes the assistant over SSE. I deliberately chose a read-only advisor pattern over an autonomous graph-modifying agent, after evaluating the reliability/complexity tradeoffs on the earlier iteration."

Two GitHub repos, clean separation of concerns, direct alignment with AI Agent developer role skills (LangGraph, ReAct, tool calling, streaming, context-aware agents).
