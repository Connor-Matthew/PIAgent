import type { NodeExecutionState } from '../../types/workflow'

export function NodeStatusCard({ state }: { state: NodeExecutionState }) {
  const statusIcon = {
    pending: '○',
    running: '⟳',
    completed: '✓',
    failed: '✗',
  }[state.status]

  const statusColor = {
    pending: 'text-slate-500',
    running: 'text-purple-400',
    completed: 'text-green-400',
    failed: 'text-red-400',
  }[state.status]

  const borderColor = {
    pending: 'border-slate-800',
    running: 'border-purple-500/30',
    completed: 'border-green-500/30',
    failed: 'border-red-500/30',
  }[state.status]

  return (
    <div className={`bg-slate-950 border ${borderColor} rounded-lg p-3 mb-2`}>
      <div className="flex justify-between items-center mb-1">
        <div className="flex items-center gap-2">
          <span className={`${statusColor} ${state.status === 'running' ? 'animate-spin' : ''}`}>
            {statusIcon}
          </span>
          <span className="text-slate-200 text-sm font-medium">{state.nodeId}</span>
          {state.status === 'running' && state.chunks.length > 0 && (
            <span className="bg-purple-500/20 text-purple-400 text-[10px] px-1.5 py-0.5 rounded">
              streaming
            </span>
          )}
        </div>
        {state.duration && (
          <span className="text-slate-600 text-xs">{state.duration}s</span>
        )}
      </div>
      {state.chunks.length > 0 && (
        <div className="text-xs text-purple-300 bg-slate-800 rounded p-2 mt-1 max-h-16 overflow-hidden">
          {state.chunks.join('')}
        </div>
      )}
    </div>
  )
}
