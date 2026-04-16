import type { NodeProps } from 'reactflow'

import { NodeCard } from './NodeCard'
import type { WorkflowNodeData } from '../../types/workflow'

export function TTSNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <NodeCard
      data={data}
      selected={selected}
      accent="yellow"
      icon="🎙"
      title="TTS 音频合成"
      subtitle="把脚本转成播客音频"
    />
  )
}
