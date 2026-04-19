# PIAgent Graph Contract 与架构收口设计建议

> **创建日期：** 2026-04-19  
> **状态：** 建议稿  
> **背景：** 基于当前 Harness v2 与控制流/子图实现 review 后的架构整理建议。  
> **目标：** 在继续扩展 if-else、iteration、Harness 自动建图之前，先把 graph 契约和模块边界收紧，避免前端、后端、Harness 对同一张图产生不同理解。

---

## 一、结论先行

当前项目不是单纯的功能 bug，而是进入了一个需要“架构收口”的阶段。主要断层集中在 **Workflow Graph 契约**：

- 前端 React Flow store、后端 GraphCompiler/ExecutionEngine、Harness GraphBuilder 都在读写 graph。
- 三者最终都依赖 `{ nodes, edges }`，但契约目前是隐式的，散落在多个文件中。
- 控制流节点引入后，`sourceHandle`、`parentNode`、`parentId`、`branchId` 的语义边界没有完全对齐。
- Harness 可能生成一个后端可执行 graph，但前端加载再保存一遍时可能丢失执行语义字段。

我的建议是：**暂停继续扩展控制流功能，先做一次 contract-first 的架构收口。**

推荐路线：

1. 定义 `WorkflowGraph v2` 为一等契约。
2. 后端新增 Pydantic schema，把 compiler 的输入从任意 dict 收紧为结构化 graph。
3. 前端新增 graph normalize/serialize round-trip 测试，保证不丢字段。
4. 明确控制流唯一执行语义：`parentId + branchId`，`sourceHandle` 只做 UI 元数据。
5. 将 Harness 定位为 graph 生产者，而不是另一套 workflow runtime。
6. 梳理命名边界：Harness、LeadAgent、AgentNode、AgentSession 不再混用概念。

---

## 二、当前项目的有效架构

PIAgent 目前已经形成了一个合理的核心架构：

```text
用户拖拽画布 / Harness 自然语言建图
        ↓
WorkflowGraph JSON
        ↓
GraphCompiler 校验并编译
        ↓
ExecutionEngine 执行
        ↓
SSE 事件流
        ↓
前端 Debug UI 展示
```

能力层围绕 runtime 提供节点能力：

```text
Provider 管理  → LLM / TTS 节点
Knowledge Base → RAG 节点
LangGraph ReAct → AgentNode 内部能力
Harness v2 → graph 生成与修订
```

这个方向是对的。真正的问题不在“模块不存在”，而在模块之间的契约还不够硬。

---

## 三、主要断层

### 3.1 Graph 契约是隐式的

当前 graph 的真实结构由这些地方共同决定：

- `frontend/src/types/workflow.ts`
- `frontend/src/stores/workflowStore.ts`
- `backend/core/compiler.py`
- `backend/core/engine.py`
- `backend/harness/builder.py`
- `backend/harness/validators.py`
- docs 中多份历史 spec

但没有一个单独的、可验证的“WorkflowGraph schema”作为真相源。

结果是字段语义容易漂移：

| 字段 | 当前风险 |
|---|---|
| `type` / `data.nodeType` | 前端和后端同时表达节点类型，可能不一致 |
| `data.config` | 前端内部字段，保存时会被展平，后端不直接理解它 |
| `parentNode` | React Flow UI 字段，不应进入后端契约 |
| `data.parentId` | 后端执行语义字段，但目前藏在 `data` 内 |
| `data.branchId` | if-else 执行语义字段，前端 normalize 时可能丢失 |
| `sourceHandle` | UI 出边锚点，不应决定后端分支路由 |

### 3.2 UI 语义和执行语义分叉

用户在画布上自然会理解：

```text
IfElse 的 true/false 出边决定分支
```

但当前后端设计实际是：

```text
IfElse 是一个黑盒节点。
分支体是它的 child nodes。
执行器通过 child.data.parentId + child.data.branchId 找到要运行的分支子图。
```

这两个心智模型如果不统一，会产生很危险的体验：用户以为画出来的分支能执行，实际后端按另一套结构跑。

### 3.3 Harness 和画布是两个 graph 入口，但没有 round-trip 保证

Harness v2 的定位是“自然语言建图”。它可以直接生成后端可执行的 graph。

问题是：如果这个 graph 被前端加载，再保存，前端序列化必须保证不丢任何后端执行字段。

当前已经暴露出风险：

- `if_else` / `iteration` 可能被前端归一化成 `llm`。
- `branchId` 可能在加载时被过滤掉。
- `parentId` 在 React Flow 与后端之间需要双向映射。

这说明项目缺少一组专门保护 graph 契约的 round-trip 测试。

### 3.4 执行器已经从 LangGraph runtime 演进成自研 runtime

早期文档描述的是：

```text
Graph JSON → GraphCompiler → LangGraph StateGraph → ExecutionEngine
```

当前代码更接近：

```text
Graph JSON → GraphCompiler → CompiledWorkflow → ExecutionEngine 自研调度
```

LangGraph 仍然有价值，但主要在 `AgentNode` 内部，而不是整个 workflow runtime 的核心。

这不是坏事。控制流、iteration、SSE debug 用自研 runtime 更直接。但文档和命名应更新，否则后续设计会继续在“LangGraph 驱动”和“PIAgent runtime 驱动”之间摇摆。

### 3.5 Debug 事件缺少完整作用域模型

单层 DAG 时代，前端 debug store 用 `nodeId` 作为状态 key 足够。

控制流和 iteration 引入后，同一个节点可能执行多次：

```text
iteration_1.item[0].llm_body
iteration_1.item[1].llm_body
iteration_1.item[2].llm_body
```

如果事件只带 `node_id`，前端状态会互相覆盖。

因此 SSE 事件契约也需要从“节点级事件”升级成“作用域节点事件”。

---

## 四、推荐的目标架构

### 4.1 WorkflowGraph v2 成为一等契约

建议新增一个明确的 graph 版本：

```ts
type WorkflowGraphV2 = {
  version: 2
  nodes: WorkflowNodeV2[]
  edges: WorkflowEdgeV2[]
}
```

节点建议分为“结构字段”和“业务配置字段”：

```ts
type WorkflowNodeV2 = {
  id: string
  type: NodeType
  position?: { x: number; y: number }

  // 图结构字段
  parentId?: string
  branchId?: string

  // 展示字段
  label?: string
  locked?: boolean

  // 节点业务配置
  config: Record<string, unknown>
}
```

边保持轻量：

```ts
type WorkflowEdgeV2 = {
  id?: string
  source: string
  target: string

  // 仅 UI 元数据，不参与后端执行路由
  sourceHandle?: string
}
```

#### 重要设计决定

`parentId` 和 `branchId` 应该从 `data` 中提升为 node 顶层字段。

原因：

- 它们是图结构语义，不是节点业务配置。
- compiler 和 engine 会直接依赖它们。
- 前端 serialize/normalize 更容易写出保真逻辑。
- Harness builder 不需要知道前端 `data.config` 的内部约定。

短期为了兼容旧图，可以支持读取旧格式：

```json
{ "data": { "parentId": "if_1", "branchId": "true" } }
```

但保存时统一写成 v2 顶层字段。

### 4.2 前端引入 Graph Adapter 层

建议不要让 `workflowStore.ts` 继续承担所有 graph 变换职责。新增一个专门模块：

```text
frontend/src/graph/
  contract.ts
  adapters.ts
  defaults.ts
  roundtrip.test.ts
```

职责划分：

| 文件 | 职责 |
|---|---|
| `contract.ts` | 定义前端侧 WorkflowGraphV2、NodeType、config 类型 |
| `adapters.ts` | React Flow Node/Edge 与 WorkflowGraphV2 的双向转换 |
| `defaults.ts` | 默认节点与默认 config |
| `roundtrip.test.ts` | 确保 graph 加载再保存不丢执行字段 |

`workflowStore.ts` 应该只负责状态管理，不再内联复杂 normalize/serialize 规则。

### 4.3 后端引入 Graph Schema 层

建议新增：

```text
backend/core/graph_schema.py
```

用 Pydantic 定义：

```py
class WorkflowGraph(BaseModel):
    version: Literal[2] = 2
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]

class WorkflowNode(BaseModel):
    id: str
    type: NodeType
    position: Position | None = None
    parentId: str | None = None
    branchId: str | None = None
    label: str | None = None
    locked: bool | None = None
    config: dict[str, Any] = Field(default_factory=dict)

class WorkflowEdge(BaseModel):
    id: str | None = None
    source: str
    target: str
    sourceHandle: str | None = None
```

GraphCompiler 的入口变成：

```py
graph = WorkflowGraph.model_validate(raw_graph)
compiler.validate(graph)
compiler.compile(graph)
```

这样 compiler 不再需要到处写 `(node.get("data") or {}).get(...)`。

### 4.4 控制流采用“容器子图”作为唯一模型

建议明确采用当前 spec 的方向：

```text
IfElse / Iteration 是容器节点。
子节点通过 parentId 归属容器。
IfElse 子节点额外通过 branchId 归属分支。
普通 sourceHandle 不参与执行路由。
```

也就是说，不推荐让 `sourceHandle=true/false` 直接驱动后端分支执行。

原因：

- iteration 天然需要 body 子图，容器模型更统一。
- 后续 group、trace、sub-workflow 都可以复用 parentId。
- 分支子图可以有多个节点，而不是一条边后面的单节点。
- 执行器可以把控制流节点当黑盒，外部图更清晰。

前端 UI 应该配合这个模型：

```text
IfElse container
  true lane
    child nodes...
  false lane
    child nodes...

Iteration container
  body lane
    child nodes...
```

拖拽节点进入容器时，前端应自动设置：

```ts
node.parentId = container.id
node.branchId = selectedBranchId // 仅 if_else 子节点
```

React Flow 的 `parentNode` / `extent` 仍然只作为 UI 渲染字段，由 adapter 从 `parentId` 推导。

### 4.5 SSE 事件升级为 scope-aware

建议为所有节点事件增加可选字段：

```ts
type ExecutionScope = {
  path: Array<{
    nodeId: string
    kind: 'root' | 'if_else' | 'iteration'
    branchId?: string
    iterationIndex?: number
  }>
}
```

事件示例：

```json
{
  "type": "node_start",
  "node_id": "llm_body",
  "node_type": "llm",
  "scope": {
    "path": [
      { "nodeId": "iteration_1", "kind": "iteration", "iterationIndex": 2 },
      { "nodeId": "if_1", "kind": "if_else", "branchId": "true" }
    ]
  }
}
```

前端 debug store 的 key 不应再只是 `nodeId`，而应由：

```text
scope path + nodeId
```

组成。

短期可以保留 `iteration_index` 作为兼容字段，但新逻辑应以 `scope.path` 为准。

### 4.6 Harness 只生产 WorkflowGraph，不拥有另一套语义

Harness v2 的边界建议固定为：

```text
用户目标
  → LeadAgent 决策循环
  → GraphBuilder 产生 WorkflowGraphV2 草稿
  → Validator 校验
  → Apply 持久化到 workflows
```

Harness 不应拥有不同于 compiler 的 graph 语义。

因此：

- Harness validator 应复用后端 GraphSchema 与 GraphCompiler。
- Harness builder 输出 v2 graph。
- Harness skill 文档应引用同一份 node type/config contract。
- Harness 暂时不自动生成控制流，直到 UI 和 compiler 的子图契约稳定。

### 4.7 命名边界收口

建议采用以下命名约定：

| 名称 | 含义 |
|---|---|
| `AgentNode` | 工作流里的可执行 ReAct 节点 |
| `Harness` | 帮用户生成或修改 workflow graph 的系统 |
| `LeadAgent` | Harness 内部的决策循环 |
| `HarnessSession` | 一次自然语言建图会话 |
| `AgentSession` | 旧 DB model 名称，后续迁移为 `HarnessSessionModel` |

短期可以不改 DB 表名，但代码和文档应停止把 Harness 叫成 Agent Mode。

---

## 五、备选方案比较

### 方案 A：继续在现有结构上补 bug

做法：

- 修 `isNodeType`
- 保留 `branchId`
- 给 `_run_if_else` 补 `iteration_index`
- 在 `useDnD` 上补一点 parentNode 逻辑

优点：

- 速度最快。
- 改动小。
- 能快速让部分测试通过。

缺点：

- 没有解决 graph contract 隐式的问题。
- 后续 Harness、控制流、debug 继续容易断。
- UI 和执行语义仍可能分叉。

结论：只适合作为短期止血，不适合作为主路线。

### 方案 B：建立 WorkflowGraph v2 契约，渐进迁移

做法：

- 新增 graph schema 与 adapter。
- 兼容读取旧 graph。
- 保存统一写 v2。
- 编译器和 Harness 逐步改用 v2 模型。

优点：

- 风险可控。
- 能保护现有数据。
- 能把前端、后端、Harness 统一到一份契约。
- 是后续控制流、trace、group 的稳定基础。

缺点：

- 需要写一轮 schema、adapter、round-trip 测试。
- 初期看起来不像“新功能”，但它是在修地基。

结论：推荐采用。

### 方案 C：彻底重写 graph/runtime 层

做法：

- 直接废弃现有 graph shape。
- 重写 compiler、engine、frontend adapter、Harness builder。

优点：

- 长期形态最干净。

缺点：

- 改动太大。
- 现有测试和功能会长时间不稳定。
- 当前项目还没到必须推倒重来的程度。

结论：不推荐。

---

## 六、推荐落地顺序

### Phase 0：立即止血

目标：先让已有控制流节点不在 UI 入口失效。

动作：

1. 前端 `isNodeType` 加入 `if_else` 和 `iteration`。
2. 前端 normalize/serialize 保留 `branchId`。
3. 后端控制流事件补齐父 iteration 上下文。
4. 增加最小测试覆盖这几个 review finding。

这一步不解决架构问题，只避免当前实现继续产生错误数据。

### Phase 1：定义 WorkflowGraph v2 contract

目标：把 graph 契约变成一等公民。

动作：

1. 新增后端 `backend/core/graph_schema.py`。
2. 新增前端 `frontend/src/graph/contract.ts`。
3. 明确 v1 兼容读取规则。
4. 明确 v2 保存格式。
5. 文档写入字段语义表。

验收标准：

- 后端 API 收到 graph 时先 schema normalize。
- compiler 不再直接依赖 `data.parentId`。
- 前端保存输出固定为 v2。

### Phase 2：前端 Graph Adapter 与 round-trip 测试

目标：保证 graph 在前端加载再保存后不丢语义。

动作：

1. 从 `workflowStore.ts` 抽出 graph adapter。
2. 增加 round-trip cases：
   - 普通线性 DAG
   - if-else 带 true/false 子图
   - iteration 带 body 子图
   - Harness 生成 graph 后前端保存
3. `workflowStore.ts` 只调用 adapter，不再内联字段过滤规则。

验收标准：

```text
WorkflowGraphV2 → ReactFlow nodes/edges → WorkflowGraphV2
```

必须保留：

- `type`
- `parentId`
- `branchId`
- `config`
- `sourceHandle`

### Phase 3：控制流 UI 与执行语义统一

目标：用户在画布上看到的结构，就是后端实际执行的结构。

动作：

1. IfElse 节点渲染成容器，包含 branch lanes。
2. Iteration 节点渲染成容器，包含 body lane。
3. 拖拽进入容器时自动设置 `parentId`。
4. 拖拽进入 if-else lane 时自动设置 `branchId`。
5. 禁止或警告跨 scope 的非法连线。

验收标准：

- 用户不需要手写 `branchId`。
- 普通 if-else 分支能通过 UI 创建并执行。
- 普通 iteration body 能通过 UI 创建并执行。

### Phase 4：SSE/debug scope-aware

目标：支持嵌套控制流的正确调试展示。

动作：

1. 后端事件增加 `scope.path`。
2. `debugStore` key 改为 `scopeKey + nodeId`。
3. Debug UI 能展示同一 body 节点在不同 iteration item 下的状态。
4. 保留旧事件字段用于兼容简单节点。

验收标准：

- iteration body 中同一个 LLM 节点运行多次时，前端不会互相覆盖状态。
- if-else inside iteration 能正确显示每个 item 走了哪个 branch。

### Phase 5：Harness 接入 v2 contract

目标：Harness 只生成 v2 graph，不维护另一套 graph 语义。

动作：

1. GraphBuilder 输出 WorkflowGraphV2。
2. ValidateGraphTool 调用同一套 GraphSchema + GraphCompiler。
3. Harness skills 更新为 v2 contract。
4. 暂不让 Harness 自动生成控制流，直到 Phase 3/4 稳定。

验收标准：

- Harness 生成 graph 后，前端加载保存不改变语义。
- Apply 后的 workflow 能直接通过后端 compiler。

---

## 七、明确非目标

这次架构收口不做：

- 复杂条件 DSL。
- 子 workflow 引用。
- OTLP tracing 后端落库。
- Harness 自动生成复杂 if-else/iteration。
- 大规模 UI 重设计。
- 数据库大迁移。

这些都可以后续做，但不应混进 graph contract 收口里。

---

## 八、测试策略

### 8.1 后端测试

新增或调整：

- `test_graph_schema.py`
- `test_compiler_m1.py`
- `test_engine_if_else.py`
- `test_engine_iteration.py`
- `test_engine_iteration_concurrent.py`

重点覆盖：

1. v1 graph 兼容读取。
2. v2 graph schema 校验。
3. `parentId` 指向不存在节点时报错。
4. if-else branch 子图只执行选中分支。
5. iteration body 节点每个 item 独立执行。
6. 嵌套控制流事件包含 scope。

### 8.2 前端测试

建议引入最小 Vitest 测试，先不用做大规模组件测试。

重点覆盖：

1. graph adapter round-trip。
2. `if_else` 和 `iteration` 不会被 normalize 成 `llm`。
3. `parentId` 能映射为 React Flow `parentNode`。
4. `branchId` 保存再加载不丢。
5. `sourceHandle` 保留为 UI metadata，但不被当成执行语义。

### 8.3 端到端手工验收

最小验收路径：

1. 创建 `Start -> IfElse -> End`。
2. 在 IfElse 的 true 分支中放一个 LLM。
3. 在 false 分支中放另一个 LLM。
4. 保存、刷新页面、重新打开。
5. 确认子节点仍在对应分支内。
6. 运行 workflow，确认只执行选中分支。
7. 创建 `Start -> Iteration -> End`。
8. 在 Iteration body 中放一个 LLM。
9. 输入数组，确认每个 item 独立运行并汇总结果。

---

## 九、风险与取舍

### 风险 1：v2 contract 改动牵涉面广

缓解：

- v1 只读兼容。
- 保存统一写 v2。
- 先做 adapter 测试，再改 store。

### 风险 2：前端容器子图 UX 会拖慢控制流上线

缓解：

- Phase 0 先止血。
- Phase 3 先做最小容器交互，不追求漂亮。
- Harness 暂不生成控制流，避免同时扩大范围。

### 风险 3：scope-aware debug 可能导致事件协议变复杂

缓解：

- 保留旧字段。
- 新增 `scope` 作为可选字段。
- Debug store 新逻辑优先用 `scope`，缺失时回退到 `nodeId`。

---

## 十、最终建议

我建议采用 **方案 B：WorkflowGraph v2 契约 + 渐进迁移**。

这条路线的核心判断是：

> PIAgent 的主轴不是 React Flow，也不是 Harness，也不是 LangGraph，而是 WorkflowGraph contract。

只要 contract 稳，前端拖拽、Harness 生成、后端执行、SSE debug 都可以各自演进。

如果 contract 继续隐式存在，后续每加一个节点或控制流能力，都会继续出现“看起来保存了，但执行语义丢了”的问题。

因此下一步优先级应是：

1. 先修当前 P1/P2，避免继续产生坏 graph。
2. 立刻定义 `WorkflowGraph v2`。
3. 把 graph adapter 和 graph schema 作为双端边界。
4. 再继续做控制流 UI、scope debug 和 Harness 自动化。

这不是一次大重写，而是一次必要的地基收紧。

