# 阶段设计：MiniMax TTS 专用节点接入

**日期**：2026-04-14
**状态**：已完成
**前置依赖**：Provider 管理系统（已完成）、TTS 抽象层（已完成，含 FishAudio 参考实现）

---

## 1. 目标

把 MiniMax `t2a_v2` 文字转语音接口接入现有 TTS 节点，复用 Provider 管理系统（加密存 key、统一 CRUD、下拉选择）。此阶段**只做 MiniMax 专用实现**，不做多厂商抽象升级。

## 2. 设计决策

| 项 | 选择 | 说明 |
|---|---|---|
| API Key 存储 | 复用 Provider 表 | 不在节点配置内明文存 key |
| Provider 分类 | 新增 `category` 字段 (`llm` \| `tts`) | 默认 `llm`，向后兼容 |
| 音频返回形式 | 方式 A：落盘 + URL | 复用现有 `/audio/{uuid}.mp3` 机制 |
| 模型列表 | 硬编码 | MiniMax 无公开 list-models 端点 |
| 连接测试 | 发送最短合成请求 | 如 `"你好"`，HTTP 200 + `base_resp.status_code=0` 判成功 |
| 节点配置暴露项 | `provider_id` / `model` / `voice_id` / `emotion` / `speed` | 其余（pitch/vol/sample_rate/format）使用默认值 |

## 3. 接口规格

**请求**：`POST https://api.minimaxi.com/v1/t2a_v2`
**鉴权**：`Authorization: Bearer {api_key}`
**请求体关键字段**：
```json
{
  "model": "speech-2.8-hd",
  "text": "...",
  "stream": false,
  "voice_setting": {"voice_id": "male-qn-qingse", "speed": 1, "vol": 1, "pitch": 0, "emotion": "happy"},
  "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1}
}
```
**响应**：`data.audio` 为 **hex 编码的 MP3 二进制**，`bytes.fromhex(...)` 解码后直接写 `.mp3` 文件。

## 4. 执行步骤

### Step 1 — Provider 表加 `category` 字段
- `backend/models/provider.py`：新增 `category = Column(String(16), default="llm", nullable=False)`
- 数据库迁移：`ALTER TABLE providers ADD COLUMN category VARCHAR(16) NOT NULL DEFAULT 'llm'`
- `backend/api/providers.py` 的 create/list/response schema 增加 `category`
- 列表接口支持 `?category=tts` 过滤
- 测试：`test_providers_api.py` 增加 category 过滤用例

### Step 2 — 实现 `MiniMaxTTSProvider`
- 新建 `backend/tts/minimax.py`
- 构造签名：`__init__(self, api_key: str, model: str = "speech-2.8-hd", base_url: str = "https://api.minimaxi.com")`
- `synthesize(text, voice, output_dir, voice_setting_overrides=None) -> str`：
  - POST `/v1/t2a_v2`
  - 校验 `base_resp.status_code == 0`
  - `audio_bytes = bytes.fromhex(resp["data"]["audio"])`
  - 写入 `{output_dir}/{uuid}.mp3`
  - 返回 `/audio/{uuid}.mp3`
- 暴露 `synthesize` 的 `voice_setting` 扩展参数（emotion/speed）
- 单测：mock httpx，验证 hex 解码路径、请求体形状

### Step 3 — 改造 TTSNode 走 Provider 系统
- `backend/nodes/tts_node.py`：
  - 从 `config["provider_id"]` 查 Provider 记录
  - 解密 `api_key_encrypted`
  - 按 `provider.type` 从注册表实例化（`minimax_tts` → `MiniMaxTTSProvider`，保留 `fish_audio` 兼容）
  - 读取 `config["model"]` / `config["voice_id"]` / `config["emotion"]` / `config["speed"]`
  - 上游文本来源仍走 `state` / 模板解析（和现有 IO 变量契约一致）
- 删除 `TTS_PROVIDERS` 硬编码字典，改为 `TTS_PROVIDER_REGISTRY: {"fish_audio": ..., "minimax_tts": ...}`
- 更新 `test_nodes.py` 中 TTSNode 相关用例

### Step 4 — MiniMax 连接测试端点
- `backend/api/providers.py` 的 `POST /providers/{id}/test`：
  - 当 `category=tts` 且 `type=minimax_tts` 时，发送 `text="你好"` 最短合成请求
  - `base_resp.status_code == 0` → 返回 `{ok: true}`
  - 否则返回错误信息
- 单测覆盖成功/失败分支

### Step 5 — 前端：Provider 管理页 category 支持
- `frontend/src/types/provider.ts`：Provider 类型加 `category: 'llm' | 'tts'`
- Provider 列表页：按 category 分 Tab 或分组；新建表单加 category 下拉 + 对应 type 下拉联动（llm → openai/anthropic/…；tts → minimax_tts/fish_audio）
- API 客户端 `api.ts`：list 支持 `category` 参数

### Step 6 — 前端：TTS 节点配置面板
- `frontend/src/components/panels/NodeConfig.tsx` 中 TTS 分支：
  - Provider 下拉：`GET /providers?category=tts`
  - Model 下拉：MiniMax 写死 `["speech-2.8-hd", "speech-2.5-hd"]`（`fish_audio` 走现有逻辑）
  - Voice ID 输入框（先手填，未来再做预设列表）
  - Emotion 下拉：`happy / sad / angry / neutral / …`
  - Speed 数字输入（0.5–2.0，默认 1.0）
- 保存到 `node.data.config`：`{provider_id, model, voice_id, emotion, speed}`

### Step 7 — 验证
- 端到端：Input → LLM → TTS（MiniMax）→ Output，观察 DebugDrawer 的 AudioPlayer 能否播放
- 边界：key 错误、文本为空、provider 未启用、模型不存在
- 回归：FishAudio 节点仍能运行

## 5. 验收标准

1. Provider 表有 `category` 字段，现有数据默认 `llm`，无破坏性迁移
2. 能通过 Provider 管理界面创建一个 `minimax_tts` Provider 并通过连接测试
3. TTS 节点配置面板可选择 MiniMax Provider 和模型、voice、emotion、speed
4. 完整工作流运行后 DebugDrawer 能播放合成音频
5. FishAudio 路径保持可用（回归）
6. 所有新增逻辑有单元测试覆盖

## 6. 非目标（明确不做）

- TTS 多厂商抽象升级（阿里百炼 / Azure / ElevenLabs 等）
- 语音预设/克隆语音上传
- 流式合成 (`stream: true`)
- 字幕 (`subtitle_enable`)
- Pronunciation dict 自定义发音

## 7. 风险与备注

- MiniMax 计费按字符，连接测试的最短请求也会产生少量费用，需在 UI 提示
- hex 响应体体积 ≈ 实际 mp3 的 2 倍，大文本合成时注意超时设置（建议 60s）
- 语音预设 voice_id 当前靠用户手填，后续可增加 MiniMax 官方音色预设表
