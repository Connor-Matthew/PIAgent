# PIAgent - Harness 模式设计文档（DeerFlow-style）

> 状态：进行中（H0-H3 已落地，H4 Sandbox 预留中）
> 范围：在现有 Agent Mode 与 Workflow Runtime 之上，引入一层 DeerFlow-style 的 harness orchestration，用于支持 lead agent、skills、sub-agents、memory 与后续 sandbox 的统一调度。
> 目标：让 PIAgent 从 “自然语言生成 workflow 草案” 进一步演进到 “可视化 super agent harness + workflow runtime”。
> 关系：
> - 当前已落地的 Agent Mode 仍然有效，详见 `2026-04-15-agent-mode.md`
> - 当前已落地的可视化 build-and-run 路线仍然有效，详见 `../plans/2026-04-16-agent-tool-use.md`
> - 本文档不是对 DeerFlow 的直接移植，而是对其 harness 思想在 PIAgent 场景下的本地化设计

## 0. 执行记录（2026-04-16）

本轮已按 H0 + H1-lite + H1-advanced + H2-lite + H3-lite 落了一条可运行的纵向切片，Harness 作为独立 orchestration 层已完整运转，并复用现有 `AgentPlanner + GraphCompiler + ExecutionEngine`，避免直接拆旧路径。

### 0.1 已完成

- 新增独立后端包 `backend/harness/`
- 新增 `HarnessOrchestrator`，支持 `fast` / `harness` 简单路由、`build()` / `run()` 两个入口
- 新增 `LeadAgent`、`GraphDraftBuilder`、`HarnessSkillRegistry` 与 typed skills 薄封装
- `LeadAgent` 当前在 Harness Path 已支持 LLM 动态 skill 选择（单次结构化规划 `LeadAgentPlan`），在 Fast Path 或 LLM 不可用时回退到硬编码 skill 链
- `LeadAgent` 的 `draft_recipe` skill 内部复用 `AgentPlanner.plan_default()`，但规划层已被 LLM 动态编排能力包裹
- `GraphDraftBuilder` 已支持 `planning_update`、`add_node`、`add_edge`、`update_node_config`、`commit_graph`
- `commit_graph` 已接入 `GraphCompiler.validate()`
- 新增 `/api/harness/auto-run` SSE 入口，并注册到 `backend/main.py`
- 前端 auto-run 已切到 `/api/harness/auto-run`，继续复用现有 SSE 消费链路和画布生长 UI
- 为兼容现有前端，`node_config_updated` 事件同时带 `patch` 字段
- 已补充 Harness 相关测试与基本回归验证（13 passed）
- 已新增 `HarnessMemoryStore`，复用 `agent_sessions` 表实现 Session Memory
- 已新增 `GraphCriticAgent`（规则版 sub-agent），在 `commit_graph` 前进行非阻塞结构风险检查
- 已新增 `skill_start` / `skill_end`、`subagent_spawned` / `subagent_result` 事件

### 0.2 本轮主要文件

- 后端 Harness 内核：
  - `backend/harness/actions.py`
  - `backend/harness/builder.py`
  - `backend/harness/context.py`
  - `backend/harness/lead_agent.py`
  - `backend/harness/orchestrator.py`
  - `backend/harness/registry.py`
  - `backend/harness/schemas.py`
  - `backend/harness/prompts.py`
  - `backend/harness/memory.py`
  - `backend/harness/skills/capabilities.py`
  - `backend/harness/skills/recipe.py`
  - `backend/harness/skills/graph_validation.py`
  - `backend/harness/skills/execution.py`
  - `backend/harness/subagents/base.py`
  - `backend/harness/subagents/graph_critic.py`
- API 接线：
  - `backend/api/harness.py`
  - `backend/main.py`
- 前端接线：
  - `frontend/src/services/api.ts`
- 测试：
  - `backend/tests/test_harness_api.py`
  - `backend/tests/test_harness_builder.py`
  - `backend/tests/test_harness_orchestrator.py`
  - `backend/tests/test_harness_memory.py`
  - `backend/tests/test_harness_subagents.py`

### 0.3 已验证

- `backend/.venv/bin/python -m pytest backend/tests/test_harness_*.py`
  - 结果：`13 passed`
- `cd frontend && npm run build`
  - 结果：通过

### 0.4 当前边界

- 旧的 `/api/agent/auto-run` 仍然存在，尚未代理到 Harness
- `fast` / `harness` 路由当前是轻量启发式，不是最终版 routing policy
- `CapabilityScoutAgent`、`RecipeChallengerAgent` 等 LLM-based sub-agents 尚未落地
- Project Memory（跨会话 provider / voice / graph style 偏好）尚未落地
- `sandbox` 仍为接口预留，未进入实现
- 尚未新增前端 feature flag；当前是直接把 auto-run 指向新的 Harness API

---

## 1. 背景

### 1.1 为什么要引入 Harness

PIAgent 当前已经具备三层能力：

1. 可视化 workflow 编辑器
2. 一句话生成 workflow 草案的 Agent Mode
3. Workflow 执行期的节点运行时

但这三层之间仍然存在一个明显空档：

- Agent Mode 更像 “recipe planner”
- Workflow Runtime 更像 “确定性执行器”
- 中间缺少一个真正的 “agent harness”

也就是说，当前系统可以：

- 理解一句话目标
- 生成当前 runtime 兼容的 graph
- 执行 graph

但还不能很好地表达这些 DeerFlow-style 能力：

- lead agent 对任务进行持续编排
- skill registry 作为能力边界层
- sub-agents 做并行探索或批判性检查
- memory 为跨轮规划提供上下文
- sandbox 为开放式 tool use 提供隔离环境

### 1.2 DeerFlow 给我们的启发

DeerFlow 的关键价值不在于某一个具体组件，而在于它把 “super agent” 收敛成一套清晰的 harness 结构：

- 一个主控 lead agent
- 一组按需调用的 skills / tools
- 一组可选的 sub-agents
- 一层 memory / context engineering
- 一套明确的边界控制与执行环境

对 PIAgent 而言，这个方向非常契合，因为我们的产品目标从来不是纯聊天，而是：

> 把 agent 的智能性、workflow 的可视化、runtime 的可控性放进同一个系统里。

---

## 2. 核心问题

### 2.1 当前 Agent Mode 的本质

当前 Agent Mode 本质上是：

`goal -> RecipeIR -> WorkflowGraphAdapter -> WorkflowGraph`

这条路径稳定、清晰、可控，但它仍然是低熵生成：

- 先选 recipe
- 再展开 graph
- 最后交给 ExecutionEngine 执行

这适合当前 phase，但不等于 harness。

### 2.2 当前缺失的能力

如果要支持更强的 agent 化体验，当前系统缺的不是 “再加一个 agent 节点”，而是下面几层：

1. 一个高于 recipe planner 的 lead agent
2. 一套结构化 skills，而不是散落在 planner / adapter / runtime 里的隐式逻辑
3. 一套 graph actions 协议，而不是只在最终时刻产出完整 graph
4. 一套 sub-agent 协作约束
5. 一套可逐步扩展的 memory 与 sandbox 边界

### 2.3 我们不应该做什么

本设计明确不建议：

- 直接把 DeerFlow 整套 runtime 当 sidecar 接进 PIAgent
- 直接让 lead agent 自由输出任意 graph JSON
- 在没有审计和隔离的前提下，马上开放 bash/file/network 的高权限 sandbox
- 用 harness 替换当前稳定的 workflow runtime

PIAgent 当前的稳定资产是：

- GraphCompiler
- WorkflowGraphAdapter
- ExecutionEngine
- Canvas + SSE 可视化链路

Harness 应该增强这些资产，而不是绕过它们。

---

## 3. 设计目标

### 3.1 产品目标

用户输入一个复杂目标后，PIAgent 应该表现得像一个 “可视化 super agent harness”：

1. Lead agent 理解目标
2. Lead agent 决定需要哪些 skills / sub-agents
3. Harness 逐步发出 graph actions
4. Canvas 渐进生长
5. Graph 被验证和定稿
6. Workflow Runtime 执行
7. 用户既看到 planning，也看到 execution

### 3.2 工程目标

Harness 模式必须满足：

- 可渐进落地，不推翻现有架构
- 每一层边界清晰，易于测试
- 与现有 SSE / frontend 事件链兼容
- 默认安全，不因为引入 harness 而带来失控 tool use

### 3.3 非目标

本 spec 当前不承诺：

- 一步到位的开放世界 autonomous agent
- 完整复刻 DeerFlow 所有 runtime 设施
- 通用桌面操作代理
- 无边界 shell / filesystem / network automation

---

## 4. 关键设计决策

### 4.1 Fast Path 与 Harness Path 并存

不是所有请求都需要走完整 Harness。

当前 AgentPlanner 对简单目标（如 "帮我搭一个翻译 workflow"）已经能在 3 次 LLM 调用内完成 `clarify → plan → adapt`。如果 Harness 把这条路径也变成 `lead agent → 选 skills → 逐步发 actions`，简单场景的延迟和 token 开销会翻倍。

因此，系统应该保留两条路径：

| 路径 | 触发条件 | 调用链 |
|------|----------|--------|
| **Fast Path** | 目标可映射到已知 recipe（关键词匹配 + LLM 判定） | AgentPlanner → RecipeIR → WorkflowGraphAdapter → graph |
| **Harness Path** | 目标需要多步编排、条件分支、或需求模糊 | LeadAgent → skills → graph actions → GraphDraftBuilder → graph |

路由逻辑建议放在 `harness/orchestrator.py`，由一次轻量 LLM 调用（或规则引擎）决定走哪条路径。Fast Path 本质上就是 Harness 下的一个 "直通 skill"。

### 4.2 Harness 是规划层，不是执行层

PIAgent 中的 Harness 必须位于 Workflow Runtime 之上。

职责划分：

- Harness：决定 “怎么搭、用哪些 skills、是否需要 sub-agents”
- Graph Builder：把 actions 落到 graph draft
- ExecutionEngine：执行最终 graph

也就是说：

`Harness != ExecutionEngine`

Harness 不替换 [backend/core/engine.py](/Users/mac/Desktop/PIAgent/backend/core/engine.py:1)，  
它只负责把更复杂的 agent orchestration 收敛成 PIAgent 可执行的 workflow。

### 4.3 Harness 输出的是 Graph Actions，不是自由 Graph

Lead agent 不应该直接写最终 graph JSON。

它应该输出受限动作：

```python
GraphAction =
  | {"type": "planning_update", "text": "..."}
  | {"type": "call_skill", "skill": "...", "input": {...}}
  | {"type": "spawn_subagent", "role": "...", "goal": "..."}
  | {"type": "add_node", "node": {...}}
  | {"type": "add_edge", "edge": {...}}
  | {"type": "update_node_config", "node_id": "...", "patch": {...}}
  | {"type": "commit_graph"}
```

这样做的好处：

- 错误空间更小
- 事件可直接映射到 UI
- 可以逐步增加 skill / sub-agent / memory 能力
- 仍然能保住 GraphCompiler 作为最终裁判

### 4.4 Skills 先做 typed internal skills

第一阶段的 skill 不应是开放式脚本，而应是 typed internal skills。

建议先做：

- `load_capabilities`
- `draft_recipe`
- `draft_graph_action`
- `validate_graph`
- `select_provider`
- `select_knowledge_base`
- `run_graph`

这些 skills 本质上是对现有能力的显式封装，而不是新发明的 runtime。

**实现原则：薄封装优先。** 第一版 skill 的 `invoke()` 方法应该是对现有函数的直接委托，加上 schema 输入输出约束，不引入额外的队列、重试、或审计机制。例如 `draft_recipe` skill 内部直接调用 `AgentPlanner._build_default_recipe()` + `AgentGenerator.generate()`，`validate_graph` 内部直接调用 `GraphCompiler().validate()`。只有当 skill 被证明需要独立的超时或错误处理时，再逐步加厚。

### 4.5 Sub-agents 是增强层，不是基础依赖

DeerFlow-style sub-agents 非常有价值，但在 PIAgent 中应该是第二阶段能力。

推荐的早期 sub-agent：

- `CapabilityScoutAgent`：探索当前 provider / KB / node 组合
- `GraphCriticAgent`：检查 draft graph 的结构风险
- `RecipeChallengerAgent`：挑战 lead agent 的默认方案

这些 sub-agents 只能输出结构化观察，不直接修改 graph。

### 4.6 Memory 分层引入

Memory 不应该一开始就做成长程复杂系统。

建议分三层：

1. Session Memory：单次 auto-run 的 planning trace
2. Project Memory：项目级偏好，例如常用 provider / voice / graph style
3. Long-term Memory：跨任务的经验沉淀

当前最适合先做的是 Session Memory 和少量 Project Memory。

### 4.7 Sandbox 作为后置能力

Sandbox 是 DeerFlow-style harness 的重要组成，但在 PIAgent 中应该后置。

原因：

- 当前系统主路径仍然是 workflow orchestration，不是 OS agent
- 高权限工具需要审计、隔离、日志与权限模型
- 一旦做错，会把风险从 “graph 生成错误” 提升到 “执行环境被误操作”

因此本 spec 里只预留 SandboxAdapter 位置，不要求当前 phase 落地。

---

## 5. 总体架构

```text
用户目标
   │
   ▼
Harness API
   │
   ▼
LeadAgent
   ├── SkillRegistry
   │    ├── load_capabilities
   │    ├── draft_recipe
   │    ├── validate_graph
   │    └── run_graph
   │
   ├── SubAgentManager (Phase 2+)
   │    ├── CapabilityScoutAgent
   │    ├── GraphCriticAgent
   │    └── RecipeChallengerAgent
   │
   └── MemoryStore
        ├── session trace
        └── project preferences
   │
   ▼
GraphDraftBuilder
   │
   ▼
GraphCompiler / WorkflowGraphAdapter
   │
   ▼
ExecutionEngine
   │
   ▼
SSE -> Frontend Canvas + Debug UI
```

---

## 6. 组件设计

### 6.1 LeadAgent

LeadAgent 是 harness 的总控者。

它负责：

- 理解用户目标
- 读取 memory
- 选择调用哪些 skills
- 决定是否需要 sub-agents
- 逐步输出 graph actions

它不直接：

- 访问数据库细节
- 写 graph JSON 到最终存储
- 直接运行 shell / filesystem / network

这些行为都应通过 skills 或 adapters 完成。

### 6.2 SkillRegistry

SkillRegistry 是 harness 的能力边界层。

它的职责是：

- 暴露技能词表
- 为每个 skill 提供 schema
- 统一超时、错误格式、审计信息

建议接口：

```python
class HarnessSkill(Protocol):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    async def invoke(self, ctx: HarnessContext, payload: BaseModel) -> BaseModel: ...
```

### 6.3 GraphDraftBuilder

GraphDraftBuilder 是连接 Harness 与 Workflow Runtime 的关键桥梁。

职责：

- 消费 graph actions
- 维护 draft graph
- 在每一步 emit UI 事件
- 在 `commit_graph` 时调用 GraphCompiler

它可以复用当前的 WorkflowGraphAdapter 思路，但不等于简单替换它。

更准确地说：

- `WorkflowGraphAdapter` 适合 recipe 展开
- `GraphDraftBuilder` 适合 action 驱动的增量搭图

二者未来可以并存。

### 6.4 SubAgentManager

SubAgentManager 负责创建、复用和收集 sub-agents 的结果。

约束：

- sub-agent 只在受控 role 下运行
- sub-agent 不直接发 graph mutations
- sub-agent 的输出必须被 lead agent 再消费一次

这能避免 “多 agent 同时改图” 造成的不可控状态。

### 6.5 MemoryStore

MemoryStore 至少需要支持：

- 保存当前 harness session 的 planning trace
- 保存当前任务中的关键决策
- 为下轮规划提供简化摘要

建议初始结构：

```python
HarnessMemory = {
  "session_id": "...",
  "goal": "...",
  "events": [...],
  "capability_snapshot": {...},
  "selected_strategy": "...",
  "graph_summary": {...},
}
```

### 6.6 SandboxAdapter

SandboxAdapter 当前只做接口预留。

未来若开放外部工具，可按 skill 级别接入：

- HTTP sandbox
- file sandbox
- shell sandbox

但当前阶段不进入默认路径。

---

## 7. 与当前 PIAgent 架构的映射

### 7.1 可直接复用的资产

以下组件可以直接成为 Harness 的基础设施：

- `AgentPlanner` 中的能力感知与 repair 逻辑
- `WorkflowGraphAdapter` 中的 graph 构建经验
- `GraphCompiler`
- `ExecutionEngine`
- 现有 SSE 事件链路
- 现有 Canvas 渐进渲染 UI

### 7.2 需要新增的模块

建议新增：

```text
backend/harness/
├── __init__.py
├── lead_agent.py
├── context.py
├── schemas.py
├── actions.py
├── memory.py
├── registry.py
├── builder.py
├── orchestrator.py
├── skills/
│   ├── __init__.py
│   ├── capabilities.py
│   ├── recipe.py
│   ├── graph_validation.py
│   └── execution.py
└── subagents/
    ├── __init__.py
    ├── capability_scout.py
    ├── graph_critic.py
    └── recipe_challenger.py
```

### 7.3 与现有 AgentPlanner 的关系

不是直接删除 AgentPlanner，而是分阶段重构。关键是明确过渡期的共存策略：

**Phase H0-H1（并行共存期）：**

- 现有 Agent Mode 的 `api/agent.py → AgentPlanner` 路径保持不动，作为 Fast Path 继续服务简单目标
- 新增 `api/harness.py` 作为 Harness Path 的独立入口
- 前端通过 feature flag（或路由参数）决定走哪条路径
- `LeadAgent` 的 `draft_recipe` skill 内部复用 `AgentPlanner` 的 `_build_default_recipe()` 和 `AgentGenerator.generate()`，确保输出格式兼容

**Phase H1-H2（收敛期）：**

- `AgentPlanner` 的核心逻辑拆成独立 skills（`draft_recipe`、`validate_graph` 等）
- `api/agent.py` 的 auto-run 路径改为由 `harness/orchestrator.py` 统一路由
- Fast Path 变成 orchestrator 下的一条快速通道，不再是独立 API

**Phase H2+（稳态）：**

- Harness 成为唯一入口
- AgentPlanner 作为 `draft_recipe` skill 的内部实现细节存在
- 旧的 `api/agent.py` 只做 thin proxy 到 Harness API

---

## 8. 事件与可视化契约

Harness 模式应沿用当前可视化 build-and-run 事件风格，但事件语义要更清晰。

建议事件族：

- `planning_start`
- `planning_update`
- `planner_action`
- `planner_observe`
- `skill_start`
- `skill_end`
- `subagent_spawned`
- `subagent_result`
- `node_added`
- `edge_added`
- `node_config_updated`
- `plan_ready`
- `workflow_built`
- `planning_error`

说明：

- `planning_update` 只展示对用户可见的摘要，不暴露原始 chain-of-thought
- `skill_start/end` 用于说明 lead agent 正在用什么能力
- `subagent_spawned/result` 只在 Phase 2+ 启用
- `node_added/edge_added` 继续作为驱动画布生长的核心事件

---

## 9. 分阶段安排

### Phase H0：Harness Lite Spec + API 骨架

执行情况：已完成

目标：

- 建立 harness 概念和模块边界
- 不改变现有主路径
- 为后续开发准备 schema、文件结构、接口约定

验收：

- 有独立 spec
- 有模块骨架
- 不影响现有 Agent Mode 和 auto-run

本轮落地说明：

- 已新增 `backend/harness/` 模块骨架与基础 `schemas / actions / registry / builder / orchestrator`
- 已新增独立 API 入口 `/api/harness/auto-run`
- 现有 Agent Mode 主路径未被替换，旧 `api/agent.py` 保持不动
- 前端 auto-run 已切到 Harness SSE 入口，但仍沿用既有事件消费链，不需要重做画布或调试 UI

### Phase H1：LeadAgent + Typed Skills

执行情况：已完成（H1-lite + H1-advanced）

目标：

- 引入 `LeadAgent`
- 把现有规划主路径收敛为一组 typed skills
- 用 graph actions 替代 “一次性直接给 graph”
- 实现 Fast Path / Harness Path 路由

范围：

- 暂不引入 sub-agents
- 暂不引入 sandbox
- Fast Path 保留现有 AgentPlanner 链路不动，Harness Path 作为新路径并存

验收：

- 简单目标走 Fast Path，复杂目标走 Harness Path，用户无感知
- Harness Path 下 `auto-run` 由 LeadAgent 驱动，逐步发出 graph actions
- 前端能看到渐进式搭图（`node_added` / `edge_added` 事件驱动画布）
- Harness 单次会话 LLM 调用不超过 10 次

本轮落地说明：

- 已引入 `LeadAgent`
- 已把 `capabilities / recipe / graph_validation / execution` 收敛成 typed skills 薄封装
- 已通过 `LeadAgent -> graph actions -> GraphDraftBuilder -> commit_graph -> execute` 跑通主链路
- 已支持 `planning_update / node_added / edge_added / node_config_updated / workflow_built / plan_ready`
- 已支持简单 `fast` / `harness` 路由
- `LeadAgent` 在 Harness Path 下已通过 `AgentLLMClient.structured_invoke(LeadAgentPlan)` 实现单次结构化规划，动态输出 skill 序列与 graph actions
- LLM 不可用时自动降级到硬编码链，确保本地开发与测试稳定
- 已补充 `skill_start / skill_end` 事件，已具备 session memory / sub-agent hooks

### Phase H2：Sub-agents

执行情况：已完成（H2-lite + H2-full 已落地）

目标：

- 支持受限 sub-agents
- 用于探索、批判和校验，而不是直接改图

建议先做：

- `CapabilityScoutAgent`
- `GraphCriticAgent`

验收：

- lead agent 能在 feature flag 下调用 sub-agents
- sub-agent 输出被 UI 可视化展示

本轮落地说明：

- 已实现 `GraphCriticAgent`（规则版），在 `commit_graph` 前自动检查：缺少 end 节点、孤立节点、悬空边、循环
- 已实现 `CapabilityScoutAgent`（LLM + 规则回退），在 `load_capabilities` 之后输出能力推荐
- 已实现 `RecipeChallengerAgent`（LLM + 规则回退），在 `draft_recipe` 之后输出方案批判与替代建议
- 所有 sub-agents 均以非阻塞方式运行，结果通过 `subagent_spawned / subagent_result` 事件进入 SSE 流
- LLM 不可用时自动回退到规则路径，确保本地开发与测试稳定

### Phase H3：Session Memory + Project Memory

执行情况：已完成（H3-lite + H3-advanced 已落地）

目标：

- 让 harness 在单次任务内更连贯
- 对常用偏好做轻量持久化

验收：

- 相同项目下的 provider / KB / voice 选择可被复用
- planning trace 可在下一轮作为上下文

本轮落地说明：

- `HarnessMemoryStore` 已落地，复用现有 `agent_sessions` 表，避免新增 DB migration
- 支持创建会话、追加事件、保存 graph/recipe 快照、跨轮恢复 session
- orchestrator 在 `build()` 入口自动加载/恢复 session memory
- 新增 `ProjectPreference` 模型与 `HarnessProjectMemoryStore`，自动记录用户常用 provider / voice / knowledge base / graph style
- orchestrator 在每次 session 结束时自动 `learn_from_session`，把实际使用的配置沉淀为项目偏好
- 在 capabilities 加载后 emit `project_memory_loaded` 事件，LeadAgent LLM 规划时会参考 project memory 摘要

### Phase H4：SandboxAdapter

目标：

- 在权限受控前提下开放更强的外部能力

前提：

- skill 审计
- 权限分级
- 失败回滚策略

验收：

- 高风险工具默认关闭
- 所有 sandbox tool use 有清晰的事件和审计日志

---

## 10. 测试策略

Harness 模式至少需要三层测试：

### 10.1 单元测试

- LeadAgent action 生成
- SkillRegistry schema 校验
- GraphDraftBuilder 的 action 应用
- MemoryStore 的读写逻辑

### 10.2 集成测试

- `goal -> harness -> graph actions -> graph`
- `goal -> harness -> commit_graph -> execute`
- sub-agent 输出被 lead agent 正确消费

### 10.3 UI / 事件测试

- Harness 事件顺序符合预期
- `node_added/edge_added` 能正确驱动画布
- `planning_error` / `skill_end(error)` 能正确落到 UI

---

## 11. 风险与权衡

### 11.1 过早引入过多 agent 角色

如果一开始就上完整 multi-agent，会让系统复杂度远超当前收益。

策略：

- 先做 Harness Lite
- 再引入有限 sub-agents

### 11.2 Harness 与 Workflow Runtime 边界模糊

如果 harness 直接接管 runtime，会导致调试困难和职责混乱。

策略：

- Harness 只做 orchestration
- Runtime 继续做确定性执行

### 11.3 Harness 路径的 LLM 调用成本

当前 Agent Mode 是 `clarify → plan → adapt` 约 3 次 LLM 调用。Harness 模式下 LeadAgent 需要 "理解目标 → 选 skills → 逐步发 actions → 验证"，可能变成 5-8 次调用。

策略：

- Fast Path / Harness Path 分流（见 4.1），简单目标不进 Harness
- LeadAgent 的 skill 调用尽量合并：例如 `load_capabilities` + `draft_recipe` 可以在一次 LLM tool_use 调用中同时触发
- 设置单次 Harness 会话的最大 LLM 调用次数上限（建议 10 次），超出则强制 `commit_graph` 或降级到 Fast Path

### 11.4 Sandbox 带来的安全复杂度

高权限工具一旦开放，产品风险会显著上升。

策略：

- sandbox 后置
- skill 默认白名单
- 事件和审计先行

---

## 12. 最终判断

PIAgent 很适合引入 DeerFlow-style harness，但正确姿势不是 “把 DeerFlow 原样搬进来”，而是：

1. 保留现有 workflow runtime 作为稳定执行底座
2. 在其上新增 Harness 层
3. 用 lead agent + typed skills + graph actions 收敛规划逻辑
4. 再按阶段补 sub-agents、memory、sandbox

换句话说：

> PIAgent 的演进方向不是从 Workflow Tool 变成 Chat Agent，  
> 而是从 Workflow Tool 升级为 Visual Super Agent Harness。

这条路线既符合 DeerFlow 的架构启发，也符合 PIAgent 当前最强的产品差异化方向。

---

## 13. Demo 优先级

H0 + H1 是最小可 demo 单元。一个能展示的 "lead agent 逐步搭图 + 画布实时生长" 比做到 H3 但每层半成品更有说服力。

**核心 demo 路径：**

1. 用户输入复杂目标（如 "帮我做一个先检索知识库再生成播客脚本最后合成音频的 workflow"）
2. Harness 面板展示 LeadAgent 的规划过程（`planning_update` 事件）
3. 画布上节点逐个出现（`node_added` / `edge_added` 事件驱动 React Flow 动画）
4. 图搭完后自动校验（`validate_graph` skill）
5. 用户确认后一键执行

**面试讲解重点：**

- **Graph Actions 协议设计**：为什么约束 agent 的输出空间比让它自由生成 JSON 更好？（错误空间、可回滚性、事件流兼容）
- **渐进式画布生长的全链路**：harness 事件 → SSE → Zustand store → React Flow 动画，这是一条完整的 real-time data flow
- **Harness vs Runtime 职责分离**：planning 与 execution 的经典架构问题，在 agent 场景下的具体落地
