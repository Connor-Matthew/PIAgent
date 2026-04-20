# PIAgent ReAct Builder Harness Agent Spec

> 创建日期：2026-04-20
> 状态：设计草案
> 作者：与用户联合设计
> 关系：修正并取代 `2026-04-18-piagent-harness-v2.md` 中关于 agent loop 的设计判断；保留其中关于 Workspace、GraphBuilder、Validator、Skills、Preferences、SSE lifecycle 的大部分外部环境设计。

---

## 1. 一句话结论

PIAgent 需要的不是一个“每回合输出 JSON Decision 的规划器”，而是一个基于 LangGraph `create_react_agent` 的 Workflow Builder Agent。

这个 agent 只存在于工作流搭建阶段。它通过工具观察和修改画布，和用户持续对话，逐步构建、校验、修正 workflow graph。搭建完成后，最终 workflow 应该像手动搭建的一样直接由 `ExecutionEngine` 运行，不再在 graph 里塞一个 `agent` 节点。

产品形态上，它应该是画布旁边的聊天窗口：用户像 mini-harness CLI 一样持续输入，agent 一边回复、一边调用工具，画布实时长出节点和连线。

核心切分：

```text
ReAct loop = agent 的心脏
PIAgent Workspace / GraphBuilder / Validator / Tools / SSE / DB = ReAct loop 的外部世界
```

---

## 2. 背景：为什么会走到这里

PIAgent 本体其实不复杂。抛开 agent/harness，它是一个可视化 AI 工作流系统：

```text
ReactFlow 画布
  -> workflow graph_json
  -> 后端保存 Workflow
  -> GraphCompiler 校验/排序
  -> ExecutionEngine 按节点运行
  -> SSE 推送运行状态
```

用户真正想要的是：既然已经有画布、节点、provider、知识库、TTS、校验器，就接入一个 harness agent，把这些能力作为工具暴露给它。用户可以一边聊天，一边让 agent 主动理解意图、感知当前画布、补充信息、修改 graph，最终完成 workflow 搭建。

这个想法和 `mini-harness` 的原始精神一致：

- CLI/API 可以持续聊天。
- agent loop 基于 LangGraph `create_react_agent`。
- agent 通过 tool calls 与外部世界交互。
- 上下文是 message history + tool observations。
- 后续增强通过 skills、clarification、loop detection、summarization 接入，而不是重写 agent graph。

但当前 PIAgent harness v2 的实际形态已经偏离了这件事：

```text
Workspace observation
  -> LeadAgent.structured_invoke()
  -> 自定义 Decision JSON
  -> HarnessSession switch/case 分发
  -> Workspace 更新
  -> 下一轮重新渲染 observation
```

这套设计可控、易校验、易持久化，但它不是“原汁原味”的 ReAct agent loop。它更像一个结构化规划器。

因此，本 spec 的目标是把当前 harness 的 agent loop 改回 mini-harness 风格，同时保留 PIAgent 已经建立好的状态、图构建、校验和前端事件能力。

---

## 3. 当前共识

### 3.1 外层 harness agent 是 authoring agent

Harness Agent 的职责是帮助用户搭工作流，而不是成为工作流的一部分。

```text
用户 + Harness Agent
  -> 构建普通 workflow graph
  -> apply/save
  -> ExecutionEngine 直接运行 graph
```

因此主路径上不应该出现 runtime `agent` 节点。

已达成的边界：

- `AgentNode` 后端实现可以暂时保留，作为遗留/高级运行时能力。
- 前端节点库不展示 `ReAct Agent`。
- harness `list_node_types` 不暴露 `agent`。
- harness `GraphBuilder` 不允许创建 `agent`。
- `agent_node` skill 不进入 authoring catalog。

这条原则可以写成：

```text
Harness Agent only authors workflows; it does not insert itself into workflows.
```

### 3.2 ReAct loop 应该回到中心

当前 PIAgent harness 的 `LeadAgent.decide()` 不应该继续作为核心 agent loop。未来核心应该更接近：

```python
agent = create_react_agent(model, tools, prompt=prompt)

async for event in agent.astream_events(
    {"messages": session.messages},
    version="v1",
):
    bridge_langgraph_event_to_sse(event)
```

也就是：

```text
用户消息
  -> LangGraph ReAct agent
  -> tool_calls
  -> PIAgent authoring tools
  -> ToolMessage observations
  -> ReAct agent 继续推理
```

### 3.3 PIAgent harness 的外部环境仍然有价值

当前 harness 中有很多东西不该推倒：

| 当前能力 | 是否保留 | 未来角色 |
|---|---|---|
| `Workspace` | 保留 | 当前画布、facts、errors、validation、open question、budget 的状态容器 |
| `GraphBuilder` | 保留 | authoring tools 的写入后端 |
| `validate_graph` | 保留 | `validate_graph` / `finalize_graph` tool 的确定性校验 |
| `SkillLoader` | 保留 | `load_skill` tool 背后的技能目录 |
| `PreferenceStore` | 保留 | prompt/context 的用户偏好来源 |
| SSE events | 保留 | 前端实时显示聊天、工具调用、图变化、暂停、ready |
| DB `AgentSession` | 保留并扩展 | 会话、消息、workspace、事件持久化 |
| `LeadAgent.decide` | 替换 | 由 ReAct runner 取代 |
| `Decision` union | 逐步退场 | 可保留一段兼容测试，不再作为主 loop 协议 |

---

## 4. 目标架构

### 4.1 模块图

```text
Frontend Chat + Canvas
  |
  | user message / resume answer
  v
HarnessSession
  |
  | messages + workspace context
  v
ReActBuilderAgentRunner
  |
  | create_react_agent(model, tools, prompt)
  v
LangGraph ReAct loop
  |
  | tool_calls
  v
PIAgent Authoring Tools
  |
  | read/write/pause/finalize side effects
  v
Workspace + GraphBuilder + Validator + DB + SSE
```

### 4.2 产品形态：Builder Chat

Harness Agent 的主入口应该是聊天窗口，而不是后台按钮或纯状态面板。

目标体验：

```text
用户在聊天窗口输入目标
  -> agent 流式回复
  -> agent 调用 authoring tools
  -> 工具产生 graph_update
  -> 画布实时更新
  -> agent 需要信息时 ask_user 暂停
  -> 用户回答后继续构图
```

这等价于把 mini-harness CLI 的体验搬到 PIAgent UI 里：

| mini-harness CLI | PIAgent Builder Chat |
|---|---|
| `input("You:")` | chat input |
| `HumanMessage` | user bubble |
| `AIMessage.content` | streaming assistant bubble |
| `AIMessage.tool_calls` | collapsible tool call row |
| `ToolMessage` | collapsible tool result row |
| clarification tool | `ask_user` question card |
| messages list | `messages_json` |
| `agent.astream(...)` | SSE stream |

聊天窗口里的消息类型：

| 类型 | UI 展示 |
|---|---|
| user message | 用户气泡 |
| agent message delta | 流式 assistant 气泡 |
| tool call | 可折叠工具调用条 |
| tool result | 默认折叠的结果摘要，必要时展开 JSON |
| graph update | 小状态条，例如“添加 RAG 节点”、“连接 rag -> llm” |
| validator report | 错误/警告列表 |
| ask_user | 问题卡片，支持选项按钮或文本输入 |
| harness ready | ready card，显示 Apply / Run 后续动作 |

原则：

- 聊天窗口驱动画布，不只是描述画布。
- 画布状态以 `graph_update.snapshot` 为准。
- 用户可以看见 agent 的工具调用过程，但默认不被 JSON 淹没。
- Builder Chat 是 authoring 体验的一部分；工作流运行仍然使用普通 run/debug 面板。

### 4.3 核心对象

#### `ReActBuilderAgentRunner`

替代当前 `LeadAgent.decide()`。

职责：

- 创建/缓存 `create_react_agent`。
- 将 session messages 输入 LangGraph。
- 流式读取 `astream_events` 或 `astream`。
- 把 LLM token、tool call、tool result、final message 转成 PIAgent SSE。
- 将最终 messages 写回 session。

它不直接修改 graph。所有副作用都必须通过 tools。

#### LangGraph checkpointer

Phase 2 必须确定 checkpointer 策略，不能拖到 Phase 5。

原因：`ask_user` 会中断 stream，如果 resume 时 LangGraph 重新执行已经完成的 tool call，就可能重复添加节点、重复连线、重复 emit `graph_update`。这类副作用一旦进入前端和 DB，就很难靠后处理修复。

推荐策略：

- 开发/测试阶段使用 in-memory checkpointer，便于单测控制。
- 产品路径使用 SQLite checkpointer，和本地 PIAgent 单体部署模型一致。
- 每个 harness session 使用稳定 `thread_id = session_id`。
- 每次 tool side effect 完成后，必须让 checkpointer 和 PIAgent session persistence 都处于可 resume 状态。
- `ask_user` pause 前必须完成 checkpoint flush；如果无法保证 flush，则不允许用异常直接中断。

如果 LangGraph 版本或 checkpointer API 不适合当前项目，则 Phase 2 需要显式记录替代方案，例如 tool idempotency key + messages checkpoint。但无论采用哪种策略，目标是不重放已执行副作用。

#### `AuthoringToolRegistry`

可以继续复用现有 `ToolRegistry` 的思想，但最终应该输出 LangChain-compatible tools。

每个工具要有：

- typed input schema
- typed output schema
- 明确 side effect
- 对 Workspace/GraphBuilder/Validator 的受控访问
- SSE emission hooks

#### `Workspace`

Workspace 不再伪装成 agent loop 的输入输出协议，而是 ReAct loop 的环境状态。

它负责提供：

- 当前 goal
- 当前 graph draft
- 当前 validation findings
- 已知 facts
- 已加载 skills
- 用户偏好
- open question
- budget/stuck information

Workspace summary 应通过 LangGraph `prompt` callable 动态渲染，而不是每轮手动重建一条新的 `SystemMessage` 插入消息历史。

原因：

- messages history 应保持真实对话和 tool observations。
- workspace summary 是当前状态视图，不应永久堆进历史。
- prompt callable 更接近 mini-harness 的 `state_modifier` 思路。
- 避免因为每轮生成不同 SystemMessage 而破坏 provider/prompt cache 的稳定性。

#### `HarnessSession`

Session 继续负责 lifecycle：

- create
- run
- pause
- resume
- apply
- abort
- persist
- emit SSE

但 `run()` 不再是 `while decide()`。它会变成启动或继续一个 ReAct stream。

#### Message persistence

Messages 必须独立持久化，不要塞进 `workspace_json.messages`。

建议在 `agent_sessions` 上新增：

```text
messages_json TEXT NOT NULL DEFAULT '[]'
```

理由：

- `workspace_json` 是结构化工作台状态；messages 是 ReAct loop transcript，两者生命周期和增长方式不同。
- 未来 messages 需要独立压缩、截断、导出、调试。
- 如果先塞进 `workspace_json.messages`，之后拆字段会牵扯迁移和兼容逻辑。

`workspace_json` 继续保存 graph draft、facts、validation、open question、budget、preferences snapshot 等结构化状态。

---

## 5. 工具设计

### 5.1 工具分类

#### 只读工具

这些工具只返回事实，不改变 graph。

| 工具 | 作用 |
|---|---|
| `inspect_canvas` | 返回当前 graph draft、选中节点、validation summary |
| `list_node_types` | 返回 authoring 可用节点类型，不包括 `agent` |
| `list_providers` | 查询 LLM/TTS provider |
| `list_knowledge_bases` | 查询可用知识库 |
| `peek_knowledge_base` | 查看知识库摘要/样例 |
| `recall_preference` | 查询用户偏好 |
| `load_skill` | 按需加载 skill markdown |

#### 写入工具

这些工具会修改 workspace graph draft，并 emit `graph_update`。

| 工具 | 作用 |
|---|---|
| `add_node` | 添加普通 workflow node |
| `update_node_config` | 更新节点配置 |
| `delete_node` | 删除节点 |
| `connect_nodes` | 添加 edge |
| `delete_edge` | 删除 edge |

这些工具内部可以继续调用 `GraphBuilder.apply(GraphAction)`，因此已有 `GraphAction` 模型仍然有价值。

写入工具必须遵守事务性约束：

```text
validate args
  -> clone current Workspace/GraphBuilder state
  -> GraphBuilder.apply(action)
  -> workspace.record_graph_update(snapshot)
  -> persist workspace/messages/checkpoint
  -> emit graph_update SSE
  -> return ToolMessage result
```

如果任一步失败：

- 不得留下半更新的 Workspace。
- 不得 emit 与持久化状态不一致的 `graph_update`。
- 错误要作为 tool observation 返回，并写入 Workspace errors。

实现上可采用 snapshot/restore，而不是数据库事务，因为 GraphBuilder 当前是内存对象。但对外语义必须是原子提交：前端看到的 graph_update 必须能从 DB/session 恢复出来。

SSE 必须在 persistence 成功之后再发出。不允许"先 emit graph_update、再写库失败"的顺序，否则前端会短暂看到一个无法从 session 恢复的图。如果 persistence 失败，应回滚 Workspace 快照，并以 tool error observation 返回，而不是发送任何 graph_update。

#### 校验/完成工具

| 工具 | 作用 |
|---|---|
| `validate_graph` | 运行确定性校验，把 findings 写入 Workspace |
| `finalize_graph` | 校验通过则将 session 置为 ready；否则返回 findings 让 agent 修复 |

`finalize_graph` 不是“LLM 说完成就完成”，而是一个有确定性结果的工具。

#### 用户交互工具

| 工具 | 作用 |
|---|---|
| `ask_user` | 暂停 agent run，向前端发出澄清问题 |

`ask_user` 是 ReAct 世界里的 tool，但在 PIAgent runtime 里会触发特殊控制流：

```python
class PauseAgentRun(Exception):
    question_id: str
```

tool 执行时：

1. 写入 `workspace.open_question`
2. emit `awaiting_user_input`
3. persist session
4. raise `PauseAgentRun`
5. `HarnessSession.run()` 捕获后结束本轮 SSE

`PauseAgentRun` 必须配合 checkpointer 使用。pause 后 resume 的第一条新输入只能追加用户回答，不能让 LangGraph 重新执行 pause 前已经完成的 tool call。

用户回答后：

1. 前端调用 resume endpoint
2. session 将回答追加为 `HumanMessage`
3. 重新进入 ReAct loop

---

## 6. 上下文管理

### 6.1 ReAct message history 是主上下文

未来主上下文应该是 LangChain messages：

```text
SystemMessage: builder agent system prompt + durable context
HumanMessage: 用户目标/补充回答
AIMessage: agent 自然语言回复或 tool calls
ToolMessage: PIAgent tools 返回的 observation
```

这能恢复 mini-harness 的原始节奏：

```text
think -> tool_call -> observe -> continue -> final response
```

### 6.2 Workspace 是结构化上下文

消息历史不适合承载所有状态。当前 graph、facts、validation、open question 应继续保存在 Workspace 中。

推荐策略：

- 每轮 prompt 通过 LangGraph `prompt(state)` callable 注入一个短的 workspace summary。
- 大对象不要每次完整塞进 system prompt。
- 工具返回结果进入 ToolMessage，同时关键事实写入 Workspace。
- 前端状态以 Workspace/graph_update 为准，不从自然语言回复里解析。

### 6.3 摘要压缩

从 mini-harness 继承 summarizer 思路：

- 当 messages 超过阈值时压缩旧消息。
- 保留最近 N 条完整消息。
- 不拆开 AI tool_call 和 ToolMessage observation。
- 摘要保留用户目标、关键决策、工具结果、当前 graph 约束、尚未解决的问题。

PIAgent 可以比 mini-harness 多一层：结构化状态不需要全靠摘要保留，因为 Workspace 本身可持久化。

### 6.4 Loop detection

从 mini-harness 继承工具调用循环检测：

- 重复调用同一查询工具
- 重复提交同样的 graph action
- 反复 finalize 失败但不修改 graph
- 长时间没有 graph_update 或有效 tool result

轻度重复时返回 warning observation；严重重复时暂停并 ask_user。

---

## 7. 事件协议

ReAct runner 应把 LangGraph events 映射成 PIAgent SSE。建议事件：

| 事件 | 说明 |
|---|---|
| `session_start` | harness session 开始 |
| `agent_message_delta` | LLM token stream |
| `agent_message` | 完整 AI message |
| `tool_call` | agent 发起工具调用 |
| `tool_result` | 工具返回 |
| `graph_update` | graph draft 被修改 |
| `validator_report` | 校验结果 |
| `awaiting_user_input` | `ask_user` 暂停 |
| `harness_ready` | `finalize_graph` 通过 |
| `session_end` | running/ready/failed/applied |

原则：

- SSE 是 UI 事件，不是 agent loop 协议。
- ReAct loop 协议是 messages + tool calls + ToolMessage。
- graph 状态以 `graph_update.snapshot` 为准。
- 前端聊天记录以 message events 为准。
- Builder Chat 消费 message/tool/ask_user/ready events；Workflow Canvas 消费 graph_update；运行调试面板消费 workflow run events。

---

## 8. 与当前 harness 的迁移关系

### 8.1 保留

- `/api/harness` 的 session/apply/resume 概念
- `AgentSession` 表
- `Workspace`
- `GraphBuilder`
- `validate_graph`
- provider/KB 查询工具
- skills 文件格式
- preferences
- 前端 AgentPanel / AgentStatusPanel 的产品位置

### 8.2 替换

| 当前 | 未来 |
|---|---|
| `LeadAgent.decide()` | `ReActBuilderAgentRunner.run()` |
| `structured_invoke(schema=dict)` | `create_react_agent(...).astream_events(...)` |
| `Decision` as loop protocol | LangChain messages + tool_calls |
| `CallTool` / `ProposeAction` / `Finalize` dispatch | LangChain tools with side effects |
| `AskUser` decision | `ask_user` tool + pause exception |
| observation-only loop | message history + tool observations + workspace summary |

### 8.3 逐步迁移计划

#### Phase 0：锁定产品边界

已完成或正在完成：

- 主路径隐藏 `AgentNode`。
- harness 不暴露/不创建 `agent` 节点。
- 明确 Harness Agent 是 authoring agent。

#### Phase 1：引入 ReAct runner

新增 `backend/harness/react_runner.py`：

- 创建 builder agent。
- 使用 PIAgent provider 创建 chat model。
- 接收 messages + workspace。
- 暂时只挂只读 tools，验证 stream/event bridge。
- 使用 prompt callable 注入 workspace summary。
- 定义 checkpointer 接口，但可以先用 in-memory 实现。

#### Phase 2：把 GraphBuilder 包成 LangChain tools

新增 `backend/harness/react_tools/`：

- `inspect_canvas`
- `add_node`
- `update_node_config`
- `connect_nodes`
- `validate_graph`
- `finalize_graph`
- `ask_user`

第一批只实现线性 workflow 能力：start -> rag/llm/tts -> end。

Phase 2 同时必须完成：

- SQLite checkpointer 策略或明确等价替代方案。
- 写入 tool 的原子提交语义。
- `ask_user` pause/resume 不重放副作用的测试。
- 第 11 节端到端场景的 pytest 验收用例（本 Phase 的核心验收以第 11 节为准，此处不再重复枚举条目，避免两处维护漂移）。

#### Phase 3：持久化 messages

扩展 `AgentSession`：

- `messages_json`

需要保存：

- message type
- content
- tool_calls
- tool_call_id
- tool name
- metadata

`messages_json` 是独立字段，不放进 `workspace_json`。

#### Phase 4：前端聊天体验对齐

前端需要从“状态面板”转成真正的 Builder Chat：

- 用户输入目标
- agent 流式回复
- 工具调用折叠展示
- 画布实时更新
- ask_user 以问题卡片暂停
- ready 后出现 apply/run 操作

推荐改造现有入口：

- `AgentPanel` 承担聊天输入和消息列表。
- `AgentStatusPanel` 降级为可折叠 activity/debug 区，或合并进消息流。
- `harnessStore` 保存 chat events、pending question、ready state。
- `workflowStore` 只从 `graph_update.snapshot` 更新画布。
- tool result 默认摘要展示，展开后看完整 payload。

目标不是做一个“agent 日志面板”，而是做一个能持续对话的搭建窗口。

#### Phase 5：切换 `/api/harness`

当 ReAct runner 支持：

- 线性 graph
- provider 绑定
- validation repair
- ask_user pause/resume
- apply

即可让 `/api/harness` 默认走 ReAct runner。旧 `Decision` loop 可保留短期 fallback，但不再作为主路径。

#### Phase 6：清理旧协议

删除或降级：

- `LeadAgent.decide`
- `Decision` loop 测试
- 自定义 decision normalization
- 只服务 Decision loop 的 prompt 文案

保留：

- `GraphAction` 模型，如果 authoring tools 仍复用它
- `Workspace`
- `GraphBuilder`
- validators

---

## 9. Non-goals

近期不做：

- 不把 mini-harness 的 bash/file/python tools 作为 PIAgent 主工具面。
- 不把 `AgentNode` 放回主节点库。
- 不让 harness agent 生成 runtime `agent` 节点。
- 不引入 sub-agents。
- 不做通用代码执行 sandbox。
- 不让 LLM 直接写 workflow JSON 绕过 GraphBuilder。
- 不从自然语言回复解析 graph change。

---

## 10. 风险与约束

### 10.1 ReAct 工具副作用要可控

LangGraph tool calls 天然允许 agent 连续调用工具。PIAgent 的写入工具必须强约束：

- schema validation
- node type allowlist
- provider existence checks
- GraphBuilder validation
- event emission
- persistence after side effect
- idempotency or checkpoint guarantee

### 10.2 Pause/resume 要小心处理

`ask_user` 不是普通 tool result。它需要中断当前 stream，并等待用户回答。实现上必须避免：

- 前端以为 session failed
- 后端丢失已产生的 messages
- resume 后重复执行暂停前的 tool side effect

Phase 2 前必须选定 checkpointer 策略，并用测试证明 resume 不会重放已执行的写入 tool。

### 10.3 上下文不能无限膨胀

ReAct message history 会比 Decision observation 更自然，但也更容易变长。必须尽早接入：

- summarization
- compact workspace summary
- tool result truncation
- graph snapshot compression

### 10.4 测试要覆盖 tool side effects

重点测试不是“LLM 会不会聪明”，而是：

- tool 调用是否正确改变 graph
- graph_update 是否发出
- validate/finalize 是否确定性
- ask_user 是否暂停/恢复
- 重复 tool call 是否被检测
- apply 后 workflow 能否被 ExecutionEngine 跑通

---

## 11. 验证标准

第一个可用版本完成时，应该能跑通这个端到端场景。这个场景应在 Phase 2 就写成 pytest，作为 ReAct runner + authoring tools 的核心验收用例：

```text
用户：帮我做一个读取知识库并回答问题的工作流
Agent：查询可用节点/provider/KB
Tool: list_node_types
Tool: list_providers
Tool: list_knowledge_bases
Agent：如果 KB 或 provider 不明确，调用 ask_user
用户：选择某个 KB/provider
Tool: add_node start
Tool: add_node rag
Tool: add_node llm
Tool: add_node end
Tool: connect_nodes ...
Tool: validate_graph
Tool: finalize_graph
前端：画布出现 start -> rag -> llm -> end
用户：apply/run
ExecutionEngine：直接运行普通 workflow graph
```

验收条件：

- 最终 graph 不包含 `agent` 节点。
- 用户目标以 chat message 进入 session，而不是一次性后台参数。
- agent 至少产生一个可展示的 assistant message。
- tool call/tool result 能在 Builder Chat 中还原为消息流。
- harness agent 的每一步工具调用可在 UI 上追踪。
- graph 修改实时反映到画布。
- 用户追问能暂停并恢复。
- apply 后 workflow 与手动搭建 workflow 使用同一运行路径。

---

## 12. 未来思路

### 12.1 CLI 作为开发调试入口

mini-harness 的 CLI 很有价值。PIAgent 可以保留一个 dev-only CLI：

```text
piagent harness chat --workflow <id>
```

用途：

- 不开前端也能调试 builder agent。
- 直接观察 messages/tool_calls。
- 回归 mini-harness 的轻量体验。

但产品主入口仍然是前端聊天面板 + 画布。

### 12.2 Builder Chat 作为主产品入口

长期看，Harness Agent 不应该藏在“生成工作流”按钮后面。它应该是画布旁边的协作窗口。

典型布局：

```text
Left: Node Library / Project Navigation
Center: Workflow Canvas
Right: Builder Chat
```

用户不需要理解 harness 内部协议，只需要像 CLI 一样说话：

```text
我想做一个读取产品文档并生成播客音频的工作流
```

agent 则通过工具实际搭图：

```text
list_knowledge_bases
list_providers
ask_user
add_node
connect_nodes
validate_graph
finalize_graph
```

UI 同时展示两件事：

- 聊天：为什么这样搭、需要用户确认什么、当前进展如何。
- 画布：实际 workflow graph 正在如何变化。

### 12.3 Skills 从 recipe 升级成 authoring playbooks

当前 skills 可以继续是 Markdown，但内容应更贴近“如何搭图”：

- 适用目标
- 推荐节点序列
- 必要 provider/KB 信息
- 常见 validation 错误
- 输出字段引用规则
- 何时 ask_user

Skills 是给 ReAct agent 的工作手册，不是硬编码模板。

### 12.4 更强的 canvas awareness

未来 `inspect_canvas` 可以返回：

- 当前选中节点
- 用户最近手动修改的节点
- graph diff
- validation delta
- UI lock 状态
- 节点布局信息

这样 agent 可以真正和用户共同编辑，而不是每次从空白图开始。

### 12.5 Safe apply 与 user confirmation

对于大改动，可以引入 preview/apply 两段式：

```text
tool: propose_patch
UI: show diff
user confirm
tool: apply_patch_to_canvas
```

第一版可以直接 graph_update，因为画布构建本身就是用户可见、可回滚的过程。

### 12.6 运行结果反馈到构图

未来可以让 harness agent 读取一次 workflow run 的结果：

```text
run_workflow_preview
inspect_run_result
repair_workflow
```

这会形成更完整的闭环：

```text
build -> validate -> run -> observe failure -> repair
```

但第一版先做到 build -> validate -> apply。

---

## 13. 最终原则

这个项目不应该变成“agent 生成 agent 节点，然后 agent 节点再运行 agent”。

它应该是：

```text
一个外层 ReAct Builder Agent，帮助用户搭建普通、可解释、可运行的 workflow graph。
```

PIAgent 的价值在画布、节点、运行时、provider、RAG、TTS、校验和可视化调试。mini-harness 的价值在轻量、真实、自然的 ReAct loop。

最终设计应该把这两者叠在一起：

```text
mini-harness ReAct loop
  + PIAgent authoring tools
  + PIAgent workspace persistence
  + PIAgent canvas UI
```

这样 harness agent 才既有“agent 的灵魂”，也不会失去 PIAgent 作为工作流产品的结构。
