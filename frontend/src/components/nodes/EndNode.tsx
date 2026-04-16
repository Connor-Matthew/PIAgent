import type { NodeProps } from 'reactflow'

import { NodeCard } from './NodeCard'
import type { WorkflowNodeData } from '../../types/workflow'

export function EndNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <NodeCard
      data={data}
      selected={selected}
      accent="slate"
      icon="⏹"
      title="结束"
      subtitle="产出最终回答"
      targetHandle
      sourceHandle={false}
    />
  )
}
