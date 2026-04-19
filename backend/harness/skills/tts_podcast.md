---
name: tts_podcast
description: 文本生成 + 语音合成，输出音频播客
applies_when: 用户目标涉及 "语音"、"播客"、"音频"、"朗读"
nodes: [start, llm, tts, end]
---

# TTS 播客 Skill

## 适用场景
用户想要一段音频输出。典型流程：先让 LLM 写脚本，再让 TTS 合成语音。

## 推荐节点组合
1. **Start**（inputs: `{topic: str, style: str}`）
2. **LLM**（system_prompt: "你是一位播客脚本写手...", prompt: "写一段关于 {start.topic} 的播客脚本，风格：{start.style}"）
3. **TTS**（text_source: `{llm.text}`, voice_id: 用户偏好或默认）
4. **End**（outputs: `{audio_url: {tts.audio_url}}`）

## 配置要点
- `tts.provider_id` 必填
- `tts.voice_id` 如果用户有偏好，优先使用 `project_preferences.preferred_tts_voice_id`
- `tts.max_chars` 默认 500，长文本会自动分段并行合成

## 常见坑
- TTS 的输入是 `state["llm_output"]`，所以 LLM 节点必须在 TTS 之前
- 如果 LLM 输出为空，TTS 会报错
