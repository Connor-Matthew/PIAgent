# 阶段设计：默认 Input / Output 节点 + 变量契约

> 日期：2026-04-14
> 状态：待实施
> 依赖：Task 1–12 已完成（后端 ExecutionEngine、SSE、所有 6 类节点、Providers API）

## 1. 动机

当前画布没有"默认入口 / 出口"的概念。用户拖入的 StartNode / EndNode 只是图的拓扑起止点，没有定义"用户输入什么"和"最终产出什么"的契约，导致：

- 新建工作流是一张空画布，用户要手动从节点库拖两个端点节点，体验断裂。
- Start 没有声明输入字段，调试抽屉无法渲染"输入表单"；运行时只能接收一段不带结构的文本。
- End 没有声明输出字段，前端"最终输出区"不知道该读 state 里的哪个 key，也无法做 API 级别的结构化返回。
- 中间节点之间的数据传递靠硬编码 key（`llm_output`、`audio_url` 等），可复用性差。

本阶段要做：**新建工作流时画布默认带一个不可删除的 Start 和 End 节点**，并给它们加上**结构化 schema + 变量引用语法**，让整个工作流从"画布拓扑"升级为"带类型契约的数据流"。

## 2. 范围

**In scope**

- 新建工作流默认落位 Start + End 两个节点；两者不可通过删除键 / 右键菜单移除；全图强制有且仅有一个 Start、一个 End。
- Start 节点的输入字段 schema：参数名 + 类型（text / number / select / file）+ 是否必填 + 默认值 / 选项。
- End 节点的输出变量 schema + "回答内容"模板字段：
  - 输出变量：参数名 + 来源（input / reference）+ 值。
  - 回答内容：支持 `{{nodeId.fieldName}}` 占位符的多行文本模板。
- WorkflowState 扩展 `node_outputs: dict[str, dict]`（以 nodeId 为 key 存每个节点的输出 map）和 `inputs: dict[str, Any]`（Start 节点收集的输入值）。
- 变量引用解析器：`{{nodeId.fieldName}}` 的正则 + 取值 + 渲染。
- 前端：Start / End 节点的配置面板（动态行表单、类型下拉、引用选择器、模板编辑框）。

**Out of scope（留给后续阶段）**

- 中间节点（LLM / RAG / Agent / TTS）的配置面板统一改造为"声明式输出变量"——本期只让中间节点**暴露一个固定的输出 schema**（见 §4.3），供 End 引用；不改中间节点的 UI。
- 类型校验（如 number 字段传入非数字）。本期只做字符串化拼接，后续再加 JSON schema 校验。
- 多入口 / 多出口工作流。

## 3. 用户故事

1. 用户点击"新建工作流"→ 画布上已经有 Start 和 End 两个节点，连线空着等待中间节点。
2. 用户选中 Start 节点 → 右栏"输入配置"，点"添加"→ 新增一行 `topic`（text，必填），再加一行 `style`（select，选项 `科普/对话/访谈`，默认 `对话`）。
3. 用户拖入 LLM、TTS 等中间节点并连线。
4. 用户选中 End 节点 → 右栏"输出配置"，点"添加"：
   - 第一行参数名 `audio_url`，类型 = `引用`，下拉选择 "TTS 节点 / audio_url" → 自动填入 `{{tts_1.audio_url}}`。
   - 第二行参数名 `title`，类型 = `输入`，手动填写字面量 `"今天的 AI 播客"`。
5. End 节点"回答内容"区填写：`🎧 ${"{{title}}"} 已生成，链接：${"{{audio_url}}"}`（`{{varName}}` 可直接引用本节点已定义的输出变量）。
6. 调试抽屉的"输入区"根据 Start schema 自动渲染出 `topic` 输入框 + `style` 下拉，用户填入 `topic = "RAG 最新进展"` → 点运行。
7. 运行完成 → 调试抽屉"最终输出区"展示回答内容渲染结果，并展示结构化的 `audio_url` / `title` 供 API 消费。

## 4. 设计

### 4.1 Workflow JSON Schema（前后端契约）

Start 节点 `data`：

```json
{
  "type": "start",
  "inputs": [
    {"name": "topic",    "type": "text",   "required": true},
    {"name": "style",    "type": "select", "options": ["科普","对话","访谈"], "default": "对话"},
    {"name": "duration", "type": "number", "default": 5}
  ]
}
```

End 节点 `data`：

```json
{
  "type": "end",
  "outputs": [
    {"name": "audio_url", "source": "reference", "value": "{{tts_1.audio_url}}"},
    {"name": "title",     "source": "input",     "value": "今天的 AI 播客"}
  ],
  "answer": "🎧 {{title}} 已生成，链接：{{audio_url}}"
}
```

- `source = "input"`：`value` 是字面量，按原样放入输出。
- `source = "reference"`：`value` 必须是形如 `{{nodeId.fieldName}}` 的单一引用（前端选择器保证格式）。
- `answer` 模板中允许两种占位符：
  - `{{varName}}`：引用本 End 节点 `outputs[*].name`（优先级高）。
  - `{{nodeId.fieldName}}`：直接引用任意上游节点输出（兜底）。

### 4.2 WorkflowState 扩展

```python
class WorkflowState(TypedDict, total=False):
    inputs: dict[str, Any]          # Start 收集的输入值（按参数名索引）
    node_outputs: dict[str, dict]   # 每个节点的输出：{nodeId: {fieldName: value}}
    answer: str                     # End 渲染后的回答内容（最终对外展示字段）
    outputs: dict[str, Any]         # End 的结构化输出（供 API 返回 / 下游消费）

    # 兼容旧字段（本阶段保留，后续阶段逐步下线）
    input: str
    messages: list[BaseMessage]
    context: str
    llm_output: str
    audio_url: str
```

每个中间节点在执行结束时，除了写入原有扁平 key（如 `llm_output`），**必须同时**把自己的输出写到 `state["node_outputs"][self.node_id]`（见 §4.3）。End 节点从 `node_outputs` 读引用。

### 4.3 中间节点的固定输出 schema（本期只暴露，不改 UI）

| 节点类型 | nodeId 示例 | 输出字段 |
|---------|-----------|---------|
| llm     | `llm_1`   | `text: str` |
| rag     | `rag_1`   | `context: str`, `documents: list[dict]` |
| agent   | `agent_1` | `text: str`, `steps: list[dict]` |
| tts     | `tts_1`   | `audio_url: str`, `duration: float` |
| start   | `start_1` | 由 `inputs` schema 动态生成（字段名 = 参数名） |

前端的"引用选择器"根据上游节点类型给出这张表中的字段列表；nodeId 从画布节点实际 id 取。

### 4.4 变量引用解析

后端新增 `backend/core/template.py`：

```python
REF_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?\s*\}\}")

def resolve_reference(token: str, state: WorkflowState, local_vars: dict | None = None) -> Any:
    """解析单个 {{x}} 或 {{x.y}}，未命中返回空字符串。"""

def render_template(template: str, state: WorkflowState, local_vars: dict | None = None) -> str:
    """把模板里所有 {{...}} 替换成字符串。"""
```

优先级：先查 `local_vars`（End 的本节点 outputs），再查 `state["node_outputs"][nodeId][fieldName]`，最后查 `state["inputs"][name]`。未命中返回 `""`（不抛异常，保持工作流鲁棒）。

### 4.5 Start / End 节点实现改动

- `backend/nodes/start_node.py`：
  - 读取 `data.inputs` schema 和运行时传入的 `state["inputs"]`；
  - 对缺失的必填字段抛 `ValueError`（走 SSE error 事件）；
  - 把 `state["inputs"]` 的每个 `name → value` 复制到 `state["node_outputs"][self.node_id]`；
  - 兼容旧路径：如果 schema 里有名为 `input` 或只有单字段，仍写入 `state["input"]`。

- `backend/nodes/end_node.py`：
  - 遍历 `data.outputs`：`input` 直接取 `value`；`reference` 调用 `resolve_reference(value, state)`；
  - 组装为 `state["outputs"] = {name: resolved_value}`；
  - 调用 `render_template(data.answer, state, local_vars=state["outputs"])` → 写入 `state["answer"]`；
  - SSE `workflow_end` 事件的 payload 同时带 `answer` 和 `outputs`。

### 4.6 Compiler 校验

`backend/core/compiler.py` 增加校验：

- 有且仅有 1 个 `type == "start"` 节点；
- 有且仅有 1 个 `type == "end"` 节点；
- End 的每个 `reference` 类型 output 的 `value` 必须匹配 `{{nodeId.fieldName}}` 正则，且 nodeId 存在于图中（fieldName 是否合法暂不强校验）。

任一失败抛 `CompilerError`，API 层返回 400。

### 4.7 前端改动

- `frontend/src/stores/workflowStore.ts`：新建工作流时 `initialNodes = [defaultStart, defaultEnd]`，两个节点的 `data.locked = true`。
- `frontend/src/components/canvas/WorkflowCanvas.tsx`：删除键 / 右键菜单对 `data.locked = true` 的节点跳过；连线验证保持原样。
- `frontend/src/components/panels/NodeConfig.tsx`：
  - `StartNodeConfig`：动态行表单，每行含 `名称 / 类型 / 必填 / 默认值 / 选项（仅 select）`。
  - `EndNodeConfig`：
    - 输出配置：动态行，`参数名 / 类型（输入 · 引用）/ 值`。当类型为"引用"时，值字段变为两级下拉：上游节点（按类型列出画布上的节点）→ 字段（按 §4.3 的表）。选中后写入 `{{nodeId.fieldName}}`。
    - 回答内容：多行 textarea，支持在光标位置插入 `{{varName}}`（本节点输出）或 `{{nodeId.fieldName}}`（引用）。
- `frontend/src/components/debug/DebugDrawer.tsx`：输入区根据当前工作流 Start 节点的 `inputs` schema 动态渲染表单；提交时把收集的 `{name: value}` 作为 `inputs` 字段 POST 到 `/api/workflows/{id}/run`。最终输出区优先展示 `state.answer`，同时提供 `outputs` 的 JSON 查看折叠块。

## 5. 受影响文件

**后端（修改 + 新增）**

- 新增 `backend/core/template.py`
- 修改 `backend/core/state.py`（扩展 WorkflowState）
- 修改 `backend/core/compiler.py`（IO 校验）
- 修改 `backend/core/engine.py`（`workflow_end` 事件 payload 增加 `answer` / `outputs`）
- 修改 `backend/nodes/start_node.py` / `backend/nodes/end_node.py`
- 修改 `backend/nodes/{llm,rag,agent,tts}_node.py`（每个节点执行后写 `node_outputs[self.node_id]`）
- 修改 `backend/api/workflows.py`（`/run` 接口接受 `inputs: dict`）
- 新增 `backend/tests/test_template.py`
- 修改 `backend/tests/test_nodes.py` / `test_compiler.py` / `test_engine.py` / `test_workflows_api.py`

**前端（全部新增 —— 前端代码尚未初始化，本阶段仅定义契约，实际组件在前端脚手架阶段实现；但**本设计文档是前端开发的依据**）

- `frontend/src/stores/workflowStore.ts`（默认节点）
- `frontend/src/components/panels/NodeConfig.tsx`（Start/End 配置面板）
- `frontend/src/components/debug/DebugDrawer.tsx`（动态输入表单 + answer 展示）
- `frontend/src/types/workflow.ts`（Start/End schema 类型）

## 6. 验收标准

1. `pytest backend/tests` 全绿；新增的 `test_template.py` 覆盖：单字段引用、嵌套引用、未命中返回空、字面量不受影响。
2. Compiler 对"无 Start / 两个 End / reference 指向不存在的 nodeId"三种情况分别抛错。
3. 集成测试：构造一个 Start → LLM → TTS → End 的工作流，Start schema 含 `topic`，End outputs 引用 `{{llm_1.text}}` 和 `{{tts_1.audio_url}}`，answer 模板 `"{{title}}: {{audio_url}}"` → 运行后 `workflow_end` 事件里 `answer` 为渲染后字符串，`outputs` 是结构化 dict。
4. `/api/workflows/{id}/run` 请求体 `{"inputs": {"topic": "RAG 最新进展"}}` 能端到端跑通。
5. 本设计文档的内容已合并回 `docs/superpowers/specs/2026-04-13-piagent-design.md`。

## 7. 执行顺序建议

1. `state.py` + `template.py`（纯数据层，先写测试）
2. `start_node.py` / `end_node.py` + 各中间节点写 `node_outputs`
3. `compiler.py` 校验
4. `engine.py` 事件 payload
5. `workflows.py` 接口
6. 跑全部测试
7. 回填主 spec
