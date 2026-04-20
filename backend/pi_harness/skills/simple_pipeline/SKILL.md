---
name: simple_pipeline
description: Start → LLM → End 最简单的直通工作流
applies_when: 用户目标最简单，只需要一次 LLM 调用
nodes: [start, llm, end]
---

# 简单直通 Skill

## 适用场景
用户目标非常明确且简单，只需要一个大模型调用。这是 `llm_basic` 的极简版。

## 推荐节点组合
1. **Start**
2. **LLM**
3. **End**

## 配置要点
- Start 的 `inputs` 至少包含一个字段（如 `input: str`）
- LLM 的 `system_prompt` 把用户目标翻译进去
- End 的 `outputs` 映射 `{result: {{llm.text}}}`

## 工具调用示例
```json
{"node_type": "start", "config": {"inputs": [{"name": "input", "type": "string", "required": true}]}}
{"node_type": "llm", "config": {"provider_id": 1, "model": "gpt-4o", "system_prompt": "You are a helpful assistant."}}
{"node_type": "end", "config": {"outputs": [{"name": "result", "source": "reference", "value": "{{llm.text}}"}]}}
```

## 常见坑
- 不要做成 Start → End 直连，否则 validator 会报 `too_simple` warning

