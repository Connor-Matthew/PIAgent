# PIAgent Harness v2 设计 Spec

> **创建日期：** 2026-04-18
> **状态：** 设计中（未实施）
> **作者：** 与用户联合设计
> **SUPERSEDES（本文取代以下所有 spec）：**
> - `2026-04-16-agent-harness.md`
> - `2026-04-16-ha1-lead-agent-loop.md`
> - `2026-04-16-harness-agent.md`
> - `2026-04-17-custom-harness-agent-design.md`
> - `2026-04-17-harness-redesign.md`

---

## 一、背景与作废声明

### 1.1 为什么要 v2

现状：`backend/harness/`（2247 行）+ `backend/agent/`（1812 行）共 ~4000 行"agent 相关代码"，但两个路径都没有真正的自主决策循环：

- `backend/agent/planner.py` 是"一次性结构化输出 → 图构建"，模型只调用 1 次，没有循环、没有工具
- `backend/harness/` 铺了 orchestrator / lead_agent / skills / subagents / validators 的架子，但路由仍是关键词匹配、subagent 大量是 Python 正则、给 LLM 的 capabilities 是"三个数字"、没有验证-修复闭环
- 两个路径并存，职责重叠，前端要同时兼容 `/api/agent/*` 和 `/api/harness/*` 两套事件协议

用户最初的要求很清楚：

> 提炼 DeerFlow 的内核，做成一个 PIAgent-native 的小型 harness。它能自主思考、自主决策、自主提问，然后根据已有的节点工具，根据用户意图自动搭建工作流。

当前的实现偏离了这个目标，走向了"铺框架却没灵魂"。v2 是一次彻底重写。

### 1.2 作废范围（v2 上线即删）

| 路径 | 处置 |
|---|---|
| `backend/harness/` | 重命名为 `backend/harness_legacy/`，从 import 树移除；v2 稳定后一次性 `git rm` |
| `backend/agent/` | 同上，重命名为 `backend/agent_legacy/`，v2 稳定后删除 |
| `backend/api/agent.py` | 废弃，统一到 `backend/api/harness.py`；v2 上线立即删除 |
| 旧事件：`planner_observe` / `planning_update` / `clarification_turn` / `planning_ready` | 废弃，全部替换为 v2 事件契约 |
| 前端 `AgentPanel` / `PlannerStatus` / `AgentStatusPanel` / `AutoRunStatus` | 保留组件文件但内容按 v2 事件契约重写，不再兼容旧事件 |

**不搞双轨期。** v2 跑通之前旧路径继续工作；v2 上线当 PR 一次性切换，删除 legacy 目录。

---

## 二、DeerFlow 内核提炼

DeerFlow 2.0 是一个"super agent harness"。其通用内核（脱离 Deep Research 场景）是：

| DeerFlow 能力 | PIAgent v2 是否采纳 | 说明 |
|---|---|---|
| Lead agent 主循环（observe → decide → act） | ✅ 全采纳 | 这是灵魂 |
| Skills（Markdown 文件 + 按需渐进加载） | ✅ 全采纳 | 避免把所有 recipe 塞进 system prompt |
| 真工具面（typed I/O, Pydantic schema） | ✅ 全采纳 | 取代今天"capabilities 三个数字" |
| AskUser 真暂停 | ✅ 全采纳 | Clarifier 合并进 harness |
| Context engineering（facts ledger + trace 分离） | ✅ 全采纳 | 核心上下文控制手段 |
| Sub-agents（独立 context / 并行） | ❌ 不做 | PIAgent 场景不需要；未来如复杂度上来再加 |
| Sandbox / Docker / 文件系统 | ❌ 不做 | 产物是 workflow JSON，不是可执行脚本 |
| LangGraph / LangChain 深度绑定 | ❌ 不做 | 直接用 Pydantic + 自有 LLM client |
| 长期记忆 / 情景记忆 / episodic embedding | ⚠️ 只保留用户偏好 | 复用已有 `project_preferences` 表；不做 embedding 检索 |
| MCP / IM 渠道 / LangSmith | ❌ 不做 | 生态层，与核心解耦 |

**一句话定位：PIAgent v2 = DeerFlow 主循环 + 按需 Skills + 6 个真工具 + 单用户偏好记忆。**

---

## 三、设计原则（五条公理）

1. **循环是基本单位，不是一次性 plan。** 每一轮必须给模型**新信息**。
2. **工具是 harness 的能力面。** 模型能做什么 = 工具集能做什么。
3. **Skills 按需加载。** 系统 prompt 只告诉模型"可用 skill 目录"；正文内容必须通过 `LoadSkill` decision 拉取。
4. **错误是观察，不是终止。** 任何工具/校验失败都进 workspace，下一轮 LLM 看得见、可以改。没有 fallback 到 hardcoded 路径。
5. **提问是一种 Decision，不是 Tool。** 模糊度超阈值时发出 `AskUser` decision，真的暂停 SSE，不猜。
6. **Decision 与 Tool 严格分层。** Decision 决定"本轮做什么"（包括可能暂停会话的行为：`AskUser`、`LoadSkill`、`ProposeAction`、`Finalize`）；Tool 只承担"同步返回事实"的只读查询。两者职责不重叠。

---

## 四、核心抽象

### 4.1 模块构成

```
HarnessSession           一次完整的"理解 → 建图 → 校验 → 执行"尝试
  ├── Workspace          可变工作台：graph 草案 + facts + trace + open_questions + budget
  ├── LeadAgent          唯一的 agent，拥有循环、工具、skills 加载器
  ├── ToolRegistry       工具名 → Tool 实例
  ├── SkillLoader        skill 名 → Markdown 文本（按需读盘）
  ├── Validator          finalize 时单次校验，无 LLM
  └── PreferenceStore    读写 project_preferences
```

### 4.2 Decision（discriminated union）

```python
# backend/harness/schemas.py
class CallTool(BaseModel):
    kind: Literal["call_tool"] = "call_tool"
    tool: str
    args: dict

class LoadSkill(BaseModel):
    kind: Literal["load_skill"] = "load_skill"
    skill: str

class ProposeAction(BaseModel):
    kind: Literal["propose_action"] = "propose_action"
    action: GraphAction          # add_node | add_edge | update_node_config | delete_node | delete_edge

class AskUser(BaseModel):
    kind: Literal["ask_user"] = "ask_user"
    question: str
    options: list[str] | None = None

class Finalize(BaseModel):
    kind: Literal["finalize"] = "finalize"
    reason: str

Decision = Annotated[
    CallTool | LoadSkill | ProposeAction | AskUser | Finalize,
    Field(discriminator="kind"),
]
```

**实现约束：**
- 必须有显式 `kind` 字段，不允许 nullable 猜语义
- `Finalize` 不是"立即成功退出"，而是"进入 finalize 尝试"；失败结果必须回写 observation

### 4.3 Tool Protocol

```python
# backend/harness/tools/base.py
class Tool(Protocol):
    name: str
    description: str          # 渲染进 system prompt
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effects: bool        # True 的工具在 dry-run 模式跳过（v2 暂不用，但预留）

    async def run(self, args: BaseModel, ctx: HarnessContext) -> BaseModel: ...
```

所有工具自描述（name / description / input_schema / output_schema），LLM 的 system prompt 通过模板自动渲染工具目录。

### 4.4 Skill（DeerFlow 风格）

Skill 是一个 Markdown 文件：

```markdown
---
name: rag_qa
description: 基于知识库回答问题的工作流模式
applies_when: 用户目标涉及 "基于 KB 回答"、"问答"、"查文档"
nodes: [start, rag, llm, end]
---

# RAG 问答 Skill

## 适用场景
...

## 推荐节点组合
1. Start（inputs: {question: str, kb_id: str}）
2. RAG（query: {start.question}, kb_id: {start.kb_id}, top_k: 3）
3. LLM（prompt: "基于以下资料回答：{rag.chunks}\n问题：{start.question}"）
4. End（outputs: {answer: {llm.output}}）

## 常见坑
- `rag.chunks` 是 list，prompt 里直接拼会变长；考虑用 LLM summarize
...
```

LeadAgent 初始只知道 skill 目录（name + description + applies_when），需要时发出 `LoadSkill(skill="rag_qa")` Decision 把正文拉进 facts ledger。

### 4.5 Validator（单层）

```python
# backend/harness/validators.py
class Finding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = None

def validate_graph(graph: dict) -> list[Finding]: ...
```

**v2 不做 draft/finalize 双层。** 只有 `Finalize` 时跑一次完整校验；Draft 期间错误通过 builder 本身的异常回写 workspace 即可。如果后续确实发现需要增量校验，再加。保持简单。

---

## 五、主循环

```python
async def lead_loop(session: HarnessSession, goal: str):
    ws = session.workspace
    ws.bootstrap(goal, preferences=session.preferences.snapshot())

    while True:
        if ws.budget_exhausted():
            return await _emergency_ask_user(ws, reason="budget")

        if ws.is_stuck():
            return await _dispatch(AskUser(
                question=ws.stuck_summary(),
            ))

        obs = ws.observation()
        decision = await session.lead_llm.decide(
            schema=Decision,
            system=render_system_prompt(tools=session.tools, skills=session.skills.catalog()),
            user=obs.render(),
            history=ws.recent_trace(window=5),
        )
        ws.append_decision(decision)
        emit_event("decision", decision)

        match decision:
            case CallTool(tool=name, args=args):
                result = await session.tools[name].run(args, ctx=session.ctx)
                ws.record_fact(name, result)
                emit_event("tool_result", name, result)

            case LoadSkill(skill=name):
                content = await session.skills.load(name)
                ws.record_skill(name, content)
                emit_event("skill_loaded", name)

            case ProposeAction(action=action):
                try:
                    session.builder.apply(action)
                    ws.record_graph_update(session.builder.snapshot())
                    emit_event("graph_update", session.builder.snapshot())
                except BuilderError as e:
                    ws.record_error("builder", str(e))
                    emit_event("builder_error", str(e))

            case AskUser(question=q, options=opts):
                await _pause_and_await(session, q, opts)

            case Finalize(reason=reason):
                findings = validate_graph(session.builder.snapshot())
                ws.record_validation(findings)
                emit_event("validator_report", findings)
                if not any(f.severity == "error" for f in findings):
                    await _commit_and_persist(session)
                    emit_event("harness_ready", session.builder.snapshot())
                    return
                # 有 error，循环继续，下一轮 LLM 看得见
```

**三件最关键的事：**
- 没有 `try: ... except: fallback to hardcoded`
- `Finalize` 失败回到循环，模型自己修
- `AskUser` 真暂停，由 `_pause_and_await` 落库 + 关闭 SSE 流

---

## 六、工具面（首批 7 个，全部只读同步）

| Tool | 输入 | 输出 | 说明 |
|---|---|---|---|
| `list_node_types` | — | 所有 node_type + 描述 + 配置字段 schema | LLM 必须知道节点集合 |
| `list_providers` | `type: llm\|tts\|embedding` | 完整 provider 列表（id/name/model/enabled） | 取代今天"三个数字" |
| `list_knowledge_bases` | — | id/name/doc_count/topic_summary | |
| `peek_knowledge_base` | `id, k=3` | k 个样本 chunk 文本 | 模型能"看见" KB 内容再决定要不要用 |
| `list_skills` | — | skill 目录（name + description + applies_when） | 按需加载入口；正文用 `LoadSkill` decision 拉取 |
| `recall_preference` | `key?` | 用户偏好字典 | 读 `project_preferences` |
| `validate_graph` | — | Findings 列表 | 主循环内部会自动在 Finalize 调；此工具是让模型能主动自检 |

**Tool 与 Decision 的分工（再次重申）：**

| 行为 | 归属 | 理由 |
|---|---|---|
| 读取事实（providers / KBs / skill 目录 / 偏好 / 校验） | **Tool** | 同步返回，不改 workspace graph，不暂停会话 |
| 加载 skill 正文 | **`LoadSkill` Decision** | 会把 Markdown 写进 workspace facts ledger（有状态变更），事件 `skill_loaded` 独立渲染 |
| 修改 graph（add_node / add_edge / update_config） | **`ProposeAction` Decision** | 有副作用，触发 `graph_update` 事件和 builder_error 流 |
| 向用户提问 | **`AskUser` Decision** | **异步**——需要 SSE 关流 + 落库 + 等 `/resume`。不是同步返回型调用 |
| 提交图 | **`Finalize` Decision** | 触发 validate + commit + persist |

**一句话判别：** 若返回后 workspace 状态不变、会话不暂停、只是纯信息 → Tool；否则 → Decision。

**工具必须 typed I/O。** 每个工具有 Pydantic schema，自动渲染进 system prompt。这是 Claude Code / MCP 的核心做法。

---

## 七、Skills 目录

### 7.1 路径与首批内容

```
backend/harness/skills/
  ├── __init__.py
  ├── loader.py                    # SkillLoader：缓存 + 按需读盘 + frontmatter 解析
  ├── llm_basic.md                 # 单次 LLM 调用
  ├── rag_qa.md                    # RAG 问答
  ├── tts_podcast.md               # 文本 → 音频播客
  ├── agent_node.md                # 多步 Agent 节点（工具循环）
  ├── simple_pipeline.md           # Start → LLM → End 直通
  └── io_contract.md               # Start/End 字段设计指南
```

### 7.2 Frontmatter 约定

```yaml
---
name: rag_qa                      # 必填，与文件名一致
description: ...                   # 必填，≤120 字，渲染到 list_skills
applies_when: ...                  # 必填，自然语言匹配条件
nodes: [start, rag, llm, end]      # 可选，常见节点组合
requires: [knowledge_base]         # 可选，前置条件
---
```

### 7.3 加载语义

- LeadAgent 初始 system prompt **只看到 catalog**（name + description + applies_when）
- 要用某个 skill 时，发 `LoadSkill(skill="rag_qa")`
- SkillLoader 读文件、解析 frontmatter，把 Markdown 正文写进 facts ledger 的 `skills` 段
- 同一 skill 在同一 session 内不重复加载

---

## 八、验证与 Finalize

### 8.1 Finalize 流程

```
LeadAgent.decide() → Finalize(reason)
    ↓
validate_graph(builder.snapshot())       单次、同步、无 LLM
    ↓
    ├── 有 error → 写入 workspace + emit validator_report → 回到循环
    └── 全 ok → commit 到 WorkflowRun → emit harness_ready → 返回
```

### 8.2 校验规则（初版，后续可加）

| code | severity | 描述 |
|---|---|---|
| `missing_start` | error | 图无 Start 节点 |
| `missing_end` | error | 图无 End 节点 |
| `cycle` | error | 存在环 |
| `dangling_edge` | error | 边引用不存在的节点 |
| `unbound_provider` | error | LLM/TTS 节点的 `provider_id` 为空或指向不存在 provider |
| `bad_template_ref` | error | `{nodeId.field}` 引用不合法 |
| `unreachable_node` | warning | 存在无入边的非 Start 节点 |
| `too_simple` | warning | 只有 Start→End 直连（可能用户意图未实现） |

### 8.3 卡死检测（workspace 内置）

- 连续 2 轮 Decision 的 hash 一致 → 卡了
- 连续 3 次同样的 builder_error → 卡了
- 连续 5 步没改动 graph 也没调新工具 → 卡了

卡了强制走 `AskUser(escalation=True)`。

---

## 九、AskUser 暂停/恢复协议

### 9.1 事件序列

```
LeadAgent 决定 AskUser(q, options)
    ↓
emit({"type": "awaiting_user_input", "question_id": uuid, "prompt": q, "options": [...]})
    ↓
Workspace 写入 DB（agent_sessions.workspace_json + status="awaiting_user"）
    ↓
SSE 流关闭（前端渲染输入框）
    ↓
==== 用户在 AgentPanel 回答 ====
    ↓
POST /api/harness/sessions/{id}/resume
    body: {question_id, answer}
    ↓
后端：加载 workspace_json → 写入 user_reply → status="running" → 重开 SSE
    ↓
循环继续，下一轮 observation 包含用户回答
```

### 9.2 持久化契约

- `agent_sessions.status` 变成 phase-aware 状态机：
  `running` / `awaiting_user` / `ready` / `failed` / `applied`
- `agent_sessions.workspace_json` 是**恢复的唯一真相来源**，至少包含：
  ```
  {
    "trace": [...],              // 按时序的 decision + result
    "facts": {...},              // 去重压缩的事实（tool_result 累积）
    "skills_loaded": {...},      // name → markdown
    "graph_draft": {...},        // 当前 builder snapshot
    "open_question": {...} | null,
    "budget": {"used": n, "cap": N}
  }
  ```
- `agent_sessions.events_json` 仍保留，定位是 **audit trail / UI replay**，不承担恢复正确性
- `/resume` 只做：加载 snapshot → 写 user_reply → 重新进 lead loop。不靠重放 events 猜状态

---

## 十、记忆层（只保留用户偏好）

**v2 明确不做**：episodic memory、向量检索相似会话、长对话总结。

**保留**：`project_preferences` 表（已存在），维护：
- `preferred_llm_provider_id`
- `preferred_tts_provider_id`
- `preferred_tts_voice_id`
- `preferred_knowledge_base_id`
- `graph_style`（例如 `"minimal"` / `"verbose"`）

### 10.1 读

- Session bootstrap 时注入 observation 的固定 preamble
- LeadAgent 可通过 `recall_preference` 工具主动读取

### 10.2 写（从 trace 学习）

Finalize 成功时：
1. 取用户最终保存的 graph（如果用户在前端编辑了再保存，以保存时为准）
2. 与 session 初始 commit 时的 graph diff
3. 更新偏好：
   - 用户替换了 LLM provider → 更新 `preferred_llm_provider_id`
   - 用户删了 RAG 节点 → 不直接写"不用 RAG"，只记录 `graph_style` 倾向
   - 用户改了 TTS voice → 更新 `preferred_tts_voice_id`
4. 写入规则是**保守累积**：只在用户明确修改时更新，不从失败 session 学习

---

## 十一、事件契约

### 11.1 新事件（全量清单）

| 事件 | payload | 前端用途 |
|---|---|---|
| `session_start` | `{session_id, goal}` | 启动提示 |
| `decision` | `{kind, summary}` | trace 渲染"模型决定 X" |
| `tool_call` | `{tool, args, call_id}` | 渲染"调用 list_providers" |
| `tool_result` | `{call_id, ok, summary, latency_ms}` | 折叠展示结果 |
| `skill_loaded` | `{skill, snippet}` | 渲染"加载了 skill: rag_qa" |
| `graph_update` | `{snapshot}` | Canvas 实时更新图 |
| `builder_error` | `{message}` | 红字 inline 提示 |
| `validator_report` | `{findings}` | 高亮问题节点/边 |
| `awaiting_user_input` | `{question_id, prompt, options?}` | 渲染输入框 |
| `user_resumed` | `{question_id, answer}` | 关闭输入框 |
| `harness_ready` | `{snapshot, workflow_id}` | "应用到画布"按钮 |
| `harness_stuck` | `{reason, summary}` | 醒目提示 |
| `session_end` | `{status, reason?}` | 流收尾 |

### 11.2 废弃（v2 上线立即删除）

- `planner_observe`
- `planning_update`
- `clarification_turn`
- `planning_ready`
- `planning_error`（并入 `session_end` + `builder_error`）
- `auto_run_*`

### 11.3 落库策略

- **durable events**（必须落库）：`session_start` / `awaiting_user_input` / `user_resumed` / `harness_ready` / `session_end` / `validator_report`
- **ephemeral events**（批量落库，每 N 条或状态切换时 flush）：`decision` / `tool_call` / `tool_result` / `skill_loaded` / `graph_update`

---

## 十二、API 与数据模型

### 12.1 API 端点（`/api/harness/*`）

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/harness/sessions` | 创建 session（body: `{goal, workflow_id?}`） |
| `GET` | `/api/harness/sessions/{id}` | 查询 session 状态 |
| `GET` | `/api/harness/sessions/{id}/events` | SSE 订阅实时事件 |
| `POST` | `/api/harness/sessions/{id}/resume` | 提交 user_reply 续跑（body: `{question_id, answer}`） |
| `POST` | `/api/harness/sessions/{id}/apply` | 把 ready 的 graph 应用到 workflow（取代旧 `/api/agent/*/apply`） |
| `POST` | `/api/harness/sessions/{id}/abort` | 中止 session |

**`/api/agent/*` 全部删除。**

### 12.2 数据模型变更

#### 现有字段（`backend/models/agent_session.py`，精确盘点）

```
id              String  PK
user_goal       Text    NOT NULL
status          String(32)  NOT NULL  default="ready"
turns_json      Text    NOT NULL  default="[]"
answered_dims_json  Text  NOT NULL  default="{}"
events_json     Text    NOT NULL  default="[]"
recipe_json     Text    NULL
graph_json      Text    NULL
rationale_text  Text    NULL
workflow_id     String  FK workflows.id  NULL
created_at      DateTime
updated_at      DateTime
```

#### v2 目标字段

```
id              String  PK                  [保留]
goal            Text    NOT NULL            [重命名自 user_goal]
status          String(32)  NOT NULL        [值域全换：running / awaiting_user / ready / failed / applied]
workspace_json  Text    NULL                [新增：snapshot 真相来源]
events_json     Text    NOT NULL  default="[]"  [保留]
workflow_id     String  FK workflows.id  NULL  [保留]
created_at      DateTime                    [保留]
updated_at      DateTime                    [保留]
```

#### 字段映射与迁移动作

| 旧字段 | v2 处置 | 说明 |
|---|---|---|
| `user_goal` | 重命名为 `goal` | 语义一致，改名让 schema 更干净 |
| `status` | **值域重定义** | 旧值 `ready` / `clarifying` / `failed` / `applied` 等全部作废 |
| `turns_json` | **DROP** | 旧 clarifier 多轮对话，功能并入 workspace_json.trace |
| `answered_dims_json` | **DROP** | 旧维度打钩，功能并入 workspace_json.facts |
| `recipe_json` | **DROP** | 旧 RecipeIR，作废（skills 取代） |
| `graph_json` | **DROP** | 并入 workspace_json.graph_draft |
| `rationale_text` | **DROP** | 可从 trace 重建，不再单独存 |
| `events_json` | 保留 | 继续做 audit log，事件类型全换（见 §11） |
| 其他 | 保留 | `id` / `workflow_id` / 时间戳 |

#### 迁移策略（dev SQLite，一次性）

这是 dev 数据库，不保留历史 session。v2 上线 PR 的 migration：

```python
# backend/migrations/2026-04-18-harness-v2.py （或等价的 Alembic revision）
def upgrade():
    # 1. drop 旧表（含所有历史 session）
    op.drop_table("agent_sessions")
    # 2. 按 v2 schema 重建
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("goal", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="running"),
        sa.Column("workspace_json", sa.Text, nullable=True),
        sa.Column("events_json", sa.Text, nullable=False, default="[]"),
        sa.Column("workflow_id", sa.String, sa.ForeignKey("workflows.id"), nullable=True),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
```

**接受"清空历史 session"的代价**，原因：
- 这是 dev 环境（见 CLAUDE.md "SQLite via SQLAlchemy，Schema 自动创建"）
- 旧 session 的事件格式与 v2 不兼容，即使保留也无法在新前端回放
- 一次性清空比写 field-by-field 迁移代码更干净，实现成本低

**如果未来需要上生产**（本 spec 范围外）：届时再做保真迁移，把旧 graph_json 映射到 workspace_json.graph_draft、旧 turns_json 转成 trace 格式。

`project_preferences` 表：不动，结构已符合 v2 需求。

### 12.3 后端目录结构

```
backend/harness/
  ├── __init__.py
  ├── session.py               # HarnessSession：外壳、启停、SSE
  ├── lead_agent.py            # LeadAgent：单一 loop() + decide()
  ├── workspace.py             # Workspace + FactsLedger + Trace + StuckDetector
  ├── schemas.py               # Decision DU + GraphAction + Finding
  ├── builder.py               # GraphBuilder.apply(action)
  ├── actions.py               # GraphAction 原语（add_node / add_edge / ...）
  ├── validators.py            # validate_graph() + Finding
  ├── prompts.py               # render_system_prompt() + observation 模板
  ├── preferences.py           # PreferenceStore：读写 project_preferences
  ├── memory.py                # WorkspaceSnapshotStore + EventLog
  ├── tools/
  │     ├── __init__.py
  │     ├── base.py            # Tool Protocol + ToolRegistry
  │     ├── list_node_types.py
  │     ├── list_providers.py
  │     ├── list_knowledge_bases.py
  │     ├── peek_knowledge_base.py
  │     ├── list_skills.py
  │     ├── recall_preference.py
  │     └── validate_graph.py
  └── skills/
        ├── __init__.py
        ├── loader.py
        ├── llm_basic.md
        ├── rag_qa.md
        ├── tts_podcast.md
        ├── agent_node.md
        ├── simple_pipeline.md
        └── io_contract.md

backend/api/harness.py         # 所有 /api/harness/* 端点

backend/harness_legacy/        # 旧 backend/harness/ 重命名；v2 上线 PR 一次性 rm
backend/agent_legacy/          # 旧 backend/agent/ 重命名；同上
```

---

## 十三、前端改动

### 13.1 事件契约切换

前端 `useSSE` hook 清理旧事件，只认 v2 事件清单。旧事件遇到直接 drop（不兼容）。

### 13.2 组件清单

| 组件 | 处置 | 说明 |
|---|---|---|
| `AgentPanel.tsx` | 保留，重写内部 | 入口 UI 不变，用户体感一致 |
| `AgentStatusPanel.tsx` | 重写 | 按 v2 事件渲染 trace，支持折叠工具调用与 skill 加载 |
| `PlannerStatus.tsx` | **删除** | 被 `AgentStatusPanel` v2 取代 |
| `ClarificationBubble.tsx` | **删除** | 合并入 `ClarificationPrompt`（新组件） |
| `AutoRunStatus.tsx` | 简化 | 只渲染 session 状态 + 进度，不再拼装 planning 事件 |
| `ApplyDraftButton.tsx` | 保留，改 endpoint | 调用 `/api/harness/sessions/{id}/apply` |

### 13.3 新组件

| 组件 | 用途 |
|---|---|
| `ClarificationPrompt.tsx` | 处理 `awaiting_user_input`：渲染 prompt + 选项按钮 or 文本输入；提交走 `/resume` |
| `ToolCallBadge.tsx` | 在 trace 里折叠显示一次 tool call（点击展开看 args/result） |
| `SkillLoadedBadge.tsx` | 渲染 "已加载 skill: X"（点击查看 markdown） |
| `ValidatorFindings.tsx` | Finalize 失败时渲染 findings 列表，点击 finding 高亮对应节点 |
| `StuckBanner.tsx` | `harness_stuck` 事件的醒目提示 |

### 13.4 Canvas 联动与编辑权限

**核心规则：session 未结束时，Canvas 对 harness 产出的图是只读的。** 避免用户手动编辑与 `workspace_json`（恢复真相来源）打架。

| Session 状态 | Canvas 行为 | 原因 |
|---|---|---|
| `running` / `awaiting_user` | 只读，所有节点锁定（hover 显示"harness 正在生成，生成完成后可编辑"） | workspace_json 是唯一真相，不能被画布侧修改覆盖 |
| `ready` | 解锁，用户可自由编辑 | harness 已产出终图，后续修改属于用户意志 |
| `applied` | 解锁，编辑即修改 workflow | 已落盘到 Workflow，走现有编辑流 |
| `failed` | 只读展示失败时的最后一版草图 | 方便用户排查，不允许基于失败图直接继续 |

**联动事件：**
- `graph_update` 实时更新 `workflowStore` 的 nodes/edges；Canvas 锁定模式下只展示、不响应用户拖拽
- `validator_report` 的 `node_id` 让对应节点闪红边（锁定模式下也显示）
- 用户在 `ready` 状态手动编辑后点"应用"，最终保存的 graph 就是画布当前状态；`preferences` 学习的 diff 基准是 harness 产出的初版（见 §10.2）

**明确不支持的场景：** 在 `running` 状态下"用户一边手改，harness 一边继续跑"。如果确实需要用户干预，harness 会主动发 `AskUser`；用户想打断就用 `POST /api/harness/sessions/{id}/abort`。

### 13.5 状态机（前端）

```
idle
  ↓ (用户点"生成")
running
  ↓ awaiting_user_input
awaiting_user
  ↓ (用户答完 /resume)
running
  ↓ harness_ready
ready
  ↓ (用户点"应用")
applied
```

任何状态收到 `harness_stuck` 或 `session_end(status=failed)` → `failed`。

### 13.6 API 层

- `services/api.ts` 里 agent 相关方法全部删除
- 新增 `services/harnessApi.ts`：
  ```ts
  createSession(goal, workflowId?)
  getSession(id)
  streamEvents(id): EventSource
  resumeSession(id, questionId, answer)
  applySession(id)
  abortSession(id)
  ```
- Zustand `agentStore` 重命名为 `harnessStore`，字段按 v2 状态机重构

---

## 十四、切换策略（无双轨）

### 14.1 开发阶段

1. `git mv backend/harness backend/harness_legacy`
2. `git mv backend/agent backend/agent_legacy`
3. 新建空的 `backend/harness/`，按 §十二 目录结构逐文件实现
4. 前端保持旧路径可用（legacy 路径暂不被任何 import 引用，只剩 `api/agent.py` → `agent_legacy` 的直接引用，保留旧 session 查看能力）

### 14.2 上线 PR（一次性切换）

同一个 PR 完成：
- 后端：`backend/api/agent.py` 删除 + `backend/harness_legacy/` + `backend/agent_legacy/` `git rm`
- 前端：旧组件删除 + `agentStore` 改名 + API 切换
- 测试：所有旧测试删除，新 harness 测试全绿
- 数据迁移：一次性 migration 清空 `agent_sessions` 旧字段（可接受，因为这是 dev 数据库）

**不搞 feature flag。** PR 合入即切换。

### 14.3 需要的测试覆盖

| 测试 | 范围 |
|---|---|
| `test_harness_session_basic` | 单次简单目标能走通 list_providers → propose_action → finalize |
| `test_harness_ask_user_pause_resume` | AskUser 真暂停、workspace 落库、resume 续跑、trace 完整 |
| `test_harness_validator_recovery` | 故意构造缺 end 的目标，模型能在 ≤3 步内修复 |
| `test_harness_skill_load` | LoadSkill 后 facts ledger 有正文；同一 session 不重复加载 |
| `test_harness_stuck_detection` | 连续重复 decision 触发 stuck → AskUser |
| `test_harness_preference_write` | Finalize + 用户手动 apply 后 preferences 被更新 |
| `test_harness_api_endpoints` | 所有 `/api/harness/*` 端点 happy path + error path |

---

## 十五、验收标准

v2 上线必须满足：

- [ ] LeadAgent 至少调用过 2 个不同的 Tool 才做出 ProposeAction（证明它在收集信息）
- [ ] 故意构造一个会触发校验失败的目标，模型能在 ≤3 步内自我修正而不是 fallback
- [ ] 故意构造一个有歧义的目标（如"做个会说话的 agent"），模型能发出 `AskUser` decision
- [ ] 暂停后通过 `/resume` API 能续上，trace 完整、graph 一致
- [ ] Skills 按需加载：`list_skills` tool 能列出 6 个；`LoadSkill` decision 能拉到 Markdown 正文；未调用前 system prompt 不含 skill 正文
- [ ] `project_preferences` 在用户手动 apply 后被更新（有单测覆盖）
- [ ] 所有 Validator 都是无 LLM 的纯函数（grep 确认 `validators.py` 无 llm 引用）
- [ ] 前端 `AgentPanel` 能看到图实时长出来（`graph_update` 驱动 Canvas）
- [ ] `backend/harness_legacy/` 和 `backend/agent_legacy/` 在上线 PR 里已 `git rm`，无残留 import
- [ ] 所有旧事件类型在前端代码中搜不到（grep `planner_observe|planning_update|clarification_turn` 零结果）

---

## 十六、明确不在本 spec 范围内

- **Sub-agents / 并行 agent 协同**：未来如复杂度上来再开 spec
- **Episodic memory / 向量检索相似会话**：user 偏好已够；再做请独立 spec
- **Sandbox / 执行代码**：PIAgent 产物是 workflow JSON，不走这条路
- **MCP 协议接入**：Tool Protocol 为未来预留了可能性，但 v2 不实现
- **路由层（fast vs harness）LLM 化判断**：v2 只有一个 harness 路径，不做路由
- **多用户 / 鉴权 / 多租户**：与 harness 解耦
- **节点级并行执行**：`core/engine.py` 的优化，与 harness 无关

---

## 十七、开工检查清单（spec 确认后）

按此顺序动刀，保证每一步都可测：

1. 重命名 `backend/harness/` → `backend/harness_legacy/`，`backend/agent/` → `backend/agent_legacy/`
2. 新建空 `backend/harness/` + 目录骨架
3. 实现 `schemas.py` + `actions.py` + `builder.py`（最小原语）
4. 实现 `tools/base.py` + `tools/list_node_types.py` + `tools/list_providers.py`（先跑通 2 个工具）
5. 实现 `workspace.py` + `prompts.py`（最小 observation 渲染）
6. 实现 `lead_agent.py`（先跑通 `CallTool` + `ProposeAction` + `Finalize` 三种 decision，暂不支持 `AskUser` / `LoadSkill`）
7. 实现 `session.py` + `api/harness.py`（端点）
8. 单元测试 happy path（LLM 走 mock）
9. 补齐剩余 5 个工具（`list_knowledge_bases` / `peek_knowledge_base` / `list_skills` / `recall_preference` / `validate_graph`）
10. 实现 `skills/loader.py` + 6 个 Markdown skill + 接入 `LoadSkill` decision 分支
11. 实现 `AskUser` decision 的暂停/恢复（含 `workspace_json` 落库 + `/resume` 端点）
12. 实现 `validators.py` + finalize 闭环
13. 实现 `preferences.py` + finalize 后学习
14. 前端：新 API client + `ClarificationPrompt` + `AgentStatusPanel` 重写
15. 前端：canvas 联动 + `graph_update` 驱动
16. 端到端跑通 §十五 全部验收项
17. 一次性删除 `harness_legacy/` 和 `agent_legacy/`，合入主干

**每一步结束后都应该有可运行的代码和至少一个新绿灯测试。** 如果卡在某步超过一天，停下来重新对齐 spec。
