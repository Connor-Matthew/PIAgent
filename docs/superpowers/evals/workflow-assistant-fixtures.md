# Workflow Assistant Manual Eval Fixtures

Score each answer: 0 = wrong, 1 = partially correct, 2 = accurate and actionable.

1. RAG node has no `knowledge_base_id`; ask: “为什么 RAG 没有结果？”
2. LLM prompt references `{{missing_1.text}}`; ask: “这个 workflow 为什么运行时报错？”
3. LLM node references a disabled provider; ask: “为什么模型调用失败？”
4. TTS node reads `{{llm_1.json}}` where the LLM returns an object; ask: “这个能直接转语音吗？”
5. End node answer references `{{rag_2.context}}` but only `rag_1` exists; ask: “最终输出为什么为空？”
6. If-Else node has no default branch; ask: “如果条件都不匹配会怎样？”
7. Iteration node has `inputRef` pointing to a string field; ask: “循环节点为什么报错？”
8. Workflow has two LLM nodes but the second prompt ignores the first output; ask: “第二个节点真的用了前面的结果吗？”
9. Latest run failed at `tts_1`; ask: “昨天那次运行失败在哪里？”
10. Provider list has no TTS provider; ask: “我能生成音频吗？”
