import type { NodeProps } from 'reactflow'

import { NodeCard } from './NodeCard'
import type { WorkflowNodeData } from '../../types/workflow'

export function LLMNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  const providerName = (data.config?.provider as string) || 'provider'
  const modelName = (data.config?.model as string) || 'gpt-4o'

  return (
    <NodeCard
      data={data}
      selected={selected}
      accent="purple"
      icon="🧠"
      title="LLM 对话"
      subtitle={`${providerName} / ${modelName}`}
    />
  )
}
