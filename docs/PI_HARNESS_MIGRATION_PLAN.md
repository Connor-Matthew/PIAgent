# pi_harness 迁移计划

> 用 **mini-harness** 替换 PIAgent 现有 LeadAgent 模块，保留全部 UI 与节点体系。
> 定位：架构演进，非重写；目标是用通用 ReAct 壳 + 领域工具/技能取代手写 agent loop。
> 本计划已按 2026-04-20 对 `/Users/mac/Desktop/mini-harness` 的实勘结果校准，默认采用“将 mini-harness 通用 agent 内核按最小子集内嵌到 `backend/pi_harness/runtime/`，不直接复用其 API / CLI / config 层”的接入方式。

---

## 0. 主体思路与目的

### 0.1 一句话概括
**把 PIAgent 里“AI agent 怎么思考”这件事，从自写 loop 换成 mini-harness 通用 ReAct 壳；“AI agent 能做什么”仍由 PIAgent 以“工具 + 技能”的形式提供；会话、SSE、持久化、应用工作流这些产品契约继续由 PIAgent 自己掌控。**

### 0.2 核心思路
PIAgent 当前的 agent 模块（`backend/harness/`）由两类代码混在一起：

- **壳代码（~1000 行）**：ReAct 循环、消息管理、prompt 组装、工具分发、技能加载。这些是**任何 agent 都要写的通用逻辑**，和 PIAgent 业务无关。
- **领域代码（~1700 行）**：WorkflowGraph 校验、provider DB、GraphBuilder、图状态、SSE 事件、会话生命周期。这些是**PIAgent 独有的资产**，沉淀了产品知识。

mini-harness 已经把“壳”做得很完整（LangGraph `create_react_agent` + skills loader + loop detection + clarification + summarization + token usage）。与其继续维护 PIAgent 自己的壳，不如**壳归壳、肉归肉**：

- **换壳**：agent loop、技能注入、通用推理流程整体交给内嵌到 `pi_harness/runtime/` 的 mini-harness-derived runtime。
- **留肉**：PIAgent 的领域资产以**工具（Tools）+ 技能（Skills）+ 会话编排（Session Orchestration）**三层形式暴露给壳。

```
┌──────────────────────────────────────────────────┐
│   PIAgent UI (画布 / 节点库 / 配置面板)           │  ← 不变
├──────────────────────────────────────────────────┤
│   PIAgent Session/API 层                         │  ← 保留
│   /api/harness/* / SSE / resume / apply          │
├──────────────────────────────────────────────────┤
│   mini-harness ReAct 壳 (LangGraph)              │  ← 新，替换手写 loop
├──────────────────────────────────────────────────┤
│   Tools               │   Skills                 │  ← 标准接口层
│   add_node / ...      │   llm_basic/SKILL.md ... │
├──────────────────────────────────────────────────┤
│   PIAgent 领域资产                                │  ← 不变
│   WorkflowGraph / Validators / Provider DB        │
│   节点体系 / 知识库 / ExecutionEngine             │
└──────────────────────────────────────────────────┘
```

### 0.3 为什么用“工具 + 技能”作为接口
这不是随意的分层，而是和 ReAct agent 的认知模型对齐：

- **Tools = “我能做什么”**：原子能力，有明确输入输出和副作用。例如 `add_node(type, config)`。Agent 通过调用工具改变世界。
- **Skills = “我该怎么做”**：按需加载的操作手册（Markdown + frontmatter），教 agent 在特定场景下如何组合工具。例如 `rag_qa/SKILL.md` 教 agent 怎么搭 RAG 流水线。

这套抽象的好处：**新增能力 = 加一个工具 + 写一份 SKILL.md**，不需要改 agent 核心代码，也不需要改 UI。

### 0.4 要达到的目的
1. **干掉手写壳代码的 bug 源**：删除 ~1000 行自写 loop，换成经过验证的 LangGraph。
2. **免费获得通用能力**：循环检测、澄清追问、会话摘要、token 统计，全部复用 mini-harness。
3. **保持产品契约零回归**：画布渐进渲染、会话历史、`resume/apply/abort`、provider 管理等现有 UX 和接口语义不变。
4. **打开扩展性**：未来加新节点类型、新 agent 能力（调试工作流、编辑现有图、推荐优化），都能通过“加工具 + 加技能”完成。
5. **技术叙事升级**：从“我自己写了个 agent”变成“我设计了一套工具 + 技能接口，让通用 agent 去驱动业务”。

### 0.5 边界与原则
- ✅ **换**：agent loop、消息管理、技能注入、通用工具分发。
- ✅ **桥**：provider/model 解析、session-scoped tools、SSE 事件适配、会话持久化、clarification/apply 语义衔接。
- ✅ **保留 PIAgent API 契约**：`/api/harness/*`、前端事件 schema、`resume` / `apply` / `abort` 生命周期仍由 PIAgent 拥有。
- ❌ **不直接复用 mini-harness API / CLI / config**：不把 `mini_harness.api.routes:/runs/stream` 直接当生产接口，也不把其 `config.yaml`、CLI、sandbox 壳直接带进 PIAgent。
- ❌ **不动**：WorkflowGraph schema、validators、节点体系、ExecutionEngine、前端整体布局、Provider DB 结构、知识库模块。
- 📏 **并存迁移**：新建 `backend/pi_harness/`，旧代码保留到最终切换，每步可独立验证、可回滚。

### 0.6 mini-harness 现状校准
实勘 `/Users/mac/Desktop/mini-harness` 后，接入假设需要按以下现实修正：

- **model 层是 config 驱动的**：`create_chat_model()` 当前直接从 `config.yaml` 读取配置并构造 `ChatOpenAI`，还没有 DB provider 注入点。
- **tool 层是全局单例 registry**：`get_tool_registry()` 返回进程级单例，`register_from_config()` 默认只支持 `cls()` 无参实例化。
- **skills 是目录式加载**：loader 只识别 `skills/<name>/SKILL.md`，不是平铺的 `*.md` 文件。
- **API 很薄**：`/runs/stream` 只流 `message` / `clarification` / `done`，不覆盖 PIAgent 现有的 `graph_update`、`awaiting_user_input`、`harness_ready`、`session_end`、`apply` 等语义。
- **依赖版本有漂移**：mini-harness 当前代码和 PIAgent 现有 `langgraph/langchain` 版本并不完全同代，直接作为外部依赖接入会把迁移风险和依赖升级绑在一起。

**结论**：mini-harness 适合被当作“内嵌式 agent runtime 内核来源”，而不是直接替代 PIAgent 的 session/API 层或作为外部包接入。迁移的关键不是“接一下路由”，而是“把需要的 runtime 核心搬进 `pi_harness/runtime/`，删掉其对外部 config / registry / API 壳的假设，再由 PIAgent 包起来”。

### 0.7 术语约定：本计划中的 mini-harness runtime
下文凡提到“mini-harness runtime”或“mini-harness create_agent(...)”，均指：

- 来自 `/Users/mac/Desktop/mini-harness` 的**通用 agent 内核最小子集**
- 被复制并维护在 `backend/pi_harness/runtime/` 下
- 只保留我们需要的内核模块，例如 ReAct agent factory、skills loader、clarification、loop detection、summarization、token usage、tool registry core
- **不复制** mini-harness 的 `api/`、`cli.py`、`config.yaml` 驱动配置层、sandbox/provider 壳、与当前迁移无关的 builtins

这是一种**受控 vendoring / 内嵌 runtime** 方案，而不是“把整个 mini-harness 当成 PIAgent 的运行时依赖”。

---

## 1. 动机与目标

### 1.1 现状痛点
- `backend/harness/` 共约 **2.7k 行**，其中 ~1k 行是手写的 agent loop、消息管理、prompt 组装、工具分发、循环控制等“壳”代码（`lead_agent.py`、`llm_client.py`、`memory.py`、`prompts.py`、`session.py` 的控制流部分）。
- 手写 loop 易出 bug、缺少通用能力（循环检测、澄清追问、摘要压缩、token 统计）。
- 工具扩展需改多处，心智负担重。
- 当前前端已经依赖一整套 session 生命周期与 SSE 契约，迁移不能只关注“模型能不能跑起来”，还要保住 `create -> stream -> clarify -> resume -> ready -> apply` 这条完整链路。

### 1.2 迁移目标
- **替换**：agent 的“壳”（ReAct loop、消息、工具分发、技能加载）统一交给内嵌到 `backend/pi_harness/runtime/` 的 mini-harness-derived runtime。
- **保留**：PIAgent 的 UI（画布、节点库、配置面板、provider 页）、节点体系、WorkflowGraph v2 schema、validators、provider DB 模型、SSE 前端渲染体验、会话路由语义。
- **收益**：
  - 删除 ~1000 行手写壳代码。
  - 免费获得 loop detection / clarification / summarization / token usage。
  - 新增节点类型或 agent 能力只需“加一个工具 + 写一份 SKILL.md”。
  - 技术栈向主流 LangGraph 生态收敛，简历/面试叙事更强。

### 1.3 非目标
- 不改 WorkflowGraph v2 schema。
- 不改 `ExecutionEngine` 以及 workflow 执行侧。
- 不改 Provider CRUD、Knowledge、节点库等现有模块。
- 不改前端整体布局与节点编辑 UX，只允许在事件解析与后端切换处做最小改动。
- 不以 mini-harness 自带 CLI 或 `/runs/stream` 直接替代 PIAgent 的 API。

---

## 2. 架构设计

### 2.1 核心抽象
把“agent 如何控制工作流”翻译成三层接口：

| 层 | 承担职责 | 对应 PIAgent 概念 |
|---|---|---|
| **Tools**（工具） | agent 可调用的原子操作（改图、查上下文、校验、定稿） | 替代 `GraphBuilder` 命令式 API |
| **Skills**（技能） | agent 的“操作手册”，按需加载 | 对应现 `backend/harness/skills/*.md` |
| **Session Orchestration**（会话编排） | SSE、clarify/resume、ready/apply、持久化 | 保留现有 Harness 产品契约 |

Agent loop 本身（ReAct 循环、消息管理、技能选择）交给 **mini-harness**；会话编排和 UI 契约继续由 PIAgent 自己维护。

### 2.2 新目录布局
```
backend/
  harness/                     # 旧版，迁移期保留，切换完删除
  pi_harness/                  # 新版，内嵌 mini-harness 内核
    __init__.py
    runtime/                   # vendored mini-harness 内核最小子集
      agent/
      skills/
      memory/
      telemetry/
      tools/
    adapters/
      provider_bridge.py       # PIAgent DB Provider -> injected model/model factory
      sse_bridge.py            # LangGraph/tool events -> 现有 harness SSE 事件
      session_store.py         # AgentSession.workspace_json/events_json <-> LangGraph state
    tools/
      graph_ops.py             # add_node / connect_nodes / patch_node_config / remove_*
      context.py               # list_providers / list_node_types / peek_knowledge_base / ...
      validate.py              # validate_graph
      finalize.py              # finalize_draft -> 标记 ready，不直接写 workflows
    skills/
      llm_basic/SKILL.md
      rag_qa/SKILL.md
      io_contract/SKILL.md
      simple_pipeline/SKILL.md
      tts_podcast/SKILL.md
      agent_node/SKILL.md      # 单独保留或并入其他技能，M2 决定
    state.py                   # WorkflowGraphDraft: per-session 可变图状态容器
    session.py                 # 新 HarnessSession 入口（路由层 thin wrapper）
  api/
    harness.py                 # 最终切换仍回到这里，对外路由不变
```

### 2.3 数据流

```
用户输入 goal
    │
    ▼
FastAPI /api/pi_harness/sessions   # 迁移期并存；最终切回 /api/harness/*
    │
    ▼
pi_harness.session.run(goal)
    │
    ▼
┌──────────────────────────────────────────────────┐
│ pi_harness.runtime.create_agent(...)            │
│   ├─ model: PIAgent provider bridge 注入        │
│   ├─ tools: session-scoped tool instances       │
│   └─ skills: pi_harness/skills/*/SKILL.md       │
└──────────────────────────────────────────────────┘
    │
    ├─ LangGraph astream / astream_events
    │
    ├─ WorkflowGraphDraft (per-session state)
    │
    └─ sse_bridge: 转换为 PIAgent 现有事件
          graph_update / awaiting_user_input
          harness_ready / session_end / ...
    │
    ▼
前端 harnessStore / 画布渐进渲染 / resume / apply
```

### 2.4 工具清单（首版）

| 工具 | 来源 | 说明 |
|---|---|---|
| `list_providers` | 搬自 `harness/tools/list_providers.py` | 列出可用 LLM providers，供 agent 选择节点配置 |
| `list_node_types` | 搬自 `harness/tools/list_node_types.py` | 列出画布支持的节点类型及 schema |
| `list_skills` | 搬自 `harness/tools/list_skills.py` | 供 agent 主动发现技能 |
| `peek_knowledge_base` | 搬自 `harness/tools/peek_knowledge_base.py` | 预览知识库 |
| `list_knowledge_bases` | 搬自 `harness/tools/list_knowledge_bases.py` | 列出知识库 |
| `recall_preference` | 搬自 `harness/tools/recall_preference.py` | 读取项目偏好 |
| **`add_node`** | **新增** | 参数：`type, config, parent_id?, branch_id?` -> 往 draft 加节点，并触发 `graph_update` |
| **`connect_nodes`** | **新增** | 参数：`from_id, to_id, source_handle?` -> 加边 |
| **`patch_node_config`** | **新增** | 参数：`id, fields` -> 改节点 config |
| **`remove_node`** / **`remove_edge`** | **新增** | 回退操作 |
| `validate_graph` | 搬自 `harness/tools/validate_graph_tool.py` | 调现有 `validators.py`，不动 |
| **`finalize_draft`** | **新增** | 校验并标记当前 draft 已完成，结束 agent run；**不直接写 `workflows` 表** |

### 2.5 技能复用
现有 `backend/harness/skills/` 下实际有 6 个技能文件：

- `llm_basic.md`
- `rag_qa.md`
- `io_contract.md`
- `simple_pipeline.md`
- `tts_podcast.md`
- `agent_node.md`

迁移时统一转成 mini-harness 所需的目录式结构 `pi_harness/skills/<name>/SKILL.md`，并补 frontmatter（至少包含 `name`、`description`、`enabled`）。其中 `agent_node.md` 需要在 M2 明确决策：单独保留，还是并入别的技能。

---

## 3. 五个关键集成点

### 3.1 Orchestration Model / Provider 桥接
**问题**：mini-harness 当前的 `create_chat_model()` 固定从 `config.yaml` 读取配置并返回 `ChatOpenAI`；PIAgent provider 存在 DB 里、Fernet 加密、支持多 provider 多 key。

**方案**：把 mini-harness 的 agent factory 内核搬到 `pi_harness/runtime/` 后，直接在 vendored runtime 里加入最小注入点，让 PIAgent 能直接提供 orchestration model，而不是强迫它先落到 `config.yaml`：

```python
def create_agent(
    model_name: str | None = None,
    tools: list[str] | None = None,
    system_prompt: str | None = None,
    *,
    model=None,
    model_factory=None,
    tool_instances=None,
):
    ...
```

PIAgent 侧实现一个 `DBProviderFactory` / `DBModelResolver`：

```python
class DBModelResolver:
    def __init__(self, db_session): ...
    def get_model(self, provider_id: str):
        # 从 DB 拉 provider，解密 key，构造 ChatOpenAI/ChatAnthropic/...
```

说明：

- **agent 自己的 orchestration model** 通过这个桥接解决。
- **工作流里 LLM 节点使用哪个 provider** 仍由 `list_providers` + `add_node(type="llm", config={provider_id: ...})` 决定，这是节点级配置，和 agent runtime 不是一回事。

**工作量**：`pi_harness/runtime` ~80–120 行扩展点 + PIAgent ~150 行 adapter。

### 3.2 Session-Scoped Tools 与图状态
**问题**：mini-harness 当前使用全局单例 `ToolRegistry`，而且默认 `cls()` 无参实例化。我们的 `add_node` / `connect_nodes` 需要操作 per-session 的可变图状态，不能放在进程级单例里。

**方案**：

- 在 `pi_harness/state.py` 定义 `WorkflowGraphDraft`（内部持有 `nodes/edges` dict）。
- 每个 session 启动时，创建一组**带状态的 tool instances**，通过构造参数或闭包捕获：
  - `draft`
  - `db_session`
  - `event_sink`
  - `session_id`
- `pi_harness/runtime.create_agent()` 支持直接传入 `tool_instances`，绕过全局 registry。

这比“强行往 `RunnableConfig` 里塞上下文”更贴合 mini-harness 当前实现，也更容易做隔离测试。

**工作量**：~150–200 行。

### 3.3 SSE 与前端契约桥
**问题**：mini-harness 自带 API 只输出 `message` / `clarification` / `done`；PIAgent 前端依赖的却是一整套 richer event family，包括 `graph_update`、`awaiting_user_input`、`harness_ready`、`session_end`，以及 trace 类的 `tool_call` / `tool_result`。

**方案**：

- **不直接复用 mini-harness API**。
- 在 `backend/api/pi_harness.py` 或 `backend/api/harness.py` 内部直接驱动 `agent.astream()` / `agent.astream_events()`。
- 在 `pi_harness/adapters/sse_bridge.py` 里把 LangGraph/tool 事件翻译成现有前端契约：
  - `session_start`
  - `tool_call`
  - `tool_result`
  - `graph_update`
  - `awaiting_user_input`
  - `user_resumed`
  - `harness_ready`
  - `session_end`

特别说明：

- clarification 不能停留在 mini-harness 的 `clarification` 事件层，而要转换成 PIAgent 现有的 `awaiting_user_input`。
- `graph_update` 需要从工具副作用或 draft diff 里生成，不能只靠 AI message。

**工作量**：~200–250 行。

### 3.4 会话持久化
**问题**：mini-harness 默认只维护内存消息列表；PIAgent 当前真实落库的是 `AgentSession.workspace_json` / `events_json`，不是一个现成的 `state_json` 字段。

**方案**：

- **Phase 1 保持现有 DB schema 不动**，避免为了迁移 agent runtime 先引入一次额外的 schema migration。
- `session_store.py` 负责在 `workspace_json` 内保存：
  - LangGraph messages
  - draft snapshot
  - open question
  - ready / failed / applied 等状态
- `events_json` 继续保存已经推给前端的事件，支持刷新回看。
- 如果后续发现消息状态过大，再单独评估是否加 `state_json` 字段；那是第二阶段优化，不是本次迁移的前置条件。

**工作量**：~150 行。

### 3.5 Finalize / Apply 语义衔接
**问题**：mini-harness 是通用 ReAct agent，没有 PIAgent 旧版 `Finalize`/`Apply` 这套产品语义；而当前前端是“agent 把图搭好 -> UI 进入 ready -> 用户点 apply 才真正落库”。

**方案**：

- 新增终止型工具 `finalize_draft`：
  - 调 `validate_graph`
  - 若合法，则标记 session `ready`
  - 结束 agent run
  - **不直接写 `workflows` 表**
- 真正持久化工作流仍由 `POST /api/harness/sessions/{id}/apply` 或迁移期的 `/api/pi_harness/sessions/{id}/apply` 完成。
- clarification 仍经由 `resume` 恢复，而不是在一个长连接里隐式继续。

这样可以完整保住当前 UX，也避免“agent 自己偷偷 apply”导致用户失去控制权。

**工作量**：~80–120 行。

---

## 4. 里程碑与验收

### M1 — Runtime Vendoring Spike（1.5–2.5 天）
**目标**：证明 mini-harness 通用内核在被内嵌到 `backend/pi_harness/runtime/` 后，可以不依赖外部包安装、`config.yaml` 或全局 registry，被 PIAgent 直接驱动。

- [x] 把 mini-harness 的最小 runtime 核心复制到 `backend/pi_harness/runtime/`
- [x] 给 vendored `create_agent()` 增加 `model` / `model_factory` 注入点
- [x] 给 vendored `create_agent()` 增加 `tool_instances` 或等价注入点
- [x] 去掉 vendored runtime 对外部 `config.yaml` 的强依赖，改成显式参数或 PIAgent 默认配置
- [x] PIAgent 侧实现 `DBModelResolver`
- [x] 做一个最小 session-scoped spike tool（可用 dummy tool，最好直接用最小版 `add_node`）
- [x] 写 smoke test 或 dev script，证明 DB provider + session tool 可以一起工作
- [x] **验收**：PIAgent 侧 smoke test 能用 DB provider 驱动 `pi_harness/runtime` agent，并成功调用一个 session-scoped tool；过程中不依赖外部 `mini_harness` 包或其 `/runs/stream`

### M2 — 图构建工具与技能迁移（2–3 天）
**目标**：agent 在 PIAgent 侧能够产出合法 WorkflowGraph v2 draft。

- [x] 实现 `WorkflowGraphDraft`
- [x] 实现 `add_node` / `connect_nodes` / `patch_node_config` / `remove_node` / `remove_edge`
- [x] 搬 `list_*` / `validate_graph` 工具
- [x] 把现有技能迁移到 `pi_harness/skills/*/SKILL.md`
- [x] 对 `agent_node.md` 做保留/合并决策
- [x] 用现有 `validators.py` 和 harness 测例做 parity 检查
- [x] **验收**：PIAgent 侧 runner 输入“做一个读 PDF 然后总结的工作流”，agent 产出的 draft 能通过 `validators.py` 校验

### M3 — Session/SSE 契约 + 前端联调（2–2.5 天）
**目标**：前端画布和会话体验与当前版本等价。

- [x] 实现 `sse_bridge`，把 tool/LangGraph 事件映射到现有 harness event schema
- [x] 新路由 `/api/pi_harness/sessions`、`/events`、`/resume`、`/apply`、`/abort`（与旧路由并存）
- [x] clarification -> `awaiting_user_input` -> `resume` 全链路打通
- [x] 前端加 feature flag 切换 v1/v2 后端
- [x] **验收**：新 UI 流程跑通 `create -> graph_update 渐进渲染 -> ask clarification -> resume -> ready -> apply`，体验不差于旧版

### M4 — 持久化与刷新恢复（1–1.5 天）
**目标**：刷新、回看、续聊与当前行为一致。

- [x] `session_store.py`：LangGraph state + draft snapshot <-> `AgentSession.workspace_json`
- [x] 事件回放/展示继续复用 `events_json`
- [x] 关标签重开后的恢复路径打通
- [x] 补回归测试，覆盖 open question、ready 状态、applied 状态恢复
- [x] **验收**：关标签后重开，会话历史、当前 draft、open question、ready/applied 状态都能完整恢复

### M5 — 切换与清理（0.5–1 天）
**目标**：切流到新实现并删除旧壳代码。

- [x] `/api/harness` 路由切到 `pi_harness`
- [x] 前端 feature flag 去掉
- [x] 删除 `backend/harness/`
- [x] 跑 parity 测试和 E2E 冒烟
- [x] 更新 `CLAUDE.md` / 相关文档里的 harness 段落

**总预估**：7–10.5 人日。

---

## 5. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| vendored runtime 的最小裁剪做得不准，带入过多无关壳代码或裁掉关键能力 | 中 | 高 | M1 先只复制最小内核子集；明确保留/剔除清单；用 smoke test 锁定最小可运行面 |
| 全局单例 config/registry 带来跨 session 污染 | 中 | 高 | 明确绕过单例，所有有状态工具都走 session-scoped instances；补隔离测试 |
| 前端 SSE schema 对齐失败，画布渲染回归 | 中 | 高 | 事件格式保持 100% 兼容；M3 必做端到端链路验收；feature flag 回滚路径 |
| Finalize / Apply 语义漂移，导致 agent 未经用户确认直接落库 | 低 | 高 | `finalize_draft` 只标记 ready，不做 apply；把 `/apply` 保持为显式独立端点 |
| Agent 质量回归（“变笨”） | 中 | 高 | M2 阶段用现有 harness 测例和目标任务做对照；技能文档质量是关键，前两天专注调 prompt/skill |
| LangGraph 版本升级破坏行为 | 低 | 中 | pin 版本；CI 加冒烟测试 |
| LangGraph message state 过大，`workspace_json` 体积膨胀 | 中 | 中 | Phase 1 先可用优先；必要时启用 summarization 或在后续单独加 `state_json` 字段 |
| vendored runtime 与 mini-harness 上游演进脱节 | 中 | 低 | 在 `backend/pi_harness/runtime/` 标注来源与同步策略；只同步我们真正依赖的核心模块 |

---

## 6. 迁移期并存策略

- 新建 `backend/pi_harness/`，旧 `backend/harness/` 原样保留。
- API 层先加 `/api/pi_harness/*` 新路由；旧 `/api/harness/*` 不动。
- 前端 `harnessStore` 读 env flag 决定打哪个后端。
- **不直接 mount mini-harness 的 FastAPI app**，避免把其薄事件协议泄漏到产品层。
- 每个 milestone 的 PR 都独立可 merge，不阻塞主线开发。
- 最终切换（M5）是一个纯删除/切流 PR，心理负担最小。

---

## 7. 决策记录

- **为什么不直接在旧 harness 里补能力（loop detection 等）？**
  能补，但壳代码本身的设计问题（消息管理、工具分发的耦合）仍在。换壳是根因修复。
- **为什么不直接复用 mini-harness 的 `/runs/stream`？**
  因为它只提供 `message` / `clarification` / `done` 级别的薄协议，不覆盖 PIAgent 前端已经依赖的 `graph_update`、`awaiting_user_input`、`harness_ready`、`apply` 等产品语义。
- **为什么不整体改造 mini-harness 来承载所有 PIAgent API？**
  mini-harness 应保持通用 ReAct 壳定位。PIAgent 特异性的东西（图 draft、SSE、DB provider、session lifecycle）继续留在 PIAgent 侧更干净。
- **为什么不把 mini-harness 作为外部依赖直接接进来？**
  因为这会把 runtime 迁移和依赖升级绑在一起：当前 mini-harness 与 PIAgent 的 LangGraph/LangChain 版本不完全同代，且 PIAgent 运行环境里并未安装 `mini_harness`。把内核最小子集直接放进 `pi_harness/runtime/`，更容易在现有代码库内渐进适配和联调。
- **为什么 Phase 1 不把 `workspace_json` 改成独立 `state_json` 列？**
  因为这会把“替换 agent runtime”和“数据库 schema 迁移”绑在一起，风险放大。先保 schema 不动，把状态塞进现有 JSON blob，后续再单独优化。
- **为什么保留 `/apply` 独立端点，而不是让 agent 自己 finalize 后直接落库？**
  因为当前产品语义就是“先 ready，再由用户确认 apply”。这既给用户控制权，也让错误恢复和回滚更清晰。
- **为什么 skills 不放 mini-harness 仓库？**
  skills 是业务知识（“PIAgent 的 LLM 节点怎么配”），应跟业务代码走；mini-harness 的 skills loader 支持任意目录，天然解耦。

---

## 8. 下一步

等确认后从 **M1 Runtime Embedding Spike** 开始，优先做两件事：

1. 把 mini-harness 的最小 runtime 内核复制到 `backend/pi_harness/runtime/`。
2. 给 vendored `create_agent()` 增加 `model` / `tool_instances` 注入点。
3. 用一个最小 stateful tool 验证“DB provider + session-scoped draft + tool call”这条链路。

只要这两个点通过，后面的风险就从“架构是否成立”下降为“工程量和细节对齐”，项目就可以按 milestone 稳定推进。
