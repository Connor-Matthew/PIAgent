---
name: io_contract
description: Start/End 字段设计指南，帮助模型正确设计输入输出契约
applies_when: 用户目标涉及多输入、多输出、复杂数据流
nodes: []
---

# Start / End 字段设计指南

## Start 节点 inputs 设计

`inputs` 是一个字段列表，每个字段有：
- `name`: 字段名（英文，驼峰或下划线）
- `type`: 数据类型（`string`, `number`, `boolean`）
- `required`: 是否必填
- `description`: 字段用途描述（给前端用户看的）

示例：
```json
[
  {"name": "question", "type": "string", "required": true, "description": "用户问题"},
  {"name": "style", "type": "string", "required": false, "description": "回答风格"}
]
```

## End 节点 outputs 设计

`outputs` 是一个输出映射列表，每个映射有：
- `name`: 输出字段名
- `source`: `"reference"`（引用上游节点输出）或 `"static"`（固定值）
- `value`: 当 source=reference 时，格式为 `{{nodeId.fieldName}}`（双大括号）；当 source=static 时，就是固定字符串

示例：
```json
[
  {"name": "answer", "source": "reference", "value": "{{llm.text}}"},
  {"name": "source", "source": "static", "value": "PIAgent"}
]
```

## 工具调用示例
```json
{"node_type": "start", "config": {"inputs": [{"name": "question", "type": "string", "required": true}]}}
{"node_type": "end", "config": {"outputs": [{"name": "answer", "source": "reference", "value": "{{llm.text}}"}]}}
```

## 模板引用规则
- 格式必须是 `{{nodeId.fieldName}}`（双大括号），严格匹配
- `nodeId` 是上游节点的 `id`
- `fieldName` 是该节点在 `state["node_outputs"][nodeId]` 中写入的 key
- 常见 fieldName：
  - `start` 节点：`inputs` 中定义的各个字段名
  - `llm` 节点：`text`
  - `rag` 节点：`context`
  - `tts` 节点：`audio_url`
  - `agent` 节点：`text`

