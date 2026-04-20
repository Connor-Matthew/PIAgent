# PIAgent Harness v3 设计 Spec

> **创建日期：** 2026-04-20
> **状态：** 设计中（未实施）
> **作者：** 与用户联合设计
> **SUPERSEDES（本文取代以下 spec）：**
> - `2026-04-18-piagent-harness-v2.md`

---

## 一、背景与作废声明

### 1.1 为什么要 v3

v2 已经落地（`backend/harness/`，~1200 行），跑通了"LeadAgent + Workspace + Skills + 6 工具 + 单 LLM 调用决策"的最小骨架，但实跑发现稳定性和"显得智能"两条都没达预期：

| 现象 | 根因 |
|---|---|
| 模型经常输出错误形状的 Decision（`commit_graph`、`from`/`to`、`name`/`arguments`、`skill_name`…），需要 `_normalize_graph_action_payload` 兜底几十行 | 单次 `with_structured_output` + 5-kind discriminated union + temperature=0，模型只能瞎猜 schema；没有原生 `tool_use` |
| 模型每轮都"重头想一遍"，无法在多轮里追踪自己的计划 | `LeadAgent.decide()` 每轮重建 `[system, user]` 两条消息，**没有消息历史**；推理链全部丢失 |
| FactsLedger 只增不减，几十轮后 system+user prompt 膨胀到 30k+ token | `FactsLedger.render()` 把所有 tool_results / skills / errors / findings 全量 dump，没有压缩，没有 prompt cache |
| Skill 要消耗整整一轮 LLM 调用去 `LoadSkill`，再花一轮去用 | `LoadSkill` 是独立 Decision kind；本质上 skill 应该是工具的"前置条件"而不是平级动作 |
| 校验只在 `Finalize` 时跑一次；模型边建边错却没有反馈 | `validate_graph()` 只在 `_handle_finalize` 调用；中间过程没有"draft 校验" |
| StuckDetector 要么误报（hash 完全相同才算 stuck）要么误漏（语义重复但 hash 不同） | 规则太字面（hash 等价 / 5 步无变更），缺乏"是否朝目标推进"的语义判断 |
| 默认模型 `gpt-4o`，agent 规划能力一般 | `DEFAULT_LLM_MODEL_BY_TYPE` 是按 provider 类型选的，不是按"agentic planning"场景选的 |
| 无 HITL：模型自己决定 `Finalize`，用户在 apply 之前看不到中间 plan | `AskUser` 是模型主动行为，不是流程级强制断点 |

**一句话：v2 把 DeerFlow 的"主循环 + 工具 + skills"骨架搬过来了，但缺了 DeerFlow 真正让它"显得智能"的那部分——多角色 agent + 共享 state + 持续上下文 + HITL 节点。**

### 1.2 v3 的核心改动

1. **从"单 agent + Decision union"改为"状态机 + 多角色 agent"**：用 LangGraph `StateGraph` 定义 `coordinator → planner → architect → builder → reflector → finalizer` 的固定骨架，每个节点是一个专职 agent，职责单一、prompt 专精。
2. **从"每轮重建 prompt"改为"共享 HarnessState + per-agent message history"**：state 是一个 `TypedDict`，所有 agent 读写同一份 state；每个 agent 维护自己的对话历史（不和其他 agent 混），保留推理链。
3. **从"`with_structured_output` json_mode"改为"LangChain `bind_tools` + 统一 ToolCall"**：每个 agent 的输出形状变成"调用约定好的工具"（`emit_plan` / `emit_action` / `request_clarification` …）；底层走 LangChain 的 `ChatModel.bind_tools()` 抽象层，对 Anthropic 链路自动启用 native `tool_use`，对 OpenAI / Google / DeepSeek 走各自的 function calling，**所有 provider 输出统一的 `AIMessage.tool_calls` 结构**，agent 代码无需感知 provider 差异。
4. **引入 prompt caching（按 provider 条件启用）**：消息按"稳定→易变"分层组织（system → loaded skills → 早期 facts → 当前任务），这种结构对所有 provider 的缓存机制都友好——Anthropic 链路下额外注入 `cache_control: ephemeral` 断点显式打点；OpenAI / DeepSeek 自动前缀匹配；Gemini 显式 `cachedContent` 留 TODO（M1 不实现）；其他 provider 自然降级，**不影响功能**。
5. **引入 HITL 断点**：`human_approve_plan` 和 `human_approve_apply` 是 LangGraph 状态机的真节点（`interrupt_before`），与底层 LLM provider 完全解耦，**任何模型都生效**。
6. **校验下沉到 builder/reflector 每一步**：每次 `propose_action` 落到 draft 后立刻跑增量校验，把 findings 注入下一轮 reflector 的输入。
7. **默认模型由 provider 配置决定，保持模型可插拔**：`settings.harness_llm_provider_id` 指定默认 provider；推荐 agentic planning 场景使用 `claude-sonnet-4-6` / `gpt-4o` / `gemini-2.0-pro` 等强 tool calling 模型，但**不在代码里硬编码任何具体模型名**。

### 1.3 作废范围

| 路径 / 概念 | 处置 |
|---|---|
| `backend/harness/lead_agent.py` | 删除（被 `agents/*.py` 取代） |
| `backend/harness/prompts.py` | 拆分到每个 agent 文件内部，统一 prompt 组装走 `agents/_prompt.py` |
| `backend/harness/workspace.py` 的 `Workspace` / `Observation` / `StuckDetector` | 用 `state.py:HarnessState` + `context/manager.py` 取代 |
| `backend/harness/schemas.py` 的 `Decision` discriminated union 及 `normalize_decision_payload` 等兜底 | 删除；agent 输出形状由各自的 `tool_use` schema 强制 |
| `backend/harness/skills/` 目录 | 保留，仍是 markdown；加载方式从"`LoadSkill` decision 触发"改为"agent 启动时由 ContextManager 决定是否注入" |
| SSE 事件契约 | **保留 v2 的事件 shape**（`agent_status` / `graph_update` / `validation_result` / `clarification_request` / `finalize` / `error`），状态机内部新增的"agent 切换"事件复用 `agent_status`，对前端透明 |

**双轨期：** v3 实施期间 v2 继续在 master 工作。新代码写到 `backend/harness_v3/`；通过 `settings.harness_version` 路由（默认仍走 v2）。v3 跑通且回归测试通过后一次性 PR：删除 v2 目录、`harness_v3/` 重命名为 `harness/`、移除路由开关。

---

## 二、DeerFlow 内核映射（v3 视角）

| DeerFlow 能力 | v2 处理 | v3 处理 | 备注 |
|---|---|---|---|
| Coordinator + Planner + Researcher 多角色 | 单 LeadAgent 揽全部 | 拆 6 个角色 agent（coordinator/planner/architect/builder/reflector/finalizer） | 每个 agent prompt < 1k tokens |
| Plan-Execute-Reflect | 隐含在 Decision 循环里 | 显式状态机节点：planner → architect → builder → reflector | reflector 决定回 builder / 回 planner / 进 finalizer |
| HITL（plan_iterations / clarification） | 只有 `AskUser` 由模型主动触发 | `human_approve_plan` 和 `human_approve_apply` 为状态机断点 + coordinator 仍可主动 `clarify` | SSE 真暂停 |
| Context engineering（per-agent context） | 共享 FactsLedger，越积越多 | 共享 `HarnessState` 但每个 agent 只读自己关心的切片，并维护独立 message history | ContextManager 负责裁剪和缓存 |
| Tool calling | 否（json_mode） | 是（LangChain `bind_tools` 抽象，跨 Anthropic / OpenAI / Google / DeepSeek 输出统一 `AIMessage.tool_calls`） | 形状错误率显著下降，且与 provider 解耦 |
| Prompt caching | 否 | 是，按 provider 条件启用（Anthropic 注入 `cache_control: ephemeral` 断点；OpenAI/DeepSeek 自动前缀匹配；Gemini TODO；其他 provider 自然降级） | 重复轮次成本显著降低；不影响功能正确性 |
| Skills（按需 markdown） | 模型主动 `LoadSkill` decision | ContextManager 在进入 builder/architect 前自动注入相关 skill | 节省 1 整轮 LLM |
| Sub-agents 并行 | 不做 | 不做 | 工作流构图场景串行就够 |

---

## 三、设计原则

1. **状态机骨架固定，agent 智能可塑。** 流程的拓扑是工程决定（写在 `graph.py`），agent 的判断是 LLM 决定（写在 prompt + 工具 schema）。
2. **共享 state，专属上下文。** 所有 agent 读写同一个 `HarnessState`；但每个 agent 给 LLM 看的"消息历史 + 上下文切片"是独立的，互不污染。
3. **形状由 tool calling 强制，不由 prompt 哀求。** 任何"必须输出 JSON 满足某 schema"的需求都通过 LangChain `bind_tools` 实现（底层映射到各 provider 的原生 tool calling），统一消费 `AIMessage.tool_calls`，不用 `with_structured_output`，不用 prompt 里写"do NOT use xxx"。
4. **校验是循环里的事实，不是终点。** builder 每写一笔就跑增量校验，findings 进 state，reflector 看见、可以让 builder 修。
5. **HITL 是流程节点，不是 agent 行为。** 计划批准 / 应用批准是 LangGraph `interrupt`，与底层 LLM provider 完全解耦；AskUser-style 的"模型主动澄清"仍保留但限定在 coordinator 阶段。
6. **prompt cache 优先于 prompt 压缩，但不绑死任何 provider。** 消息按"稳定→易变"分层组织，对所有 provider 的缓存机制都友好；Anthropic 链路下额外注入显式 `cache_control` 断点，其他 provider 自然降级。能 cache 的不删；删要删的是真过时的 facts，由 ContextManager 在转入下一个 agent 时执行。
7. **模型可插拔。** 默认 provider 由 `settings.harness_llm_provider_id` 决定，代码不硬编码具体模型名；推荐使用 tool calling 能力强的模型（如 `claude-sonnet-4-6` / `gpt-4o` / `gemini-2.0-pro`）。

---

## 四、模块布局

```
backend/harness_v3/
├── __init__.py
├── graph.py                  # LangGraph StateGraph 定义（节点 + 边 + interrupt）
├── state.py                  # HarnessState TypedDict + reducer 工具
├── session.py                # HarnessSession（暴露给 API 层；驱动 graph.invoke / astream）
│
├── agents/
│   ├── __init__.py
│   ├── _base.py              # AgentBase：统一 LLM 调用 + tool_use + cache 注入
│   ├── _prompt.py            # 通用 prompt 模板片段（角色定义、common rules）
│   ├── coordinator.py        # 入口：理解 goal / 决定 clarify or plan
│   ├── planner.py            # 产出 Plan（节点列表 + 数据流意图）
│   ├── architect.py          # 把 Plan 转成 节点骨架 + 字段契约
│   ├── builder.py            # 一步一步 emit GraphAction；每步增量校验
│   ├── reflector.py          # 看校验结果 + 当前 draft，决定回 builder / 回 planner / 去 finalizer
│   └── finalizer.py          # 最终全量校验 + 生成给前端的总结
│
├── context/
│   ├── manager.py            # ContextManager：为每个 agent 切片 state + 注入 skill + 维护 cache breakpoints
│   └── memory.py             # 跨 session 的偏好读写（继续用 project_preferences 表）
│
├── llm/
│   ├── client.py             # 基于 LangChain bind_tools 的多 provider 统一封装
│   └── cache.py              # prompt cache 断点策略
│
├── tools/                    # tool_use schema 定义（每个 agent 用到的工具）
│   ├── plan_tools.py         # emit_plan / request_clarification
│   ├── action_tools.py       # add_node / add_edge / update_node_config / delete_*
│   ├── reflect_tools.py      # accept_draft / request_rebuild / request_replan
│   └── finalize_tools.py     # finalize_workflow / abort_with_reason
│
├── skills/                   # 复用 v2 的 markdown skill（io_contract / llm_basic / rag_qa / tts_podcast / simple_pipeline）
│
└── validators.py             # 复用 v2 validators（pure function，无 LLM）
```

**新增依赖：** `langgraph>=0.2`（仅用 `StateGraph` + `interrupt`，不用 LangChain 的 agent 抽象）。

---

## 五、状态机

### 5.1 节点 + 边

```
                            ┌────────────────────┐
                            │       START        │
                            └─────────┬──────────┘
                                      ▼
                           ┌────────────────────┐
                           │    coordinator     │  理解 goal、判断模糊度
                           └────────┬───────────┘
                       (clarify)    │    (proceed)
                          ┌─────────┴─────────┐
                          ▼                   ▼
                ┌──────────────────┐  ┌───────────────────┐
                │ clarify(ask_user)│  │      planner      │  产出 Plan
                └─────────┬────────┘  └─────────┬─────────┘
                          │ user_reply          │
                          └────────► coordinator│
                                                ▼
                                  ┌───────────────────────┐
                                  │  human_approve_plan   │  ← interrupt
                                  └─────────┬─────────────┘
                              (approved)    │   (revise)
                                  ┌─────────┴────────────┐
                                  ▼                      ▼
                           ┌────────────────┐    (back to planner with feedback)
                           │   architect    │  Plan → 节点骨架 + 字段契约
                           └────────┬───────┘
                                    ▼
                           ┌────────────────┐
                           │    builder     │  逐步 emit GraphAction + 增量校验
                           └────────┬───────┘
                                    ▼
                           ┌────────────────┐
                           │   reflector    │  看 draft + findings 决定下一步
                           └────────┬───────┘
                  ┌──────────────┬──┴──┬───────────────┐
                  │ rebuild      │     │ replan        │ finalize
                  ▼              │     ▼               ▼
              (back to builder)  │ (back to planner) ┌────────────────┐
                                 │   with feedback   │   finalizer    │
                                 │                   └────────┬───────┘
                                 │                            ▼
                                 │            ┌──────────────────────────┐
                                 │            │  human_approve_apply     │ ← interrupt
                                 │            └────────┬─────────────────┘
                                 │                     ▼
                                 │                 ┌───────┐
                                 └────────────────►│  END  │
                                                   └───────┘
```

### 5.2 LangGraph 伪代码

```python
# backend/harness_v3/graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from backend.harness_v3.state import HarnessState
from backend.harness_v3.agents import (
    coordinator, planner, architect, builder, reflector, finalizer,
)

def build_graph():
    g = StateGraph(HarnessState)

    g.add_node("coordinator", coordinator.run)
    g.add_node("clarify", coordinator.run_clarify)
    g.add_node("planner", planner.run)
    g.add_node("human_approve_plan", _hitl_plan)
    g.add_node("architect", architect.run)
    g.add_node("builder", builder.run)
    g.add_node("reflector", reflector.run)
    g.add_node("finalizer", finalizer.run)
    g.add_node("human_approve_apply", _hitl_apply)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        lambda s: "clarify" if s["coordinator_decision"] == "clarify" else "planner",
        {"clarify": "clarify", "planner": "planner"},
    )
    g.add_edge("clarify", "coordinator")          # 用户回复后回到 coordinator
    g.add_edge("planner", "human_approve_plan")
    g.add_conditional_edges(
        "human_approve_plan",
        lambda s: "architect" if s["plan_approved"] else "planner",
        {"architect": "architect", "planner": "planner"},
    )
    g.add_edge("architect", "builder")
    g.add_edge("builder", "reflector")
    g.add_conditional_edges(
        "reflector",
        lambda s: s["reflector_decision"],        # "rebuild" | "replan" | "finalize"
        {"rebuild": "builder", "replan": "planner", "finalize": "finalizer"},
    )
    g.add_edge("finalizer", "human_approve_apply")
    g.add_edge("human_approve_apply", END)

    return g.compile(
        interrupt_before=["human_approve_plan", "human_approve_apply"],
        checkpointer=...,  # 复用 SQLite session 持久化
    )

def _hitl_plan(state: HarnessState) -> dict:
    # interrupt() 让 SSE 暂停，前端展示 plan 并提交批准/修改
    payload = interrupt({"kind": "approve_plan", "plan": state["plan"]})
    return {"plan_approved": payload["approved"], "plan_feedback": payload.get("feedback", "")}

def _hitl_apply(state: HarnessState) -> dict:
    payload = interrupt({"kind": "approve_apply", "graph": state["draft_graph"], "summary": state["finalize_summary"]})
    return {"apply_approved": payload["approved"]}
```

### 5.3 终止条件

| 条件 | 触发节点 | 处理 |
|---|---|---|
| `state["budget_remaining"] <= 0` | 任何 agent 入口检查 | reflector 强制 `finalize`；finalizer 在 summary 标记"超预算，已尽力" |
| 同一 reflector 决定连续 3 轮 `rebuild` 且 findings 集合不变 | reflector | 强制改为 `replan`（带反馈给 planner） |
| planner 连续 2 轮被 `human_approve_plan` 拒绝且无新增澄清 | human_approve_plan 后路由 | 回到 coordinator，要求重新 clarify |
| 任何 agent 工具调用抛异常 | `_base.AgentBase` | 把 error 写进 `state["errors"]`，路由继续；**不退出**，由 reflector 看到错误后决定下一步 |

---

## 六、HarnessState 字段定义

`HarnessState` 是 LangGraph 节点之间唯一的共享数据结构。所有 agent 读写它，但**只读自己关心的切片**（详见第七节每个 agent 的 input slice）。

```python
# backend/harness_v3/state.py
from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from backend.harness_v3.schemas import (
    Plan, GraphDraft, Finding, AgentMessage,
)


class HarnessState(TypedDict):
    # ── 输入 / 元数据 ──
    session_id: str
    goal: str
    preferences: dict                      # 来自 project_preferences

    # ── coordinator 输出 ──
    coordinator_decision: NotRequired[Literal["clarify", "proceed"]]
    clarification_question: NotRequired[str | None]
    clarification_options: NotRequired[list[str] | None]
    user_reply: NotRequired[str | None]    # 由 API 层在恢复 interrupt 时写入

    # ── planner 输出 ──
    plan: NotRequired[Plan]                # see §6.2
    plan_iteration: int                    # planner 已被调用次数
    plan_feedback: NotRequired[str]        # human_approve_plan / reflector 的反馈
    plan_approved: NotRequired[bool]

    # ── architect 输出 ──
    skeleton: NotRequired[dict]            # 节点骨架（id/type/parent_scope）+ 字段契约（每个节点期望的 inputs/outputs）

    # ── builder / draft ──
    draft_graph: GraphDraft                # {nodes, edges}，每次 builder 完成一轮就更新
    last_actions: list[dict]               # builder 上一轮 emit 的 GraphAction 列表
    builder_iteration: int

    # ── 校验 ──
    findings: list[Finding]                # 增量校验产出；reflector 看
    findings_history: list[list[Finding]]  # 每一轮 builder 完成后的 findings 快照（用于"集合不变"判定）

    # ── reflector 输出 ──
    reflector_decision: NotRequired[Literal["rebuild", "replan", "finalize"]]
    reflector_reason: NotRequired[str]
    reflector_targeted_actions: NotRequired[list[str]]  # 给 builder 的 action_id hint（要修哪些）

    # ── finalizer 输出 ──
    finalize_summary: NotRequired[str]     # 给用户看的中文总结
    finalize_warnings: NotRequired[list[Finding]]
    apply_approved: NotRequired[bool]

    # ── 预算 ──
    budget_used: int
    budget_cap: int                        # 默认 30
    budget_remaining: int                  # = cap - used

    # ── 错误流 ──
    errors: list[dict]                     # {source, agent, message, ts}

    # ── 每个 agent 自己的消息历史（独立维护，互不污染）──
    coordinator_messages: Annotated[list[BaseMessage], add_messages]
    planner_messages: Annotated[list[BaseMessage], add_messages]
    architect_messages: Annotated[list[BaseMessage], add_messages]
    builder_messages: Annotated[list[BaseMessage], add_messages]
    reflector_messages: Annotated[list[BaseMessage], add_messages]
    finalizer_messages: Annotated[list[BaseMessage], add_messages]

    # ── 已加载 skill（由 ContextManager 决定，不是 agent 主动 LoadSkill）──
    loaded_skills: dict[str, str]          # skill_name → markdown content

    # ── SSE 输出缓冲（agent 内部 emit，由 session.py 转发）──
    sse_outbox: NotRequired[list[dict]]
```

### 6.2 关键子结构

```python
# backend/harness_v3/schemas.py
from pydantic import BaseModel, Field
from typing import Literal

class PlanStep(BaseModel):
    id: str                                # "s1", "s2"...
    intent: str                            # 自然语言：本步要达成什么
    node_kind: Literal["start", "llm", "rag", "tts", "agent", "end"]
    inputs_from: list[str]                 # 上游 step.id（不是节点 id，因为节点还没建）
    notes: str = ""

class Plan(BaseModel):
    summary: str                           # 一句话总览
    steps: list[PlanStep]
    open_questions: list[str] = []         # planner 仍想问但不阻塞流程的问题（写进 plan）
    estimated_complexity: Literal["trivial", "simple", "medium", "complex"]

class GraphDraft(BaseModel):
    nodes: list[dict]                      # 同 WorkflowGraph v2，但允许部分字段缺失
    edges: list[dict]

class Finding(BaseModel):                  # 复用 v2 validators 的 Finding
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = None

class AgentMessage(BaseModel):             # 给 SSE 用，不是 LLM message
    agent: str
    kind: Literal["thinking", "tool_call", "result", "decision"]
    payload: dict
```

---

## 七、各 Agent 详细规格

每个 agent 一个小节，包含：**职责 / 输入切片 / system prompt 大纲 / 可调用工具（tool_use schema） / 输出（写回 HarnessState 的字段） / 默认模型 / 失败处理**。

通用约定：

- **默认 provider 由 `settings.harness_llm_provider_id` 指定**，模型名取该 provider 的 `selected_models[0]`。代码不硬编码任何具体模型名。推荐使用 tool calling 能力强的模型（如 `claude-sonnet-4-6` / `gpt-4o` / `gemini-2.0-pro`）。
- **温度统一 0.2**（除 planner 设 0.4 鼓励多样性）。
- **所有 agent 通过 LangChain `bind_tools` 输出**，统一消费 `AIMessage.tool_calls`；不允许自由文本作为"决定"。每个 agent 至少绑定一个工具，模型必须发起一次 tool_call 才算完成本轮。底层 provider：Anthropic 走 native `tool_use`，OpenAI / DeepSeek / Google 走各自的 function calling，agent 代码无需感知差异。
- **prompt cache breakpoints**：消息按"稳定→易变"分层组织（system → loaded_skills → 早期 facts → 当前任务），对所有 provider 缓存机制都友好；Anthropic provider 下额外在 system prompt 末尾、loaded_skills 末尾、第一个稳定 facts 块末尾注入 3 个 `cache_control: ephemeral` 标记；其他 provider 自然降级，无需特殊处理。
- **每个 agent 内部都会在 system prompt 末尾追加一段"common safety rules"**：禁止虚构节点类型、禁止编造 provider id、引用上游字段必须用 `{{nodeId.field}}` 语法。

### 7.1 coordinator

**职责：** 理解 `goal`，判断是否需要先澄清；如果澄清，问一个最关键的问题；否则 `proceed` 让 planner 接手。也是 user_reply 回流的目的地。

**输入切片：**

```python
{
  "goal": state["goal"],
  "preferences": state["preferences"],
  "user_reply": state.get("user_reply"),
  "messages": state["coordinator_messages"],   # 累积的对话
}
```

**System prompt 大纲：**

```
You are the Coordinator of PIAgent harness. Your only job is to read the user's goal
and decide ONE of two actions:

1. clarify — when the goal is ambiguous on a dimension that materially changes the
   workflow shape (e.g. "is this RAG-grounded or open-ended LLM?", "single output
   or multi-modal?"). Ask exactly ONE question. Provide 2–4 options when applicable.

2. proceed — when the goal is concrete enough that a plan can be drafted. You may
   still leave residual ambiguity for the planner to handle.

Heuristic: if you can name the rough node sequence in your head, proceed. If you
cannot, clarify.

Never fabricate node types beyond: start, llm, rag, tts, agent, end.
Never ask more than one question per turn.
```

**可调用工具：**

```python
TOOLS = [
    {
        "name": "request_clarification",
        "description": "Ask the user one clarifying question before planning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "reason": {"type": "string", "description": "Why this question is needed."},
            },
            "required": ["question", "reason"],
        },
    },
    {
        "name": "proceed_to_planning",
        "description": "Goal is clear enough; proceed to the planner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One-line restatement of the goal in your own words."},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
        },
    },
]
```

**输出（state delta）：**

| 工具 | state 写入 |
|---|---|
| `request_clarification` | `coordinator_decision="clarify"`, `clarification_question`, `clarification_options` |
| `proceed_to_planning` | `coordinator_decision="proceed"`, `coordinator_messages.append(restated_goal)` |

**失败处理：** 若模型未发起任何 tool_call，记一条 error，重试一次（同一 message 历史 + 末尾追加 "You must call exactly one tool."）。第二次仍失败 → 默认 `proceed_to_planning(summary=goal)` 并写 warning。

---

### 7.2 planner

**职责：** 产出 `Plan`：高层步骤列表（不是节点 id，是"意图"），描述数据流。**不写节点字段、不写边的具体 source/target**——那是 architect 和 builder 的事。

**输入切片：**

```python
{
  "goal": state["goal"],
  "coordinator_summary": state["coordinator_messages"][-1].content,
  "plan_feedback": state.get("plan_feedback", ""),       # 来自 reflector 或 human_approve_plan
  "previous_plan": state.get("plan"),                    # 重新规划时存在
  "preferences": state["preferences"],
  "loaded_skills": state["loaded_skills"],               # ContextManager 已注入 io_contract / simple_pipeline
  "messages": state["planner_messages"],
}
```

**System prompt 大纲：**

```
You are the Planner of PIAgent harness. Produce a Plan that another agent
(Architect) can turn into a concrete graph. A Plan is a list of steps; each
step says what to do, what node kind to use, and which previous steps it
consumes.

You may use only these node kinds: start, llm, rag, tts, agent, end.
Every plan MUST start with a single `start` step and end with a single `end` step.

Keep plans minimal: 3–8 steps for "simple", 8–15 for "medium". If you find yourself
producing >15 steps, you are over-engineering — rethink.

If `plan_feedback` is present, treat it as ground truth and rebuild accordingly.
```

**可调用工具：**

```python
TOOLS = [
    {
        "name": "emit_plan",
        "description": "Submit a complete plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "estimated_complexity": {"enum": ["trivial", "simple", "medium", "complex"]},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "intent": {"type": "string"},
                            "node_kind": {"enum": ["start", "llm", "rag", "tts", "agent", "end"]},
                            "inputs_from": {"type": "array", "items": {"type": "string"}},
                            "notes": {"type": "string"},
                        },
                        "required": ["id", "intent", "node_kind", "inputs_from"],
                    },
                },
                "open_questions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "estimated_complexity", "steps"],
        },
    },
    {
        "name": "request_clarification",       # 极少触发；仅当 plan_feedback 暴露根本性误解
        "input_schema": { ... 同 coordinator ... },
    },
]
```

**输出（state delta）：** `plan`, `plan_iteration += 1`, `planner_messages.append(...)`。

**失败处理：** schema 由 tool_use 强制；若 step.id 重复或 inputs_from 引用了不存在的 step，agent base 自动反射回去再要求重写一次（最多 2 次）。

**默认温度：** 0.4。

---

### 7.3 architect

**职责：** 把 `Plan` 翻译成 `skeleton`：每个 plan step 对应一个具体的节点骨架（id、type、parent_scope=null、初步 config 占位），并推导**字段契约**——每个节点期望的 outputs 字段名 + 它们将被下游谁用 `{{...}}` 引用。

**输入切片：**

```python
{
  "plan": state["plan"],
  "loaded_skills": state["loaded_skills"],   # ContextManager 注入 io_contract.md
  "preferences": state["preferences"],
  "messages": state["architect_messages"],
}
```

**System prompt 大纲：**

```
You are the Architect of PIAgent harness. Translate the approved Plan into a
node skeleton: stable node ids, node types, and a field contract describing
which downstream nodes will reference which upstream outputs (using the
{{nodeId.fieldName}} template form).

Use these output fields per node type (DO NOT invent others):
  start  → fields declared in inputs[]
  llm    → text
  rag    → context, documents
  tts    → audio_url, duration
  agent  → text, steps

Node ids should be short and semantic ("ingest", "summarize", "tts1").
Do not write node configs (provider_id, model, prompt). That is Builder's job.
```

**可调用工具：**

```python
TOOLS = [
    {
        "name": "emit_skeleton",
        "input_schema": {
            "type": "object",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "type": {"enum": ["start", "llm", "rag", "tts", "agent", "end"]},
                            "from_plan_step": {"type": "string"},
                            "expected_outputs": {"type": "array", "items": {"type": "string"}},
                            "consumed_by": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "type", "from_plan_step"],
                    },
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                        },
                        "required": ["source", "target"],
                    },
                },
            },
            "required": ["nodes", "edges"],
        },
    },
]
```

**输出（state delta）：** `skeleton`, `architect_messages.append(...)`。**不**直接写 `draft_graph`——builder 才是图的唯一作者。

**失败处理：** 若 skeleton 节点数 ≠ plan steps 数，反射重写一次。

---

### 7.4 builder

**职责：** 按 skeleton 顺序，**逐节点**调用 GraphAction 工具，把节点和边写入 `draft_graph`；每写完一个节点就跑一次增量校验（仅校验当前 draft）。本节点的循环在 builder 内部进行，**不**回到 reflector，直到 skeleton 全部写完或某节点连续 2 次校验失败。

**输入切片：**

```python
{
  "plan": state["plan"],
  "skeleton": state["skeleton"],
  "draft_graph": state["draft_graph"],
  "loaded_skills": state["loaded_skills"],   # ContextManager 按 plan.steps 中出现的 node_kind 注入对应 skill
  "preferences": state["preferences"],
  "reflector_targeted_actions": state.get("reflector_targeted_actions"),  # 重建模式下的 hint
  "providers": <由 session 注入的可用 provider 摘要：[{id, type, category, models[]}]>,
  "messages": state["builder_messages"],
}
```

**System prompt 大纲：**

```
You are the Builder of PIAgent harness. Translate the Skeleton into a concrete
draft graph by emitting GraphAction tool calls one at a time.

Emit actions in this order:
  1. add_node for each skeleton node (start → ... → end)
  2. add_edge for each skeleton edge
  3. update_node_config for each node that needs runtime config
     (provider_id for llm/tts; inputs schema for start; outputs mapping for end)

When configuring an llm/tts node, pick a provider_id from the provided
`providers` list. If none match the required category, leave provider_id null
and the validator will flag it for the Reflector.

For end node outputs, ALWAYS use {{nodeId.fieldName}} double-brace template
referring to a node already in the draft.

After each tool call, the system will reply with the current findings. Use them
to decide your next action. If a finding says your last action was wrong,
correct it before continuing.

If you are in REBUILD mode (reflector_targeted_actions is set), focus on those
node ids only; do not touch unrelated parts of the graph.
```

**可调用工具：**

```python
TOOLS = [
    {"name": "add_node",       "input_schema": {... 同 v2 GraphAction.AddNode ...}},
    {"name": "add_edge",       "input_schema": {... source, target ...}},
    {"name": "update_node_config", "input_schema": {... node_id, config patch ...}},
    {"name": "delete_node",    "input_schema": {"node_id": {"type": "string"}}},
    {"name": "delete_edge",    "input_schema": {"source": ..., "target": ...}},
    {"name": "builder_done",   "description": "Mark this builder turn as complete; reflector will inspect.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]
```

**输出（state delta）：**

- `draft_graph`（每次工具调用后增量更新）
- `findings`（每次工具调用后由 `validators.validate_graph(draft_graph, db)` 重算并覆盖）
- `findings_history.append(findings)`（在 `builder_done` 时追加快照）
- `last_actions`（本轮所有工具调用的列表）
- `builder_iteration += 1`
- `builder_messages.append(...)`

**循环细节：** builder 内部就是一个"tool_use → tool_result（含最新 findings）→ 下一个 tool_use"的多轮对话，全部塞在同一次 `messages.create` 流式调用里（用 Anthropic 的 multi-turn tool_use loop）。每轮 token 用 `state["budget_used"] += 1`。

**失败处理：** 若同一个 action 被 emit 后 findings 数量增加且模型连续 2 次发同样的 action，强制 `builder_done` 退到 reflector。

---

### 7.5 reflector

**职责：** 看当前 `draft_graph` 和 `findings`，决定下一步走 `rebuild`（回 builder 修） / `replan`（回 planner 重做） / `finalize`（进 finalizer）。**不**自己改图。

**输入切片：**

```python
{
  "goal": state["goal"],
  "plan": state["plan"],
  "draft_graph": state["draft_graph"],
  "findings": state["findings"],
  "findings_history": state["findings_history"][-3:],  # 最近 3 轮，用于判断是否在打转
  "last_actions": state["last_actions"],
  "builder_iteration": state["builder_iteration"],
  "plan_iteration": state["plan_iteration"],
  "messages": state["reflector_messages"],
}
```

**System prompt 大纲：**

```
You are the Reflector of PIAgent harness. You read the current draft graph and
its validation findings, then decide ONE of three next steps:

- rebuild: the plan is sound but the graph has fixable issues. Identify the
  specific node ids that need rework and pass them to the Builder.

- replan: the plan itself is wrong (e.g. wrong node sequence, missing a stage).
  Provide concrete feedback the Planner can act on.

- finalize: the graph satisfies the goal AND has no error-severity findings.
  Warnings are acceptable as long as you can justify each.

Hard rules:
- If `findings_history` shows the same set of error codes for 3 builder turns,
  prefer replan over rebuild.
- If `plan_iteration` >= 3, prefer finalize (or rebuild) over replan.
- If `findings` contains any `error`-severity finding, do NOT finalize.
```

**可调用工具：**

```python
TOOLS = [
    {
        "name": "request_rebuild",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "target_node_ids": {"type": "array", "items": {"type": "string"}},
                "instructions": {"type": "string", "description": "Concrete fix the Builder should apply."},
            },
            "required": ["reason", "target_node_ids", "instructions"],
        },
    },
    {
        "name": "request_replan",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "feedback_to_planner": {"type": "string"},
            },
            "required": ["reason", "feedback_to_planner"],
        },
    },
    {
        "name": "accept_draft",
        "input_schema": {
            "type": "object",
            "properties": {
                "justification": {"type": "string", "description": "Why this draft satisfies the goal despite any warnings."},
            },
            "required": ["justification"],
        },
    },
]
```

**输出（state delta）：**

| 工具 | state 写入 |
|---|---|
| `request_rebuild` | `reflector_decision="rebuild"`, `reflector_targeted_actions`, `reflector_reason` |
| `request_replan` | `reflector_decision="replan"`, `plan_feedback=feedback_to_planner`, `reflector_reason` |
| `accept_draft` | `reflector_decision="finalize"`, `reflector_reason=justification` |

**失败处理：** 若决定 `accept_draft` 但 findings 含 error，agent base 拦截，自动改写为 `request_rebuild` 并把 error 列表作为 instructions。

---

### 7.6 finalizer

**职责：** 跑一次完整的 `validate_graph(draft_graph, db)`（含 provider 校验），若仍有 error 就把决定权推回 reflector（设 `reflector_decision=None` 让状态机重入）；否则产出给前端的中文总结、warning 列表、推荐的 workflow name，等待 `human_approve_apply`。

**输入切片：**

```python
{
  "goal": state["goal"],
  "plan": state["plan"],
  "draft_graph": state["draft_graph"],
  "messages": state["finalizer_messages"],
}
```

**System prompt 大纲：**

```
You are the Finalizer of PIAgent harness. The validator has already run and
returned no errors. Your job is to:

1. Write a 2–4 sentence Chinese summary describing what this workflow does,
   suitable for showing to a non-technical user above an "apply" button.
2. List any warnings the user should be aware of (verbatim from findings).
3. Suggest a short workflow name (Chinese, ≤ 12 chars).

Never invent capabilities the graph does not have.
```

**可调用工具：**

```python
TOOLS = [
    {
        "name": "finalize_workflow",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "suggested_name": {"type": "string"},
                "warnings": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["summary", "suggested_name"],
        },
    },
    {
        "name": "abort_with_reason",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]
```

**输出（state delta）：** `finalize_summary`, `finalize_warnings`, `finalizer_messages.append(...)`。

---

## 八、ContextManager 行为规约

`backend/harness_v3/context/manager.py` 在每个 agent 节点的入口被调用，负责：

1. **切片 state** 为该 agent 的 input dict（见每个 agent 的"输入切片"）。
2. **加载 skill**：根据当前 agent + plan/skeleton 内容，决定哪些 skill markdown 应该注入 `state["loaded_skills"]`。规则：
   - 进入 planner 前：若 `loaded_skills` 不含 `simple_pipeline.md` → 注入。
   - 进入 architect 前：必注入 `io_contract.md`。
   - 进入 builder 前：根据 `skeleton` 中出现的 node_kind 注入对应 skill（`llm` → `llm_basic.md`、`rag` → `rag_qa.md`、`tts` → `tts_podcast.md`），已加载的不重复。
3. **裁剪 message history**：每个 agent 自己的 `*_messages` 超过 20 条时，保留最近 10 条 + 第一条 + 摘要剩下的（用一个轻量 LLM 总结，可选；MVP 直接截取）。
4. **prompt cache 标记**：组装最终 messages 时，在 system prompt 末尾、loaded_skills 末尾、第一个 facts 块末尾分别打 `cache_control: {"type": "ephemeral"}`。

---

## 九、SSE 事件契约

**保留 v2 的事件 shape**，新增内容通过现有事件类型承载：

| 事件 | v2 触发 | v3 触发 |
|---|---|---|
| `agent_status` | `LeadAgent` 切阶段 | 每次 LangGraph 节点切换时发；`payload.agent` ∈ {coordinator, planner, architect, builder, reflector, finalizer, human_approve_plan, human_approve_apply} |
| `graph_update` | builder commit 后 | builder 每次 tool_call 写图后发增量 |
| `validation_result` | finalize 时 | 每次 builder 增量校验后发；finalizer 再发一次完整版 |
| `clarification_request` | `AskUser` decision | coordinator 的 `request_clarification` 工具触发 |
| `finalize` | `Finalize` decision | `human_approve_apply` interrupt 触发；payload 含 summary + warnings + suggested_name |
| `error` | 任何异常 | 同上；额外带 `agent` 字段 |

**新增建议事件**（非破坏性，前端可忽略）：

- `plan_proposed`：planner 完成后发；payload = `state["plan"]`。前端可在 plan 批准 UI 上展示。
- `reflection`：reflector 完成后发；payload = `{decision, reason, targeted_actions?}`。

---

## 十、LLM Client 与 Provider

`backend/harness_v3/llm/client.py`：

```python
class HarnessLLM:
    """Unified tool-calling client built on LangChain ChatModel.bind_tools().

    所有 provider 走同一条 `bind_tools` 抽象，输出统一为 `AIMessage.tool_calls`。
    Anthropic 链路下额外注入 `cache_control: ephemeral` 断点；其他 provider
    的缓存依赖各自机制（OpenAI/DeepSeek 自动前缀匹配；Gemini 待实现），
    不影响功能正确性。
    """

    def __init__(self, db: Session, *, default_provider_id: int | None = None):
        self.db = db
        self.default_provider_id = (
            default_provider_id or settings.harness_llm_provider_id
        )

    async def call(
        self,
        *,
        agent_name: str,                            # 仅用于日志 / 监控
        system: str,
        messages: list[BaseMessage],
        tools: list[BaseTool] | list[type[BaseModel]],   # LangChain Tool 或 Pydantic schema
        force_tool: str | None = None,
        cache_hints: list[CacheHint] | None = None,      # provider 无关的"建议缓存到此"标记
        temperature: float = 0.2,
        provider_id: int | None = None,
    ) -> AIMessage:
        provider = build_provider(self.db, provider_id or self.default_provider_id)
        chat_model = provider.create_chat_model(temperature=temperature)

        # 1. 统一通过 LangChain bind_tools 绑定工具；
        #    底层映射：Anthropic→native tool_use，OpenAI/DeepSeek→function calling，
        #    Google→function calling。所有 provider 输出 AIMessage.tool_calls。
        tool_choice = (
            {"type": "tool", "name": force_tool} if force_tool else "any"
        )
        bound = chat_model.bind_tools(tools, tool_choice=tool_choice)

        # 2. 按 provider 类型条件注入缓存提示（provider 无关的失败安全降级）。
        prepared_messages = _apply_cache_hints(
            provider.kind, system, messages, cache_hints or []
        )

        return await bound.ainvoke(prepared_messages)


def _apply_cache_hints(
    provider_kind: str,
    system: str,
    messages: list[BaseMessage],
    hints: list[CacheHint],
) -> list[BaseMessage]:
    """provider 条件注入缓存断点。

    - anthropic        → 在 hints 指定位置注入 `cache_control: {"type": "ephemeral"}`
    - openai/deepseek  → no-op（自动前缀匹配，stable→volatile 排序已经够）
    - google           → no-op（M1 不实现 cachedContent）
    - 其他             → no-op
    """
    sys_msg = SystemMessage(content=system)
    if provider_kind != "anthropic":
        return [sys_msg, *messages]

    # Anthropic 专属：把 hints 落到 message.additional_kwargs
    return _inject_anthropic_cache_breakpoints(sys_msg, messages, hints)
```

**调用方约定：** agent 代码只构造 `tools`（用 LangChain `BaseTool` 子类或 Pydantic schema）和"语义级" `CacheHint`（"system 末尾"、"loaded_skills 末尾"、"早期 facts 末尾"）。是否真的实现缓存、用什么语法实现——`HarnessLLM` 内部按 provider 决定。**agent 不感知 provider 差异**。

**默认 provider 选择：** `settings.harness_llm_provider_id` 指定全局默认 provider id（指向 `Provider` 表的一行）；调用时可通过 `provider_id=` 覆盖（如希望 reflector 用更强模型）。代码不硬编码任何具体模型名；模型名读取自 `provider.selected_models[0]`。

---

## 十一、持久化与恢复

复用现有 `AgentSession` 表（`backend/models/`），但 schema 增加列：

| 列 | 类型 | 说明 |
|---|---|---|
| `harness_version` | str | "v2" / "v3"，路由用 |
| `langgraph_checkpoint` | JSON | LangGraph SqliteSaver 写入；失败重启时直接 resume |
| `current_node` | str | 最近停在哪个 LangGraph 节点（用于前端展示） |

LangGraph `interrupt` 通过 checkpoint 自然支持暂停/恢复，HarnessSession 在 API 层只需 `graph.invoke(state, config={"configurable": {"thread_id": session_id}}, command=Command(resume=user_payload))`。

---

## 十二、实施计划

### M1：state + graph 骨架（1 天）
- `state.py` HarnessState 完整定义
- `graph.py` LangGraph 节点 + 边 + interrupt（agent 用 stub，只产 mock state）
- 单元测试：状态机能从 START 走到 END，所有路由分支可达

### M2：LLM client + tool calling 适配（1 天）
- `llm/client.py` 基于 LangChain `bind_tools` 的统一封装
- `_apply_cache_hints` 按 provider 条件注入（Anthropic 显式 `cache_control`；OpenAI/DeepSeek/Google 自然降级）
- 单元测试：每个 provider（Anthropic / OpenAI / DeepSeek）的 tool_call 调用都能拿到统一的 `AIMessage.tool_calls` 结构

### M3：6 个 agent（3 天，按依赖顺序）
- coordinator → planner → architect → builder → reflector → finalizer
- 每个 agent 一组单元测试：给定固定 input slice，断言 tool_call 形状和 state delta

### M4：ContextManager + skill 注入（0.5 天）
- 复用 v2 skill 文件
- 测试：进入各 agent 时 `loaded_skills` 包含预期内容

### M5：HarnessSession + API 接线（0.5 天）
- `session.py` 包装 `graph.astream`，转发 SSE
- API 层支持 `command=Command(resume=...)` 处理 HITL 答复
- 复用现有 `/api/harness/*` 路由，仅在 settings 里切 version

### M6：回归 + 切换（0.5 天）
- 跑现有 harness 集成测试，对齐事件契约
- 删除 v2 目录，重命名 `harness_v3/` → `harness/`

**总计：≈ 6.5 天**

---

## 十三、测试策略

### 13.1 单元测试

| 模块 | 覆盖点 |
|---|---|
| `state.py` | reducer（add_messages 合并）正确；snapshot/restore round-trip |
| `graph.py` | 所有 conditional_edges 的分支可达；interrupt 在正确节点触发 |
| 每个 agent | 给定输入切片，模型 tool_call 形状（用 mock LLM 固定返回）；state delta 字段命中 |
| `validators.py`（复用 v2） | 已有覆盖，无需重写 |
| `context/manager.py` | skill 注入规则；message history 裁剪 |

### 13.2 集成测试

| 场景 | 期望 |
|---|---|
| Goal: "给我一个简单 LLM workflow" | coordinator → planner（简单 plan）→ architect → builder → reflector(accept) → finalizer，无 HITL 修改 |
| Goal: "做一个能朗读 RAG 答案的助手" | planner 包含 rag + tts；reflector 至少 1 次 rebuild（修 template ref）|
| Goal: "做点 AI 的东西" | coordinator clarify 一次；用户回复后 proceed |
| Goal 中 RAG 但无可用 RAG provider | builder 留 provider_id null → finder 给 error → reflector rebuild 失败 → reflector 改判 finalize 报 warning（或 abort）|
| 跑到 builder 后 budget 耗尽 | reflector 强制 finalize；finalizer summary 标注"超预算" |

### 13.3 手测

- 同一 goal 跑 3 次，观察 plan 的稳定性（temperature=0.4 应有合理多样性，但节点 kind 序列稳定）
- `human_approve_plan` 中提交 "请改成不用 RAG"，验证 planner 真的去掉 rag step

---

## 十四、不做（明确拒绝）

| 想做但 v3 不做 | 原因 |
|---|---|
| Sub-agents 并行 | 工作流构图本质串行；并行只增复杂度 |
| 引入 LangChain agent 抽象（AgentExecutor 等） | LangGraph StateGraph 已足够；多一层抽象多一层调试地狱 |
| 用 embedding 做长期记忆 | 单用户单偏好，`project_preferences` 表已够 |
| MCP 集成 | 与 PIAgent 核心解耦；未来如需独立做 |
| 让模型自由生成 prompt 模板 | 节点 prompt 模板 = 业务约束，应该由产品而非 LLM 决定 |
| 把 validator 的 rule 写成 LLM 校验 | 校验是确定性问题，LLM 反而引入不确定 |

---

## 十五、ADR

### ADR-001: 引入 LangGraph 而非自己写状态机

**Status:** Accepted

**Context:** v2 自己用一个 `while True` 跑 LeadAgent 循环。v3 需要 6 节点 + interrupt + checkpoint，自己写要重新实现一套。

**Decision:** 引入 `langgraph>=0.2`，仅使用 `StateGraph` + `interrupt` + `SqliteSaver`，不引入 LangChain agent。

**Consequences:**
- ✅ interrupt / checkpoint / 状态可视化白嫖
- ✅ 节点切换 / 路由测试容易
- ❌ 多一个 ~3MB 依赖
- ❌ LangGraph 版本升级有破坏性变更风险（用 `>=0.2,<0.3` 锁住）

### ADR-002: 用 LangChain `bind_tools` 替代 `with_structured_output`

**Status:** Accepted

**Context:** v2 的 `with_structured_output(json_mode)` + 5-kind union 错误率 ~30%，需要 `_normalize_*` 几十行兜底；同时项目要求保持多模型可插拔，不能绑死任一 provider。

**Decision:** 所有 agent 通过 LangChain `ChatModel.bind_tools(tools, tool_choice=...)` 统一绑定工具，消费 `AIMessage.tool_calls`。底层映射：Anthropic → native `tool_use`；OpenAI / DeepSeek / openai_compatible → function calling；Google → function calling。LangChain 抽象层负责把不同 provider 的原生输出归一为 `tool_calls`。

**Consequences:**
- ✅ 形状错误率显著下降（强 tool calling 模型接近 100%）
- ✅ 无需在 prompt 里写"do NOT use xxx" 反向指令
- ✅ **多 provider 同一份 agent 代码**，新增 provider 不改 agent
- ✅ Pydantic schema 复用：tool 定义一次即可同时用于运行时校验和 LLM 形状约束
- ❌ 依赖 LangChain 版本演进；`bind_tools` API 在 0.2 系列稳定，但需锁版本
- ❌ 个别 provider 的 tool calling 能力弱（如部分本地模型），需要在 prompt 里加"必须 call 一个 tool"作为兜底

### ADR-003: HITL 作为状态机节点而非 agent 行为

**Status:** Accepted

**Context:** v2 的 `AskUser` 是模型主动行为，模型可能永远不问。

**Decision:** plan 批准和 apply 批准是 LangGraph `interrupt`，强制暂停。可在 settings 中 `auto_approve_plan=True` 关掉 plan 批准（但 apply 批准永不可关）。

**Consequences:**
- ✅ 用户始终能在关键决策点介入
- ❌ 简单工作流也要点一次"批准"，体验稍重；通过默认 `auto_approve_plan=True` 缓解

---

## 十六、附录

### 16.1 术语表

| 术语 | 定义 |
|---|---|
| HarnessState | LangGraph 节点共享的 TypedDict |
| input slice | 某 agent 从 HarnessState 中实际读取的字段子集 |
| state delta | 某 agent 写回 HarnessState 的字段子集 |
| skeleton | architect 产物：节点骨架（无 config 细节）+ 字段契约 |
| draft_graph | builder 维护的工作流 JSON（增量演化）|
| finding | 校验产物：`{severity, code, message, node_id?}` |
| HITL | Human-in-the-loop，本文中特指 `human_approve_plan` / `human_approve_apply` |
| tool calling | LLM 输出"调用工具"形式的结构化决定。LangChain `bind_tools` 抽象到所有主流 provider：Anthropic 走 native `tool_use`，OpenAI/DeepSeek/Google 走 function calling，统一消费 `AIMessage.tool_calls`。 |
| breakpoint | prompt cache 的语义截断点。在 Anthropic 链路下落地为 `cache_control: ephemeral`；其他 provider 自然降级（无显式语法，依赖前缀匹配或不缓存）。 |

### 16.2 与 v2 字段映射

| v2 概念 | v3 对应 |
|---|---|
| `Workspace.goal` | `HarnessState["goal"]` |
| `Workspace.facts` (FactsLedger) | 拆分到 `loaded_skills`、`findings`、`errors`、各 agent message history |
| `Workspace.trace` | LangGraph checkpoint 自带 |
| `Workspace.budget` | `budget_used` / `budget_cap` / `budget_remaining` |
| `Workspace.graph_draft` | `draft_graph` |
| `Workspace.open_question` | `clarification_question` + `user_reply` |
| `Decision.kind = "call_tool"` | builder 的 GraphAction tools |
| `Decision.kind = "load_skill"` | 不存在（由 ContextManager 自动注入）|
| `Decision.kind = "propose_action"` | builder 的 GraphAction tools |
| `Decision.kind = "ask_user"` | coordinator 的 `request_clarification` |
| `Decision.kind = "finalize"` | reflector 的 `accept_draft` → finalizer |
| `StuckDetector` | 状态机内部的循环计数 + reflector 规则（见 §5.3）|
