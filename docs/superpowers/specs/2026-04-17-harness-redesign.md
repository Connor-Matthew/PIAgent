# Harness 重新设计 Spec

> **创建日期：** 2026-04-17
> **状态：** 设计中（未实施）
> **背景：** 现有 `backend/harness/` 实现了 harness 的外壳，但缺少灵魂——没有真正的 agent 循环、没有真正的工具面、没有验证-恢复闭环、SubAgent 没有 agency。本 spec 描述完整的重新设计方案与 5 阶段迁移路线。

---

## 一、问题诊断

### 1.1 "harness" 应该是什么

harness 一词来自两个传统：

- **eval harness**（lm-eval-harness）：把无状态的下一 token 预测器，套上"加载数据集 / 多轮调用 / 计分"的脚手架
- **agent harness**（Claude Code、Cursor、OpenHands 本身就是 harness）：把 LLM 套进一个**带工具、带状态、带循环、带验证**的运行时，让它能在真实世界里"干活"

**灵魂只有一句话：harness 让模型从"答题"变成"做事"。**

它的 4 项核心责任，缺一不可：

| 责任 | 含义 |
|---|---|
| **控制循环** | observe → think → act → observe，有预算、有终止、有"卡住了怎么办" |
| **工具/能力面** | 模型真能调用的副作用（读文件、查 DB、问用户、跑校验） |
| **上下文工程** | 每次 LLM 调用窗口里**到底放了什么**——记忆、scratch、压缩摘要、错误回放 |
| **验证与恢复** | 输出错了怎么知道？知道之后怎么修？ |

### 1.2 现状审计（基于代码）

顺着 `backend/harness/orchestrator.py` 与 `backend/harness/lead_agent.py` 看完，本质上是：

> **一次"结构化输出 → 图构建器"管线，外面包了个事件流，加了几个名字叫 subagent 的小函数。**

具体证据：

1. **路由是关键词匹配** —— `orchestrator.py:132` 一堆 `"快速"/"复杂"/"播客"`，LLM 在这一步根本没参与判断
2. **"循环"的动作空间是假的** —— `lead_agent.py:286` `decide()` 让 LLM 选 `add_node/add_edge/commit`，但这些动作单次 `plan()` 一把就能给完，循环并没有让模型获得**新信息**再决策，等于在原地踏步
3. **SubAgent 没有 agency**：
   - `subagents/graph_critic.py` 全是 Python 规则，**一个 LLM 调用都没有**
   - `subagents/recipe_challenger.py:60` 主要靠 `"音频" in goal` 这种正则
   - 它们没有自己的工具、没有自己的循环、没法 spawn 别的 agent —— 是函数披了个 agent 的名字
4. **上下文是饿着的** —— `lead_agent.py:129` 给 LLM 的 capabilities 是 `{"llm_providers": 3, "tts_providers": 1}` **三个数字**，连 provider 名字、模型 ID、知识库主题都没传。模型在没有信息的情况下不可能做出真决策
5. **memory 是日志不是学习** —— `harness/memory.py` 把 events 塞进 JSON 列存起来，下一次会话只是把它读出来塞回 prompt，没有"从过去 N 次失败里抽取规律"这一步
6. **没有验证-修复闭环** —— `validate_graph` 失败时循环直接 fallback 或退出，模型从来没看见错误并据此修改

**结论：当前 harness 没有让 LLM 比单次结构化输出多做任何一件事。**

---

## 二、设计原则（五条公理）

1. **循环是基本单位，不是一次性 plan。** 每一轮必须给模型**新信息**，否则就是表演。
2. **工具是 harness 的能力面。** 模型能做什么，等于工具集能做什么；prompt 写得再花哨也补不上工具的缺口。
3. **诚实命名。** 自己有循环、能调工具的才叫 SubAgent；纯规则函数叫 Validator。
4. **错误是观察，不是终止。** 任何工具/校验失败都进 trace，下一轮 LLM 看得见、可以修——而不是 fallback 到 hardcoded 路径。
5. **用户是一种工具。** 当模糊度超过阈值，模型应该能 `ask_user(...)` 然后**真的暂停**等回复，而不是猜。

---

## 三、核心抽象

```
HarnessSession             # 一次完整的"理解→建图→校验→执行"尝试
  ├── Workspace            # 可变工作台：图草案 + scratchpad + 待回答问题 + 预算
  ├── Trace                # 顺序事件流，既是日志，也是 prompt 上下文来源
  ├── MemoryService        # 短期(本会话)+长期(偏好)+情景(相似旧会话检索)
  └── LeadAgent            # 拥有循环、工具、子 agent
```

### 3.1 LeadAgent 主循环骨架

```python
async def loop(self):
    while not done and budget_left:
        obs   = Workspace.observation()      # 真·新信息
        dec   = self.decide(obs)             # 一次结构化 LLM 调用 → Decision (DU)
        res   = self.dispatch(dec)           # 路由到 tool / subagent / action / ask
        Workspace.append(dec, res)
```

### 3.2 Decision 类型（discriminated union）

```python
Decision = OneOf:
  CallTool(name, args)
  SpawnSubAgent(name, brief)
  ProposeAction(GraphAction)             # 复用今天的 add_node/add_edge/update_config
  AskUser(question, options?)            # 触发暂停
  Finalize(reason)                       # 触发提交+校验+dry_run
```

实现约束：

- `Decision` 必须有显式 discriminant，例如 `kind: Literal["call_tool","spawn_subagent","propose_action","ask_user","finalize"]`；不要再靠 `action/skill/done` 这种多 nullable 字段猜语义
- **P1 允许过渡兼容，但不允许长期双轨。** 可以在 orchestrator 边界写一个 `DecisionV1 -> DecisionV2` adapter，让旧测试先活着；但 loop 内部、trace、prompt、前端事件一律以 `DecisionV2` 为准
- `Finalize` 的语义不是“立即成功退出”，而是“进入 finalize 尝试”；失败结果必须回写 observation，供下一轮修复

### 3.3 Tool ABC

```python
class Tool(Protocol):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effects: bool                     # 便于审计与 dry-run 模式跳过
    async def run(self, args) -> BaseModel
```

### 3.4 SubAgent

```python
class SubAgent:                            # 自己也是个 LeadAgent，作用域受限
    brief: str                             # "审一下当前 recipe 是否匹配目标"
    allowed_tools: set[str]                # 比 Lead 小的子集
    budget: int                            # 步数/token 上限
    return_schema: type[BaseModel]         # 强制契约
    async def run(ctx) -> SubAgentReport
```

### 3.5 Validator

```python
class Validator:                           # 纯规则，无 LLM，无循环
    async def check(graph) -> list[Finding]
```

Validator 要分两层，避免把“草稿期的正常不完整”误判成致命错误：

- `DraftValidator`：用于每次 `ProposeAction` 后的增量检查。允许 graph 暂时不完整，例如短时间缺 `start/end`、provider 尚未绑定；输出 warning / draft-error，但**不阻止循环继续**
- `FinalizeValidator`：用于 `Finalize` 阶段的严格检查。要求 graph 满足 compiler 与执行前置条件，失败会把 findings 写回 workspace，并继续循环修复
- 同一条规则可以同时有 draft/finalize 两种 severity 映射；例如“缺 end 节点”在 draft 阶段是 warning，在 finalize 阶段是 error

### 3.6 关键变化

- 抛弃今天的 `LeadAgentPlan`（一次吐出 N 步），改成**每轮一个 `Decision`**
- 抛弃 `CapabilityScout/RecipeChallenger` 的 SubAgent 名号——它们要么升级为真 SubAgent（带循环和工具），要么降级为 Validator
- `GraphAction` 保留（`backend/harness/actions.py` 不动），它是好的原语
- loop 内部只消费 `DecisionV2 + ToolResult + ValidatorFinding`，不再混用旧的 skill/action/done 半结构化协议

---

## 四、主循环算法

```python
async def lead_loop(session, goal):
    workspace = session.workspace
    workspace.bootstrap(goal)                # 写入初始 observation

    while True:
        if workspace.budget_exhausted():
            return await self._emergency_finalize(workspace, reason="budget")

        if workspace.is_stuck():              # 见 §六 卡死检测
            return await self._dispatch(AskUser(
                question=workspace.stuck_summary(),
                escalation=True,
            ))

        observation = workspace.observation()
        # observation 包含：
        #   - 当前 graph 的浓缩描述（节点列表+连边+各节点已配置字段）
        #   - 上一轮决策与结果（含错误字符串）
        #   - 当前已知 facts（来自 tool_result 累积）
        #   - 待回答的 user 问题（如果之前 ask_user 但未回复，循环理论上已暂停）
        #   - 剩余预算与已用步数

        decision = await self.lead_llm.decide(
            schema=Decision,
            system=SYSTEM_PROMPT,            # 描述工具与 subagent
            user=observation.render(),        # 见 §九 上下文工程
            history=workspace.recent_trace(window=K),
        )

        workspace.append_decision(decision)

        match decision:
            case CallTool(name, args):
                result = await self.tools[name].run(args)
                workspace.record_fact(name, result)

            case SpawnSubAgent(name, brief):
                report = await self.subagents[name].run(brief, parent_workspace=workspace)
                workspace.record_subagent(name, report)

            case ProposeAction(action):
                try:
                    self.builder.apply(action)
                    findings = await self.run_draft_validators(self.builder.graph)
                    workspace.record_validation(findings)
                except BuilderError as e:
                    workspace.record_error("builder", str(e))
                    # 不退出！下一轮模型看得见这个错

            case AskUser(q, options):
                await self.pause_and_await(q, options)   # §七 暂停/恢复
                # pause_and_await 返回时，user_reply 已写入 workspace

            case Finalize(reason):
                result = await self._finalize(workspace, reason)
                workspace.record_finalize_attempt(result)
                if result.ok:
                    return result
```

**三件最关键的事**：
- **没有 `try: ... except: fallback to hardcoded`**。错误进 workspace，模型自己处理
- `Finalize` 只是触发提交 + 校验 + dry_run，**结果还会回到循环**（见 §六）
- `AskUser` 真的会暂停 SSE 流（见 §七）

---

## 五、工具面（最关键的缺口补全）

| Tool | 输入 | 输出 | 副作用 | 替代了什么 |
|---|---|---|---|---|
| `list_providers` | `type: llm\|tts, detailed: bool` | 完整列表（id/name/model/voices） | 无 | 今天给 LLM 的 `{"llm_providers": 3}` |
| `inspect_provider` | `id` | 完整 schema + 可用模型 + 最近用过的 cost | 无 | 没有 |
| `list_knowledge_bases` | — | id/name/doc_count/topic_summary | 无 | 同上 |
| `peek_knowledge_base` | `id, k=3` | k 个样本 chunk | 无 | **没有**——模型现在根本不知道 KB 里有什么 |
| `list_recipes` | — | recipe 目录 + 每个的描述/适用场景 | 无 | 隐式藏在 `RecipeSkill` 里 |
| `recall_similar_sessions` | `goal, k=3` | 过去 k 次最相似目标的结果（成功/失败/最终图） | 无 | **没有**——情景记忆缺失 |
| `propose_node` / `propose_edge` / `update_node_config` | GraphAction | 应用后的 diff + Validator 报告 | 改 workspace | 复用 builder |
| `validate_graph` | — | Findings 列表（错误/警告） | 无 | 已有但只在 commit 时跑 |
| `dry_run` | `sample_input` | 执行轨迹（mock providers） | 无 | **没有**——没人模拟过会不会真能跑 |
| `ask_user` | `question, options?` | 用户回复字符串 | 暂停循环 | **没有**——Clarifier 在 harness 路径被绕过了 |

**Tool 必须 typed I/O。** 走 Pydantic schema，自动渲染到 LLM 的 system prompt 里，模型知道每个工具吃什么吐什么。这是 Claude Code/MCP 的核心做法，照抄。

---

## 六、SubAgent 与 Validator 的诚实分类

### 6.1 升级为真 SubAgent（有自己的循环和工具子集）

| SubAgent | 何时被 spawn | brief 示例 | 允许的工具 | budget |
|---|---|---|---|---|
| `RecipeChallenger` | LeadAgent 想质疑当前 recipe 选择 | "用户目标是 X，我选了 start_llm_tts_end，请挑战" | `list_recipes`, `recall_similar_sessions`, `peek_knowledge_base` | 5 步 |
| `CapabilityScout` | 决定 provider 时 | "为这个目标推荐最合适的 LLM provider" | `list_providers`, `inspect_provider`, `recall_similar_sessions` | 3 步 |
| `IOContractDesigner` | 设计 Start/End 输入输出字段时 | "目标是 X，设计 Start 节点的 inputs 和 End 的 outputs" | `recall_similar_sessions` | 4 步 |

它们都返回 `SubAgentReport`，里面有 `recommendation` + `reasoning` + `confidence`。LeadAgent 不必听话——它只是一个意见。

### 6.2 降级为 Validator（纯规则，删掉 LLM 路径）

| Validator | 检查内容 | 改自 |
|---|---|---|
| `GraphStructureValidator` | 环、孤立节点、缺 start/end、悬挂边 | 今天的 `GraphCriticAgent` |
| `IOContractValidator` | End 节点引用是否指向真实节点字段、类型是否匹配 | 新增 |
| `ProviderBindingValidator` | LLM/TTS 节点的 provider_id 是否存在且 enabled | 今天 compiler 里有，抽出来 |
| `TemplateRefValidator` | `{nodeId.field}` 引用是否合法 | 今天 compiler 里有 |

Validator 是同步的、零成本、每次 ProposeAction 之后都跑。**这是验证-恢复闭环的基础。**

### 6.3 Validator 分层（draft vs finalize）

这一层必须写死规则，否则实现时很容易退回“每次一校验就炸”：

| 规则 | Draft 阶段 | Finalize 阶段 |
|---|---|---|
| 缺 `start` / `end` | warning | error |
| provider 未绑定 | warning | error |
| 引用不存在的节点/字段 | error | error |
| cycle / dangling edge | error | error |
| graph 过度复杂但能运行 | warning | warning |

也就是说：

- **draft validator 的职责是提供可修复反馈，不是阻断建图**
- **finalize validator 的职责是保护 execution，不让坏图进入运行时**
- stuck detection 只统计“连续重复的 final-error”或“连续重复的 draft-error”，不要把 warning 也算进去

---

## 七、验证-恢复闭环

三层验证，错误一律进 workspace 而不是抛异常：

```
ProposeAction → Builder 应用 → DraftValidators 跑 → Findings 进 workspace
                                                        ↓
                                               下一轮 LLM 看见 findings
                                                        ↓
                                        决定：修补 / 撤销 / 换思路
```

```
Finalize → CommitGraph(dry) → FinalizeValidators 全跑 → dry_run(sample_input)
                                                          ↓
                                        成功？ → 标记 ready_to_execute，进入真实 execution
                                        失败？ → 错误进 workspace, 循环继续
                                                    ↓
                                        如果连续 N 次 Finalize 失败 → ask_user("我尝试了 X，
                                                                        一直失败因为 Y，
                                                                        要不要换思路？")
```

这里有一个实现约束：

- `CommitGraphAction` / `Finalize` 在 loop 中应该优先走“dry commit”或等价路径，**先拿到 findings，再决定是否真正进入 execution**
- 当前 `builder.apply(CommitGraphAction())` 会直接跑严格校验；重构时要把“提交草稿”和“准备执行”拆开，否则 validate failure 仍然会短路掉循环

### 7.1 卡死检测

- 连续 2 轮 `Decision` 的 hash 一致 → 卡了
- 连续 3 次 Validator 报同样的错 → 卡了
- 连续 5 步没有改动 graph 也没调新工具 → 卡了

卡了就强制走 `AskUser(escalation=true)`，把卡住的状态告诉用户。

---

## 八、暂停/恢复协议（让 AskUser 真的能用）

今天 SSE 是单向流。需要扩展成可暂停可续：

```
LeadAgent 决定 AskUser(q)
   ↓
emit({"type":"awaiting_user_input", "question_id": uuid, "prompt": q, "options": [...]})
   ↓
Workspace 持久化到 DB（记 status="awaiting_user"，存完整 workspace snapshot）
   ↓
SSE 流关闭（前端看到 awaiting_user_input 后渲染输入框）
   ↓
==== 用户回复 ====
   ↓
POST /api/harness/sessions/{id}/resume  body={question_id, answer}
   ↓
后端从 DB 恢复 Workspace，把 user_reply 写进去，重开 SSE 流，循环继续
```

这一步其实已经有基础——`AgentSession` 模型支持 `events` 持久化，`HarnessMemoryStore.append_event` 已经在写。但**events 只能做审计日志，不能当恢复真相来源**。恢复主路径必须有一份结构化 snapshot。

建议最小持久化契约：

- `agent_sessions.status` 扩成 phase-aware 状态机：`planning` / `awaiting_user` / `ready_to_execute` / `executing` / `completed` / `failed`
- 新增 `workspace_json`（或等价字段集合），至少保存：
  - `trace`
  - `facts_ledger`
  - `open_questions`
  - `graph_draft`
  - `budget_state`
  - `pending_execution_inputs`
- `events_json` 继续保留，但定位是 audit trail / UI replay，不承担恢复正确性的责任
- `/resume` 只做一件事：加载 `workspace_json`，写入用户回答，重新进入 lead loop；不要靠重放全部 events 来“猜”当前状态

如果担心迁移成本，P3 也至少要满足：**snapshot 是 source of truth，events 是 derived log。**

---

## 九、记忆层（从日志升级到学习）

三层：

| 层 | 存储 | 内容 | 何时写 | 何时读 |
|---|---|---|---|---|
| **Workspace** | 内存 | 当前会话的 trace + facts + open_qs | 每步 | 每轮 observation |
| **Episodic** | `agent_sessions` 表（已有），新增 `goal_embedding` 列 | 历次会话的 goal + 最终 graph + 是否成功 + 用户是否 commit 到 workflow | finalize 时 | `recall_similar_sessions` 工具调用时（向量近邻 top-k） |
| **Project preferences** | `project_preferences` 表（已有） | "用户偏好用 DeepSeek"、"用户从不用 RAG"、"用户的 TTS 默认 voice" | finalize 时统计聚合 | bootstrap observation 时注入 |

**关键改进：从 trace 中抽取规律。** finalize 时跑一个轻量分析：
- 用户最终保存的 graph vs 最初 commit 的 graph 的 diff → 推断"用户调整了什么"
- 写入 `project_preferences.adjustments`，下次 bootstrap 注入

Episodic memory 的具体实现可以简化：优先复用现有 embedding 能力链路；如果当前工程只稳定支持 OpenAI embedding，就明确把 `recall_similar_sessions` 标成“有 OpenAI embedding 能力时启用”的增强项。存储可先用 BLOB，查询走暴力 cosine（数据量小，没必要上 Chroma）。

---

## 十、上下文工程（observation 怎么渲染）

每轮塞给 LLM 的 user prompt 结构（按重要性，靠后越重要）：

```
[FIXED PREAMBLE]  目标 / 路由 / 项目偏好摘要

[FACTS LEDGER]    所有 tool_result 累积去重后的事实
                  形如 "providers.llm = [{id:1, name:'OpenAI', model:'gpt-4o'}, ...]"
                  这是模型的"工作记忆"，比直接塞 raw tool result 节省 token

[GRAPH STATE]     当前 graph 的紧凑文本表示
                  "Nodes: start[s], llm[m1 prov=1 model=gpt-4o], end[e]
                   Edges: s→m1, m1→e"

[RECENT TRACE]    最近 K 步的 (decision, result_summary)
                  K=5 够了，再老的压成 1 行摘要

[OPEN QUESTIONS]  ask_user 暂停后用户的回答（如果有）

[VALIDATOR FINDINGS] 上一轮校验的所有 findings（错误优先）

[TURN PROMPT]     "Decide your next action. Respond with the Decision schema."
```

**关键**：facts ledger 与 trace 分离。事实是去重压缩的、永久有效；trace 是按时序的、可遗忘的。这是 Claude Code 的 context 处理方式（系统消息里 facts，最近消息里 trace）。

---

## 十一、事件契约扩展

保留现有事件，新增：

| 新事件 | payload | 前端用途 |
|---|---|---|
| `tool_call` | `{name, args, call_id}` | 在 trace 渲染"调用 X" |
| `tool_result` | `{call_id, ok, summary, latency_ms}` | 显示结果摘要 |
| `subagent_loop_start` | `{name, brief, budget}` | 折叠显示子 agent 进度 |
| `subagent_step` | `{name, decision_summary}` | 子 agent 内部步进 |
| `subagent_loop_end` | `{name, report}` | 显示子 agent 报告 |
| `validator_report` | `{validator, findings}` | 实时高亮问题节点/边 |
| `awaiting_user_input` | `{question_id, prompt, options?}` | 渲染输入框 |
| `user_resumed` | `{question_id, answer}` | 关闭输入框 |
| `dry_run_result` | `{ok, errors, traced_outputs}` | 显示模拟运行结果 |
| `harness_stuck` | `{reason, summary}` | 醒目提示 |

废弃：`planner_observe`（被 `tool_call/result` 取代）、过细的 `planning_update`（除了 reasoning 文本）

事件契约升级还需要两个工程约束：

- **兼容窗口**：P1-P2 期间前端继续兼容 `planning_update` / `planner_observe`，后端通过 feature flag 同时发新旧事件；等 `AgentStatusPanel` 与 `useAgentAutoRun` 完成切换后，再删旧事件
- **落库策略**：不要每个 event 都立即 commit 数据库。SSE 可以实时发，但 DB 持久化应走批量 flush（例如每 N 条、每一步结束、状态切换点、流关闭前）；否则 tool/subagent 事件一多，session 表会成为瓶颈

建议把事件分层：

- `durable events`：状态切换、awaiting_user、user_resumed、plan_ready、dry_run_result、planning_error
- `ephemeral events`：tool_call/tool_result/subagent_step 等高频 UI 事件，可批量写入或只保留摘要

---

## 十二、文件级映射（重构边界）

| 现状 | 重构后 |
|---|---|
| `harness/orchestrator.py` `_build_single_shot` + `_build_with_loop` | `harness/session.py`：`HarnessSession` 类，只剩 setup → run lead loop → execute → persist |
| `harness/lead_agent.py` `plan/decide` + 两套 hardcoded fallback | `harness/lead_agent.py`：单一 `loop()` + `decide()`，无 fallback |
| `harness/actions.py` | 保留，新增 `Finalize` 替代 `CommitGraphAction` |
| `harness/builder.py` | 保留，`apply` 后挂 Validator hook |
| `harness/subagents/graph_critic.py` | **移到** `harness/validators/graph_structure.py` |
| `harness/subagents/recipe_challenger.py` | 重写为真 SubAgent，删掉 `_analyze_with_rules` |
| `harness/subagents/capability_scout.py` | 重写为真 SubAgent |
| 新增 `harness/tools/` | `base.py`(Tool ABC) + 每个工具一个文件 |
| 新增 `harness/validators/` | 每个 Validator 一个文件 |
| 新增 `harness/workspace.py` | `Workspace` + `Trace` + `FactsLedger` |
| `harness/memory.py` | 加 `EpisodicMemory`（embedding + cosine top-k）+ `WorkspaceSnapshotStore` |
| `harness/prompts.py` | 系统 prompt 改为"工具描述 + Decision schema 说明"，user prompt 改为 §十 结构 |
| `api/harness.py` | 加 `POST /sessions/{id}/resume` |
| `models/agent_session.py` | 新增 `workspace_json`（或等价持久化结构）与 phase-aware status |

### 前端改动

- `AgentStatusPanel` 渲染 `tool_call/result` 与 `subagent_loop_*`
- 新组件 `ClarificationPrompt` 处理 `awaiting_user_input`
- `useAgentAutoRun` 处理暂停/恢复
- 迁移期同时兼容旧事件，直到新 trace UI 稳定

---

## 十三、5 阶段迁移路线（不要一次大爆炸）

| 阶段 | 范围 | 见效 |
|---|---|---|
| **P0** | 改名 + 抽 Validator：把 `subagents/graph_critic` 移到 `validators/`，删掉 SubAgent 标签。**不改行为**。 | 命名诚实，无回归风险 |
| **P1** | 引入 Tool ABC，把 `load_capabilities` / `validate_graph` 包装成 Tool；引入带 `kind` 的 `DecisionV2`；把 `decide()` 喂给它的"capabilities_summary 三个数字"换成 `list_providers` 工具的真返回；旧协议只保留 adapter | LLM 第一次拿到真信息——立刻看到效果 |
| **P2** | 实现验证-恢复闭环：错误进 workspace 不抛；卡死检测；ProposeAction 后强制跑 **draft validators**；Finalize 跑 **finalize validators**；事件改为批量持久化 | "试错→修正"出现，灵魂第一次出场 |
| **P3** | AskUser + 暂停/恢复 API；`peek_knowledge_base` + `dry_run` 工具；新增 `workspace_json` snapshot 持久化 | Agent 会问你了，会模拟跑了，也真的能续跑了 |
| **P4** | 把 `RecipeChallenger`/`CapabilityScout` 重写为真 SubAgent；情景记忆 `recall_similar_sessions` | 真正的多 agent 协同 + 跨会话学习 |

每阶段都能独立部署、有可见收益。**P1 做完，模型行为质量已经会跨一大步——这是性价比最高的一刀。**

---

## 十四、第一刀（24 小时见效）

如果只能做一件事，**做 P1**。具体动作：

1. 新增 `backend/harness/tools/base.py`：
   ```python
   class Tool(Protocol):
       name: str
       input_schema: type[BaseModel]
       output_schema: type[BaseModel]
       async def run(self, args) -> BaseModel
   ```
2. 把 `list_providers` 写成第一个 Tool，**返回 provider 详细列表而非数字**
3. 定义 `DecisionV2(kind=...)`，并在 orchestrator 边界保留一个临时 adapter 兼容旧 `action/skill/done`
4. 改 `_decide_with_llm` 的 user prompt：循环里把 `tool_result` 累加进 observation
5. 给前端 trace 先加兼容层：新事件优先，旧事件继续可渲染
6. 跑一遍既有测试，断的修

就这 6 步，会立刻发现：模型真的开始"挑 provider"了，而不是机械套 recipe。**那一刻就是 harness 长出灵魂的瞬间。**

---

## 十五、验收标准

完成 P1-P4 后，新 harness 应满足：

- [ ] LeadAgent 至少调用过 2 个不同的 Tool 才做出 ProposeAction（证明它在收集信息）
- [ ] 故意构造一个会触发校验失败的目标，模型能在 ≤3 步内自我修正而不是 fallback
- [ ] 故意构造一个有歧义的目标（如"做个 agent，但没说要不要 TTS"），模型能触发 `ask_user`
- [ ] 暂停后通过 `/resume` API 能续上，trace 完整
- [ ] 同一个目标连跑 3 次，第二次起 `recall_similar_sessions` 能命中
- [ ] Draft 阶段允许图暂时不完整，但 Finalize 阶段不会放过缺 `start/end`、缺 provider、坏引用
- [ ] 迁移期打开 feature flag 时，旧前端仍能读懂主要 planning 事件
- [ ] 所有 Validator 都是无 LLM 的纯函数（grep 确认）
- [ ] 所有 SubAgent 都有自己的 loop（grep 确认 `while` 或 `for step`）

---

## 十六、不在本 spec 范围内

- **路由层（fast vs harness）的 LLM 化判断**：可作为后续优化，但不是灵魂所在
- **节点级并行执行**：`core/engine.py` 的优化，与 harness 无关
- **MCP 协议接入**：Tool ABC 设计预留可能性，但本 spec 不实现
- **多用户 / 鉴权**：与 harness 解耦
