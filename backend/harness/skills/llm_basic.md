---
name: llm_basic
description: 单次 LLM 调用，把输入文本传给大模型，拿到文本输出。
applies_when: 用户目标只涉及"生成文本"、"回答问题"、"翻译"、"摘要"等单次 LLM 任务
nodes: [start, llm, end]
---

# LLM 基础 Skill

## 适用场景
用户只需要一次大模型调用，不需要知识库检索、不需要语音合成、不需要多轮工具循环。

## 推荐节点组合
1. **Start**（inputs: `{question: str}`）
2. **LLM**（system_prompt: 根据目标定制, model: gpt-4o 或同等级）
3. **End**（outputs: `{answer: {llm.text}}`）

## 配置要点
- `llm.provider_id` 必填，否则校验会失败
- `temperature` 默认 0.7；创意任务可提高到 0.9
- `system_prompt` 尽量具体，把用户目标翻译成明确的角色设定

## 常见坑
- 不要漏 End 节点，否则图不合法
- Start 到 LLM 的 edge 必须存在，否则 LLM 收不到输入
