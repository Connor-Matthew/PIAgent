import type { NodeProps } from 'reactflow'

import { NodeCard } from './NodeCard'
import type { WorkflowNodeData } from '../../types/workflow'

export function StartNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <NodeCard
      data={data}
      selected={selected}
      accent="blue"
      icon="入"
      title="用户输入"
      subtitle="入口节点"
      targetHandle={false}
      sourceHandle
    />
  )
}
