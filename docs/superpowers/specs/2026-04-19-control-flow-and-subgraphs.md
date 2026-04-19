# 控制流节点与嵌套子图 设计 Spec

> **创建日期：** 2026-04-19
> **状态：** 设计中（未实施）· **v0.3 修订 2026-04-19**（见 §附录 B）
> **作者：** 与用户联合设计
> **灵感来源：** 借鉴 iFLYTEK astron-agent 的 `IterationNode` / `IFElseNode` 与变量池设计，但用 PIAgent 现有的 LangGraph + `WorkflowState` 架构重新落地。

---

## 一、背景与目标

### 1.1 为什么要做

当前 PIAgent 工作流只能执行"一条直线"：`GraphCompiler.topological_sort` 返回单一顺序，`ExecutionEngine.run` 顺序 `for node in order` 调用 `node.execute(state)`（见 [backend/core/compiler.py:125-154](backend/core/compiler.py) 与 [backend/core/engine.py](backend/core/engine.py)）。这意味着：

- 无法表达"根据 LLM 输出走不同分支"
- 无法表达"对一批输入并行跑同一段子流程"
- 所有节点必须挂在同一层级，复杂工作流视觉上是一团面条

业界对照（astron-agent 的 [`engine/nodes/iteration/`](https://github.com/iflytek/astron-agent) 与 [`engine/nodes/if_else/`](https://github.com/iflytek/astron-agent)）已经把这两类节点做成标配。PIAgent 作为作品集项目，缺这两个意味着"只会拓扑排序"，补上之后才算一个可讲故事的工作流引擎。

本 spec 是后续 OTLP tracing（#1）和节点分组 UX（#3）的前置：

- **tracing** 需要有嵌套结构才有 span 父子关系可画
- **分组** 的 parent/child 关系在本 spec 中就已落地，#3 只是复用同一机制做"无执行语义的 Group 节点"

### 1.2 目标（本 spec 覆盖）

1. 新增两个控制流节点：**If-Else**（多分支）和 **Iteration**（批处理循环，支持并发与错误策略）
2. 在工作流数据模型上增加 `parentId` 字段，支持**嵌套子图**（iteration body 与 if-else 分支体都作为子节点挂在父下面）
3. 重写 `GraphCompiler` 与 `ExecutionEngine` 使之理解嵌套子图、条件路由、并发 fan-out
4. 扩展 SSE 事件协议，新增分支决策与迭代项事件
5. 前端 React Flow 用 `parentNode` + `extent: 'parent'` 渲染嵌套；节点配置面板为控制流节点做专属 UI

### 1.3 非目标（本 spec 不做，留给后续）

- **OTLP tracing**：单独成 spec（#1），本 spec 只保证事件协议能承载 trace_id
- **节点分组 UX**（无执行语义的 Group）：本 spec 建立 `parentId` 机制，后续 spec 复用
- **子工作流引用**（astron 的 Flow 节点，把另一个 workflow 当作节点）：暂缓
- **条件 DSL 全家桶**：本 spec 只做最小可用的操作符集合（见 §3.1），astron 那套 26 操作符是过度设计
- **深度大于 2 的嵌套**：第一版只支持 iteration 里嵌 if-else、if-else 里嵌 if-else；iteration 里嵌 iteration 在编译器上允许，但 UX 上不鼓励
- **harness 自动生成控制流**：harness v2 暂不需要会搓 iteration/if-else，人手搭即可

### 1.4 设计哲学

- **扁平存储 + parentId 关联**：所有节点仍在顶层 `nodes[]`，用 `parentId` 表达层级。不引入嵌套 JSON。理由见 §2.1。
- **子图是"节点的私有属性"**：Iteration / If-Else 节点在语义上"拥有"一组子节点，外部节点不能直接连到子节点上（编译器强制）
- **状态隔离最小化**：不做深度命名空间，子节点在执行时能看到父上下文与兄弟节点输出。**引用语法第一版保持扁平**：作用域内用 `{{nodeId.field}}`（iteration body 内的兄弟节点互引用、或从 body 内引用外部节点都走这一条），iteration 额外注入 `{{item}}` / `{{index}}`。不引入任何三段式语法。

---

## 二、数据模型

### 2.1 Node JSON 扩展

当前 node shape（见 [frontend/src/types/workflow.ts:32-46](frontend/src/types/workflow.ts)）：

```ts
{ id: string; type: string; position?: {x,y}; data: Record<string, unknown> }
```

**后端持久化 graph JSON 新增一个可选字段**：

```ts
{
  id: string
  type: string
  position?: { x: number; y: number }
  data: Record<string, unknown>

  // 新增
  parentId?: string         // 指向 iteration / if_else / group 节点 id
}
```

`extent: 'parent'` 是 React Flow UI 节点字段，不进入后端持久化 graph JSON。前端加载时根据 `parentId` 重新推导 `parentNode` 与 `extent`（见 §7.2）。

> **graph JSON 扁平约定**：前端 [workflowStore.ts:303-322](frontend/src/stores/workflowStore.ts) 的 `toGraphJSON()` 会把 `node.data.config` 的字段**展平**进 `data`。本 spec 所有后端字段（`parentId`、`branchId`、`inputRef`、`itemVar` 等）都直接写在 `data` 顶层，不放 `data.config.*`。前端内部仍保留 `data.config` 结构做 UI 绑定，只在序列化时展平——这个映射约定不变。

**为什么选扁平 + parentId 而不是嵌套 JSON**：

| 维度 | 扁平 + parentId | 嵌套 JSON |
|---|---|---|
| React Flow 渲染 | 原生支持（`parentNode` prop） | 需要把嵌套结构拍平才能渲染 |
| 序列化/DB | 无 schema 变化，`graph_json` 照旧 | 需要递归序列化/反序列化 |
| 深层嵌套 | 线性扫一遍 `nodes[]` 就能处理 | 递归，栈深度风险 |
| 编译器改动 | 按 parentId 分组即可 | 递归下降 |
| harness 差量更新 | 现有 `add_node(parent_id=...)` 模式兼容 | 需要路径定位 |

扁平方案全面胜出。astron 的 dsl_engine 看似嵌套，底层存储也是扁平（iteration 节点的 body 字段只是逻辑视图，节点本身在全局 node 表里）。

### 2.2 Edge 扩展

Edge shape 不变（仍只有 source/target）。**`sourceHandle` 只作为前端可视元数据**，不参与后端执行路由：

```ts
{
  id?: string
  source: string
  target: string
  sourceHandle?: string   // 仅前端 UI 提示；后端读取时忽略
}
```

**执行路由的唯一真理是"子图关系"**：if-else 内部的执行由 engine 根据 `parentId` + `branchId` 自己决定；if-else 节点从整体上看就是一个"黑盒"，后续节点通过从 if-else 节点出发的**一条普通 edge** 继续执行。这样避免了"出边路由 vs 子图路由"两套语义并存。

Iteration 同理：body 通过 `parentId` 关联；外部只有一条进边指向 iteration、一条出边从 iteration 出来。

### 2.3 新节点类型

```ts
type NodeType =
  | 'start' | 'llm' | 'rag' | 'agent' | 'tts' | 'end'
  | 'if_else' | 'iteration'      // 新增
```

#### If-Else 节点 config

```ts
{
  branches: [
    { id: 'true',  label: '是', condition: ConditionExpr, outputField?: string }
    { id: 'false', label: '否', condition: null,         outputField?: string }  // else
  ]
}

// outputField 格式："nodeId.fieldName"，必须指向该分支内的直接子节点。
// 分支执行完后，engine 解析 outputField 把结果写入 node_outputs[<if_else_id>].result。
// 若分支未声明 outputField 或分支内无节点，result 为 null。

type ConditionExpr = {
  left: string        // 模板引用，如 "{{llm_1.text}}"
  op: 'eq' | 'ne' | 'contains' | 'not_contains' | 'gt' | 'lt' | 'is_empty' | 'is_not_empty'
  right: string       // 字面量或模板引用；op=is_empty/is_not_empty 时忽略
}
```

**最小操作符集**（8 个）。条件语义见 §3.1。第一版不支持 AND/OR 组合；嵌套 if-else 就够了。

**分支 → 子节点的归属**：子节点通过 `parentId = <if_else_id>` + `branchId` 字段指定所属分支（**不走 edge 的 sourceHandle**）：

```ts
// 后端看到的 graph JSON（扁平）
data: { branchId: 'true' | 'false' }   // 只当 parentId 指向 if_else 时有效
// 前端内部（UI 绑定）对应 node.data.config.branchId，序列化时展平
```

#### Iteration 节点 config

```ts
{
  inputRef: string            // 模板引用，必须解析为 array，如 "{{start.items}}"
  itemVar: string             // body 内部可引用的"当前项"变量名，默认 "item"
  indexVar: string            // body 内部可引用的"当前索引"变量名，默认 "index"
  maxConcurrency: number      // 1 = 串行；>1 = 并发（默认 5）
  errorStrategy: 'fail_fast' | 'continue' | 'ignore_error_output'
  outputField: string         // body 里哪个节点的输出作为每次迭代的结果，格式 "nodeId.fieldName"
}
```

**输出**：`node_outputs[<iteration_id>] = { results: [...], errors: [...] }`。`results` 是每次迭代 `outputField` 解析出来的值组成的数组，保持输入顺序（即使并发也按 index 归位）。

---

## 三、执行语义

### 3.1 If-Else 求值

1. 解析 `left` 和 `right`（见下方"typed reference 规则"）
2. 按 `op` 比较，返回 bool
3. 选中第一个条件为 true 的 branch（按 branches 数组顺序），没有匹配则走 `condition: null` 的 else 分支
4. 把选中分支的所有子节点（`parentId == if_else_id && data.branchId == selected_branch`）按子图拓扑顺序执行
5. 未选中分支的子节点**完全跳过**（不发 node_start / node_end），其 `node_outputs` 保持未设置
6. 分支执行完后，根据选中分支的 `outputField`（形如 `childId.field`）从 `node_outputs` 取值，连同 `branchTaken` 一起作为 if-else 节点自身的输出：`node_outputs[<if_else_id>] = { branchTaken: 'true'|'false', result: any }`。外部节点后续通过 `{{<if_else_id>.result}}` 引用选中分支的输出，**无需也不允许**穿透到分支内部节点。

**typed reference 规则**：

- 如果 `left` / `right` 是完整模板引用（例如 `{{start.items}}`、`{{llm_1.text}}`），engine 使用 `resolve_reference`，保留原始类型（list、dict、number、string）。
- 如果是混合文本模板（例如 `Score: {{node.score}}`），才使用 `render_template`，结果视为 string。
- `eq` / `ne` 使用 Python 等值比较；`contains` / `not_contains` 对 string/list/dict key 生效；`gt` / `lt` 尝试把两边转换为 float，转换失败则条件求值失败并抛错；`is_empty` / `is_not_empty` 对 `None`、空字符串、空 list/dict 判空。

**边界情况**：

- 没有子节点的分支：if-else 直接走下一个外部节点，不报错
- 条件求值失败（如引用不存在的节点）：抛异常，整个工作流失败（未来可按 errorStrategy 处理）

### 3.2 Iteration 执行

1. 解析 `inputRef`，得到 `items: list`。`inputRef` 必须是完整模板引用（例如 `{{start.items}}`），engine 使用 `resolve_reference` 保留原始类型；如果解析失败或结果不是 array/list，抛错。第一版不支持把混合文本模板解析成数组。
2. 找出所有 `parentId == iteration_id` 的子节点，在"子图视图"下做一次拓扑排序（body 的子 DAG）
3. 根据 `maxConcurrency`：
   - `= 1`：`for i, item in enumerate(items)`，串行执行 body
   - `> 1`：`asyncio.Semaphore(maxConcurrency)` 控制并发，`asyncio.gather` 跑
4. 每次迭代有独立的 `node_outputs` 分区（scope 见 §3.3），迭代结束把 `outputField` 指定的字段收集到 `results[i]`
5. 错误策略：
   - `fail_fast`：第一个 item 失败即取消其他并发任务，整个 iteration 节点失败
   - `continue`：失败 item 在 `errors` 里记 `{index, error}`，`results[i] = None`
   - `ignore_error_output`：同 continue，但不记 errors

### 3.3 变量作用域

**核心规则**：迭代体内部的子节点看到的 `WorkflowState` 是父 state 的**浅拷贝 + 额外注入**：

```python
child_state = {
  "inputs": parent_state["inputs"],                    # 只读共享
  "node_outputs": { **parent_state["node_outputs"] },  # 浅拷贝；子节点写入不污染父
  "input": items[i],                                   # ← 关键：覆盖 LLM 节点读取的 state["input"]
  "_iter_context": {                                   # iteration 专属
      "item": items[i],
      "index": i,
      "itemVar": "item",
      "indexVar": "index",
  },
}
```

> **为什么要 override `state["input"]`**：当前 [llm_node.py:51](backend/nodes/llm_node.py) 等节点直接读 `state["input"]`，**不会渲染 config 里的模板**。如果只注入 `_iter_context` 而不改 `input`，iteration body 里的 LLM 拿不到当前 item。第一版选"override input"这个最小改动——每次迭代 `child_state["input"] = items[i]`（如果 item 是 dict，转 JSON 字符串或 repr；字符串/数字直接赋值）。未来如果做通用的"节点输入绑定"（让用户在 LLM config 里写 `prompt: "{{item.text}}"` 并被渲染），再扩能力。

**模板解析扩展**（[template.py](backend/core/template.py)）——当前 `resolve_reference` 遇到 `{{item.foo}}` 会当作 `node_outputs["item"]["foo"]` 去查，这必然失败。需要改成：

1. **先检查 `_iter_context`**：如果 `part1` 等于 `_iter_context["itemVar"]` 或 `_iter_context["indexVar"]`，从 `_iter_context` 取值；如果有 `part2`，对 dict/list item 做 key/index 访问（字符串 key 走 `dict[key]`，纯数字字符串走 `list[int]`）。
2. **再走现有路径**：`{{nodeId.field}}` 查 node_outputs；`{{varName}}` 查 local_vars / inputs。

这意味着 REF_RE 正则不变（仍是 `nodeId` + 可选 `.field`），但 `resolve_reference` 的查找顺序第一步插入 `_iter_context` 分支。

**子节点之间引用**：iteration body 内的节点 `llm_A` 和 `llm_B`，`llm_B` 可以引用 `{{llm_A.text}}`（因为浅拷贝的 `node_outputs` 在本次迭代内是共享的）。

**跨作用域引用**（body 内引用外部节点）：允许，因为 `node_outputs` 从父拷贝来，外部节点的输出天然可见。

**外部节点引用 body 内部节点**：**禁止**。编译器验证：只有 iteration 节点本身可以被外部引用，其子节点不能。

If-Else 的子节点不需要 `_iter_context`，但也走同样的浅拷贝机制，确保未执行分支不污染状态。

### 3.4 模板引用语法（第一版收口）

**正则保持不变**（[backend/core/template.py:6](backend/core/template.py)）：`\{\{\s*([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?\s*\}\}`

**作用域内可用的引用形式**（穷举）：

| 形式 | 语义 | 解析来源 |
|---|---|---|
| `{{nodeId.field}}` | 引用同作用域内节点输出 | `state["node_outputs"][nodeId][field]`（iteration body 内可引用 body 内节点 + 外部节点，因为浅拷贝） |
| `{{nodeId}}` | 引用输入变量或 End 自身 var | 现有 local_vars → inputs 逻辑 |
| `{{item}}` / `{{index}}` | iteration 当前迭代项 / 索引 | 新增：`_iter_context` |
| `{{item.key}}` | iteration item 是 dict/list 时的字段访问 | 新增：`_iter_context` + dict/list 访问 |

**不支持**（已决策，本 spec 不做）：

- 三段式 `{{parentId.childId.field}}` —— 外部节点要拿 if-else/iteration 的结果，通过父节点自身输出（`{{if_id.result}}` / `{{iter_id.results}}`）
- AND/OR 条件组合
- 跨 iteration 边界的精确下标引用（`{{iter_1[2].llm_x.text}}`）

---

## 四、编译器改造

[backend/core/compiler.py](backend/core/compiler.py) 是改动核心。

### 4.1 验证规则增量

在现有 `validate()` 基础上添加**两档**规则——结构性规则 M1 就上（跟节点类型无关）；语义性规则等相关节点类型注册后再上。

**结构性（M1 生效）**：

1. **parentId 存在性**：`parentId` 必须指向同一 `nodes[]` 中的节点
2. **跨层级 edge 限制**：edge 的 source 与 target 要么都在同一 parentId 层级（包括都在顶层），要么 source 是外部节点且 target 是 parent 节点（进入容器），要么 source 是 parent 节点且 target 是外部节点（从容器出来）。**不允许外部节点直接连到子节点，也不允许子节点直接连到外部节点。**
3. **子图无循环**：每个 parent 的子节点集合内部做一次 Kahn 判环
4. **子图连通性**：每个 parent 的子节点集合内至少要有一个"入口"（无内部入边的节点）
5. **exactly-one start/end**：保持现状（start/end 不能有 parentId）

**语义性（随节点类型注册启用）**：

6. **parent 类型合法性**（M2 起）：parent 必须是**已注册的"容器类"节点类型**（M2 加 `if_else`；M3 加 `iteration`；M5 加 `group`）。实现上给 `NodeRegistry` 加 `is_container(node_type) -> bool` 标志，validate 用它判断而不是硬编码名单。
7. **分支标签合法性**（M2 起）：parent 是 if_else 时，子节点 `data.branchId` 必须是 parent 声明的某个 branch.id
8. **iteration outputField 合法性**（M3 起）：`outputField` 形如 `childId.field`，childId 必须是 iteration 的直接子节点
9. **if-else branch outputField 合法性**（M2 起）：同上，childId 必须属于对应分支
10. **模板引用作用域合法性**（M2/M3 起）：在已知引用字段里扫描模板引用（End outputs/answer、if-else condition/outputField、iteration inputRef/outputField 等）。外部作用域不能引用任何 descendant 子节点，只能引用容器节点自身输出（如 `{{if_id.result}}`、`{{iter_id.results}}`）。子图内部可以引用同作用域兄弟节点与父作用域已有输出。

> **M1 的 "unknown node type" 陷阱**：当前 `validate` 看到未注册类型会直接抛错（[compiler.py:44](backend/core/compiler.py)）。M1 不注册 `if_else` / `iteration`，所以 M1 的测试不能造 `type: "if_else"` 节点。M1 测试 fixture 用**两个现有节点**（比如把 llm_b 的 `parentId` 指向 llm_a）来触发结构性规则 1-5——这种 JSON 在语义上不合法，但足以验证结构性校验逻辑；真正"合法的带容器工作流"要到 M2 才能端到端测。

### 4.2 编译产物

当前 `compile()` 直接返回 LangGraph `CompiledGraph`。**新方案放弃直接 1:1 映射到 LangGraph**，理由：

- LangGraph 的 conditional_edges 能表达 if-else，但 Send API 用于 iteration 要求 body 在同一 StateGraph 里，嵌套 body 的拓扑会污染顶层 graph
- 为了保持事件协议一致性（每个节点一次 node_start/node_end），我们自己接管调度

新的 `compile()` 返回一个轻量的 `CompiledWorkflow` 对象：

```python
@dataclass
class CompiledWorkflow:
    nodes: dict[str, NodeInstance]           # node_id -> 已实例化的 node
    top_level_order: list[str]               # 顶层节点执行顺序（不含 parentId 的节点）
    children_by_parent: dict[str, list[str]] # parent_id -> 子节点 id 列表（按子图拓扑序）
    edges_by_source: dict[str, list[EdgeRef]] # 普通邻接表；用于调试、后续扩展，不参与 if_else 分支路由
    node_defs: dict[str, dict]               # 原始 node def，engine 需要查 parentId / branchId
```

LangGraph 仍用于单层内线性节点调度（可选；也可以完全不用 LangGraph，engine 自己跑，后续 spec 决定）。**第一版决定：放弃 LangGraph，engine 自己实现调度**。这让后面加 tracing 更直接。

### 4.3 向后兼容

旧工作流（无 `parentId`、无 if_else / iteration 节点）走现有路径不变——`children_by_parent` 为空，`top_level_order` 就是全部节点的拓扑序。

---

## 五、引擎改造

[backend/core/engine.py](backend/core/engine.py) 当前 `run()` 是 ~100 行的 for 循环。新版大致结构：

```python
class ExecutionEngine:
    async def run(self, graph_json, user_input, inputs, on_event):
        compiled = GraphCompiler().compile(graph_json)
        state: WorkflowState = {"inputs": inputs, "node_outputs": {}, ...}
        await self._emit(on_event, {"type": "workflow_start"})

        try:
            await self._run_scope(
                compiled=compiled,
                scope_nodes=compiled.top_level_order,
                state=state,
                on_event=on_event,
                parent_id=None,
            )
            # workflow_end 发送 answer/outputs 见原逻辑
        except Exception as e:
            # 照旧 workflow_end failed
            ...

    async def _run_scope(self, compiled, scope_nodes, state, on_event, parent_id):
        """执行一个作用域内的节点（顶层或子图）"""
        for node_id in scope_nodes:
            node = compiled.nodes[node_id]
            node_def = compiled.node_defs[node_id]

            if node_def["type"] == "if_else":
                await self._run_if_else(compiled, node_id, state, on_event)
            elif node_def["type"] == "iteration":
                await self._run_iteration(compiled, node_id, state, on_event)
            else:
                await self._run_single(node, state, on_event)

    async def _run_single(self, node, state, on_event):
        # 现有逻辑：emit node_start -> node.execute -> emit node_end
        ...

    async def _run_if_else(self, compiled, if_else_id, state, on_event):
        # 1. emit node_start
        # 2. 求值 condition，选中 branchId
        # 3. emit branch_taken 事件（新增）
        # 4. 取 children[parentId=if_else_id, branchId=selected] 按子图拓扑序
        # 5. branch_state = shallow_copy(state)，_run_scope(children, branch_state, ...)
        # 6. 从 branch_state 解析选中分支 outputField
        # 7. 只把 node_outputs[if_else_id] = {branchTaken, result} 写回父 state
        # 8. emit node_end with output={branchTaken, result}

    async def _run_iteration(self, compiled, iter_id, state, on_event):
        # 1. emit node_start
        # 2. resolve inputRef -> items
        # 3. children = compiled.children_by_parent[iter_id] (按子图拓扑序)
        # 4. semaphore = asyncio.Semaphore(maxConcurrency)
        # 5. 创建 N 个 task: _run_iter_item(i, item, children, state_snapshot, on_event)
        # 6. asyncio.gather / 按 errorStrategy 处理
        # 7. 收集 results[i] = child_state["node_outputs"][outputField.nodeId][outputField.field]
        # 8. emit node_end with output={results, errors}

    async def _run_iter_item(self, index, item, children, parent_state, on_event, iter_id, error_strategy):
        # 浅拷贝 state + 注入 _iter_context
        child_state = {**parent_state, "node_outputs": dict(parent_state["node_outputs"]),
                       "input": coerce_item_to_input(item),
                       "_iter_context": {"item": item, "index": index,
                                         "itemVar": item_var, "indexVar": index_var}}
        await self._emit(on_event, {"type": "iteration_item_start", "node_id": iter_id, "index": index})
        try:
            await self._run_scope(compiled, children, child_state, on_event, parent_id=iter_id)
            await self._emit(on_event, {"type": "iteration_item_end", "node_id": iter_id, "index": index, "status": "completed"})
            return child_state
        except Exception as e:
            await self._emit(on_event, {"type": "iteration_item_end", "node_id": iter_id, "index": index, "status": "failed", "error": str(e)})
            if error_strategy == "fail_fast":
                raise
            return None  # continue / ignore
```

**关键设计点**：

- `_run_scope` 是递归入口，所有嵌套层级共用
- iteration 的并发通过 `asyncio.gather + Semaphore`，不依赖 LangGraph
- 子节点 emit 的 `node_start` / `node_end` 事件保持原协议，前端天然能渲染；只是多了一个 `iteration_index` 可选字段用于区分同一节点的多次执行

---

## 六、SSE 事件协议扩展

现有事件（见 [frontend/src/types/workflow.ts:81-95](frontend/src/types/workflow.ts)）保持兼容。新增：

```ts
type SSEEvent =
  | { type: 'workflow_start' }
  | { type: 'node_start'; node_id: string; node_type: string; iteration_index?: number }  // +iteration_index
  | { type: 'node_stream'; ... }
  | { type: 'node_heartbeat'; ... }
  | { type: 'node_end'; ...; iteration_index?: number }                                    // +iteration_index
  | { type: 'branch_taken'; node_id: string; branch_id: string; condition_result: boolean } // 新
  | { type: 'iteration_item_start'; node_id: string; index: number; total: number }        // 新
  | { type: 'iteration_item_end'; node_id: string; index: number; status: 'completed'|'failed'; error?: string } // 新
  | { type: 'workflow_end'; ... }
```

**为什么在节点事件上加 `iteration_index`**：同一个 body 内的节点可能跑 N 次，前端需要区分哪次迭代触发了哪个事件。

**debugStore 数据结构（最终方案）**：`nodeStates` 保持单一的 `Map<string, NodeExecutionState>`，但 **key 改成 composite**：`${nodeId}#${iteration_index ?? 0}`。不再用联合类型 `NodeExecutionState | NodeExecutionState[]`（避免分支处理）。

配套 helper：

- `getNodeState(nodeId, iterationIndex?)`：给 canvas 节点组件用，默认取 `#0`
- `getAggregatedNodeStatus(nodeId)`：给画布节点高亮用，聚合所有 `${nodeId}#*` 的状态（任一 running → running；全 completed → completed；任一 failed → failed）

---

## 七、前端改造

### 7.1 类型（[frontend/src/types/workflow.ts](frontend/src/types/workflow.ts)）

- `NodeType` 加 `'if_else' | 'iteration'`
- 后端 `WorkflowGraph.nodes[i]` 加 `parentId?: string`；React Flow UI node 运行时加 `parentNode` 与 `extent?: 'parent'`
- `WorkflowGraph.edges[i]` 加 `sourceHandle?: string`
- `SSEEvent` 加三个新 type 与 `iteration_index`

### 7.2 Store（[frontend/src/stores/workflowStore.ts](frontend/src/stores/workflowStore.ts)）

**字段映射约定**（关键——后端用 `parentId`，React Flow 11 用 `parentNode` + `extent: 'parent'`）：

| 方向 | 代码位置 | 转换 |
|---|---|---|
| 加载 graph（后端 → React Flow） | `normalizeGraphNode` | 若 `node.parentId` 存在，设 React Flow node 的 `parentNode = parentId` 且 `extent = 'parent'` |
| 保存 graph（React Flow → 后端） | `toGraphJSON` | 若 React Flow node 有 `parentNode`，写入后端 JSON 的 `parentId` 字段；`extent` 不落盘（前端重新加载时可依据 `parentId` 恢复） |

其他改动：

- 新增 action `addChildNode(parentId, nodeType, position)`：往容器内加子节点，自动设 `parentNode = parentId` 与 `extent = 'parent'`
- 删除父节点时级联删除所有子节点（弹 confirm）
- `data.config.branchId`（UI 内部）⇄ 后端 `data.branchId`（toGraphJSON 展平已天然完成）

### 7.3 React Flow 渲染（[frontend/src/components/canvas/WorkflowCanvas.tsx](frontend/src/components/canvas/WorkflowCanvas.tsx)）

- React Flow 11 原生支持：子节点设 `parentNode: <iter_id>` + `extent: 'parent'` 即会被限制在父容器内
- Iteration 节点用一个"大方框"组件，背景半透明，内部留空间给子节点
- If-Else 节点同理，但内部分"true 区"和"false 区"两栏（用视觉分隔而非两个 parent）

### 7.4 节点组件（[frontend/src/components/nodes/](frontend/src/components/nodes/)）

新增两个：

- `IterationNode.tsx`：顶部标题栏（显示 inputRef 预览、concurrency、error strategy 标签），内容区是子画布（其实就是 React Flow 的 subflow 子区域）
- `IfElseNode.tsx`：顶部显示条件，下方两个 source handle（true / false），handle 颜色区分；内部两栏分别承载 true/false 子节点

### 7.5 配置面板（[frontend/src/components/panels/NodeConfig.tsx](frontend/src/components/panels/NodeConfig.tsx)）

- `IterationNodeConfig`：输入引用选择器（下拉列出上游 array 输出）、itemVar/indexVar 输入框、concurrency 数字输入、errorStrategy 下拉、outputField 选择器（下拉列出 body 内节点+字段）
- `IfElseNodeConfig`：条件编辑器（left 引用选择器 + op 下拉 + right 输入框）；第一版固定两分支 true/false

### 7.6 DebugDrawer

- `debugStore.nodeStates` 迁移到 composite key（见 §六末尾方案），并提供 `getNodeState` / `getAggregatedNodeStatus` helper
- 时间轴 UI：iteration 节点在时间轴上展开为 N 行（按 index），父行显示聚合状态

---

## 八、harness 兼容

harness v2 的 `GraphBuilder.add_node` / `add_edge` 需要支持 `parentId` 参数，但 **v1 只需要"能画，不需要会生成"**：

- `add_node(type, config, parent_id=None)`：透传 parentId
- 工具面暂不新增 `add_iteration` / `add_if_else` 高阶工具——让 harness 用基础 `add_node` 搭建，或者第一版直接禁止 harness 生成控制流节点（纯人工搭）

这条路径留给后续 spec，本 spec 只保证 harness 不会因为 schema 新字段而崩。

---

## 九、Milestone / PR 拆分

5 个独立可合并的 PR，每个都有对应 pytest 用例。

### M1 — 数据模型 + 编译器验证（纯后端，无执行）

**范围**：

- [backend/core/compiler.py](backend/core/compiler.py)：新增 `parentId` 验证、跨层 edge 验证、子图判环。**不碰 compile() 的产物，仍返回旧的 LangGraph CompiledGraph。**
- [frontend/src/types/workflow.ts](frontend/src/types/workflow.ts)：类型新增字段
- [frontend/src/stores/workflowStore.ts](frontend/src/stores/workflowStore.ts)：`toGraphJSON` 保留新字段

**测试**：

- `test_compiler_rejects_orphan_parent_id`
- `test_compiler_rejects_cross_scope_edge`
- `test_compiler_rejects_cycle_in_subgraph`
- `test_compiler_accepts_nested_parent_id`

**退出标准**：旧工作流全部跑通；带 parentId 的 JSON 能通过 validate 但暂时不会被 engine 用到（因为没有 if_else/iteration 节点存在）。

### M2 — If-Else 节点 + engine 子图调度骨架

**范围**：

- [backend/nodes/](backend/nodes/) 新增 `if_else_node.py`（只负责条件求值，不负责调度）
- [backend/core/engine.py](backend/core/engine.py)：重写为"自己调度"模型（§5 的 `_run_scope` / `_run_if_else`），彻底去掉 LangGraph（改动较大，但时机最合适）
- [backend/core/compiler.py](backend/core/compiler.py)：`compile()` 返回新的 `CompiledWorkflow` 对象
- SSE 事件：新增 `branch_taken`
- 前端：新增 `IfElseNode.tsx`、`IfElseNodeConfig.tsx`；React Flow 支持 sourceHandle 可视元数据
- `debugStore` 处理 `branch_taken`

**测试**：

- `test_engine_runs_linear_without_control_flow`（回归）
- `test_engine_runs_if_else_true_branch`
- `test_engine_runs_if_else_false_branch`
- `test_engine_skips_unselected_branch_nodes`
- `test_if_else_condition_operators`（8 个操作符各一条）

**退出标准**：能手动搭一个 Start → LLM → IfElse → (LLM_A or LLM_B) → End 的工作流并正常执行。

### M3 — Iteration 节点（串行版）

**范围**：

- `backend/nodes/iteration_node.py`
- engine `_run_iteration` / `_run_iter_item`，`maxConcurrency = 1` 路径
- `_iter_context` 注入到 state，template.py 扩展支持 `{{item}}` / `{{index}}`
- SSE：`iteration_item_start` / `iteration_item_end`、节点事件上的 `iteration_index`
- 前端：`IterationNode.tsx`、`IterationNodeConfig.tsx`
- `debugStore.nodeStates` 使用 composite key 记录 `iteration_index`

**测试**：

- `test_engine_runs_iteration_serial`
- `test_iteration_exposes_item_and_index_in_template`
- `test_iteration_collects_results_in_order`
- `test_iteration_empty_input_produces_empty_results`

**退出标准**：能手动搭 Start → Iteration(body: LLM) → End，输入数组跑出结果数组。

### M4 — Iteration 并发 + 错误策略

**范围**：

- engine 的 Semaphore 并发、`errorStrategy` 三种模式
- 前端配置面板加并发度与错误策略选项

**测试**：

- `test_iteration_parallel_preserves_order`
- `test_iteration_fail_fast_cancels_siblings`
- `test_iteration_continue_records_errors`
- `test_iteration_concurrency_bounded`（使用 asyncio.sleep 验证并发上限）

**退出标准**：并发跑 10 个 item，输出数组顺序正确；fail_fast 时能观察到其他 task 被取消。

### M5 — UX 打磨

**范围**：

- React Flow 子画布拖拽手感（把节点拖入/拖出父容器）
- 父节点删除时的级联删除 confirm
- DebugDrawer 时间轴的 iteration 展开 UI
- 节点分组（#3）的无语义 Group 节点（作为 iteration/if_else 机制的副产物，免费获得）

**测试**：

- 前端 vitest 单测 store 的级联删除
- 手动 UX 验收 checklist

**退出标准**：能不看代码，纯在画布上搭一个 iteration 套 if_else 的工作流并跑通。

---

## 十、测试策略

- **pytest**：每个 milestone 的测试清单见上。所有测试用 [backend/tests/conftest.py](backend/tests/conftest.py) 的 in-memory SQLite
- **engine 测试模式**：mock node（类似现有 [backend/tests/test_engine.py](backend/tests/test_engine.py) 的 `FakeNode`），验证调度逻辑，不真的调 LLM
- **回归**：M2 起每个 PR 都要跑 `test_compiler.py` / `test_engine.py` / `test_nodes.py` 全量
- **并发测试**：用 `asyncio.Event` 控制 fake node 的完成顺序，验证 Semaphore 真的限并发
- **前端**：只对 store 做 vitest 单测（级联删除、toGraphJSON 序列化）；画布交互靠手动验收

---

## 十一、开放问题 / 推迟决定

1. **LangGraph 彻底去掉还是保留做单层调度？** 本 spec 决定"彻底去掉"（M2 一次性完成）。如果 M2 工作量爆炸，可以回退到"保留 LangGraph 做单层，控制流手写"。
2. **条件 DSL 是否要加 AND/OR？** 本 spec 不做。真实需求出现再开 spec。
3. **iteration 内 emit node_stream 事件怎么聚合？** 第一版：带 iteration_index 原样透传，前端自己按 index 分组。
4. **harness 是否在 v1 就学会生成 if_else / iteration？** 本 spec 否。单开 spec。
5. **group 节点（纯视觉分组）是否在 M5 一起做？** 可以，因为机制已具备；但不强制。

---

## 十二、与 #1 tracing / #3 分组 的协同路线

- **tracing（#1）**：本 spec 的事件协议已预留 `iteration_index` 与 `branch_taken`，后续 spec 只需在 SSE 事件上加 `trace_id` / `span_id` 字段，engine 在 `_run_scope` / `_run_iter_item` 处创建 child span 即可。父子 span 关系自然映射到 parentId 层级。
- **节点分组（#3）**：M5 引入的 `group` 节点类型复用同一 `parentId` 机制，engine 遇到 type=group 直接 `_run_scope(children)` 透传，无额外语义。前端用同样的 React Flow 嵌套渲染。

---

## 附录 A — 决策记录

| 决策 | 选项 | 选择 | 原因 |
|---|---|---|---|
| 子图表示 | 嵌套 JSON / 扁平+parentId | 扁平+parentId | React Flow 原生支持；DB schema 零变更 |
| 调度引擎 | LangGraph / 自研 | 自研（M2 一次性切换） | 控制流的 LangGraph 适配复杂度 > 自研；为 tracing 让路 |
| 条件 DSL 规模 | 26 操作符 / 8 操作符 | 8 操作符 | YAGNI |
| iteration 状态隔离 | 命名空间 / 浅拷贝 | 浅拷贝 | 简单，语义够用 |
| 跨作用域引用外部 → 子节点 | 允许 / 禁止 | 禁止 | 维持子图"封装性"，便于未来抽成 subflow |
| harness v1 是否生成控制流 | 是 / 否 | 否 | 减小本 spec 范围 |

---

## 附录 B — v0.2 修订记录（2026-04-19）

基于用户审校反馈，修正 9 处执行语义不一致/不清晰的地方。改动均为"收紧定义"，不改变整体方向。

| # | 原问题 | 修订 |
|---|---|---|
| 1 | §1.4 三段式 `parentId.childId.field` 与 §3.4 "不扩展语法" 自相矛盾 | 删除三段式描述；§3.4 改为列举**作用域内所有合法引用形式**的表格 |
| 2 | §2.3 if-else 子节点写 `data.config.branchId`，与前端 `toGraphJSON` 把 config 展平进 data 冲突 | 统一改为 `data.branchId`；§2.1 新增"graph JSON 扁平约定"说明框 |
| 3 | if-else 只输出 `{ branchTaken }`，外部无法拿分支结果 | §2.3 给每个 branch 加 `outputField`；§3.1 明确 `node_outputs[if_id] = { branchTaken, result }` |
| 4 | §2.2 sourceHandle 必须是 `'true'\|'false'` 参与路由，与 §2.3 parentId+branchId 子图路由并存 | sourceHandle 降级为**纯前端 UI 提示**；执行路由唯一依据是 parentId + branchId；if-else 对外仍是"黑盒节点 + 一条普通出边" |
| 5 | 模板 resolver 当前会把 `{{item.foo}}` 当作 `node_outputs["item"]["foo"]` 查找 | §3.3 明确改造 `resolve_reference`：**先特殊处理 itemVar/indexVar，支持 dict/list key 访问，再走现有路径** |
| 6 | LLMNode 读 `state["input"]`，不渲染 config 模板——光注入 `_iter_context` 不够 | §3.3 方案：每次迭代 `child_state["input"] = items[i]`（最小改动）；未来再做通用"节点输入绑定" |
| 7 | M1 要求"不改 compile 产物"但又校验 parent 类型为 iteration/if_else——M1 不注册这俩类型会被 unknown-type 检查拦 | §4.1 拆成"结构性规则（M1）"与"语义性规则（随节点类型注册启用）"两档；M1 只做 5 条结构性检查 |
| 8 | 后端 `parentId` ⇄ React Flow 11 `parentNode` + `extent: 'parent'` 映射未明示 | §7.2 新增映射表格，规定 `normalizeGraphNode` 与 `toGraphJSON` 的转换 |
| 9 | debugStore 既说 `Map<..., state \| state[]>` 又说 composite key | 统一方案：composite key `${nodeId}#${iter_index ?? 0}` + `getNodeState` / `getAggregatedNodeStatus` helper |

### v0.3 追加修订（2026-04-19）

| # | 原问题 | 修订 |
|---|---|---|
| 10 | §2.1 把 `extent` 写进后端 Node JSON，但 §7.2 又说不落盘 | 明确后端持久化 graph JSON 只新增 `parentId`；`extent` 仅为 React Flow UI 字段，加载时由 `parentId` 恢复 |
| 11 | if-else 正文说分支状态隔离，伪代码却把父 state 直接传给 `_run_scope` | §5 伪代码改为用 `branch_state` 浅拷贝执行分支，最后只把 if-else 节点自身输出写回父 state |
| 12 | `inputRef` / condition 若用 `render_template` 会丢失 list/dict/number 类型 | §3.1 / §3.2 新增 typed reference 规则：完整模板引用用 `resolve_reference` 保留原始类型，混合文本才用 `render_template` |
| 13 | iteration 伪代码漏掉 v0.2 新增的 `state["input"]` override | §5 `_run_iter_item` 伪代码补上 `input: coerce_item_to_input(item)` 与 itemVar/indexVar |
| 14 | `edges_by_source` 注释还写"用于 if_else 路由"，与 sourceHandle 降级冲突 | §4.2 改为普通邻接表，不参与 if-else 分支路由 |
| 15 | "外部不能引用子图内部节点"没有进入 compiler 验证规则 | §4.1 语义性规则新增模板引用作用域合法性校验 |

**实施顺序建议**：本修订落完即可按原 §九 M1–M5 推进，不需要额外"修订 PR"独立合并。
