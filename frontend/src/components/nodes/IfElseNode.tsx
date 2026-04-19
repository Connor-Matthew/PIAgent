import type { NodeProps } from 'reactflow'
import { Handle, Position } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function IfElseNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  const branches = (data.config?.branches as Array<{ id: string; label?: string }> | undefined) || []
  const trueBranch = branches.find((b) => b.id === 'true')
  const falseBranch = branches.find((b) => b.id === 'false')

  return (
    <div
      className={[
        'min-w-[200px] rounded-xl border-2 bg-slate-800/95 px-4 py-3 backdrop-blur transition-all duration-300',
        selected ? 'border-amber-300' : 'border-amber-500',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="bg-amber-500 flex h-6 w-6 items-center justify-center rounded text-xs text-white">
          ◈
        </span>
        <div>
          <div className="text-sm font-semibold text-slate-100">If-Else</div>
          <div className="text-[11px] text-slate-400">条件分支</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-400">
        <div className="rounded bg-slate-900/60 px-2 py-1 text-center">
          {trueBranch?.label ?? '是'}
        </div>
        <div className="rounded bg-slate-900/60 px-2 py-1 text-center">
          {falseBranch?.label ?? '否'}
        </div>
      </div>

      <Handle type="target" position={Position.Left} className="!bg-amber-500 !h-3 !w-3" />
      <Handle
        type="source"
        position={Position.Right}
        id="true"
        className="!bg-emerald-500 !h-3 !w-3"
        style={{ top: '60%' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="false"
        className="!bg-rose-500 !h-3 !w-3"
        style={{ top: '80%' }}
      />
    </div>
  )
}
