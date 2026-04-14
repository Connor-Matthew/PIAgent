import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function RAGNode({ selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[170px] ${selected ? 'border-green-400' : 'border-green-500'}`}>
      <div className="flex items-center gap-2">
        <span className="bg-green-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">📚</span>
        <span className="text-slate-100 text-sm font-semibold">RAG 知识检索</span>
      </div>
      <Handle type="target" position={Position.Left} className="!bg-green-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} className="!bg-green-500 !w-3 !h-3" />
    </div>
  )
}
