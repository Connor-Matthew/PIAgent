# PIAgent - Custom Harness Agent 需求与设计说明

> 状态：需求确认稿
> 用途：作为交给新助手/新实现者的定制版 `Harness Agent` 构建说明
> 目标：从 DeerFlow 的 harness 思路中抽象出一套适合 PIAgent 的定制版 harness agent，但不照搬 DeerFlow 全量系统

---

## 1. 文档目的

这份文档不是实现计划，也不是代码 walkthrough。

它的用途是明确回答下面几个问题：

- 我们希望新的 `custom harness agent` 解决什么问题
- 它在 PIAgent 里应该处于哪一层
- `v1` 需要包含哪些能力
- `v1` 明确不做哪些能力
- 它和当前 `ExecutionEngine`、`Agent Mode`、`AgentNode`、前端画布的边界是什么
- 新助手在实现时应该遵守哪些架构约束

这份文档应被理解为一份 **framework-first, product-safe** 的需求说明。

---

## 2. 背景与问题定义

PIAgent 当前已经有三块相关能力：

1. `Agent Mode`
   - 能把自然语言目标收敛成 `RecipeIR`
   - 再通过 `WorkflowGraphAdapter` 展开成受限 workflow graph

2. `backend/harness`
   - 已有 harness 雏形
   - 已引入 `DecisionV2`、基础 Tool 协议、一些 loop 和 session memory 概念
   - 但整体仍更像“结构化输出 + 图构建壳”，还不是真正的 harness runtime

3. `Workflow Runtime`
   - `ExecutionEngine`、`GraphCompiler`、节点注册表、前端画布与 apply/run 链路已存在
   - 这一层是确定性 workflow 执行的稳定资产

当前系统的核心问题不是“没有 agent”，而是：

- 上层没有一个真正的、持续调度的 harness 中枢
- `backend/harness` 还缺少完整的 `session / workspace / trace / validator / recovery` 机制
- `AgentNode` 虽然接了 ReAct，但工具面仍偏占位，尚未成为真实可用的 runtime agent
- planning、tool use、memory、pause/resume、validation 还没有被统一到一套明确的运行时抽象中

因此，我们要构建的不是“另一个 planner”，而是一套 **PIAgent 定制版 Harness Agent Framework**。

---

## 3. 总体目标

新的 `custom harness agent` 需要达成下面两项目标：

### 3.1 上层目标

提供一个真正的 `Harness LeadAgent` 中枢，使系统能以会话为单位完成：

`理解目标 -> 轻量澄清 -> 逐步决策 -> 增量建图 -> 校验 -> 产出 draft`

### 3.2 下层目标

在保留当前 `ExecutionEngine` 的前提下，把 `AgentNode` 升级为真正的 runtime tool loop，使其具备：

- 受控工具调用
- 节点级推理与观察闭环
- 清晰的事件与预算边界

---

## 4. v1 范围决定

下面这些是已确认的 `v1` 边界，属于硬约束。

### 4.1 架构方向

`v1` 采用 **Framework-first, Product-safe** 路线：

- 目标是形成一套可以复用的 harness framework
- 但 `v1` 不追求成为通用平台或独立产品
- 先服务 PIAgent 当前产品形态

### 4.2 DeerFlow 迁移策略

采用 **选择性迁移骨架**，不是纯概念借鉴，也不是尽量兼容 DeerFlow。

要求：

- 借鉴 DeerFlow 的 harness 抽象方式
- 抽取适合 PIAgent 的核心原语
- 保留 PIAgent 自己的产品契约、workflow graph、运行时与前端事件模型

### 4.3 功能范围

`v1` 同时覆盖两层：

1. 上层 Harness 中枢
2. 下层 Runtime `AgentNode` tool loop

### 4.4 工具面范围

`v1` 的工具面只开放两类：

1. `workflow-native` 工具
2. `content-generation` 工具

明确不开放：

- 任意 shell
- 任意 filesystem
- 任意 network / HTTP
- 任意外部系统调用

### 4.5 交互节奏

`v1` 采用 **轻量澄清后再规划** 的模式：

- 通常先问 0-2 个关键问题
- 再进入建图与产出 draft

### 4.6 默认结果

`v1` 默认产出 **可审阅 graph draft**，不是默认 auto-run。

标准主链路为：

`goal -> clarify -> plan/build -> draft_ready -> user review/apply -> run`

### 4.7 `ask_user` 边界

`ask_user / pause-resume` 只在 **上层 Harness 规划期** 支持。

`AgentNode` 运行期不直接问用户。

### 4.8 memory 范围

`v1` 只做 **会话级 memory**：

- 当前 session 可恢复
- 当前 session 的 trace / graph snapshot / tool result 可追踪

明确不做：

- 项目级长期偏好学习
- 相似会话召回
- 长期用户画像

### 4.9 接入策略

`v1` 采用 **并行接入**：

- 保留现有稳定路径
- 新增一条 `custom harness agent` 路径或 feature flag
- 逐步验证后再考虑切流

---

## 5. 非目标

下面这些明确不属于 `v1`：

- 替换当前 `ExecutionEngine`
- 让 harness 直接接管整个 workflow 执行层
- 完整复刻 DeerFlow 全量能力
- 开放 sandbox、MCP、skills marketplace、外部环境执行
- 做真正的多智能体群体协作
- 做长期 memory 学习系统
- 让 `AgentNode` 在运行期越权修改整张 workflow graph
- 在 `v1` 中追求任意自由 DAG 自动生成

---

## 6. 目标架构

新的系统应被拆成三层。

### 6.1 Harness Framework 层

这是本次要新建或重构的核心层，负责：

- `session`
- `workspace`
- `lead loop`
- `tool registry`
- `validator pipeline`
- `trace`
- `pause/resume`
- `runtime agent runtime`

这一层是定制版 harness agent 的“灵魂”。

### 6.2 Product Adapter 层

这一层负责把 framework 接入 PIAgent 现有产品：

- FastAPI API
- SSE 事件流
- 前端状态面板
- graph draft review / apply
- feature flag 或平行入口

它的职责是“接入”和“翻译”，不是再次发明 agent 逻辑。

### 6.3 Workflow Runtime 层

这一层继续保留 PIAgent 现有稳定资产：

- `ExecutionEngine`
- `GraphCompiler`
- 节点注册表
- workflow graph JSON 契约

这一层仍然是确定性执行层。

---

## 7. 核心对象模型

`v1` 至少需要以下 6 个一等对象。

### 7.1 `HarnessSession`

表示一次完整的 harness 会话。

职责：

- 持有 `session_id`
- 管理当前阶段
- 管理预算
- 管理暂停、恢复、终止
- 持久化结构化 snapshot

不负责：

- 直接思考下一步
- 直接执行 graph
- 直接自由改 graph JSON

### 7.2 `Workspace`

作为会话的“真相来源”，用于给 LLM 生成 observation，并作为恢复依据。

至少应包含：

- `goal`
- 已澄清事实
- graph draft
- planning notes
- 最近若干轮 observation
- tool results
- validator findings
- pending question
- 最近一次失败原因
- 预算消耗

要求：

- `events` 可以继续保留为审计日志
- 但恢复与继续推理的主要依据必须是 `Workspace snapshot`

### 7.3 `LeadLoop`

这是上层智能中枢。

标准形式：

`observe -> decide(one decision) -> dispatch -> write back`

要求：

- 每轮只产出一个 `Decision`
- 不再以“一次吐完整 plan”作为主路径
- 决策协议应以显式 discriminated union 为正式契约

### 7.4 `ToolRegistry`

统一管理 framework 能力面。

要求：

- 统一 typed input/output
- 统一可用性声明
- 统一审计标签
- 统一超时与副作用元数据

### 7.5 `ValidatorPipeline`

负责在建图和 finalize 阶段提供可恢复的校验反馈。

要求：

- 区分 `DraftValidator` 与 `FinalizeValidator`
- 校验失败默认回写 observation，而不是直接终止 session

### 7.6 `AgentRuntime`

供 `AgentNode` 使用的节点级 runtime 壳。

要求：

- 复用同一套 tool protocol
- 有自己的预算和受限工具子集
- 不允许越权修改整个 harness session

---

## 8. 主链路要求

`v1` 的标准主链路固定为 5 个阶段。

### 8.1 阶段 1：Session 启动

收到用户目标后：

- 创建 `HarnessSession`
- 初始化 `Workspace`
- 写入初始事实
- 启动 SSE 事件流

初始状态至少包含：

- `goal`
- `session_id`
- `phase = clarifying`
- `clarify_budget = 2`
- 空 draft

### 8.2 阶段 2：轻量澄清

在澄清期只允许两类决策：

- `ask_user`
- `finalize_clarification`

典型澄清维度：

- 是否需要知识库
- 是否需要音频输出
- 风格与目标受众

要求：

- 最多 0-2 轮
- 发出 `ask_user` 后 session 必须进入 `waiting_user`
- 用户回复后必须恢复原 session，而不是开新 session

### 8.3 阶段 3：规划与建图

澄清结束后进入 `planning` 阶段。

开放动作面：

- `call_tool`
- `propose_action`
- `finalize`

要求：

- `call_tool` 用于获取结构化事实
- `propose_action` 只能使用受限 graph action
- 不允许 LLM 直接自由吐出最终 graph JSON 作为主路径

### 8.4 阶段 4：Finalize 产出 Draft

`finalize` 不是立即成功退出，而是一次正式的 finalize 尝试。

要求：

- 运行 `FinalizeValidator`
- 生成标准化 graph snapshot
- 写入 session snapshot
- 发出 `draft_ready`

若 finalize 失败：

- 失败必须回写到 `Workspace`
- 允许下一轮继续修复
- 不应默认 fallback 到硬编码路径

### 8.5 阶段 5：Review / Apply / Run

到 `draft_ready` 为止，Harness Framework 的主任务完成。

后续步骤继续复用产品现有能力：

- 用户 review draft
- 用户 apply graph
- 用户 run workflow
- `ExecutionEngine` 负责执行

---

## 9. Tool 模型要求

### 9.1 Tool 协议

`v1` 的 tools 必须采用 typed I/O。

协议至少需要包含：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `availability = planning | runtime | both`
- `side_effect_level = none | draft_mutation | external`
- `timeout_seconds`
- `audit_tag`

### 9.2 Planning Tools

首批 planning tools 至少应覆盖：

- `list_providers`
- `inspect_provider`
- `list_knowledge_bases`
- `peek_knowledge_base`
- `list_voices`
- `validate_graph_draft`
- `summarize_workspace`

要求：

- 以无副作用事实查询为主
- 帮助上层 loop 做 provider / kb / voice / draft gap 决策

### 9.3 Content Tools

首批内容工具至少应覆盖：

- `search_knowledge`
- `draft_script_outline`
- `draft_script_section`
- `rewrite_for_tone`
- `compress_context`
- `select_voice_for_script`

要求：

- 不直接改 graph
- 不直接碰外部环境
- 可供上层 planning 和下层 runtime 复用

### 9.4 Runtime Tools

`AgentNode` 运行期只允许看到受限子集。

`v1` 建议运行期可用：

- `search_knowledge`
- `draft_script_section`
- `rewrite_for_tone`
- `compress_context`
- `select_voice_for_script`

`v1` 明确运行期不可用：

- `ask_user`
- graph mutation
- session mutation
- apply / run workflow
- 任意 shell / file / network

---

## 10. Validator 模型要求

### 10.1 Validator 不是 Tool，也不是 SubAgent

Validator 应被实现为单独一层恢复机制。

它的职责是：

- 检查 draft
- 返回 findings
- findings 回写到 `Workspace`
- 供下一轮 loop 修复

### 10.2 `DraftValidator`

用于建图过程中的增量检查。

要求：

- 可以在每次 graph action 后执行
- 可以返回 warning 或 draft_error
- 默认不阻止 loop 继续

首批规则至少包括：

- 重复节点 ID
- 悬挂边
- 非法 node type
- provider / kb / voice 绑定合法性
- 模板引用是否指向存在字段

### 10.3 `FinalizeValidator`

用于产出 draft 前的严格检查。

要求：

- 必须在 finalize attempt 时执行
- 必须满足 graph review/apply 前置条件

首批规则至少包括：

- graph 能通过 `GraphCompiler`
- start/end 完整
- end 输出引用成立
- recipe / graph / provider 绑定一致
- 若包含 `agent` 节点，其工具配置必须在允许白名单内

### 10.4 失败语义

Validator 失败的默认语义是：

- 这是一条 observation
- 不是整个 session 的硬终止

---

## 11. Runtime `AgentNode` 要求

新的 framework 必须把 `AgentNode` 从“节点里临时拼一个 ReAct agent”升级为“使用统一 runtime 壳的节点级 agent”。

### 11.1 `AgentNode` 的职责

- 读取节点配置
- 读取当前 workflow state
- 调用 `AgentRuntime`
- 产出节点输出

### 11.2 `AgentRuntime` 的职责

- 管理 runtime tool loop
- 管理节点级预算
- 管理 runtime trace
- 限制工具权限
- 将结果写回 node output

### 11.3 `AgentNode` 的边界

明确不允许：

- 修改整个 harness session
- 询问用户
- 直接重写整张 workflow graph
- 调用超出 runtime 白名单的工具

---

## 12. Session / Trace / Pause-Resume 要求

### 12.1 Session 恢复要求

`v1` 必须支持会话级恢复。

恢复依据至少包括：

- 当前 phase
- `Workspace snapshot`
- 最近若干轮 decisions / observations
- pending question
- graph draft snapshot

### 12.2 Trace 要求

Trace 需要同时满足两种用途：

1. 审计与调试
2. observation 压缩输入来源

要求：

- 保留顺序事件流
- 但不能只依赖原始 events 作为恢复真相来源

### 12.3 Pause / Resume 范围

`v1` 只在规划期支持 pause / resume。

标准情况：

- `ask_user` -> `waiting_user`
- 用户回复 -> 恢复同一 `HarnessSession`
- 继续 `LeadLoop`

---

## 13. SSE 与产品接入要求

### 13.1 接入方式

`v1` 采用并行接入，不应破坏当前稳定路径。

允许方式：

- 新 API 入口
- 现有入口下的 feature flag
- 新前端开关

### 13.2 事件模型

SSE 事件应围绕 session phase 与 loop 动作来组织，至少应能表达：

- session start
- entering clarification
- ask user
- clarification finalized
- tool call
- tool result
- graph action applied
- validator findings
- finalize attempt
- draft ready
- session failed

### 13.3 产品边界

Harness Framework 负责：

- 从目标收敛出 draft

产品现有链路继续负责：

- draft review
- apply
- run
- 执行态 UI

---

## 14. 需要复用的现有资产

新助手在实现时应尽量复用下面这些资产，而不是推倒重来：

- `ExecutionEngine`
- `GraphCompiler`
- 当前 workflow graph JSON 契约
- 节点注册表与现有 `llm / rag / tts / end / start / agent` 节点体系
- 现有前端 Canvas 与 apply/run 流程
- 现有 provider / knowledge base / TTS 数据模型

可以被替换或重构的对象：

- 现有 `backend/harness` 主循环实现
- 现有 `HarnessContext` 贫弱数据模型
- 现有基于摘要数字的 capability prompt 方式
- 当前 `AgentNode` 的临时 ReAct 组装方式

---

## 15. 成功标准

当下面这些条件都满足时，可以认为 `custom harness agent v1` 达标：

1. 用户输入目标后，系统能创建一个可恢复的 harness session
2. 系统能在规划期进行 0-2 轮关键澄清
3. 上层 loop 按“一轮一个 decision”工作，而不是一次吐完整 plan
4. graph 通过受限 graph actions 增量形成，而不是主要依赖自由 graph 生成
5. finalize 失败可以回写 observation 并继续修复
6. 最终可以稳定产出一个可 review 的 graph draft
7. apply/run 仍与现有产品路径兼容
8. `AgentNode` 能在运行期使用受限工具完成节点级推理
9. `AgentNode` 不会越权修改 session 或 graph
10. 整体接入以并行路径存在，不破坏当前稳定链路

---

## 16. 给新助手的直接构建要求

如果把这份文档交给新的助手，它应按下面原则理解任务：

1. 你要构建的是 **PIAgent 定制版 Harness Agent Framework**
2. 不要把它实现成另一个单次 planner
3. 不要替换 `ExecutionEngine`
4. 不要在 `v1` 中开放 shell/filesystem/network
5. 不要把恢复真相来源只建立在事件日志上
6. 必须把 `Workspace snapshot` 作为恢复与继续推理的主要依据
7. 必须把 `LeadLoop` 设计成真正的一轮一个 decision 的循环
8. 必须把 `AgentNode` 升级为使用统一 runtime 壳的节点级 tool loop
9. 必须保留与现有 workflow graph、Canvas、apply/run 的兼容性
10. 必须优先保证边界清晰和产品稳定，而不是追求 DeerFlow 式全量能力

---

## 17. 一句话总结

我们要的不是“把 DeerFlow 搬进 PIAgent”，也不是“再写一个 planner”。

我们要的是：

**一套基于 DeerFlow harness 思想抽象出来、但严格服从 PIAgent 当前产品边界的定制版 Harness Agent Framework。**

它在 `v1` 中应做到：

- 上层有真正的 Harness LeadAgent 中枢
- 下层有真正的 Runtime AgentNode tool loop
- 中间通过 typed tools、workspace、validators、pause/resume、draft-first 流程连接起来
- 同时不破坏当前 workflow runtime 的稳定性
