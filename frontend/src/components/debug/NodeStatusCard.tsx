import type { NodeExecutionState } from '../../types/workflow'

export function NodeStatusCard({ state }: { state: NodeExecutionState }) {
  const statusIcon = {
    pending: '○',
    running: '⟳',
    completed: '✓',
    failed: '✗',
  }[state.status]

  const statusColor = {
    pending: 'text-gray-400',
    running: 'text-purple-600',
    completed: 'text-green-600',
    failed: 'text-red-600',
  }[state.status]

  const borderColor = {
    pending: 'border-gray-200',
    running: 'border-purple-200',
    completed: 'border-green-200',
    failed: 'border-red-200',
  }[state.status]

  return (
    <div className={`bg-white border ${borderColor} p-3 mb-2`}>
      <div className="flex justify-between items-center mb-1">
        <div className="flex items-center gap-2">
          <span className={`${statusColor} ${state.status === 'running' ? 'animate-spin' : ''}`}>
            {statusIcon}
          </span>
          <span className="text-gray-900 text-sm font-medium">{state.nodeId}</span>
          {state.status === 'running' && state.chunks.length > 0 && (
            <span className="bg-purple-100 text-purple-700 text-[10px] px-1.5 py-0.5">
              streaming
            </span>
          )}
          {state.status === 'running' && state.progressLabel && (
            <span className="bg-gray-100 text-gray-700 text-[10px] px-1.5 py-0.5">
              {state.progressLabel}
            </span>
          )}
        </div>
        {state.duration && (
          <span className="text-gray-400 text-xs">{state.duration}s</span>
        )}
      </div>
      {state.heartbeatMessage && (
        <div className="text-[11px] text-gray-500 mb-1">
          {state.heartbeatMessage}
          {typeof state.heartbeatElapsed === 'number' ? ` (${state.heartbeatElapsed}s)` : ''}
        </div>
      )}
      {state.chunks.length > 0 && (
        <div className="text-xs text-purple-700 bg-gray-50 p-2 mt-1 max-h-16 overflow-hidden">
          {state.chunks.join('')}
        </div>
      )}
      {state.output && (
        <div className="text-xs text-gray-600 bg-gray-50 p-2 mt-1 max-h-24 overflow-auto whitespace-pre-wrap">
          {state.output}
        </div>
      )}
    </div>
  )
}
