import type { NodeProps } from 'reactflow'

import { NodeCard } from './NodeCard'
import type { WorkflowNodeData } from '../../types/workflow'

export function RAGNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <NodeCard
      data={data}
      selected={selected}
      accent="green"
      icon="📚"
      title="RAG 知识检索"
      subtitle="为脚本注入上下文"
    />
  )
}
