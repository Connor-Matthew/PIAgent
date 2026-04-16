# Agent Visual Build-and-Run 实现方案

## 目标

用户输入一段自然语言目标后，系统表现得像一个“可视化工作流代理”：

1. Agent 先理解目标，决定要做哪些步骤
2. 画布上逐步长出节点和连线，而不是一次性整图替换
3. 构建完成后自动执行
4. 执行过程、工具调用、节点输出都能被可视化追踪

目标体验不是“静态模板生成器”，而是“可观察的 agent orchestration”。

---

## 核心结论

这个目标是对的，而且可以做。

但这里要明确区分两种不同的 agent loop：

### A. Planner Loop（画布外）

这是“用户说一句话后，系统自己思索、自己决定怎么搭工作流”的那层 agent。

它负责：

- 理解用户目标
- 查询当前能力（LLM/TTS/知识库/可用节点）
- 决定下一步图操作
- 持续发出“新增节点 / 新增边 / 更新配置”的构建指令

它不直接执行 workflow node，而是负责“搭图”。

### B. Runtime Agent Loop（画布内）

这是 workflow 里的 `agent` 节点本身。

它负责：

- 在某个节点运行时进行 tool use
- 输出 think / act / observe 的执行轨迹

它属于“工作流执行期能力”，不是“一句话生成工作流”能力本身。

### 设计原则

要实现你要的体验，应该先把 **Planner Loop** 做出来，  
而不是先把 `agent` 节点塞进默认生成图里。

这样用户看到的效果仍然是：

- agent 在想
- agent 在搭图
- 画布在生长
- workflow 在运行

但底层实现不会和当前 runtime 架构冲突。

---

## 为什么这样拆

当前代码已经有一个稳定基座：

- Agent mode 负责把一句话目标变成草案
- `RecipeIR -> WorkflowGraphAdapter -> WorkflowGraph`
- ExecutionEngine 负责执行 graph

现阶段真正缺的不是“再加一个 agent 名字”，而是：

1. 让 planner 以流式、可视化的方式逐步构建图
2. 让前端把这个构建过程渲染出来
3. 让构建期和执行期共用同一套可观察事件协议

所以这份方案的核心不是“AgentNode 接管一切”，而是：

**让 planner 变成一个可视化的 graph-building agent。**

---

## 目标体验

```
用户输入：
"帮我总结最近 AI Agent 的趋势，生成一篇讲稿，并转成播客音频"

    │
    ▼
[Planning]
Agent 开始分析目标
    │  ← SSE: planning_start
    │  ← SSE: planning_update { text: "需要检索、总结、语音合成" }
    ▼
[Capability Check]
Agent 检查当前可用 provider / 知识库 / 节点能力
    │  ← SSE: planner_action { name: "load_capabilities" }
    │  ← SSE: planner_observe { ... }
    ▼
[Build Graph]
Agent 决定先放 Start，再放 RAG，再放 LLM，再放 TTS，再放 End
    │  ← SSE: node_added
    │  ← SSE: edge_added
    │  ← SSE: node_config_updated
    ▼
[Build Complete]
图验证通过
    │  ← SSE: plan_ready
    │  ← SSE: workflow_built
    ▼
[Auto Execute]
执行引擎自动运行
    │  ← SSE: workflow_start / node_start / node_stream / node_end
    ▼
[Done]
前端同时看到：
- 画布上的图
- 构建时的 agent 决策轨迹
- 执行时的节点运行轨迹
```

---

## 总体架构

### 1. Planner Agent

新增一个“规划代理”层，不直接产出最终 graph JSON，而是产出一串结构化 graph intents。

示意：

```python
PlannerIntent =
  | {"type": "planning_update", "text": "..."}
  | {"type": "add_node", "node": {...}}
  | {"type": "add_edge", "edge": {...}}
  | {"type": "update_node_config", "node_id": "...", "patch": {...}}
  | {"type": "commit_graph"}
```

这层可以由 LLM 驱动，但必须输出受限词表的结构化动作。

### 2. Graph Builder / Adapter

新增一个 builder，负责消费 planner intents，并生成当前可运行的 graph 草案。

职责：

- 校验 node type 是否受支持
- 校验 provider / voice / knowledge base 引用是否合法
- 维护当前 draft graph
- 每次变更后可选择发出前端事件
- `commit_graph` 时走 GraphCompiler 校验

### 3. Execution Engine

继续复用现有 `ExecutionEngine.run()`。

也就是说：

- 规划期负责“怎么搭”
- 构建期负责“搭出来并校验”
- 执行期负责“跑起来”

这三层职责必须分开。

---

## 事件模型

为了满足“可视化思索 + 可视化搭图 + 可视化执行”，需要两组事件。

### A. 规划 / 搭图事件

建议新增：

- `planning_start`
- `planning_update`
- `planner_action`
- `planner_observe`
- `node_added`
- `edge_added`
- `node_config_updated`
- `plan_ready`
- `workflow_built`
- `planning_error`

说明：

- `planning_update` 是面向用户的摘要性思路，不暴露原始 chain-of-thought
- `planner_action` / `planner_observe` 用于显示“查能力 / 查知识库 / 选 provider / 选节点模版”等可观察动作
- `node_added` / `edge_added` 才是驱动画布生长的核心事件

### B. 执行事件

继续沿用现有：

- `workflow_start`
- `node_start`
- `node_stream`
- `node_heartbeat`
- `node_end`
- `workflow_end`

如果某个 workflow 里真的用了 `agent` 节点，再额外新增：

- `agent_action`
- `agent_observe`

`agent_think` 不应该作为必须事件。  
如果要显示思路，优先显示可公开的摘要，而不是模型内部推理全文。

---

## Phase 拆分

## Phase 1: 可视化 Planner Loop MVP

**目标：** 一句话输入后，agent 能自己“逐步搭图”，画布可生长，随后自动执行。

### 范围

先不追求自由 DAG，也不要求 planner 默认生成 `agent` 节点。

Planner 在这一阶段只允许从受限图模板中选择和拼装：

- `start -> llm -> end`
- `start -> rag -> llm -> end`
- `start -> llm -> tts -> end`
- `start -> rag -> llm -> tts -> end`

### 用户体验

虽然底层还是受限词表，但前端体验已经是“agent 在搭图”：

- 先出现 Start
- 再出现 RAG/LLM/TTS
- 再连线
- 再执行

### 后端改动

- `backend/agent/planner.py`
  - 新增面向流式规划的接口，例如 `plan_and_stream()`
  - 但它返回的是结构化 intents，不直接负责画布状态

- `backend/agent/adapter.py`
  - 新增 builder 能力，例如 `GraphDraftBuilder`
  - 消费 intents，维护 draft graph，生成 `node_added` / `edge_added`

- `backend/api/agent.py`
  - 新增 `POST /api/agent/auto-run`
  - 统一输出 planning + build + execution 的 SSE 流

- `frontend/src/hooks/useAgentSession.ts`
  - 接收规划/搭图事件

- `frontend/src/stores/workflowStore.ts`
  - 新增 `addEdge`
  - 支持按事件逐步追加节点和连线

- `frontend/src/components/canvas/WorkflowCanvas.tsx`
  - 新增节点生长动画 / 连线渐显动画

### 这一阶段的价值

它已经满足你的核心期待：

- 用户讲一句话
- agent 自己组织工作流
- 画布渐进出现
- 然后自动运行

同时又不会过早引入多分支、merge、自由 DAG 的复杂度。

---

## Phase 2: Runtime AgentNode 真正 Tool Use

**目标：** 当 workflow 中存在 `agent` 节点时，它能在执行期真的调用工具，并把过程可视化。

### 范围

新增 `backend/tools/`：

- `web_search`
- `http_request`
- 后续可补 `knowledge_lookup`

`AgentNode` 改成从工具注册表加载工具，而不是硬编码 placeholder。

### 可视化

执行期新增：

- `agent_action`
- `agent_observe`

前端在 DebugDrawer / ExecutionTimeline 中渲染：

```text
[Action] web_search("AI Agent news")
[Observe] 返回 5 条结果
[Action] http_request(...)
[Observe] 请求成功
```

### 注意

这一阶段是“工作流内 agent 节点的 tool loop”，  
不是“一句话自动搭工作流”的唯一前提。

换句话说：

- Phase 1 先满足“会搭图”
- Phase 2 再增强“图里的 agent 节点会思考和用工具”

---

## Phase 3: 显式输入映射 + 分支 + Merge

**目标：** 让 planner 真正具备“自由组合排列”能力，而不是只选四种线性链路。

前置条件：

1. 显式输入映射
2. 文本 merge / select 节点
3. 音频 merge 节点
4. 更严格的 GraphPlanIR / GraphAction schema

这阶段完成后，planner 才能安全地升级到：

- 双分支检索
- 多脚本合成
- 多音轨 TTS
- 回退链路
- 更自由的 DAG 结构

---

## 关键实现选择

### 1. Planner 不直接写最终 graph

planner 只能发受限动作，不能直接任意写 graph JSON。

原因：

- 降低错误空间
- 便于实时校验
- 便于把每一步变更同步到画布

### 2. 前端画布跟随事件，而不是等待整图

不要只在 `plan_ready` 时一次性 `setDraftWorkflow()`。

而是要支持：

- `addNode()`
- `addEdge()`
- `updateNodeData()`

这样才能实现“慢慢渲染出来”。

### 3. 可视化思考只展示摘要，不展示原始 CoT

可显示：

- “需要先检索资料，再生成脚本”
- “已选择 OpenAI 作为 LLM provider”
- “检测到可用 TTS，因此追加音频输出”

不要求也不依赖暴露模型原始内部推理。

### 4. 自动执行必须建立在已校验 graph 之上

只有当 draft graph 通过 GraphCompiler 校验后，才能进入执行阶段。

---

## API 草案

### `POST /api/agent/auto-run`

请求：

```json
{
  "goal": "帮我整理 AI Agent 趋势，生成讲稿并转成播客"
}
```

响应：

`text/event-stream`

事件顺序示例：

```text
planning_start
planning_update
planner_action
planner_observe
node_added
edge_added
node_config_updated
plan_ready
workflow_built
workflow_start
node_start
node_stream
node_end
workflow_end
```

---

## 开发顺序建议

### Step 1

先做 Planner Loop MVP：

- `auto-run` SSE
- `node_added / edge_added`
- 前端画布渐进渲染
- 构建完成后自动执行

### Step 2

补齐 Runtime `AgentNode` 的真实 tool use：

- 工具注册表
- `agent_action / agent_observe`
- DebugDrawer 展示

### Step 3

再推进更自由的 graph 规划：

- 输入映射
- merge/select
- 更丰富的 graph intents

---

## 最终判断

你要的方向不是“太激进”，而是产品上非常对。

真正需要修正的不是目标，而是实现路径：

- 不是先把 `agent` 节点硬塞成 planner 默认产物
- 而是先做一个 **可视化的 Planner Loop**
- 再把 Runtime AgentNode 的 tool-use 接上
- 最后再开放更自由的 DAG 组合

这样做，既能保住你要的体验：

- 一句话
- agent 自己思索
- agent 自己搭图
- 画布慢慢渲染
- 自动执行
- 全程可视化

又不会把当前已经稳定的 workflow runtime 一次性推翻。
