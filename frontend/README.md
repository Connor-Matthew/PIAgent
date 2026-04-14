# PIAgent - AI Agent 工作流编排平台

PIAgent 是一个可视化 AI Agent 工作流编排平台，支持通过拖拽方式构建、编辑和运行多节点 AI 工作流。

![PIAgent](./docs/preview.png)

## 技术栈

- **后端**: Python 3.12 + FastAPI + LangGraph + SQLAlchemy + SQLite + Chroma
- **前端**: Vite + React 18 + TypeScript + TailwindCSS + React Flow + Zustand

## 核心特性

- 🎨 **可视化画布**: 基于 React Flow 的节点式工作流编辑器
- 🤖 **多节点类型**: Start、LLM、RAG、Agent、TTS、End
- 🔌 **多模型支持**: OpenAI、Anthropic、Google、DeepSeek
- 📚 **知识库集成**: 基于 Chroma 的 RAG 向量检索
- 🔊 **语音合成**: Fish Audio TTS 节点
- 🐛 **实时调试**: SSE 流式事件，支持分块输出与音频播放
- 💾 **工作流持久化**: SQLite 存储，支持 CRUD 操作

## 快速开始

### 1. 安装依赖

```bash
# 后端
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 前端
cd frontend
npm install
```

### 2. 环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 .env，填入各厂商 API Key
```

### 3. 启动服务

```bash
# 后端
python -m backend.main

# 前端（新终端）
cd frontend
npm run dev
```

访问 http://localhost:5173

### 4. 运行测试

```bash
cd backend
pytest -q
```

## 项目结构

```
.
├── backend/
│   ├── api/            # FastAPI 路由
│   ├── compiler.py     # DAG 编译器
│   ├── engine.py       # 执行引擎
│   ├── nodes/          # 节点实现
│   ├── rag/            # RAG / Chroma
│   ├── providers/      # LLM / TTS 提供商
│   └── tests/          # 单元测试
└── frontend/
    ├── src/
    │   ├── components/ # React 组件
    │   ├── stores/     # Zustand 状态
    │   ├── hooks/      # 自定义 Hooks
    │   ├── services/   # API 封装
    │   └── types/      # TypeScript 类型
    └── README.md
```

## 支持的节点

| 节点 | 说明 |
|------|------|
| Start | 接收用户输入，写入共享状态 |
| LLM | 调用大语言模型，支持 System Prompt 和流式输出 |
| RAG | 基于知识库的向量检索增强 |
| Agent | ReAct Agent，支持工具调用 |
| TTS | 语音合成，输出音频文件 |
| End | 收集最终结果并返回 |

## API 端点

### 工作流
- `GET /api/workflows` - 列出工作流
- `POST /api/workflows` - 创建工作流
- `GET /api/workflows/{id}` - 获取工作流
- `PUT /api/workflows/{id}` - 更新工作流
- `DELETE /api/workflows/{id}` - 删除工作流
- `POST /api/workflows/{id}/run` - 运行工作流
- `GET /api/workflows/{id}/runs/{run_id}/events` - SSE 事件流

### 提供商
- `GET /api/providers` - 列出可用 LLM 提供商
- `GET /api/providers/{name}/models` - 列出模型
- `POST /api/providers/{name}/test` - 测试连接

### 知识库
- `POST /api/knowledge-bases` - 创建知识库
- `POST /api/knowledge-bases/{id}/upload` - 上传文档
- `POST /api/knowledge-bases/{id}/query` - 查询知识库

## 开发计划

详见根目录 `docs/plan.md`

## License

MIT
