import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function StartNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[160px] ${selected ? 'border-blue-400' : 'border-blue-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-blue-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">入</span>
        <span className="text-slate-100 text-sm font-semibold">用户输入</span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-blue-500 !w-3 !h-3" />
    </div>
  )
}
