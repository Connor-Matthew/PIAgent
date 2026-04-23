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
        'min-w-[200px] border-2 bg-white px-4 py-3 backdrop-blur transition-all duration-300',
        selected ? 'border-black' : 'border-gray-700',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="bg-gray-700 flex h-6 w-6 items-center justify-center text-xs text-white">
          ◈
        </span>
        <div>
          <div className="text-sm font-semibold text-gray-900">If-Else</div>
          <div className="text-[11px] text-gray-500">条件分支</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px] text-gray-600">
        <div className="bg-gray-100 px-2 py-1 text-center">
          {trueBranch?.label ?? '是'}
        </div>
        <div className="bg-gray-100 px-2 py-1 text-center">
          {falseBranch?.label ?? '否'}
        </div>
      </div>

      <Handle type="target" position={Position.Left} className="!bg-gray-700 !h-3 !w-3" />
      <Handle
        type="source"
        position={Position.Right}
        id="true"
        className="!bg-gray-500 !h-3 !w-3"
        style={{ top: '60%' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="false"
        className="!bg-gray-500 !h-3 !w-3"
        style={{ top: '80%' }}
      />
    </div>
  )
}
