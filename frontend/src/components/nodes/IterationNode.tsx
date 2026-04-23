import type { NodeProps } from 'reactflow'
import { Handle, Position } from 'reactflow'
import type { WorkflowNodeData } from '../../types/workflow'

export function IterationNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  const inputRef = (data.config?.inputRef as string) || ''
  const maxConcurrency = (data.config?.maxConcurrency as number) || 1
  const errorStrategy = (data.config?.errorStrategy as string) || 'fail_fast'

  return (
    <div
      className={[
        'min-w-[200px] border-2 bg-white px-4 py-3 backdrop-blur transition-all duration-300',
        selected ? 'border-black' : 'border-gray-700',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="bg-gray-700 flex h-6 w-6 items-center justify-center text-xs text-white">
          ↻
        </span>
        <div>
          <div className="text-sm font-semibold text-gray-900">Iteration</div>
          <div className="text-[11px] text-gray-500">循环迭代</div>
        </div>
      </div>

      {inputRef && (
        <div className="mb-1.5 text-[11px] text-gray-600 truncate max-w-[180px]">
          {inputRef}
        </div>
      )}

      <div className="flex items-center gap-2 text-[10px] text-gray-600">
        <span className="bg-gray-100 px-1.5 py-0.5">
          {maxConcurrency > 1 ? `并发 ${maxConcurrency}` : '串行'}
        </span>
        <span className="bg-gray-100 px-1.5 py-0.5">
          {errorStrategy === 'fail_fast' ? '快速失败' : errorStrategy === 'continue' ? '继续' : '忽略错误'}
        </span>
      </div>

      <Handle type="target" position={Position.Left} className="!bg-gray-700 !h-3 !w-3" />
      <Handle type="source" position={Position.Right} className="!bg-gray-700 !h-3 !w-3" />
    </div>
  )
}
