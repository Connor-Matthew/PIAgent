import type { NodeProps } from 'reactflow'

import { NodeCard } from './NodeCard'
import type { WorkflowNodeData } from '../../types/workflow'

export function AgentNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <NodeCard
      data={data}
      selected={selected}
      accent="pink"
      icon="🤖"
      title="ReAct Agent"
      subtitle="执行期工具调用"
    />
  )
}
