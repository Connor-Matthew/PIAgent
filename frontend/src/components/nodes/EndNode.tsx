import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function EndNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 ${selected ? 'border-slate-400' : 'border-slate-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-slate-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">⏹</span>
        <span className="text-slate-100 text-sm font-semibold">结束</span>
      </div>
      <Handle type="target" position={Position.Left} className="!bg-slate-500 !w-3 !h-3" />
    </div>
  )
}
