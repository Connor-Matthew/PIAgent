# PIAgent — AI Agent 工作流编排平台 设计文档

> **更新记录**
> - 2026-04-14：默认 Input / Output 节点 + 变量契约阶段已实施完成。后端已新增 `template.py`、扩展 `WorkflowState`、完成 `CompilerError` IO 校验、`/run` 接口支持 `inputs` dict，全部 64 项测试通过。
> - 2026-04-14：Provider 实例化管理阶段已实施完成。后端新增 `providers` 表、`core/crypto.py`、Provider CRUD API、模型列表缓存、`openai_compatible` 协议支持，`compiler.py` 增加 provider_id 校验，全部 82 项测试通过。
> - 2026-04-15：MiniMax TTS 专用节点接入阶段已实施完成。Provider 表新增 `category` 字段（`llm`/`tts`）、新增 `MiniMaxTTSProvider`、`TTSNode` 复用 Provider 系统、前端 Provider 管理页和 TTS 配置面板均支持 category 切换，全部 91 项测试通过。
> - 2026-04-15（计划）：节点级流式执行阶段。LLM/Agent 节点接入 token 级 `node_stream` 推送，长耗时节点（TTS）增加 `node_heartbeat` 心跳事件，前端 NodeStatusCard 实现打字机渲染与计时器。详见 `plans/2026-04-15-streaming-execution.md`。
> - 2026-04-15（计划）：TTS 长文本分片并行合成阶段。新增句子级分片器，`asyncio.gather + Semaphore` 并发合成，按序拼接 mp3，进度复用 `node_stream` 事件契约（`delta.phase = "tts_chunk"`）。详见 `plans/2026-04-15-tts-chunking.md`。

## 项目定位

面向 AI Agent 开发方向的全栈项目，用于简历展示和面试。通过可视化拖拽界面编排 AI 工作流，支持大模型调用、RAG 知识检索、ReAct Agent 自主决策、音频合成等多节点协同，最终实现"输入文字 → AI 生成 → 语音合成 → 播客播放"的完整链路。

**目标版本：** 功能完整的 V1，可作为产品雏形演示。

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | React 18 + TypeScript + React Flow + Zustand + Vite + TailwindCSS |
| 后端 | Python 3.12 + FastAPI + LangChain + LangGraph + SQLAlchemy |
| AI/Agent | LangGraph StateGraph + ReAct Agent + RAG (Chroma + Embedding) + Tool Calling |
| 通信 | RESTful API + SSE (Server-Sent Events) + LLM Streaming |
| 存储 | SQLite（工作流定义 + 执行记录）+ Chroma（向量数据库） |

## 架构方案

**方案：LangGraph 驱动引擎 + SSE 实时推送**

```
前端 React Flow (画布编排)
    ↕ REST API + SSE
后端 FastAPI
    ├── Graph Compiler (画布 JSON → LangGraph StateGraph 编译)
    ├── Node Registry (节点注册与实例化)
    └── Execution Engine (LangGraph 运行时 + SSE 状态推送)
        ├── LLM Providers (OpenAI / Anthropic / Google / DeepSeek)
        ├── Vector Store (Chroma + Embedding 模型)
        └── TTS Service (抽象接口，可插拔 Provider)
    ↕ SQLAlchemy ORM
SQLite + Chroma
```

核心流程：
1. 前端提交画布 JSON（nodes + edges）
2. Graph Compiler 验证 DAG（环检测）→ 拓扑排序 → 为每个节点创建 LangGraph node → 编译为 StateGraph
3. WorkflowState 在节点间流转，每个节点读取/写入共享状态
4. 执行过程通过 SSE 实时推送节点状态（start / stream / end）到前端

## 节点体系

6 种核心节点类型：

### 1. 用户输入节点 (Start)
- 工作流入口；新建工作流时**默认存在于画布且不可删除**，全图强制有且仅有一个
- 声明式输入字段 schema：`inputs: [{name, type, required, default, options}]`
  - `type`：`text` / `number` / `select` / `file`
  - 调试抽屉的输入区根据此 schema 动态渲染表单
- 运行时把用户填入的 `{name: value}` 写入 `state["inputs"]` 并冗余到 `state["node_outputs"][start_id]`

### 2. 大模型节点 (LLM)
- 通过 LangChain ChatModel 调用 LLM
- 可配置：**Provider 实例（`provider_id`）**、模型（从该实例动态拉取的列表里选）、Temperature、System Prompt、流式开关
- 支持流式输出（streaming tokens）
- Provider 为 DB 存储的一等实体（见 §Provider 管理），支持 OpenAI / Anthropic / Google / DeepSeek / **OpenAI 兼容协议**（接 Ollama / vLLM / 硅基流动等）

### 3. RAG 知识检索节点
- 完整 RAG 链路：文本 → Embedding → 向量检索 (Chroma) → Reranking → 上下文注入
- 可配置：知识库选择、Top-K、相似度阈值
- 知识库管理：文档上传 → 分块 → Embedding → 入库

### 4. Agent 节点 (ReAct)
- LangGraph ReAct Agent
- LLM 自主推理，决定调用哪些 Tool（RAG 检索、TTS 合成等）
- Thought → Action → Observation 循环
- 面试核心亮点：展示 Agent 自主决策能力

### 5. TTS 音频合成节点
- LangChain Tool 封装
- 接收文本，调用 TTS 服务生成音频（当前接入 MiniMax `t2a_v2`，hex → mp3 落盘 → 返回 `/audio/{uuid}.mp3` URL）
- 抽象接口设计（`BaseTTSProvider` + `synthesize` / `synthesize_bytes` 双层接口），支持多 Provider 切换
- 复用 Provider 管理系统：节点配置只选 `provider_id` + 模型 + voice/emotion/speed，API key 加密存 DB
- **长文本分片并行合成**（计划阶段）：超过单片上限自动按句子切分 → `asyncio.gather + Semaphore(5)` 并发合成 → 按序拼接 mp3 → 通过 `node_stream` 事件推送进度
- 输出音频 URL

### 6. 结束节点 (End)
- 工作流终点；新建工作流时**默认存在于画布且不可删除**，全图强制有且仅有一个
- 声明式输出变量：`outputs: [{name, source, value}]`
  - `source = "input"`：`value` 为字面量，按原样输出
  - `source = "reference"`：`value` 为 `{{nodeId.fieldName}}`，从上游节点输出中取值
- 回答内容模板：`answer: str`，支持 `{{varName}}`（本节点输出）和 `{{nodeId.fieldName}}`（跨节点引用）两种占位符
- 运行结束时生成 `state["outputs"]`（结构化）和 `state["answer"]`（渲染后文本），一起随 `workflow_end` 事件返回

## LangGraph State 设计

```python
class WorkflowState(TypedDict, total=False):
    inputs: dict[str, Any]          # Start 收集的结构化输入，按参数名索引
    node_outputs: dict[str, dict]   # 每个节点的输出快照：{nodeId: {fieldName: value}}
    outputs: dict[str, Any]         # End 解析后的结构化输出（对外 API）
    answer: str                     # End 渲染后的回答内容（面向最终观众）
    messages: list[BaseMessage]     # LLM 对话历史

    # Legacy fields (kept for backward compatibility)
    input: str
    context: str
    llm_output: str
    audio_url: str

约定：每个中间节点在执行结束时**必须**把自己的输出写入 `state["node_outputs"][self.node_id]`，供下游通过 `{{nodeId.fieldName}}` 引用。中间节点的固定输出字段：

| 节点 | 输出字段 |
|------|---------|
| llm   | `text` |
| rag   | `context`, `documents` |
| agent | `text`, `steps` |
| tts   | `audio_url`, `duration` |
| start | 由 `inputs` schema 动态生成 |

## 变量引用语法

End 节点和任何模板字段都通过 `{{...}}` 占位符引用上游数据：

- `{{varName}}` — 本节点已声明的输出变量（优先级最高，仅在 End 节点可用）
- `{{nodeId.fieldName}}` — 任意上游节点的输出字段（如 `{{llm_1.text}}`、`{{tts_1.audio_url}}`）

解析器位于 `backend/core/template.py`，未命中的引用渲染为空字符串（保持鲁棒，不抛异常）。Compiler 层会校验 `reference` 类型的 End output 必须指向画布中实际存在的 nodeId。

状态流转示例（Start → RAG → LLM → TTS → End）：
- Start（`inputs: [{name: "topic"}]`，用户填入 `"AI 教育播客"`）→ `state.inputs = {topic: "AI 教育播客"}`
- RAG → `state.node_outputs["rag_1"] = {context: "...", documents: [...]}`
- LLM → `state.node_outputs["llm_1"] = {text: "大家好，欢迎收听..."}`
- TTS → `state.node_outputs["tts_1"] = {audio_url: "/audio/xxx.mp3", duration: 180.3}`
- End（`outputs: [{name: "audio_url", source: "reference", value: "{{tts_1.audio_url}}"}]`，`answer: "🎧 链接：{{audio_url}}"`）→ `state.outputs = {audio_url: "/audio/xxx.mp3"}`、`state.answer = "🎧 链接：/audio/xxx.mp3"`

## 前端 UI 设计

三栏布局 + 底部调试抽屉：

### 左栏：节点库
- 按分组展示：基础节点 / 大模型 / 工具
- 拖拽添加到画布

### 中间：React Flow 画布
- 节点拖拽、连线、选中
- 自定义节点渲染（每种节点有独立样式和 icon）
- 连接锚点（Handle）+ 连线验证
- 底部工具栏：缩放、撤销/重做、调试按钮
- 调试时节点实时高亮执行状态

### 右栏：节点配置面板
- 选中节点后显示详细配置
- **Start 节点：输入配置** — 动态行表单，每行 `参数名 / 类型（text · number · select · file）/ 必填 / 默认值 / 选项（仅 select）`，点"添加"增加一行
- **End 节点：输出配置 + 回答内容**
  - 输出配置：动态行，每行 `参数名 / 类型（输入 · 引用）/ 值`
    - 类型 = 输入：值是手动输入的字面量
    - 类型 = 引用：值是两级下拉选择器（上游节点 → 字段），选中后写入 `{{nodeId.fieldName}}`
  - 回答内容：多行 textarea，支持在光标位置插入 `{{varName}}` 或 `{{nodeId.fieldName}}`
- LLM 节点：**Provider 实例下拉**（数据源 `/api/providers?enabled=true`）→ **模型下拉**（数据源 `/api/providers/{id}/models`，带"刷新"按钮）、Temperature 滑块、System Prompt 编辑、流式开关
- RAG 节点：知识库选择、Top-K、相似度阈值
- TTS 节点：Provider 选择、音色选择

### 底部：调试抽屉 (Debug Drawer)
- 上滑展开，支持简洁/详细两种模式切换
- **左侧**：文本输入区 + 运行按钮
- **中间（详细模式）**：执行链路，每个节点实时显示状态
  - 完成 ✓（绿色）/ 运行中 ⟳（紫色，带 streaming 标签）/ 等待 ○（灰色）
  - 显示每个节点的耗时和中间输出
  - LLM 节点支持流式文本逐字展示
- **右侧**：最终输出，包含 AI 播客音频播放器（播放/暂停、进度条、时长）
- **简洁模式**：只显示输入、loading、最终音频播放

## API 设计

### 工作流 CRUD
```
GET    /api/workflows           — 工作流列表
POST   /api/workflows           — 创建工作流
GET    /api/workflows/{id}      — 获取工作流详情
PUT    /api/workflows/{id}      — 更新工作流
DELETE /api/workflows/{id}      — 删除工作流
```

### 工作流执行
```
POST   /api/workflows/{id}/run              — 触发执行（body: {"inputs": {...}} 按 Start schema 填充）
GET    /api/workflows/{id}/runs             — 执行记录列表
GET    /api/workflows/{id}/runs/{rid}       — 执行详情
GET    /api/workflows/{id}/runs/{rid}/events — SSE 实时事件流
```

### SSE 事件格式
```
event: workflow_start   // { }
event: node_start       // { node_id, node_type, status: "running" }
event: node_stream      // { node_id, node_type, delta, seq }
                        //   delta 为字符串（LLM token）或对象 { phase, ... }
                        //   例：{ phase: "tts_chunk", current: 3, total: 7 }
                        //   例：{ phase: "thought" | "action" | "observation", text } ← Agent 节点
event: node_heartbeat   // { node_id, node_type, elapsed, message }  ← 长耗时非流式节点
event: node_end         // { node_id, node_type, status: "completed" | "failed", duration, output, error? }
event: workflow_end     // { status, duration, answer, outputs }
```
**事件契约约定**：
- `node_stream.seq` 单调递增，前端用于检测乱序/丢包（防御性校验）
- `node_end.output` 为节点最终输出；流式节点累积 `delta` 后应等于 `output` 的对应字段
- `node_heartbeat` 与 `node_stream` 互斥使用：能流式的节点（LLM/Agent）发 stream，不能流式的（TTS）发 heartbeat
- 流中断/异常时必须 emit `node_end` with `status=failed`，避免前端永远卡 running

### 知识库 (RAG)
```
POST   /api/knowledge-bases              — 创建知识库
POST   /api/knowledge-bases/{id}/upload  — 上传文档
GET    /api/knowledge-bases/{id}         — 知识库详情
POST   /api/knowledge-bases/{id}/query   — 检索测试
```

### Provider 管理

Provider 是 DB 存储的一等实体，按 `category` 分为 `llm` 和 `tts`。LLM 支持 5 种 `type`：`openai` / `anthropic` / `google` / `deepseek` / `openai_compatible`；TTS 当前支持 `fish_audio` 和 `minimax_tts`。`api_key` 使用 Fernet 对称加密存储，GET 接口返回 `sk-***` + 尾 4 位。同一 `type` 可存在多个实例（以 `name` 区分）。

```
GET    /api/providers                       — 列表（key masked）
POST   /api/providers                       — 创建 {type, name, base_url?, api_key, enabled?}
GET    /api/providers/{id}                  — 详情（key masked）
PUT    /api/providers/{id}                  — 更新（api_key 省略则不改）
DELETE /api/providers/{id}                  — 删除（被 LLM 节点引用时 409）
POST   /api/providers/{id}/test             — 鉴权测试（调用 list-models 端点，200 即通过）
GET    /api/providers/{id}/models           — 模型列表（extra_config 缓存 + ?refresh=true 强刷新）
GET    /api/providers/types                 — 类型元信息（是否需要 base_url、默认值等）供前端渲染
GET    /api/audio/{filename}                — 音频文件访问
```

模型列表策略：`openai` / `openai_compatible` / `deepseek` / `anthropic` 调用各自的 `GET /v1/models`；`google` 用 SDK `list_models` 或静态兜底。结果写入 `Provider.extra_config.cached_models`。

首次启动种子迁移：若 `providers` 表为空且 `.env` 仍有旧 key，自动建一批默认 Provider 行，然后旧 key 逐步废弃。

## 项目目录结构

### 后端 backend/
```
backend/
├── main.py                  — FastAPI 入口
├── config.py                — 配置管理
├── database.py              — SQLite 连接
├── api/
│   ├── workflows.py         — 工作流 CRUD + 执行（/run 接受 {"inputs": {...}}）
│   ├── knowledge.py         — 知识库管理
│   └── providers.py         — 模型 Provider
├── core/
│   ├── compiler.py          — Graph Compiler（画布 JSON → LangGraph）+ IO 节点唯一性校验 + provider_id 校验 + CompilerError
│   ├── engine.py            — 执行引擎 + SSE 推送（workflow_end 带 answer / outputs）
│   ├── state.py             — WorkflowState 定义（inputs / node_outputs / answer / outputs + 兼容字段）
│   ├── template.py          — {{nodeId.fieldName}} / {{varName}} 变量引用解析与模板渲染
│   └── crypto.py            — Fernet 对称加密（Provider api_key 存储用）
├── nodes/
│   ├── base.py              — BaseNode 抽象基类
│   ├── start_node.py
│   ├── llm_node.py          — LangChain ChatModel
│   ├── rag_node.py          — Retriever + VectorStore
│   ├── agent_node.py        — ReAct Agent
│   ├── tts_node.py          — TTS Tool
│   ├── end_node.py
│   └── registry.py          — 节点注册表
├── providers/
│   ├── __init__.py          — PROVIDER_REGISTRY + build_provider(db_row) 工厂
│   ├── base.py              — BaseLLMProvider（list_models / test_connection / create_chat_model）
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   ├── google_provider.py
│   ├── deepseek_provider.py
│   └── openai_compatible_provider.py
├── tts/
│   ├── base.py              — BaseTTSProvider
│   ├── fish_audio.py        — FishAudio 实现
│   └── minimax.py           — MiniMax t2a_v2 实现
├── rag/
│   ├── embeddings.py        — Embedding 模型
│   ├── vectorstore.py       — Chroma 封装
│   └── loader.py            — 文档加载 + 分块
└── models/
    ├── workflow.py
    ├── run.py
    ├── knowledge_base.py
    └── provider.py          — Provider 表（type / name / base_url / api_key_encrypted / enabled / extra_config）
```

### 前端 frontend/
```
frontend/                     — Vite + React + TypeScript
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── canvas/           — React Flow 画布
│   │   │   ├── WorkflowCanvas.tsx
│   │   │   ├── CanvasToolbar.tsx
│   │   │   └── MiniMap.tsx
│   │   ├── nodes/            — 自定义节点组件
│   │   │   ├── StartNode.tsx
│   │   │   ├── LLMNode.tsx
│   │   │   ├── RAGNode.tsx
│   │   │   ├── AgentNode.tsx
│   │   │   ├── TTSNode.tsx
│   │   │   └── EndNode.tsx
│   │   ├── panels/
│   │   │   ├── NodeLibrary.tsx    — 左侧节点库
│   │   │   └── NodeConfig.tsx     — 右侧配置面板
│   │   ├── debug/
│   │   │   ├── DebugDrawer.tsx
│   │   │   ├── ExecutionTimeline.tsx
│   │   │   ├── NodeStatusCard.tsx
│   │   │   └── AudioPlayer.tsx
│   │   └── common/
│   ├── stores/
│   │   ├── workflowStore.ts      — 画布状态
│   │   └── debugStore.ts         — 调试状态
│   ├── hooks/
│   │   ├── useSSE.ts             — SSE 事件监听
│   │   └── useWorkflow.ts
│   ├── services/
│   │   └── api.ts                — API 调用封装
│   └── types/
│       └── workflow.ts           — 类型定义
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 面试亮点

| 考点 | 项目中的体现 |
|------|-------------|
| LangGraph 图编译 | 前端画布 JSON → DAG 验证（环检测）→ 拓扑排序 → LangGraph StateGraph 编译 |
| RAG 全链路 | 文档加载 → 分块策略 → Embedding → Chroma 存储 → 相似度检索 → Reranking → 上下文注入 |
| ReAct Agent | Thought → Action → Observation 循环，LLM 自主决定工具调用 |
| LLM 流式输出 + SSE | LangChain streaming → FastAPI StreamingResponse → SSE → 前端逐 token 渲染（打字机效果）；事件回调 `on_event` 沿 engine → node → provider 透传，异步生成器分层清晰 |
| 节点级状态推送粒度 | 从「节点黑盒等待」升级为「节点内部过程可见」：LLM 走 token 级 `node_stream`，TTS 走 2s `node_heartbeat`，前端 RAF 节流避免高频重渲染 |
| TTS 长文本分片并行 | 句子级智能分片（句号 → 逗号 → 强切 + 贪心合并）+ `asyncio.gather + Semaphore(5)` 并发 + 按序拼接 mp3 + 单片重试。总耗时从 N×T 压到 ≈T，进度复用 `node_stream` 事件契约 |
| 接口正交分解 | `synthesize`（高层落盘，返回 URL）vs `synthesize_bytes`（底层纯字节）拆分，让并行编排在不污染高层接口的前提下成为可能 |
| 设计模式 | 策略模式（多 LLM Provider）、模板方法（BaseNode）、观察者（SSE 事件推送） |
| 密钥安全存储 | Fernet 对称加密 api_key，API 返回 mask、仅执行时解密；SECRET_KEY 派生与开发/生产差异化处理 |
| 多租户 Provider 抽象 | `openai_compatible` 协议类型使一套接口同时支撑 OpenAI / Ollama / vLLM / DeepSeek / 硅基流动等 OpenAI 兼容服务 |
| React Flow 交互 | 自定义节点渲染、Handle 连接验证、拖拽、画布状态序列化 |
