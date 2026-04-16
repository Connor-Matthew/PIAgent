# Agent Tool-Use 实现方案

## 目标

用户输入一句话 → Agent 自动规划 → 画布逐步渲染节点和连线 → 自动执行 → 结果流式展示。

分两个 Phase 实现。

---

## Phase 1: Agent 节点支持真正的 Tool-Use

**目标：** 用户手动搭一个包含 Agent 节点的工作流，运行时 Agent 能自主调用工具，前端能看到 think → act → observe 的全过程。

### 1.1 内置工具实现

新建 `backend/tools/` 目录：

```
backend/tools/
├── __init__.py          # 工具注册表（TOOL_REGISTRY）
├── base.py              # 工具基类（如果需要）
├── web_search.py        # 联网搜索（调 DuckDuckGo 或 Tavily）
└── http_request.py      # 通用 HTTP 请求
```

每个工具用 LangChain 的 `@tool` 装饰器定义，例：

```python
# backend/tools/web_search.py
from langchain_core.tools import tool

@tool
def web_search(query: str) -> str:
    """Search the web for up-to-date information about a topic."""
    # 用 httpx 调 DuckDuckGo Instant Answer API 或 Tavily
    ...
```

工具注册表：

```python
# backend/tools/__init__.py
from backend.tools.web_search import web_search
from backend.tools.http_request import http_request

TOOL_REGISTRY: dict[str, Tool] = {
    "web_search": web_search,
    "http_request": http_request,
}
```

### 1.2 改造 AgentNode

当前 `agent_node.py` 已经用了 `create_react_agent` 和 `@tool`，但工具是占位的。改造点：

**a) 工具从 `TOOL_REGISTRY` 获取而非硬编码：**

```python
from backend.tools import TOOL_REGISTRY

# 在 _build_agent 中：
tool_names = self.config.get("tools", [])
tools = [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]
```

**b) 流式输出 ReAct 过程的每一步：**

当前已经流式输出了 `node_stream`（LLM token），需要新增事件类型让前端能展示完整的 ReAct 循环：

```
新 SSE 事件类型：
- agent_think:  LLM 在思考（文本推理）
- agent_action: LLM 决定调用工具（tool name + args）
- agent_observe: 工具返回结果
```

在 `astream_events` 循环中，根据 event 类型分发：

```python
if event_name == "on_tool_start":
    await self._emit(on_event, {
        "type": "agent_action",
        "node_id": self.node_id,
        "tool_name": data["name"],
        "tool_args": data["input"],
    })
elif event_name == "on_tool_end":
    await self._emit(on_event, {
        "type": "agent_observe",
        "node_id": self.node_id,
        "tool_name": ...,
        "result": data["output"],
    })
```

### 1.3 前端展示 ReAct 过程

在 `DebugDrawer` 中新增 ReAct 步骤渲染：

```
[Think] 我需要搜索最新的 OpenAI 新闻...
[Action] web_search("OpenAI latest news 2026")
[Observe] 搜索结果: 1. OpenAI 发布... 2. ...
[Think] 拿到了 5 条新闻，让我总结一下...
[Output] 以下是 OpenAI 最新动态的总结...
```

### 1.4 NodeConfig 面板增加工具选择

Agent 节点的配置面板需要让用户勾选想启用的工具：

- [ ] Web Search
- [ ] HTTP Request

这就是给 `node.data.config.tools` 数组加值。

### 1.5 要改的文件清单

| 文件 | 改动 |
|------|------|
| `backend/tools/__init__.py` | **新建** 工具注册表 |
| `backend/tools/web_search.py` | **新建** 搜索工具 |
| `backend/tools/http_request.py` | **新建** HTTP 工具 |
| `backend/nodes/agent_node.py` | 改造工具加载 + ReAct 事件流 |
| `frontend/src/components/debug/DebugDrawer.tsx` | 新增 ReAct 步骤渲染 |
| `frontend/src/components/panels/NodeConfig.tsx` | Agent 节点增加工具选择 UI |
| `frontend/src/types/workflow.ts` | 增加 agent 相关事件类型 |
| `backend/tests/test_agent_node_tools.py` | **新建** 工具调用测试 |

---

## Phase 2: 一句话全自动 — 规划 + 渐进渲染 + 自动执行

**目标：** 用户输入一句话，画布自动"生长"出节点，自动连线，自动执行。

### 2.1 整体流程

```
用户输入 "帮我总结最近关于 AI Agent 的新闻，并生成一段播客音频"
    │
    ▼
[Planning] Agent 分析意图，决定需要: 搜索 → LLM 总结 → TTS
    │  ← SSE: planning_start, planning_think
    ▼
[Build Step 1] 创建 Start 节点
    │  ← SSE: node_added { node: start_1 }      ← 前端收到后在画布上渲染
    ▼
[Build Step 2] 创建 Agent 节点 (带 web_search 工具)
    │  ← SSE: node_added { node: agent_1 }
    │  ← SSE: edge_added { source: start_1, target: agent_1 }
    ▼
[Build Step 3] 创建 LLM 节点
    │  ← SSE: node_added { node: llm_1 }
    │  ← SSE: edge_added { source: agent_1, target: llm_1 }
    ▼
[Build Step 4] 创建 TTS 节点
    │  ← SSE: node_added, edge_added
    ▼
[Build Step 5] 创建 End 节点
    │  ← SSE: node_added, edge_added
    ▼
[Build Complete]
    │  ← SSE: workflow_built { workflow_id }
    ▼
[Auto Execute] 自动触发执行，复用现有 SSE 执行流
    │  ← SSE: workflow_start, node_start, node_stream, node_end, ...
    ▼
[Done]
    ← SSE: workflow_end
```

### 2.2 后端：新 API 端点

```
POST /api/agent/auto-run
Body: { "goal": "帮我总结..." }

Response: SSE stream，包含 planning → building → executing 全过程事件
```

这个端点内部串联三步：
1. 调用改造后的 `AgentPlanner`，跳过澄清，直接规划
2. 逐节点构建 graph，每加一个节点就发一个 SSE 事件
3. 构建完成后自动调用 `ExecutionEngine.run()`

### 2.3 前端：画布渐进渲染

`useAgentSession` hook 监听新的 SSE 事件类型：

- `node_added`: 调用 `workflowStore.addNode()` 在画布上添加节点（带动画）
- `edge_added`: 调用 `workflowStore.addEdge()` 添加连线
- `workflow_built`: 标记构建完成，切换到执行模式
- 执行阶段复用现有的 `node_start` / `node_end` / `node_stream` 事件

节点出现时可以加一个 fade-in + scale 的 CSS 动画，让"生长"感更强。

### 2.4 要改的文件清单（Phase 2 增量）

| 文件 | 改动 |
|------|------|
| `backend/api/agent.py` | 新增 `POST /api/agent/auto-run` 端点 |
| `backend/agent/planner.py` | 新增 `plan_and_stream()` 方法，逐步发射节点事件 |
| `frontend/src/hooks/useAgentSession.ts` | 监听 `node_added` / `edge_added` 事件 |
| `frontend/src/stores/workflowStore.ts` | 确保 `addNode` / `addEdge` 支持动态追加 |
| `frontend/src/components/canvas/WorkflowCanvas.tsx` | 节点出现动画 |
| `frontend/src/components/agent/AgentPanel.tsx` | 新增"一键运行"模式 UI |

---

## 开发顺序建议

```
Phase 1（预计 2-3 天）:
  Step 1: 实现 web_search 和 http_request 工具
  Step 2: 改造 AgentNode 接入真实工具 + ReAct 事件流
  Step 3: 前端 DebugDrawer 展示 ReAct 过程
  Step 4: NodeConfig 添加工具选择 UI
  Step 5: 写测试，手动验证

Phase 2（预计 2-3 天，基于 Phase 1）:
  Step 1: 后端 auto-run 端点 + 逐步构建事件
  Step 2: 前端画布渐进渲染 + 节点动画
  Step 3: 自动执行串联
  Step 4: 整体联调
```
