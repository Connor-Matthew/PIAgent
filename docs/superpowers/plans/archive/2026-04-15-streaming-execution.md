# 阶段设计：节点级流式执行（LLM Token Streaming + 节点心跳）

**日期**：2026-04-15
**状态**：待执行
**前置依赖**：MiniMax TTS 阶段完成、SSE 通道已就绪（`node_stream` 事件类型已在前端预留）

---

## 1. 目标

把工作流执行从「节点级动态、节点内黑盒」升级为「节点内部也实时可见」：

- **LLM / Agent 节点**：token 级流式渲染（打字机效果）
- **TTS / RAG / 其他长耗时节点**：心跳事件 + 进度提示，避免「死等转圈」
- **前端**：节点卡片实时显示中间文本 / 进度，不再只有「running spinner → 完成跳出整段文字」

## 2. 设计决策

| 项 | 选择 | 说明 |
|---|---|---|
| 事件类型 | 复用预留的 `node_stream` + 新增 `node_heartbeat` | 类型定义已在 `frontend/src/types/workflow.ts:59` 占位 |
| 流式协议 | SSE（沿用现有通道） | 不引入 WebSocket，保持架构一致 |
| LLM SDK 调用 | 切换到 `stream=True` + async generator | OpenAI/Anthropic/DeepSeek/Google 都支持 |
| Chunk 隔离 | 事件带 `node_id`，前端按 node_id 维护独立 buffer | 避免并行/嵌套节点串台 |
| 心跳频率 | 每 2s 一次 | 平衡感知与开销 |
| 失败处理 | 流中断时 emit `node_end` with `status=failed` | 不留前端永远等待状态 |
| 向后兼容 | 不流式的节点（Input/Output/RAG）保持原行为 | 只在确实长耗时的节点接入 |

## 3. 事件契约扩展

### 3.1 `node_stream`（新接通，类型已存在）
```json
{
  "type": "node_stream",
  "node_id": "llm_1",
  "node_type": "llm",
  "delta": "今天",
  "seq": 12
}
```
- `delta`：本次增量文本（不是累计）
- `seq`：单调递增，前端用于检测乱序/丢包（SSE 理论上有序，做防御性校验）

### 3.2 `node_heartbeat`（新增）
```json
{
  "type": "node_heartbeat",
  "node_id": "tts_1",
  "node_type": "tts",
  "elapsed": 2.1,
  "message": "合成中..."
}
```
- 用于无法 token 流的节点（TTS、外部 API 调用）
- 前端展示为节点卡片上的「已运行 X 秒」+ 可选状态文案

### 3.3 不变的事件
`workflow_start` / `node_start` / `node_end` / `workflow_end` 行为不变，只是 `node_end` 的 `output.text` 应该等于所有 `node_stream.delta` 拼接结果（前端可校验）。

## 4. 执行步骤

### Step 1 — 引擎层支持事件回调透传
- `backend/core/engine.py`：在调用 `node_instance.execute(...)` 时把 `on_event` 透传给节点（目前只在 engine 主循环用）
- `backend/nodes/base.py`：`BaseNode.execute` 签名增加 `on_event: Callable | None = None` 可选参数，默认节点不使用
- 引入辅助方法 `BaseNode._emit(on_event, event_dict)`，统一封装事件发射

### Step 2 — LLM 节点改造为流式
- `backend/nodes/llm_node.py`：
  - 调用 provider 时使用 `stream=True`
  - `async for chunk in stream:`，每个 chunk emit `node_stream` 事件
  - 累积 `full_text`，最终写入 `state["node_outputs"][node_id]["text"]`
  - 维护本地 `seq` 计数器
- `backend/providers/base.py` & 各 provider 子类：
  - `chat_completion` 增加 `stream: bool = False` 参数
  - 流式时返回 async generator，非流式保持原 dict 返回
  - OpenAI / DeepSeek / OpenAI 兼容：用官方 SDK 的 stream 模式
  - Anthropic：使用 `client.messages.stream()`
  - Google：使用 `generate_content(..., stream=True)`
- 单测：mock provider 流式输出，断言 emit 顺序 + 累积文本正确

### Step 3 — Agent 节点流式（可选阶段，复杂度更高）
- `backend/nodes/agent_node.py`：LangGraph `create_react_agent` 支持 `astream_events`
- 把 `on_chain_start` / `on_llm_stream` / `on_tool_start` / `on_tool_end` 转换成 `node_stream` 事件
- `delta` 字段加 `phase: "thought" | "action" | "observation"` 标签
- 前端 NodeStatusCard 按 phase 分段渲染

### Step 4 — TTS / 长耗时节点心跳
- `backend/nodes/tts_node.py`：
  - 用 `asyncio.create_task` 包装 `provider.synthesize(...)`
  - 主协程 `while not task.done():` 每 2s emit `node_heartbeat`
  - 任务完成后取消心跳循环
- 抽出公共工具：`backend/core/heartbeat.py` 提供 `async def with_heartbeat(coro, on_event, node_id, interval=2.0)` 装饰器
- 单测：mock 一个 5s 任务，断言至少 emit 2 次心跳

### Step 5 — 前端 Store 接入新事件
- `frontend/src/stores/debugStore.ts`：
  - `node_stream`：找到对应 node 的 status card，append `delta` 到 `streamingText` 字段（按 `seq` 排序，丢弃重复）
  - `node_heartbeat`：更新该节点的 `elapsed` + `message`
  - `node_end`：用 `output` 替换 `streamingText`（最终态），清理 `seq` buffer
- `frontend/src/types/workflow.ts`：增加 `node_heartbeat` 到事件 union 类型
- `frontend/src/hooks/useSSE.ts`：注册 `addEventListener('node_heartbeat', ...)`

### Step 6 — 前端 NodeStatusCard 渲染
- `frontend/src/components/debug/NodeStatusCard.tsx`：
  - LLM/Agent 节点：渲染 `streamingText`（打字机效果，CSS 加 cursor 闪烁）
  - TTS/其他节点：渲染 `elapsed` 计时 + `message`
  - 完成后切换为最终输出展示
- 性能：高频 chunk 使用 `requestAnimationFrame` 节流，避免 React 每 token 重渲染

### Step 7 — 验证
- 端到端：Input → LLM (流式) → TTS (心跳) → Output
  - 观察 LLM 节点卡片文字逐字出现
  - 观察 TTS 节点卡片计时器跳动
- 边界：
  - LLM 流中途中断（强杀连接） → 前端能否正确进入 failed
  - 多 LLM 节点并行执行（未来 DAG 并发场景）→ chunk 不串台
  - 心跳与节点完成竞态 → 不会在 `node_end` 后还发心跳

## 5. 验收标准

1. LLM 节点执行时，前端节点卡片文字逐字出现（不是一次性整段）
2. TTS 节点执行时，前端节点卡片显示「已运行 X.X 秒」实时跳动
3. 流式响应的最终拼接文本与非流式模式输出一致（回归保证）
4. 所有 4 个 LLM provider（OpenAI / Anthropic / DeepSeek / Google）流式都跑通
5. 流中断/网络异常时节点状态正确转为 failed，不卡 running
6. 关闭流式开关（节点配置加 `stream: false`）能回退到原行为
7. 新增逻辑有单测覆盖（mock provider 流 + heartbeat 至少触发一次）

## 6. 非目标（明确不做）

- WebSocket 替换 SSE
- 流式 TTS（MiniMax 接口本身不支持）
- 节点执行的暂停/恢复/取消（cancellation 是另一个独立阶段）
- 前端虚拟滚动（除非长文本卡顿明显）
- 多 SSE 通道复用（一个 run 一个连接的现状不变）

## 7. 风险与备注

- **背压**：高速 LLM（如 Groq）token 速率可能超过前端渲染能力，必须做 RAF 节流
- **断线重连**：SSE 断线后不支持续传，重新跑整个 run 是当前唯一选项（未来再考虑断点续传）
- **provider 流式 API 差异大**：Anthropic 的 stream 是 event-based，Google 的是 chunked text，需要在 provider 层抹平差异
- **事件量级**：一段 500 token 的 LLM 输出会产生 500 个 SSE 事件，DevTools 网络面板会很长——这是预期的，不是性能问题
- **测试成本**：流式 mock 比非流式复杂，建议封装一个 `MockStreamProvider` 测试工具

## 8. 简历/面试讲点

- SSE vs WebSocket 选型：单向推送够用，HTTP/2 多路复用、自动重连、运维简单
- 节点级 vs token 级状态推送：从「黑盒等待」到「过程可见」的体验跃迁
- 异步生成器 + 事件回调透传的清晰分层（engine → node → provider）
- 心跳模式补足非流式接口的体验缺口
- 前端 RAF 节流应对高频更新的工程权衡
