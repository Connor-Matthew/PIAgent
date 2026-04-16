# 阶段设计：TTS 长文本分片并行合成

**日期**：2026-04-15
**状态**：待执行
**前置依赖**：MiniMax TTS 阶段完成、流式执行阶段已落地（复用 `node_stream` 事件做进度回调）

---

## 1. 目标

解决 AI 播客场景下「LLM 生成的长脚本（数千至上万字）→ TTS 节点单次 API 调用必然失败」的问题。在 TTS 节点内部实现：

- **智能分片**：按语义边界切分长文本，单片不超过 provider 限额
- **并行合成**：用 `asyncio.gather + Semaphore` 控制并发，把总耗时从串行 N×T 压到 ≈T
- **顺序拼接**：按输入顺序拼接 mp3 二进制，输出单一音频 URL
- **进度回调**：每完成一片 emit 一个 `node_stream` 事件，前端可显示「3/7 片」
- **失败重试 + 部分降级**：单片失败重试，全部失败才整体 fail

## 2. 设计决策

| 项 | 选择 | 说明 |
|---|---|---|
| 分片粒度 | 句子级，单片 ≤ 500 字 | MiniMax 限额约 5000 字，留足 buffer |
| 切分边界 | 优先中文句号/问号/感叹号 → 换行 → 逗号 → 强切 | 保证语义完整、不切断词 |
| 并发上限 | `asyncio.Semaphore(5)` | 默认值，可在节点配置 `max_concurrency` 覆盖 |
| 拼接方式 | 直接 bytes concat（同 codec 前提） | 简单、零依赖；如有兼容性问题再引 `pydub` |
| 顺序保证 | `asyncio.gather(...)` 返回顺序 == 输入顺序 | 不需要额外 index 标记 |
| 进度事件 | 复用 `node_stream`，`delta` 字段携带进度 dict | 与流式执行阶段事件契约统一 |
| 重试策略 | 单片失败指数退避重试 2 次 | 第三次失败整体 fail |
| 短文本旁路 | 长度 ≤ 单片上限时不分片，直接走原路径 | 避免无谓开销 |

## 3. 执行步骤

### Step 1 — 文本分片器
- 新建 `backend/tts/chunker.py`
- `def split_text(text: str, max_chars: int = 500) -> list[str]`：
  - 第一遍：按 `。！？\n` 切句
  - 第二遍：超长句按 `，；` 二次切
  - 第三遍：仍超长则强切（极端情况）
  - 合并：贪心合并相邻短片直到接近 `max_chars`
- 单测：
  - 短文本不分片
  - 多句长文本按句号切
  - 单句超长按逗号切
  - 无标点超长强切
  - 边界：空字符串、单字符、纯标点

### Step 2 — Provider 接口扩展（保持向下兼容）
- `backend/tts/base.py`：
  - 现有 `synthesize(text, voice, output_dir) -> str` 不动（返回 URL 的高层接口）
  - 新增 `synthesize_bytes(text, voice, **kwargs) -> bytes`，只负责拿到音频 bytes，不落盘
- `backend/tts/minimax.py`：
  - 把现有 `synthesize` 实现拆成 `synthesize_bytes`（hex 解码）+ 落盘逻辑
  - `synthesize` 改为调用 `synthesize_bytes` 后写文件

### Step 3 — 并行合成编排
- 新建 `backend/tts/parallel.py`
- `async def synthesize_long_text(provider, text, voice, output_dir, max_chars=500, max_concurrency=5, on_progress=None) -> str`：
  ```python
  chunks = split_text(text, max_chars)
  if len(chunks) == 1:
      return await provider.synthesize(text, voice, output_dir)  # 旁路

  sem = asyncio.Semaphore(max_concurrency)
  total = len(chunks)
  done = 0

  async def one(idx, chunk):
      nonlocal done
      async with sem:
          audio = await with_retry(lambda: provider.synthesize_bytes(chunk, voice), retries=2)
          done += 1
          if on_progress:
              await on_progress({"current": done, "total": total})
          return audio

  results = await asyncio.gather(*[one(i, c) for i, c in enumerate(chunks)])
  merged = b"".join(results)
  filename = f"{uuid.uuid4().hex}.mp3"
  path = os.path.join(output_dir, filename)
  with open(path, "wb") as f:
      f.write(merged)
  return f"/audio/{filename}"
  ```
- 重试工具 `with_retry` 用指数退避 1s / 2s
- 单测：mock provider，验证并发上限、顺序、单片重试、全部失败

### Step 4 — TTSNode 接入
- `backend/nodes/tts_node.py`：
  - 读取 `config["max_chars"]`（默认 500）和 `config["max_concurrency"]`（默认 5）
  - 调用 `synthesize_long_text(...)`，把 `on_event` 包装成 `on_progress` 回调（emit `node_stream`）
  - 进度事件 payload：`{"type": "node_stream", "node_id": ..., "delta": {"phase": "tts_chunk", "current": 3, "total": 7}}`
- 短文本走旁路时不发进度事件（避免噪音）

### Step 5 — 前端进度渲染
- `frontend/src/components/debug/NodeStatusCard.tsx`：
  - TTS 节点收到 `node_stream` 且 `delta.phase === "tts_chunk"` 时，渲染进度条「合成中 3/7 片」
  - 完成后切换为 AudioPlayer
- `frontend/src/types/workflow.ts`：`delta` 字段类型扩展为 `string | { phase: string; [k: string]: any }`

### Step 6 — 配置面板暴露
- `frontend/src/components/panels/NodeConfig.tsx` TTS 分支：
  - 新增「单片字数上限」数字输入（默认 500，范围 200–1000）
  - 新增「最大并发」数字输入（默认 5，范围 1–10）
  - 折叠在「高级」区域，普通用户无感

### Step 7 — 验证
- 端到端：用 5000 字播客脚本跑一次完整流程
  - 验证总耗时 ≈ 单片耗时 × ceil(总片数 / 并发数)
  - 验证拼接后的 mp3 能完整播放、无明显断裂
  - 验证前端进度条逐步推进
- 边界：
  - 100 字短文本：走旁路，无进度事件
  - 故意把 `max_chars=50` 强制大量分片：验证并发上限确实生效
  - mock 单片必失败：验证整体 fail 路径
  - 网络抖动模拟：单片首次失败 + 重试成功

## 4. 验收标准

1. 5000 字脚本能成功合成单一可播放 mp3
2. 总耗时显著低于串行（5 并发时应 ≈ 1/5）
3. 短文本（≤ 单片上限）走原路径，行为与改造前一致（回归保证）
4. 单片失败自动重试 2 次，全部失败才整体 fail
5. 前端能看到「X/N 片」进度推进
6. 节点配置可调整 `max_chars` 和 `max_concurrency`，不配则用默认值
7. 分片器单测覆盖各类边界（空、单字、超长无标点等）

## 5. 非目标（明确不做）

- 跨 provider 的统一长文本接口（只针对 MiniMax 这一具体场景）
- 流式 TTS（MiniMax 接口本身不支持）
- 分片间的 prosody 平滑（句末停顿、音量归一化等专业音频处理）
- 失败片段的部分音频导出（要么全成功要么整体 fail）
- 分片缓存（同句相同 voice 直接复用）—— 未来优化
- 前端音频波形可视化

## 6. 风险与备注

- **拼接质量**：MiniMax 同请求参数下生成的 mp3 应该 codec 一致，bytes 直拼可行。如果实测发现衔接处「咔哒」声明显，再引入 `pydub`/`ffmpeg` 做交叉淡入。
- **并发触发限流**：MiniMax 可能有 QPS 限制，5 并发是保守值；如收到 429 应在 retry 中识别并加大退避
- **句子超长且无逗号**：极端情况会强切，可能产生不自然的停顿。可在 UI 提示「检测到 N 处强制切分」
- **计费透明度**：分片不增加字符数计费，但用户可能误以为「分了片所以更贵」，UI 文案要解释
- **顺序假设**：`asyncio.gather` 返回顺序确实 == 输入顺序，这是 Python 文档保证的，不需要 index 标记。但代码里加一行注释说明，避免后人误改
- **磁盘开销**：长音频 mp3 可能 10MB+，需要后续做「过期 run 音频清理」（独立阶段）

## 7. 简历/面试讲点

- 「为什么不用流式？」→ MiniMax 接口本身不支持，转而用「分片 + 并行 + 进度推送」达到等价的「过程可见 + 总耗时压缩」
- **分片算法的权衡**：纯长度切（简单但割裂语义）vs 句子边界（自然但片长方差大）vs 贪心合并（折中方案，最终采用）
- **并发控制**：Semaphore 而非无限 gather，工程视角的「保护下游」意识
- **顺序保证 + 异步并发**：`asyncio.gather` 返回顺序的语义点
- **失败模型**：单片重试 vs 整体降级 的策略选择
- **接口分层**：`synthesize` (高层、落盘) vs `synthesize_bytes` (底层、纯字节) 的拆分让并行编排成为可能——这是「正交分解」的实际案例
- **与流式 LLM 的对偶**：LLM 是「过程推送」，TTS 是「分片推送」，本质都是把不可见的长任务拆成可见的进度
