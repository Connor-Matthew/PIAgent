---
name: agent_node
description: 多步 Agent 节点（工具循环），让 LLM 自主决定调用哪些工具
applies_when: 用户目标涉及 "agent"、"工具调用"、"自主决策"、"多步推理"
nodes: [start, agent, end]
---

# Agent 节点 Skill

## 适用场景
用户需要一个能自主决策、调用多个工具的 AI agent。例如：
- "做一个能查文档然后生成音频的 agent"
- "一个能搜索知识库并回答问题的 agent"

## 推荐节点组合
1. **Start**（inputs: `{query: str}`）
2. **Agent**（system_prompt: 角色设定, tools: ["rag", "tts"], provider_id: 必填）
3. **End**（outputs: `{result: {agent.text}}`）

## 配置要点
- `agent.tools` 是字符串列表，当前支持 `"rag"` 和 `"tts"`
- Agent 节点内部使用 ReAct 循环，会自己决定什么时候调用工具、什么时候给出最终答案
- `provider_id` 和 `model` 同 LLM 节点

## 常见坑
- Agent 节点的输出字段是 `agent.text`（最终答案文本），不是 `llm.text`
- 不要在一个 workflow 里同时用 Agent 节点和普通 LLM 节点做同样的事，选一个即可
