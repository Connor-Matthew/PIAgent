# PIAgent - Agent 模式设计文档

> 状态：重写版 · M0-M5 已落地
> 范围：在现有手动 workflow 编排能力之上，新增 Agent 模式。用户输入一句话目标，Agent 先做有限轮澄清，再生成一张与当前 runtime 兼容的 workflow 草图，交由用户 review / apply / run。
> 与主 spec 的关系：本文档是当前 phase 的落地设计。稳定后回填 `2026-04-13-piagent-design.md`。

---

## 1. 背景与目标

### 1.1 为什么要做 Agent 模式

PIAgent 当前本质上是一个可视化 workflow 编排器：用户拖节点、配参数、点击运行。工程基础已经比较扎实，但产品叙事仍然偏向 "手动工作流工具"。

Agent 模式要解决的不是把产品做成黑盒，而是补上一层 "自然语言目标 -> 结构化澄清 -> 可编辑 workflow 草案" 的体验闭环：

- 降低门槛：用户不需要先理解 DAG 才能开始
- 保留可控性：Agent 的输出不是最终结果，而是一张可审阅、可修改的图
- 形成差异化：把 "Agent 的智能性" 和 "Workflow 的可控性" 放到同一个产品里

### 1.2 本 phase 的成功标准

本 phase 不追求 "自由生成任意复杂 DAG"，而追求下面这件事稳定可用：

1. 用户输入目标
2. Agent 最多澄清 3-5 轮
3. 后端产出一张当前 runtime 可执行的 workflow 草案
4. 前端把草案渲染到 Canvas
5. 用户点击 Apply 后，草案作为普通 workflow 落库并可直接运行

---

## 2. 当前 phase 的边界

### 2.1 用户承诺

当前 phase 承诺的是：

- 生成与当前编译器兼容的 graph JSON
- 优先生成单链路、低歧义、可直接运行的图
- 在资源不足时做能力感知的降级，而不是幻想不存在的节点或 provider

### 2.2 明确非目标

以下内容不进入当前 phase：

- 自由形态 DAG 生成
- 多分支音频合成
- `AudioMerge` 节点
- Planner 自动生成 `agent` 节点
- 双主持双音色的多轨 TTS

这些能力都依赖 runtime 先补齐：

- 分支间显式数据路由
- 多 TTS 分支的合流节点
- 更细粒度的节点输入映射
- 更稳定的 AgentNode 工具实现

### 2.3 对播客场景的现实化定义

当前 phase 仍然可以服务 "做一期播客" 这样的目标，但生成的 graph 以单链路为主：

- `start -> llm -> end`
- `start -> rag -> llm -> end`
- `start -> llm -> tts -> end`
- `start -> rag -> llm -> tts -> end`

如果用户希望 "双主持对谈"，当前 phase 只把它落实到脚本风格上，不落实成双 TTS 分支。

---

## 3. 现有 runtime 约束

这部分是 Agent 模式必须服从的现实边界。

### 3.1 持久化对象不是 WorkflowState，而是 WorkflowGraph

当前后端真正保存的是：

```python
graph = {
    "nodes": [...],
    "edges": [...],
}
```

`WorkflowState` 是执行时的可变状态，由 `ExecutionEngine` 在 run 阶段创建和推进；它不是 Planner 的输出契约。

因此 Agent 模式的契约必须是：

`LLM structured output -> adapter -> WorkflowGraph -> run-time WorkflowState`

而不是：

`LLM structured output -> WorkflowState`

### 3.2 当前稳定节点词表

当前 runtime 已注册节点包括：

- `start`
- `llm`
- `rag`
- `tts`
- `agent`
- `end`

但对 Planner 而言，当前 phase 只开放以下节点给自动生成：

- `start`
- `llm`
- `rag`
- `tts`
- `end`

`agent` 节点保留给未来 phase。原因是它的工具执行仍偏占位实现，不适合作为 Planner 的默认产物。

### 3.3 当前数据流的关键限制

当前 graph 虽然是 DAG，但节点间的数据路由能力仍然有限：

- `rag` 通过全局 `state["context"]` 影响后续 `llm`
- `llm` 主要把文本写入 `state["llm_output"]` 和 `node_outputs[llm_id]["text"]`
- `tts` 默认读取 `state["llm_output"]` 或 `state["input"]`
- `end` 通过 `{{node_id.field}}` 从 `node_outputs` 引用结果

这意味着当前 phase 不应生成：

- 需要显式 merge 的分支图
- 依赖自定义 per-edge 参数映射的复杂图
- 依赖不存在字段的模板引用

---

## 4. 用户旅程

### 4.1 典型旅程

```text
[Step 1] 用户切到 Agent 模式
            ↓
[Step 2] 输入："做一期面向计算机本科生的 Transformer 科普播客"
            ↓
[Step 3] Agent 进入澄清阶段（最多 3-5 轮）
          Q1: 风格偏严肃技术还是轻松科普？
          Q2: 需要引用知识库资料吗？
          Q3: 最终是否需要直接生成音频？
            ↓
[Step 4] Agent 生成 RecipeIR
            ↓
[Step 5] adapter 把 RecipeIR 展开成 WorkflowGraph
            ↓
[Step 6] 前端渲染 Canvas 草案：
          start -> rag -> llm -> tts -> end
            ↓
[Step 7] 用户 review，修改节点配置
            ↓
[Step 8] 用户点击 Apply，workflow 落库
            ↓
[Step 9] 用户点击 Run，ExecutionEngine 正常执行
```

### 4.2 关键交互原则

- 透明：前端要能看到当前在澄清、在生成草案、在做 repair，还是在等待用户
- 可降级：用户可以随时跳过剩余澄清，用默认值生成草案
- 可编辑：Agent 产出的 graph 与手动创建的 workflow 完全等价
- 不硬撑：当运行时能力不足时，明确降级，不生成幻想节点

---

## 5. 核心设计

### 5.1 总体结构

当前 phase 采用两阶段 Planner：

- Phase A · Clarify：决定还需不需要继续问，并输出下一个维度问题
- Phase B · Generate：不直接生成 graph，而是先生成一个低熵的 `RecipeIR`

然后由 adapter 做确定性展开：

`RecipeIR -> WorkflowGraph`

### 5.2 为什么不用自由 DAG 生成

原因不是 "模型不够聪明"，而是当前 runtime 还没有为自由 DAG 生成提供足够稳定的地面：

- 节点词表有限
- 部分节点是占位能力
- 数据流主要依赖共享 state，而不是显式端口映射
- 当前真正需要的是一个能稳定跑通的 phase，而不是一个看起来更通用但高失败率的设计

所以本 phase 的核心决策是：

> LLM 只决定 "用哪个 recipe + 关键参数是什么"，不直接自由画图。

### 5.3 三层契约

#### Layer 1 · ClarifyDecision

Phase A 的结构化输出：

```python
ClarifyDim = Literal[
    "audience_level",
    "tone",
    "duration_minutes",
    "script_format",
    "include_code_snippets",
    "use_knowledge_base",
    "need_audio_output",
]

class ClarifyDecision(BaseModel):
    need_more_info: bool
    next_dim: ClarifyDim | None = None
    next_question: str | None = None
    rationale: str
```

约束：

- `need_more_info=true` 时，`next_dim` 和 `next_question` 必填
- `next_dim` 只能从预定义维度清单中选择

#### Layer 2 · RecipeIR

Phase B 的结构化输出：

```python
RecipeLiteral = Literal[
    "start_llm_end",
    "start_rag_llm_end",
    "start_llm_tts_end",
    "start_rag_llm_tts_end",
]

AudienceLevelLiteral = Literal[
    "general",
    "general_tech",
    "undergraduate_cs",
    "advanced",
]

ToneLiteral = Literal[
    "neutral_explanatory",
    "casual_educational",
    "serious_technical",
]

ScriptFormatLiteral = Literal["monologue", "dialogue"]

class RecipeIR(BaseModel):
    recipe: RecipeLiteral
    goal_summary: str
    audience_level: AudienceLevelLiteral
    tone: ToneLiteral
    duration_minutes: int
    script_format: ScriptFormatLiteral
    include_code_snippets: bool
    use_knowledge_base: bool
    need_audio_output: bool
    knowledge_base_id: str | None = None
    llm_provider_id: int | None = None
    tts_provider_id: int | None = None
    tts_voice_id: str | None = None
```

设计原则：

- 不让模型输出 node 坐标
- 不让模型输出 `end.outputs` / `answer` 这样的样板字段
- 不让模型输出低价值但高失败率的 `rationale`
- 不要求模型拼装完整 graph JSON

#### Layer 3 · WorkflowGraph

adapter 接收 `RecipeIR` 和运行时 capabilities，生成最终可保存的 `WorkflowGraph`。

adapter 负责：

- 选择标准节点 ID，如 `start_1`, `rag_1`, `llm_1`, `tts_1`, `end_1`
- 生成合法 `nodes` / `edges`
- 填充默认 config
- 生成 `end.outputs` 与 `answer`
- 调用编译器做 DAG 校验
- 校验 provider / voice / knowledge base 是否真实存在

`WorkflowState` 只在执行期由 engine 创建，不再作为 Planner 契约出现。

### 5.4 能力感知的默认草案

默认草案不是写死为某一条链路，而是根据 capabilities 选择最低风险的合法 recipe：

1. 如果没有启用的 LLM provider：Agent 模式不可用，直接返回配置错误
2. 如果有 LLM + TTS + KB，且目标明显需要音频：默认 `start_rag_llm_tts_end`
3. 如果有 LLM + TTS：默认 `start_llm_tts_end`
4. 如果有 LLM + KB：默认 `start_rag_llm_end`
5. 否则：默认 `start_llm_end`

这条规则同时用于：

- 用户主动跳过澄清
- 分类器失效时的兜底
- Phase B 多轮 repair 后仍未通过时的降级草案

### 5.5 Rationale 的处理

解释性文字不进入关键路径：

- 主流程只关心拿到能跑的 `WorkflowGraph`
- 若需要展示 "为什么这样规划"，在 `graph` 生成成功后做一次单独的非结构化说明调用
- 说明失败不影响 Apply / Run

---

## 6. 架构设计

### 6.1 后端模块

```text
backend/
├─ agent/
│  ├─ __init__.py
│  ├─ planner.py              # AgentPlanner，总控 Phase A / Phase B
│  ├─ clarifier.py            # ClarifyDecision 生成
│  ├─ generator.py            # RecipeIR 生成
│  ├─ adapter.py              # RecipeIR -> WorkflowGraph
│  ├─ capabilities.py         # 读取可用 provider / voice / KB / defaults
│  ├─ defaults.py             # 各 recipe 的默认参数与模板
│  ├─ prompts.py              # Prompt 模板
│  ├─ schemas.py              # Pydantic 契约
│  ├─ validator.py            # repair 前后的统一校验
│  └─ session_store.py        # AgentSession 存取
├─ api/
│  └─ agent.py                # /api/agent/*
```

### 6.2 与现有 ExecutionEngine 的关系

关系非常简单：

- Planner 产出的是 `WorkflowGraph`
- `apply` 后保存到现有 `workflows` 表
- 用户 run 时继续走现有 `POST /api/workflows/{id}/run`

执行期 `WorkflowState` 和 SSE 仍然由现有 runtime 负责。

### 6.3 前端模块

```text
frontend/src/
├─ components/
│  ├─ agent/
│  │  ├─ AgentPanel.tsx
│  │  ├─ ClarificationBubble.tsx
│  │  ├─ PlannerStatus.tsx
│  │  └─ ApplyDraftButton.tsx
│  └─ canvas/
│     └─ AutoLayout.ts
├─ hooks/
│  └─ useAgentSession.ts
├─ services/
│  └─ agentApi.ts
└─ stores/
   └─ agentStore.ts
```

### 6.4 SSE 事件

Agent 模式新增事件：

| 事件 | 载荷 | 含义 |
|---|---|---|
| `agent_session_started` | `{ session_id, goal }` | 会话创建成功 |
| `clarify_question` | `{ turn_index, next_dim, question }` | 下一轮澄清问题 |
| `clarify_completed` | `{ total_turns, answered_dims }` | 澄清结束 |
| `recipe_generating` | `{ attempt }` | Phase B 正在生成 |
| `recipe_repairing` | `{ attempt, errors }` | 带错误清单 repair |
| `plan_ready` | `{ recipe, graph, defaults_applied, rationale? }` | graph 草案准备完成 |
| `agent_error` | `{ stage, message, recoverable }` | 当前阶段失败 |

---

## 7. 数据模型

### 7.1 AgentSession

```python
class AgentSession(BaseModel):
    session_id: str
    user_goal: str
    status: Literal[
        "clarifying",
        "generating",
        "ready",
        "applied",
        "failed",
    ]
    clarification_turns: list[ClarificationTurn]
    recipe_ir: RecipeIR | None
    generated_graph: dict | None
    rationale_text: str | None
    workflow_id: str | None
```

### 7.2 数据库存储建议

```sql
CREATE TABLE agent_sessions (
    id                 TEXT PRIMARY KEY,
    user_goal          TEXT NOT NULL,
    status             TEXT NOT NULL,
    turns_json         TEXT NOT NULL,
    recipe_json        TEXT,
    graph_json         TEXT,
    rationale_text     TEXT,
    workflow_id        TEXT,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL
);
```

说明：

- `recipe_json` 便于调试与 replay
- `graph_json` 便于前端断线重连后恢复草案

---

## 8. API 设计

```text
POST /api/agent/sessions
  body: { goal: string }
  resp: { session_id }
  说明: 创建 session，并先做 capabilities 检查；若通过则触发第一次 clarify

POST /api/agent/sessions/{id}/answer
  body: { answer: string }
  resp: 202
  说明: 提交本轮回答，继续推进 planner

POST /api/agent/sessions/{id}/skip
  resp: 202
  说明: 跳过剩余澄清，直接生成默认草案或进入 Phase B

GET /api/agent/sessions/{id}/events
  说明: 订阅该 session 的 SSE 事件

GET /api/agent/sessions/{id}
  说明: 获取当前 session 状态，支持刷新恢复

POST /api/agent/sessions/{id}/apply
  resp: { workflow_id }
  说明: 将 generated_graph 写入 workflows 表
```

---

## 9. 关键技术决策

### 9.1 为什么仍然采用两阶段

两阶段的优点依然成立：

- 澄清阶段关注 "还缺不缺信息"
- 生成阶段关注 "选哪个 recipe 和参数"
- 两个阶段都能独立测试与观察失败样本

### 9.2 为什么从自由 graph 降到 RecipeIR

这是本次重写最重要的决策：

- 当前 runtime 还不适合自由 graph 生成
- 低熵 `RecipeIR` 更符合现阶段代码 reality
- 失败时更容易做 repair
- adapter 可以沉淀稳定的 graph 构造逻辑

未来若 runtime 补齐分支路由和 merge 节点，可以再升级为更通用的 `GraphPlanIR`。

### 9.3 为什么 Planner 不直接选 `agent` 节点

当前 `agent` 节点虽已注册，但仍依赖占位工具实现。若直接允许 Planner 生成：

- 用户会得到看起来更高级、但实际更不可控的图
- repair 失败样本会显著增加

因此当前 phase 明确禁止 Planner 自动生成 `agent` 节点。

### 9.4 失败分类与回退策略

#### Phase A · Clarify

| 失败类型 | 判定信号 | 处理策略 |
|---|---|---|
| Schema failure | 不满足 `ClarifyDecision` 校验 | 1 次正常重试 + 1 次带错误信息 repair |
| Missing capability context | 问题依赖未注入的 voice / KB / provider 信息 | 补齐上下文后重跑，不计入 repair 次数 |
| Clarification deadlock | 连续 2 轮没有获得新维度信息 | 结束澄清，转默认草案路径 |

#### Phase B · Generate

`RecipeIR` 的处理链路：

```text
首次生成 RecipeIR
  -> validator 校验字段、capabilities、recipe 合法性
  -> adapter 尝试展开 graph
  -> compiler.validate(graph)
  -> 若失败，带错误列表做 repair
  -> 最多 2 次 repair
  -> 若仍失败，回落到能力感知的默认草案
```

#### 不再承诺的内容

当前文档不再承诺 "任何情况下都一定给用户 runnable graph"。

现实约束是：

- 至少要有一个启用的 LLM provider，Agent 模式才有意义
- 如果连最低能力都不存在，系统应尽早暴露配置错误，而不是伪造草案

### 9.5 V1 支持的 recipe 与 graph 展开

#### Recipe: `start_llm_end`

```text
start_1 -> llm_1 -> end_1
```

#### Recipe: `start_rag_llm_end`

```text
start_1 -> rag_1 -> llm_1 -> end_1
```

#### Recipe: `start_llm_tts_end`

```text
start_1 -> llm_1 -> tts_1 -> end_1
```

#### Recipe: `start_rag_llm_tts_end`

```text
start_1 -> rag_1 -> llm_1 -> tts_1 -> end_1
```

每个 recipe 都由 adapter 生成标准节点 config，Planner 本身不写低层 graph 细节。

---

## 10. 分阶段执行计划

### 10.1 总体节奏

现实预估：

- M0-M4 合计约 2 周
- M5 作为后续 spike，不并入本 phase 交付承诺

### 10.2 Milestones

| 阶段 | 目标 | 关键交付物 | 预估周期 |
|---|---|---|---|
| M0 · 契约落地 | 固化 `RecipeIR -> WorkflowGraph -> WorkflowState` 边界 | `schemas.py` 草案、spec 定稿、recipe 白名单 | 0.5-1 天 |
| M1 · Capabilities + adapter | 能从 `RecipeIR` 稳定生成 graph | `capabilities.py`、`defaults.py`、`adapter.py`、graph unit tests | 2-3 天 |
| M2 · Clarifier + session API | 多轮澄清与 session 生命周期跑通 | `clarifier.py`、`session_store.py`、`/sessions`、`/answer`、`/skip` | 3-4 天 |
| M3 · Repair + fallback | 失败分类、repair、默认草案生效 | `validator.py`、repair loop、capability-aware fallback | 2-3 天 |
| M4 · Frontend 融合 | 前端能完整收发事件并 apply graph | `AgentPanel`、`useAgentSession`、Canvas 注入、Apply 流程 | 3-4 天 |
| M5 · Phase 2 spike | 评估自由 graph / 多分支 / merge 的可行性 | 方案文档与风险评估 | 3-5 天 |

### 10.3 每个阶段的验收标准

#### M0

- 文档中不再混用 `WorkflowState` 和 `WorkflowGraph`
- Prompt、schema、runtime 词表一致

#### M1

- 给定合法 `RecipeIR`，adapter 必须稳定产出可保存 graph
- 产出的 graph 必须通过现有 `GraphCompiler.validate`

#### M2

- 能完整走通 `create -> clarify -> answer -> clarify_completed`
- session 状态可刷新恢复

#### M3

- Schema 错误、capability 缺失、deadlock 三类失败都有明确路径
- 默认草案选择逻辑覆盖 4 种 capability 组合

#### M4

- `plan_ready` 后前端可直接渲染到 Canvas
- 用户可点击 Apply，把 graph 保存为普通 workflow

### 10.4 测试计划

必须补的测试：

- `test_clarify_decision_schema`
- `test_recipe_ir_validation`
- `test_adapter_builds_start_llm_end`
- `test_adapter_builds_start_rag_llm_tts_end`
- `test_fallback_selects_lowest_risk_recipe`
- `test_agent_session_lifecycle`
- `test_apply_generated_graph_creates_workflow`

---

## 11. 与主 spec 的融合

本 phase 至少完成 M1 + M2 后，再回填主 spec：

1. 架构章节：新增 `backend/agent/*`
2. API 章节：新增 `/api/agent/*`
3. 前端章节：新增 `components/agent/*`
4. SSE 协议：新增 Agent 专用事件
5. 技术谈资：补上 "低熵 RecipeIR + adapter" 这条设计决策

Phase 2 spike 结论已单独整理在：

- [`docs/superpowers/plans/archive/2026-04-15-agent-mode-phase2-spike.md`](../plans/archive/2026-04-15-agent-mode-phase2-spike.md)

---

## 附录 A · Prompt 设计

### A.1 Clarifier Prompt

#### A.1.1 可追问维度

Clarifier 只允许从以下维度中选择：

| 维度 | 影响 | 默认值 |
|---|---|---|
| `audience_level` | 影响术语深度 | `general_tech` |
| `tone` | 影响脚本风格 | `casual_educational` |
| `duration_minutes` | 影响脚本长度 | `10` |
| `script_format` | 影响脚本写法（独白 / 对话） | `monologue` |
| `include_code_snippets` | 影响是否强调代码讲解 | `false` |
| `use_knowledge_base` | 影响是否引入 `rag` recipe | 若存在 KB 默认 `true`，否则 `false` |
| `need_audio_output` | 影响是否引入 `tts` recipe | `true` |

#### A.1.2 Clarifier System Prompt

```text
你是 PIAgent 的澄清助手。你唯一的任务是判断是否还需要追问用户信息。

【目标】
{user_goal}

【已回答维度】
{answered_dims_json}

【允许追问的维度】
{allowed_dims_json}

【运行时能力】
{capabilities_summary_json}

【规则】
1. 每轮最多追问一个维度
2. 只能从允许维度里选，不得自创维度
3. 如果默认值已经足够，直接返回 need_more_info=false
4. 如果连续两轮没有获得新维度，直接结束
5. 问题必须是中文自然语言

【输出】
{
  "need_more_info": true | false,
  "next_dim": "<allowed dim key or null>",
  "next_question": "<中文问题 or null>",
  "rationale": "<一句话说明>"
}
```

### A.2 Generator Prompt

#### A.2.1 必须注入的运行时上下文

```json
{
  "supported_recipes": [
    "start_llm_end",
    "start_rag_llm_end",
    "start_llm_tts_end",
    "start_rag_llm_tts_end"
  ],
  "enabled_llm_providers": [
    { "id": 1, "name": "OpenAI", "default_model": "gpt-4o" }
  ],
  "enabled_tts_providers": [
    {
      "id": 2,
      "name": "MiniMax",
      "voices": ["female-shaonv", "male-qn-jingying"]
    }
  ],
  "knowledge_bases": [
    { "id": "kb_transformer", "name": "Transformer 资料库" }
  ],
  "defaults": {
    "audience_level": "general_tech",
    "tone": "casual_educational",
    "duration_minutes": 10,
    "script_format": "monologue",
    "include_code_snippets": false,
    "need_audio_output": true
  }
}
```

#### A.2.2 Generator System Prompt

```text
你是 PIAgent 的 workflow 规划器。你的任务不是画任意 DAG，而是从受支持的 recipe 中选择一个，并填好 RecipeIR。

【用户目标】
{user_goal}

【澄清结果】
{clarification_summary_json}

【运行时能力】
{capabilities_json}

【规则】
1. 只能使用 supported_recipes 中的字面量
2. 如果需要知识库，knowledge_base_id 必须来自 knowledge_bases
3. 如果需要音频输出，tts_provider_id 和 tts_voice_id 必须来自 enabled_tts_providers
4. 如果未显式指定 provider，可使用 null，由 adapter 选默认值
5. 只输出 RecipeIR JSON，不要输出解释文字

【输出 schema】
{recipe_ir_schema_json}
```

#### A.2.3 Few-shot 示例

示例 1：

输入：

- goal: "做一期 10 分钟的 Transformer 科普播客"
- 澄清：`use_knowledge_base=true`, `need_audio_output=true`, `audience_level=undergraduate_cs`

输出：

```json
{
  "recipe": "start_rag_llm_tts_end",
  "goal_summary": "生成一段面向计算机本科生的 Transformer 科普播客脚本并合成音频",
  "audience_level": "undergraduate_cs",
  "tone": "casual_educational",
  "duration_minutes": 10,
  "script_format": "monologue",
  "include_code_snippets": false,
  "use_knowledge_base": true,
  "need_audio_output": true,
  "knowledge_base_id": "kb_transformer",
  "llm_provider_id": 1,
  "tts_provider_id": 2,
  "tts_voice_id": "female-shaonv"
}
```

示例 2：

输入：

- goal: "给我一份注意力机制讲稿，不需要音频"
- 澄清：`use_knowledge_base=false`, `need_audio_output=false`

输出：

```json
{
  "recipe": "start_llm_end",
  "goal_summary": "生成一份关于注意力机制的讲稿",
  "audience_level": "general_tech",
  "tone": "neutral_explanatory",
  "duration_minutes": 8,
  "script_format": "monologue",
  "include_code_snippets": false,
  "use_knowledge_base": false,
  "need_audio_output": false,
  "knowledge_base_id": null,
  "llm_provider_id": 1,
  "tts_provider_id": null,
  "tts_voice_id": null
}
```

#### A.2.4 Repair Prompt

```text
你上次输出的 RecipeIR 有以下问题：
{validation_errors_json}

请仅修正报错字段，保持其他字段不变。
只输出修正后的 RecipeIR JSON。
```

---

*文档结束*
