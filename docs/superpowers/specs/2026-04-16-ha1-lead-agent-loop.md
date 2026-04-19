# HA1: LeadAgent Multi-Step Decision Loop

> 状态：待实施
> 范围：把 LeadAgent 从单次规划升级为多步决策循环，让 Harness 具备 observation-driven 的持续调度能力
> 前置：`2026-04-16-agent-harness.md`（H0-H3 已落地），`2026-04-16-harness-agent.md`（目标态定义）
> 目标：HA1 完成后，Harness Path 下 LeadAgent 能根据前一步执行结果动态调整下一步行为

---

## 1. 背景与动机

当前 `LeadAgent.plan()` 是单次调用：一次 LLM call 返回全部 actions，Orchestrator 机械执行。LeadAgent 从不观察自己行为的结果。

这意味着：
- 模型无法根据 observation 调整策略
- "会调用 skill" 和 "会持续调度 skill" 不是一回事
- 系统更接近 "单次 planner" 而非 "agent loop"

HA1 的核心目标：引入 `decide → execute → observe → decide again` 的多步循环。

---

## 2. 架构决策

### 2.1 循环放在 Orchestrator，不放在 LeadAgent

LeadAgent 保持纯粹的 "给定上下文，返回一个决策" 函数。Orchestrator 拥有 emit、builder、sub-agents、memory，适合做循环调度。

好处：
- LeadAgent 保持单一职责，易测试
- Orchestrator 已有 emit 闭包、builder 实例、sub-agent 调度逻辑
- 现有 `LeadAgent.plan()` 完全不改，零回归风险

### 2.2 Feature Flag 控制

通过 `harness_loop_enabled` 开关控制。关闭时行为完全不变。仅在 `route == "harness"` 且 `agent_llm_enabled` 时生效。

### 2.3 兼容策略

- `LeadAgent.plan()` 保留不动，Fast Path 和旧 Harness Path 不受影响
- 新增 `LeadAgent.decide()` 方法，与 `plan()` 并存
- 现有 5 个 orchestrator 测试不修改

---

## 3. 新增 Schema 设计

### 3.1 LeadDecision — 单步决策

```python
class LeadDecision(BaseModel):
    reasoning: str           # 中文推理说明
    action: dict | None      # 一个 GraphAction dict（add_node/add_edge/commit_graph 等）
    skill: str | None        # 要调用的 skill 名称
    skill_input: dict | None # skill 参数
    done: bool = False       # True = 循环终止
```

约束：每次决策只能输出一个 action 或一个 skill 或 done=True，三选一。

### 3.2 DecisionObservation — 执行反馈

```python
class DecisionObservation(BaseModel):
    step_index: int
    action_taken: str         # "add_node", "draft_recipe", "commit_graph" 等
    success: bool
    error: str | None
    graph_snapshot: dict | None   # builder.snapshot() 输出
    skill_result_summary: str | None
```

### 3.3 LoopTraceEntry — trace 记录

```python
class LoopTraceEntry(BaseModel):
    step_index: int
    decision: LeadDecision
    observation: DecisionObservation
    timestamp: float
```

---

## 4. 核心循环设计

### 4.1 Orchestrator 主循环伪代码

```python
builder = GraphDraftBuilder(...)
history: list[DecisionObservation] = []
step = 0

while step < max_steps:
    emit(lead_step_start, step)
    snapshot = builder.snapshot()

    decision = lead_agent.decide(
        goal, capabilities=capabilities,
        graph_snapshot=snapshot, history=history,
    )
    emit(lead_decision, step, decision)

    if decision.done:
        emit(lead_step_end, step, done=True)
        break

    observation = _execute_decision(decision, builder, ...)
    emit(lead_observation, step, observation)
    history.append(observation)
    emit(lead_step_end, step, done=False)
    step += 1

# 超限保护：强制 commit
if step >= max_steps and not builder.draft.committed:
    force_commit(builder)
```

### 4.2 _execute_decision 分发逻辑

- `decision.action` → `coerce_graph_action()` → `builder.apply()` → emit 对应事件
- `decision.skill == "draft_recipe"` → `registry.recipe.invoke()` → 转 actions → apply to builder
- `decision.skill == "validate_graph"` → `registry.graph_validation.invoke()`
- `decision.action.kind == "commit_graph"` → 跑 sub-agents（GraphCritic 等）→ `builder.apply(CommitGraphAction())`
- 返回 `DecisionObservation`

### 4.3 Builder Snapshot（MVP）

```python
def snapshot(self) -> dict:
    return {
        "node_count": len(self.draft.nodes),
        "edge_count": len(self.draft.edges),
        "node_ids": list(self._node_index.keys()),
        "committed": self.draft.committed,
        "planning_notes": list(self.draft.planning_notes),
    }
```

---

## 5. SSE 新事件

| 事件类型 | 载荷 | 说明 |
|----------|------|------|
| `lead_step_start` | `{step: int}` | 每步 LLM 调用前 |
| `lead_decision` | `{step: int, decision: dict}` | LLM 返回决策后 |
| `lead_observation` | `{step: int, observation: dict}` | 执行决策后 |
| `lead_step_end` | `{step: int, done: bool}` | 记录完成后 |

---

## 6. Prompt 设计

### 6.1 系统提示（build_lead_decision_system_prompt）

与现有 `build_lead_agent_system_prompt` 类似，但关键区别：
- 指导 LLM 每次只返回一个下一步动作
- 解释它会收到的 observation 反馈格式
- 告知当 graph 已 committed 时应设置 `done: true`

### 6.2 用户提示（build_lead_decision_user_prompt）

输入：goal、route、capabilities_summary、memory_summary、graph_snapshot、history（前几步的 observations）

格式化为："这是你当前的位置，你的下一步是什么？"

---

## 7. 文件变更清单

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `backend/config.py` | 新增 2 行 | `harness_loop_enabled`, `harness_loop_max_steps` |
| `backend/harness/schemas.py` | 新增 3 个 class | `LeadDecision`, `DecisionObservation`, `LoopTraceEntry` |
| `backend/harness/builder.py` | 新增 1 个方法 | `GraphDraftBuilder.snapshot()` |
| `backend/harness/prompts.py` | 新增 2 个函数 | `build_lead_decision_system_prompt`, `build_lead_decision_user_prompt` |
| `backend/harness/lead_agent.py` | 新增 1 个方法 + 抽取 1 个函数 | `LeadAgent.decide()`, 模块级 `draft_to_actions()` |
| `backend/harness/context.py` | 新增 1 个字段 | `HarnessContext.loop_trace` |
| `backend/harness/orchestrator.py` | 新增 2 个方法 + 修改 1 个方法 | `_build_with_loop()`, `_execute_decision()`, 修改 `build()` 加分支 |
| `backend/harness/__init__.py` | 新增导出 | 导出新 schema |
| `backend/tests/test_harness_orchestrator.py` | 新增 5 个测试 | 见下方测试清单 |

---

## 8. 测试策略

### 8.1 新增测试

| 测试名 | 验证目标 |
|--------|----------|
| `test_loop_multi_step_chain` | FakeLoopLLMClient 返回 3 步决策（draft_recipe → commit → done），验证事件顺序 |
| `test_loop_budget_exceeded` | max_steps=2，LLM 不返回 done，验证超限后强制 commit |
| `test_loop_llm_failure_falls_back` | decide() 抛异常，验证回退到单次 plan() 路径 |
| `test_loop_disabled_uses_single_shot` | flag=False，验证行为与现有完全一致 |
| `test_loop_observation_drives_next_decision` | 验证第 N+1 步的 history 包含第 N 步的 observation |

### 8.2 回归测试

现有 5 个 orchestrator 测试不修改，全部必须继续通过。

### 8.3 FakeLoopLLMClient 设计

```python
class FakeLoopLLMClient:
    def __init__(self, decisions: list[LeadDecision], plan: LeadAgentPlan | None = None):
        self._decisions = iter(decisions)
        self._plan = plan

    def structured_invoke(self, *, schema, system_prompt, user_prompt, **kw):
        if schema is LeadDecision:
            return next(self._decisions)
        if schema is LeadAgentPlan and self._plan:
            return self._plan
        raise RuntimeError("no mock configured")
```

---

## 9. 风险与控制

| 风险 | 控制措施 |
|------|----------|
| LLM 延迟累积（每步 15s × 10 步 = 150s） | step budget 默认 10，多数场景 3-5 步完成 |
| Prompt 膨胀（history 增长） | DecisionObservation 只含 snapshot 摘要，不含完整 graph |
| draft_recipe 一次性产出完整图 | 可接受——loop 让 LLM 在 commit 前还能审视和调整 |
| 循环路径与旧路径行为不一致 | Feature flag 默认关闭，旧路径完全不动 |

---

## 10. 实施顺序

Step 1-6 互相独立，可并行。Step 7 依赖 1-6。Step 8-9 依赖 7。

推荐顺序：
1. config.py（2 行，零风险）
2. schemas.py（纯新增）
3. builder.py（纯新增）
4. prompts.py（纯新增）
5. lead_agent.py（纯新增 + 安全抽取）
6. context.py（纯新增）
7. orchestrator.py（核心改动，feature flag 保护）
8. __init__.py（导出）
9. 测试

---

## 11. 任务清单

- [ ] Step 1: `backend/config.py` — 加 `harness_loop_enabled` 和 `harness_loop_max_steps`
- [ ] Step 2: `backend/harness/schemas.py` — 加 `LeadDecision`、`DecisionObservation`、`LoopTraceEntry`
- [ ] Step 3: `backend/harness/builder.py` — 加 `GraphDraftBuilder.snapshot()`
- [ ] Step 4: `backend/harness/prompts.py` — 加 loop 专用 prompt 函数
- [ ] Step 5: `backend/harness/lead_agent.py` — 加 `decide()` 方法，抽取 `draft_to_actions()`
- [ ] Step 6: `backend/harness/context.py` — 加 `loop_trace` 字段
- [ ] Step 7: `backend/harness/orchestrator.py` — 加 `_build_with_loop()`、`_execute_decision()`，修改 `build()` 分支
- [ ] Step 8: `backend/harness/__init__.py` — 导出新 schema
- [ ] Step 9: 新增 5 个 loop 测试
- [ ] Step 10: 运行全量 harness 测试，确认旧测试 + 新测试全部通过
- [ ] Step 11: 运行全量后端测试回归
- [ ] Step 12: 前端构建验证（npm run build）

---

## 12. 验收标准

HA1 完成当且仅当：

1. `harness_loop_enabled=True` 时，Harness Path 走多步决策循环
2. 至少一个测试覆盖 3 步以上的 decision-observation 链路
3. 后一步 decision 能读取前一步 observation（history 传递正确）
4. step budget 超限时强制 commit
5. LLM 不可用时自动回退到单次 plan() 路径
6. `harness_loop_enabled=False` 时行为与当前完全一致
7. 现有 5 个 orchestrator 测试 + 全量 harness 测试全部通过
8. 前端构建不受影响
