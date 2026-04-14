import { Handle, Position, type NodeProps } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function LLMNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  return (
    <div className={`bg-slate-800 border-2 rounded-xl px-4 py-3 min-w-[180px] ${selected ? 'border-purple-400' : 'border-purple-500'}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="bg-purple-500 text-white w-6 h-6 rounded flex items-center justify-center text-xs">🧠</span>
        <span className="text-slate-100 text-sm font-semibold">LLM 对话</span>
      </div>
      <div className="text-xs text-slate-400">
        {(data.config?.provider as string) || 'openai'} / {(data.config?.model as string) || 'gpt-4o'}
      </div>
      <Handle type="target" position={Position.Left} className="!bg-purple-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} className="!bg-purple-500 !w-3 !h-3" />
    </div>
  )
}
