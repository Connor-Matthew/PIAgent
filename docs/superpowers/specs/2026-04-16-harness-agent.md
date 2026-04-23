# PIAgent - Harness Agent 设计文档

> 状态：提案草案
> 范围：定义 PIAgent 从当前 “Harness 骨架 + Recipe Planner + Workflow Runtime” 演进到真正 `Harness Agent` 的目标态、边界和分期路线。
> 目标：把 “看起来像 agent” 的现状，升级为 “具有持续调度能力的 harness + 具有真实 tool loop 的 runtime agent”。
> 关系：
> - 当前已落地的 Harness 骨架详见 `2026-04-16-agent-harness.md`
> - 当前已落地的 Agent Mode 详见 `2026-04-15-agent-mode.md`
> - 当前 Runtime Tool Use 的历史计划已归档，详见 `../plans/archive/2026-04-16-agent-tool-use.md`
> - 本文档不重复记录已完成内容，而是定义下一阶段的目标态和实施标准

---

## 1. 为什么需要单独写这份 spec

当前 PIAgent 已经有三块能力：

1. `Agent Mode` 能把自然语言目标收敛成 `RecipeIR`
2. `Harness` 能把部分 planning 过程包装成统一 orchestration 壳
3. `Workflow Runtime` 能稳定执行一张确定性的 graph

但这三者拼起来，还不等于真正的 `Harness Agent`。

目前系统更接近：

`goal -> 受限 planner -> 固定 recipe 展开 -> 确定性执行`

而目标中的 `Harness Agent` 应该更接近：

`goal -> lead agent loop -> bounded skills / sub-agents / memory / sandbox -> graph or runtime decisions -> execution`

也就是说，当前系统已经有 harness 的形状，但还没有 harness 的核心行为：

- Lead agent 会根据前一步 observation 决定下一步动作
- Skill registry 是真正的能力边界，而不只是函数薄封装
- Graph 是增量构造出来的，而不是主要靠固定 recipe 展开
- Runtime 中的 agent 节点能真实进行 tool loop
- Memory 与 sandbox 会真实参与决策和边界控制

因此需要一份新的 spec，明确回答：

- 什么才算 `Harness Agent`
- 当前差距具体在哪里
- 应按什么顺序演进，才能既保住稳定性，又逐步变得更像真正 agent

---

## 2. 目标定义

### 2.1 什么叫 Harness Agent

在 PIAgent 语境里，`Harness Agent` 指的是一种双层结构：

1. **Harness 规划层**
   - 由 `LeadAgent` 主控
   - 能循环读取上下文、调用 skills、读取 observations、调整策略
   - 最终把任务收敛为可执行 graph 或明确的 runtime plan

2. **Runtime 执行层**
   - 由 `ExecutionEngine` 执行 graph
   - graph 中的普通节点保持确定性
   - graph 中的 `agent` 节点可以在受控边界内进行真实 tool loop

换句话说：

- Harness Agent 不是单个 `AgentNode`
- Harness Agent 也不是一次性 planner
- Harness Agent 是 “持续调度的上层 agent” 与 “可控执行的下层 runtime” 的组合

### 2.2 成功标准

当以下条件成立时，PIAgent 才能算进入 `Harness Agent` 阶段：

1. `LeadAgent` 不再只是单次结构化规划，而是支持多步决策循环
2. 每次 skill 调用都有 typed input/output、统一错误格式和审计事件
3. Harness Path 主要依赖 graph actions 增量搭图，而不是默认退回固定 recipe 展开
4. `agent` 节点具备真实工具调用能力，而不是 placeholder
5. Memory 不只是展示摘要，而会影响后续选择
6. 开放式工具调用存在 sandbox / policy 边界

### 2.3 非目标

本 spec 不追求下面这些事情一步到位：

- 一开始就支持完全开放、任意复杂的 DAG 自动生成
- 一开始就让所有节点都变成 agent 节点
- 用 harness 取代 `ExecutionEngine`
- 在没有安全边界前开放任意 shell / filesystem / network 执行

本 spec 的目标是：**在不破坏现有稳定链路的前提下，渐进式把系统做成真正的 harness agent。**

---

## 3. 当前差距

### 3.1 当前 Harness 更像单次 planning wrapper

当前 `HarnessOrchestrator` 已经把 planning、build、run 串起来了，但 `LeadAgent` 本质上仍偏单次决策：

- Fast Path 直接走硬编码 skill 链
- Harness Path 主要走一次 `LeadAgentPlan`
- 之后大部分 graph 仍由 `draft_recipe` 产物展开

这意味着：

- 模型还没有真正根据 observation 连续调整动作
- “会调用 skill” 和 “会持续调度 skill” 还不是一回事

### 3.2 当前 recipe 仍然是主导结构的核心

当前 `draft_recipe` 的输出仍然是受限 `RecipeIR`，并由 adapter 展开成：

- `start -> llm -> end`
- `start -> rag -> llm -> end`
- `start -> llm -> tts -> end`
- `start -> rag -> llm -> tts -> end`

这条路径非常稳定，但它本质上仍然是：

- 选套餐
- 按套餐拼图

而不是：

- 看当前上下文
- 增量做决策
- 必要时修改之前的搭图策略

### 3.3 Runtime 仍然以确定性节点执行为主

当前 `ExecutionEngine` 的核心行为是：

- topological sort
- 按顺序执行每个节点
- 收集节点输出
- 交给 `end` 节点做模板引用和结果拼装

这很好，但它说明：

- Runtime 主链路现在不是 agent loop
- 工具调用顺序主要由图预先决定，而不是运行时由模型决定

### 3.4 AgentNode 还不是真实 tool loop

当前 `AgentNode` 已接入 ReAct 形式，但工具仍偏占位：

- 工具集很小
- 工具实现仍是 placeholder
- 没有统一的 runtime 工具注册表
- 缺少完整的 `agent_action / agent_observe / policy_intervention` 事件模型

所以它只能算 “agent 节点接口已存在”，还不能算 “runtime agent 已成立”。

### 3.5 Memory 和 Sub-agent 目前主要是补充性而不是决定性

当前：

- memory 已能保存 session / project 摘要
- sub-agents 已能给出建议或批判

但它们还没有深度改变主循环的决策方式。真正的 harness agent 中：

- memory 应影响下一步动作选择
- sub-agent 结果应能改变主 plan，而不只是作为旁路提示

---

## 4. 目标架构

### 4.1 总览

目标态的 PIAgent 应拆成五层：

1. **入口层**
   - API
   - SSE / UI event stream
   - session resume / cancel / debug

2. **Harness 规划层**
   - `HarnessOrchestrator`
   - `LeadAgentLoop`
   - `SkillRegistry`
   - `SubAgentManager`
   - `MemoryContextAssembler`

3. **Graph 构建层**
   - `GraphDraftBuilder`
   - `GraphValidation`
   - `GraphPlanIR` / `GraphAction`

4. **Runtime 执行层**
   - `ExecutionEngine`
   - 普通确定性节点
   - `AgentNode` runtime tool loop

5. **安全与环境层**
   - `SandboxAdapter`
   - tool policy
   - audit / approval / rate limit / timeout

### 4.2 两个 agent，不同职责

目标态里应该明确存在两个不同级别的 agent：

#### A. Harness LeadAgent

负责：

- 理解目标
- 决定是否继续澄清
- 决定调用哪个 skill
- 决定是否拉起 sub-agent
- 决定如何增量搭图
- 决定什么时候 `commit_graph`

不负责：

- 直接访问数据库细节
- 直接运行 shell / network / filesystem
- 直接写最终 graph JSON 到存储

#### B. Runtime AgentNode

负责：

- 在 graph 执行期基于上下文进行 tool loop
- 调工具、看 observation、再调下一步
- 生成节点级结果

不负责：

- 改写整张 graph
- 决定系统级 routing
- 操作不在 policy 允许范围内的能力

### 4.3 推荐的主循环

#### Harness 主循环

```python
ctx = load_context(goal, session_memory, project_memory)

while not done and step_budget_not_exceeded:
    decision = lead_agent.decide(ctx, available_skills, available_subagents)

    if decision.type == "call_skill":
        result = registry.invoke(decision.skill, decision.payload)
        ctx.observe(result)
        emit(skill events)
        continue

    if decision.type == "spawn_subagent":
        report = subagent_manager.run(decision.role, decision.payload)
        ctx.observe(report)
        emit(subagent events)
        continue

    if decision.type == "graph_action":
        builder.apply(decision.action)
        ctx.observe(builder.snapshot())
        emit(graph events)
        continue

    if decision.type == "commit_graph":
        builder.commit()
        done = True
```

#### Runtime AgentNode 循环

```python
while not finished and tool_budget_not_exceeded:
    model_step = llm.decide(messages, tools, context)

    if model_step.type == "tool_call":
        obs = tool_registry.invoke(model_step.tool, model_step.args, sandbox=adapter)
        messages.append(obs)
        emit(agent_action / agent_observe)
        continue

    if model_step.type == "final":
        return model_step.output
```

---

## 5. 设计原则

### 5.1 先把决策回路做出来，再追求自由度

最先要补的是：

- `LeadAgent` 的多步循环
- `AgentNode` 的真实 tool loop

不是一上来就追求任意 DAG 生成。

### 5.2 优先受限动作，不让模型直接写自由结构

无论是 Harness 还是 Runtime，都不应该让模型直接获得无限自由：

- Harness 侧发受限 `GraphAction`
- Runtime 侧调受控 `ToolRegistry`

这能最大限度保住：

- 可观测性
- 可回放性
- 可验证性
- UI 事件映射

### 5.3 保留 Fast Path

即使进入 Harness Agent 阶段，也不应该让所有请求都走完整 agent loop。

对于简单目标，应继续保留：

`goal -> planner/direct skill -> graph`

只有复杂、模糊、多阶段目标，才进入完整 Harness Path。

### 5.4 Harness 规划层与 Runtime 执行层必须分离

`Harness != ExecutionEngine`

Harness 的价值是：

- 规划
- 收敛
- 调度

Runtime 的价值是：

- 执行
- 流式反馈
- 结果产出

把两者混在一起，会导致：

- 调试困难
- 责任模糊
- 安全边界不清

---

## 6. 核心能力拆解

### 6.1 LeadAgent Loop

需要把当前一次性 `LeadAgentPlan` 升级为循环式 `LeadAgentLoop`。

建议能力：

- step budget
- 可恢复 session trace
- 统一 decision schema
- 每一步都有 reasoning summary
- 支持根据 observation 改 plan

建议输出：

```python
LeadDecision =
  | {"kind": "planning_update", ...}
  | {"kind": "call_skill", "name": "...", "payload": {...}}
  | {"kind": "spawn_subagent", "role": "...", "payload": {...}}
  | {"kind": "graph_action", "action": {...}}
  | {"kind": "commit_graph"}
  | {"kind": "finish_without_graph"}
```

### 6.2 Skill Registry

目标态的 skill registry 应该为每个 skill 提供：

- 名称
- 描述
- input schema
- output schema
- timeout
- retry policy
- audit metadata

第一批建议 skills：

- `load_capabilities`
- `draft_recipe`
- `select_provider`
- `select_knowledge_base`
- `draft_node_config`
- `validate_graph`
- `run_graph`
- `resume_session_memory`
- `write_project_memory`

第二批建议 skills：

- `web_search`
- `http_fetch`
- `knowledge_lookup`
- `code_search`
- `sandbox_exec`

### 6.3 Incremental Graph Builder

`GraphDraftBuilder` 应从“能接 action”升级为“增量搭图的主战场”。

需要补的能力：

- 节点模板与默认配置库
- 显式输入映射
- 条件分支
- merge/select 节点
- 结构约束与局部修复
- builder snapshot 作为新的 observation 回流给 LeadAgent

这样 LeadAgent 才能真正做到：

- 先搭一版
- 看 builder 状态
- 再补节点或修配置

### 6.4 Runtime AgentNode

`AgentNode` 需要从 placeholder 进化到真实 tool-use runtime：

- 从统一 `backend/tools/` 加载工具
- 工具有 schema 与 policy
- 支持事件：
  - `agent_action`
  - `agent_observe`
  - `agent_thought_summary`
  - `agent_finish`
  - `agent_intervention`
- 支持工具 budget / token budget / timeout
- 支持 sandbox adapter

### 6.5 Memory

Memory 至少要分三层：

1. `SessionMemory`
   - 当前任务的 planning trace
   - 当前任务的 intermediate observations

2. `ProjectMemory`
   - 常用 provider / voice / kb 偏好
   - 常见 graph style 偏好
   - 历史成功模式

3. `ExecutionMemory`
   - runtime 工具调用历史
   - 失败案例与回退信息

目标态不是“把 memory 存起来”，而是“memory 能改变下一步决策”。

### 6.6 Sandbox / Policy

真正的 harness agent 一旦有开放式工具调用，就必须有 sandbox。

建议边界：

- 默认 deny
- 按 tool category 放行
- shell / fs / network 分级
- 每个 tool 有 timeout / size / domain / path 限制
- 所有开放式调用都带 audit trace

Sandbox 可以后置落地，但 policy 接口需要先预留。

---

## 7. 分期路线

### Phase HA1：LeadAgent 真正循环化

目标：

- 把单次 `LeadAgentPlan` 升级为多步 `LeadAgentLoop`
- 每一步基于 observation 决定下一个 skill / sub-agent / graph action

范围：

- 暂不做开放式 tools
- 暂不做自由 DAG
- 仍以 typed internal skills 为主

验收：

- 一个 Harness 会话内允许 3-10 步决策
- 至少存在 “调用 skill -> 读取结果 -> 调整下一步” 的真实链路
- session resume 后能从 trace 恢复上下文

涉及模块：

- `backend/harness/lead_agent.py`
- `backend/harness/orchestrator.py`
- `backend/harness/schemas.py`
- `backend/harness/prompts.py`
- `backend/harness/memory.py`

### Phase HA2：Graph Builder 成为主通道

目标：

- 让 Harness Path 主要通过 `GraphAction` 增量搭图
- 降低对固定 recipe 展开的依赖

范围：

- 先支持节点模板化增量拼接
- 再支持输入映射和局部修复

验收：

- 至少一种复杂目标不再主要依赖 `RecipeIR -> Adapter`
- builder snapshot 能作为 planning observation 回流
- UI 能看到更细粒度的搭图演进

涉及模块：

- `backend/harness/builder.py`
- `backend/harness/actions.py`
- `backend/harness/skills/*`
- `backend/core/compiler.py`

### Phase HA3：Runtime AgentNode 真正 Tool Use

目标：

- graph 中的 `agent` 节点在执行期能真实调用工具

范围：

- 建立 `backend/tools/`
- 工具注册表、schema、policy、runtime events
- 先接 `web_search / http_request / knowledge_lookup`

验收：

- `agent` 节点能至少连续调 2 次工具
- 前端 timeline 能看到 action / observe
- 工具失败时能回传 observation 而不是直接崩溃

涉及模块：

- `backend/nodes/agent_node.py`
- `backend/tools/`
- `backend/core/engine.py`
- 前端调试面板 / 时间线

### Phase HA4：自由 DAG 能力升级

目标：

- 从“线性 recipe 扩展”升级到“受控自由组合”

范围：

- 显式输入映射
- merge/select 节点
- 分支与回退链路
- 更严格的 `GraphPlanIR`

验收：

- planner 可安全生成非线性 DAG
- graph compile / validate / recover 流程可回放
- 不会因为更自由而显著提高坏图率

### Phase HA5：Memory 与 Sandbox 完整落地

目标：

- memory 和 sandbox 从旁路能力升级为一等能力

范围：

- 让 ProjectMemory 真正影响 provider / kb / graph style 选择
- 让开放式工具调用接入 sandbox 与 policy

验收：

- memory 会影响至少两类真实决策
- 开放式工具调用均可审计、可限制、可回放

---

## 8. 推荐实施顺序

推荐顺序不是：

`先做任意复杂 graph -> 再补 agent`

而应该是：

1. `LeadAgentLoop`
2. `SkillRegistry` 强化
3. `AgentNode` 真实 tool use
4. `GraphBuilder` 自由度提升
5. `Memory + Sandbox` 深化

原因：

- 先把“决策回路”补齐，系统才开始像 harness agent
- 先把 runtime tool loop 补齐，系统才开始像真正 agent
- graph 自由度放在后面，能显著降低前期失控风险

---

## 9. 风险与控制

### 9.1 Token / 延迟暴涨

Lead loop 和 runtime tool loop 都会增加调用次数。

控制策略：

- 保留 Fast Path
- 设置 step budget / tool budget
- 把 reasoning 压缩成 planning summary，而不是全量暴露 chain-of-thought

### 9.2 图结构失控

一旦增量搭图更自由，坏图率会上升。

控制策略：

- 受限 `GraphAction`
- builder snapshot 验证
- `GraphCompiler` 作为最终裁判
- commit 前 critic / validator

### 9.3 工具能力失控

一旦 runtime agent 真正调工具，就会带来安全与观测问题。

控制策略：

- tool registry
- policy
- sandbox
- 审计事件

### 9.4 职责耦合

若 Harness 和 Runtime 相互侵入，维护成本会急剧升高。

控制策略：

- Harness 只负责调度与收敛
- Runtime 只负责执行
- 共享契约走 schema / event / tool registry，而不是直接互调内部细节

---

## 10. 对当前项目的结论

从本 spec 的标准看，PIAgent 当前状态更适合被定义为：

- 已有 `Harness Skeleton`
- 已有 `Planner-driven Workflow Builder`
- 已有 `Deterministic Workflow Runtime`
- 已有 `AgentNode Interface`

但还不能被定义为真正的 `Harness Agent`。

下一阶段的核心，不是继续把 planner prompt 写得更聪明，而是补齐两条真正的回路：

1. **Harness 侧的持续调度回路**
2. **Runtime 侧的真实工具调用回路**

只有这两条回路都成立，PIAgent 才会从 “agent 风格工作流系统” 进入 “真正的 harness agent 系统”。

---

## 11. Implementation Plan

本节不是再次描述目标，而是把上面的目标态拆成可执行施工单。

推荐策略：

- 每个 phase 都做成可合并、可测试、可回退的小纵切
- 不一次性替换现有 Fast Path
- 每个阶段都先补 schema / event / tests，再补更自由的行为

### 11.1 总体实施顺序

推荐按 6 个 PR 组推进：

1. `HA1-A`：`LeadDecision` schema + loop trace + session resume 能力
2. `HA1-B`：`LeadAgentLoop` 落地，支持 observation-driven 多步 skill 调度
3. `HA2`：`GraphDraftBuilder` 升级，builder snapshot 回流为 planning observation
4. `HA3-A`：runtime tool registry + `AgentNode` 真实 tool loop MVP
5. `HA3-B`：前端 timeline / debug 面板渲染 `agent_action` / `agent_observe`
6. `HA4/HA5`：自由 DAG、memory 决策化、sandbox / policy

这样做的好处是：

- HA1 完成后，系统已经开始像真正 harness
- HA3 完成后，系统已经开始像真正 agent
- HA4 / HA5 可以在前两者稳定后逐步放权

### 11.2 Phase HA1 实施清单

目标：

- 让 `LeadAgent` 从 “单次计划返回” 升级为 “多步循环决策”

后端任务：

- 在 `backend/harness/schemas.py` 新增 `LeadDecision`、`DecisionObservation`、`LoopTraceEntry`
- 在 `backend/harness/prompts.py` 新增 loop 模式 prompt，替代单次 `LeadAgentPlan` 的主路径
- 在 `backend/harness/lead_agent.py` 引入 `LeadAgentLoop.run_step()` 或等价接口
- 在 `backend/harness/orchestrator.py` 中把 `build()` 改为：
  - 初始化 context
  - while loop 执行 decision
  - 处理 `call_skill / spawn_subagent / graph_action / commit_graph`
- 在 `backend/harness/memory.py` 中补 session trace 的读写与 resume
- 为每一步 emit 新事件：
  - `lead_step_start`
  - `lead_step_end`
  - `lead_decision`
  - `lead_observation`

兼容策略：

- `settings` 下新增 feature flag，例如 `harness_loop_enabled`
- 关闭 flag 时仍走当前单次 `LeadAgentPlan` 路径

测试任务：

- 新增 `backend/tests/test_harness_lead_loop.py`
- 覆盖：
  - skill -> observe -> next skill 的真实多步链路
  - step budget 超限
  - session resume
  - LLM 失败时降级

验收标准：

- 至少一个 harness 请求会执行 3 步以上 decision
- 下一步 decision 能读取前一步 observation
- 前端能收到连续 lead loop 事件

### 11.3 Phase HA2 实施清单

目标：

- 让 `GraphDraftBuilder` 从 “动作消费者” 变成 “增量搭图主通道”

后端任务：

- 在 `backend/harness/actions.py` 增补更细粒度动作：
  - `select_node_template`
  - `bind_input`
  - `repair_graph`
- 在 `backend/harness/builder.py` 中新增 `snapshot()`，返回：
  - 当前节点列表
  - 当前边列表
  - 未满足输入
  - 已知风险
  - 最近一次校验结果
- 在 `backend/harness/skills/` 中新增：
  - `draft_node_config`
  - `select_provider`
  - `select_knowledge_base`
- builder 每次 apply 后都能产出可观察 snapshot，回流给 `LeadAgentLoop`
- 对复杂目标优先走 “actions 增量搭图”，仅在必要时回退 `RecipeIR -> Adapter`

测试任务：

- 新增 `backend/tests/test_harness_builder_loop.py`
- 覆盖：
  - 多次 add/update 后 snapshot 正确
  - builder snapshot 能驱动后续 decision
  - commit 前 validation / critic 结果能改变后续动作

验收标准：

- 至少一种复杂目标主要通过 actions 逐步长图，而不是一次性 recipe 展开
- `planning_update / node_added / edge_added / node_config_updated` 事件明显更细粒度

### 11.4 Phase HA3 实施清单

目标：

- 让 workflow 中的 `agent` 节点在 runtime 真正进行 tool loop

后端任务：

- 新增 `backend/tools/`
- 建立统一工具注册表：
  - `base.py`
  - `registry.py`
  - `schemas.py`
  - `policy.py`
- 第一批工具建议：
  - `web_search`
  - `http_request`
  - `knowledge_lookup`
- 重写 `backend/nodes/agent_node.py`：
  - 从 registry 读取工具
  - 替换当前 placeholder tool
  - 输出 runtime events：
    - `agent_action`
    - `agent_observe`
    - `agent_finish`
    - `agent_intervention`
- 在 `backend/core/engine.py` 中保持节点级事件不变，但允许透传 agent 子事件

前端任务：

- 在执行时间线中渲染 `agent_action / agent_observe`
- 在 DebugDrawer 中增加 agent loop 片段视图

测试任务：

- 新增 `backend/tests/test_agent_node_tools.py`
- 覆盖：
  - 连续 2 次 tool call
  - tool error -> observation -> recovery
  - policy deny -> intervention event

验收标准：

- 一个 `agent` 节点能完成至少一次 “tool_call -> observation -> second tool_call -> final”
- timeline 中能清楚看到 action / observe 序列

### 11.5 Phase HA4 实施清单

目标：

- 从线性 recipe 扩展升级为受控自由组合 DAG

后端任务：

- 在 `backend/agent/` 或 `backend/harness/` 中新增更严格的 `GraphPlanIR`
- 新增节点能力：
  - merge / select / branch
  - 显式 input mapping
- `GraphCompiler` 补更强的结构校验：
  - 输入是否满足
  - merge 规则
  - 节点字段可引用性
- `LeadAgentLoop` 可以基于 builder snapshot 决定分支与修复

测试任务：

- 新增 DAG 级集成测试
- 覆盖：
  - 非线性图成功构建
  - merge / select 正确运行
  - 错误 DAG 被拒绝并给出修复路径

验收标准：

- 至少一种非线性 graph 能稳定由 harness 构建并运行
- 坏图率不会显著高于当前 recipe-only 路径

### 11.6 Phase HA5 实施清单

目标：

- 让 memory 和 sandbox 从“配角”变成真正决策基础设施

后端任务：

- memory：
  - `ProjectMemory` 增加偏好与成功模式写入
  - `LeadAgentLoop` prompt 中显式消费 memory 片段
  - 决策结果写回 memory
- sandbox / policy：
  - 新增 `SandboxAdapter`
  - 区分 shell / fs / network policy
  - tool 级 timeout、path/domain allowlist
  - 审计日志与失败原因标准化

测试任务：

- 覆盖：
  - memory 改变 provider / kb 选择
  - sandbox deny / allow 的两种路径
  - audit trace 完整落库或完整事件化

验收标准：

- memory 至少影响两类真实选择
- 开放式工具调用全部可审计、可限制、可回放

### 11.7 推荐文件触达顺序

第一轮建议优先动这些文件：

- `backend/harness/schemas.py`
- `backend/harness/lead_agent.py`
- `backend/harness/orchestrator.py`
- `backend/harness/memory.py`
- `backend/tests/test_harness_orchestrator.py`

第二轮再动：

- `backend/harness/builder.py`
- `backend/harness/actions.py`
- `backend/harness/skills/*`

第三轮再动：

- `backend/nodes/agent_node.py`
- `backend/tools/*`
- `backend/core/engine.py`
- 前端执行调试 UI

这样可以避免一开始同时改 planning、builder、runtime 三层，降低耦合风险。

### 11.8 测试与回归矩阵

每个 phase 至少跑下面几类测试：

- 单元测试：
  - schema coercion
  - skill invocation
  - builder apply / snapshot
  - tool registry / policy

- 集成测试：
  - harness build
  - harness run
  - session resume
  - agent runtime tool loop

- 端到端回归：
  - Fast Path 仍可用
  - 旧 Harness Path 未启用新 flag 时行为不变
  - 新 Harness Path 在启用 flag 后可稳定出图并执行

建议命令：

- `backend/.venv/bin/python -m pytest backend/tests/test_harness_*.py`
- `backend/.venv/bin/python -m pytest backend/tests/test_agent_node_tools.py`
- `cd frontend && npm run build`

### 11.9 第一阶段的明确停止线

为了避免 spec 落地时无限扩张，建议先把第一阶段停止线写清楚。

HA1 完成即可视为第一阶段结束，当且仅当：

- `LeadAgentLoop` 已真实落地
- harness 主链路已不再完全依赖单次 `LeadAgentPlan`
- decision / observation / trace 事件完整可见
- Fast Path 未被破坏
- 现有 harness 测试与新增 lead loop 测试全部通过

在这之前，不建议提前把自由 DAG、开放 shell tools、复杂 sandbox 一次性并进来。
