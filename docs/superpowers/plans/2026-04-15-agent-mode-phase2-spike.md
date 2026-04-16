# 阶段设计：Agent Mode Phase 2 Spike（自由 Graph / 多分支 / Merge）

**日期**：2026-04-15  
**状态**：已完成  
**关联 spec**：[/Users/mac/Desktop/PIAgent/docs/superpowers/specs/2026-04-15-agent-mode.md](/Users/mac/Desktop/PIAgent/docs/superpowers/specs/2026-04-15-agent-mode.md:1)

---

## 1. 结论

当前代码基线已经可以稳定支持：

- `start -> llm -> end`
- `start -> rag -> llm -> end`
- `start -> llm -> tts -> end`
- `start -> rag -> llm -> tts -> end`

但还**不适合**直接升级到“自由生成任意 DAG”。真正的瓶颈不在模型能力，而在 runtime 的数据路由和节点语义边界还不够硬。

Phase 2 的推荐路线不是“放开 planner 自由画图”，而是先补三块 runtime 地基：

1. 节点间显式输入映射
2. 多分支结果 merge / select
3. `agent` 节点的真实工具契约

---

## 2. 现状评估

### 2.1 已具备的能力

- GraphCompiler 已能校验 DAG 基本合法性
- `end` 节点已经支持 `{{node_id.field}}` 引用
- `rag -> llm -> tts` 单链路在当前共享 state 模式下稳定
- Agent mode 已经收敛成 `RecipeIR -> adapter -> WorkflowGraph`

### 2.2 仍然缺失的能力

- 没有 per-edge input mapping，节点消费上游数据仍主要靠共享 state
- 没有 `AudioMerge` 或其他通用 merge 节点
- 没有多分支产物的仲裁规则（优先级、拼接、聚合、回退）
- `agent` 节点工具仍偏占位，不适合作为 planner 默认产物

---

## 3. 为什么现在不放开自由 Graph

如果现在让 planner 直接生成任意图，最容易爆炸的地方有四个：

### 3.1 分支数据不知道如何落到下游节点

当前 graph 虽然长得像 DAG，但运行时没有稳定的“某个 edge 把某个字段映射到下游哪个参数”协议。  
一旦进入多分支，planner 就会开始幻想“边上传值”这类 runtime 并不存在的语义。

### 3.2 Merge 节点不存在

多主持、多音轨、双脚本对比、检索结果融合，这些场景最终都需要 merge。  
没有 merge 节点，planner 生成分支图只会停在“看起来合理、实际上落不了地”的状态。

### 3.3 `agent` 节点还不够稳

`agent` 节点注册存在，但工具执行没有被收敛成严格契约。  
它适合未来 phase 的“显式启用高级模式”，不适合当前 phase 的自动生成默认路径。

### 3.4 Repair 成本会急剧上升

当前 repair 只修 `RecipeIR`，错误空间相对小。  
一旦直接修自由 graph，错误会同时来自 node vocabulary、字段映射、模板引用、provider 组合和图结构本身，失败面会陡增。

---

## 4. Phase 2 推荐前置项

### 4.1 P0：显式输入映射

目标：

- 节点 config 支持声明式输入来源
- edge 或 node config 能明确写出“字段从哪里来”

验收：

- 不依赖共享 `state["llm_output"]` 也能让 `tts` 指向指定文本字段
- `end` 以外的节点也能消费 `{{node.field}}` 风格引用，或等价映射协议

### 4.2 P0：Merge / Select 节点

目标：

- 至少补一个文本 merge 节点和一个音频 merge 节点
- 明确 merge 语义：拼接 / 取首个成功 / 结构化聚合

验收：

- 两个 llm 分支结果能汇入同一个下游节点
- 两个 tts 分支结果能稳定产出一个下游可消费结果

### 4.3 P1：AgentNode 工具契约

目标：

- 工具输入输出 schema 化
- 明确失败模式、超时、重试与副作用边界

验收：

- planner 可以在 feature flag 下安全地产出 `agent` 节点
- 至少有一条真实工具链不是 placeholder

---

## 5. 规划建议

推荐拆成两个后续阶段：

### Phase 2A

- 先补显式输入映射
- 再补文本 merge
- 允许 planner 生成“受限双分支文本图”

### Phase 2B

- 补音频 merge
- 补 `agent` 节点真实工具
- 再讨论更自由的 `GraphPlanIR`

这样做的好处是：每一步都能把 runtime 能力和 planner 词表保持一致，不会让 prompt 先于系统现实。

---

## 6. 最终建议

下一阶段不要直接把当前 `RecipeIR` 推翻。  
更稳的演进路径是：

1. 保留现有 `RecipeIR` 作为稳定路径
2. 在 feature flag 下新增 `GraphPlanIR`
3. 只对已经被 runtime 明确支持的 branch / merge 形态开放 planner 生成

也就是说，当前 phase 的“低熵 recipe + adapter”不是临时妥协，而是下一阶段继续演进的安全基座。
