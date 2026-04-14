import { useDebugStore } from '../../stores/debugStore'
import { NodeStatusCard } from './NodeStatusCard'

export function ExecutionTimeline() {
  const nodeStates = useDebugStore((s) => s.nodeStates)

  return (
    <div className="flex-1 p-4 overflow-y-auto">
      <div className="text-xs text-slate-400 mb-3">执行链路</div>
      {Array.from(nodeStates.values()).map((state) => (
        <NodeStatusCard key={state.nodeId} state={state} />
      ))}
      {nodeStates.size === 0 && (
        <div className="text-sm text-slate-600 text-center mt-8">等待运行...</div>
      )}
    </div>
  )
}
