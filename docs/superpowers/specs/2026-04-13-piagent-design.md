# PIAgent — AI Agent 工作流编排平台 设计文档

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
- 工作流入口
- 接收用户文本输入，写入 LangGraph State
- 触发图执行

### 2. 大模型节点 (LLM)
- 通过 LangChain ChatModel 调用 LLM
- 可配置：模型提供商、模型选择、Temperature、System Prompt
- 支持流式输出（streaming tokens）
- 多 Provider：OpenAI / Anthropic / Google / DeepSeek

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
- 接收文本，调用 TTS 服务生成音频
- 抽象接口设计（BaseTTSProvider），支持多 Provider 切换
- 输出音频 URL

### 6. 结束节点 (End)
- 工作流终点
- 汇总所有节点输出（文本 + 音频），返回最终结果给前端

## LangGraph State 设计

```python
class WorkflowState(TypedDict):
    input: str                  # 用户原始输入
    messages: list[BaseMessage] # LLM 对话历史
    context: str                # RAG 检索的上下文
    llm_output: str             # LLM 生成的文本
    audio_url: str              # TTS 生成的音频 URL
    node_outputs: dict          # 各节点输出快照
```

状态流转示例：
- Start → `state.input = "AI 教育播客"`
- RAG → `state.context = "检索到的相关文档内容..."`
- LLM → `state.llm_output = "大家好，欢迎收听..."`
- TTS → `state.audio_url = "/audio/xxx.mp3"`
- End → 返回完整 state 给前端

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
- LLM 节点：Provider 选择、模型选择、Temperature 滑块、System Prompt 编辑、流式开关
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
POST   /api/workflows/{id}/run              — 触发执行
GET    /api/workflows/{id}/runs             — 执行记录列表
GET    /api/workflows/{id}/runs/{rid}       — 执行详情
GET    /api/workflows/{id}/runs/{rid}/events — SSE 实时事件流
```

### SSE 事件格式
```
event: node_start    // { node_id, status: "running" }
event: node_stream   // { node_id, chunk: "文本片段" }  ← LLM 流式
event: node_end      // { node_id, status: "completed", duration, output }
event: workflow_end  // { status: "completed", duration }
```

### 知识库 (RAG)
```
POST   /api/knowledge-bases              — 创建知识库
POST   /api/knowledge-bases/{id}/upload  — 上传文档
GET    /api/knowledge-bases/{id}         — 知识库详情
POST   /api/knowledge-bases/{id}/query   — 检索测试
```

### 模型 & 配置
```
GET    /api/providers                  — Provider 列表
GET    /api/providers/{name}/models    — 模型列表
POST   /api/providers/{name}/test      — 连通性测试
GET    /api/audio/{filename}           — 音频文件访问
```

## 项目目录结构

### 后端 backend/
```
backend/
├── main.py                  — FastAPI 入口
├── config.py                — 配置管理
├── database.py              — SQLite 连接
├── api/
│   ├── workflows.py         — 工作流 CRUD + 执行
│   ├── knowledge.py         — 知识库管理
│   └── providers.py         — 模型 Provider
├── core/
│   ├── compiler.py          — Graph Compiler（画布 JSON → LangGraph）
│   ├── engine.py            — 执行引擎 + SSE 推送
│   └── state.py             — WorkflowState 定义
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
│   ├── base.py              — BaseLLMProvider
│   ├── openai.py
│   ├── anthropic.py
│   ├── google.py
│   └── deepseek.py
├── tts/
│   ├── base.py              — BaseTTSProvider
│   └── fish_audio.py
├── rag/
│   ├── embeddings.py        — Embedding 模型
│   ├── vectorstore.py       — Chroma 封装
│   └── loader.py            — 文档加载 + 分块
└── models/
    ├── workflow.py
    ├── run.py
    └── knowledge_base.py
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
| LLM 流式输出 + SSE | LangChain streaming → FastAPI StreamingResponse → SSE → 前端逐 token 渲染 |
| 设计模式 | 策略模式（多 LLM Provider）、模板方法（BaseNode）、观察者（SSE 事件推送） |
| React Flow 交互 | 自定义节点渲染、Handle 连接验证、拖拽、画布状态序列化 |
