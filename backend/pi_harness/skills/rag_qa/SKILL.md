---
name: rag_qa
description: 基于知识库回答问题的工作流模式
applies_when: 用户目标涉及 "基于 KB 回答"、"问答"、"查文档"
nodes: [start, rag, llm, end]
requires: [knowledge_base]
---

# RAG 问答 Skill

## 适用场景
用户的问题需要参考私有文档/知识库才能准确回答。例如：
- "根据我们的产品手册回答..."
- "查一下内部 wiki 里关于...的资料"

## 推荐节点组合
1. **Start**（inputs: `{question: str, kb_id: str}`）
2. **RAG**（query: 使用模板引用 `{{start.question}}`, kb_id: `{{start.kb_id}}`, top_k: 3）
3. **LLM**（prompt: "基于以下资料回答：{{rag.context}}\n\n问题：{{start.question}}"）
4. **End**（outputs: `{answer: {{llm.text}}}`）

## 配置要点
- `rag.knowledge_base_id` 必填，且该 KB 必须已存在
- `rag.top_k` 默认 3，文档很长时可提高到 5
- LLM 的 prompt 模板中，`{rag.context}` 是检索到的文档拼接文本

## 常见坑
- `rag.context` 可能很长，prompt 中直接拼会变长；如果超长，考虑在 LLM 前加一个 summarize 步骤（但 v1 暂不支持自动 summarize，需要用户手动调 top_k）
- 如果 KB 为空，RAG 会返回空字符串，LLM 会基于自身知识回答，这可能不是用户想要的

