import type { AgentSession, AgentSessionEvent } from '../../types/agent'


const STATUS_LABELS: Record<AgentSession['status'], string> = {
  clarifying: '澄清中',
  generating: '生成中',
  ready: '草案已就绪',
  applied: '已应用',
  failed: '失败',
}


interface PlannerStatusProps {
  session: AgentSession
  events: AgentSessionEvent[]
  isStreaming: boolean
}


function formatAnsweredDims(answeredDims: Record<string, unknown>) {
  return Object.entries(answeredDims).map(([key, value]) => {
    if (typeof value === 'boolean') {
      return `${key}: ${value ? 'yes' : 'no'}`
    }
    return `${key}: ${String(value)}`
  })
}


export function PlannerStatus({ session, events, isStreaming }: PlannerStatusProps) {
  const answeredDimLabels = formatAnsweredDims(session.answered_dims || {})
  const graphSummary = session.generated_graph
    ? `${session.generated_graph.nodes.length} nodes / ${session.generated_graph.edges.length} edges`
    : '等待生成'
  const latestRepair = [...events].reverse().find((event) => event.type === 'recipe_repairing')
  const latestFallback = [...events].reverse().find((event) => event.type === 'recipe_fallback')
  const latestError = [...events].reverse().find((event) => event.type === 'agent_error')

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Planner</div>
          <div className="rounded-full border border-slate-800 bg-slate-900 px-2 py-1 text-[11px] text-slate-300">
            {STATUS_LABELS[session.status]}
          </div>
        </div>
        <div className="mt-3 text-sm text-slate-100">
          {session.recipe_ir?.recipe || '尚未选择 recipe'}
        </div>
        <div className="mt-2 text-xs text-slate-400">{graphSummary}</div>
        <div className="mt-2 text-xs text-slate-500">
          {isStreaming ? 'SSE 已连接' : 'SSE 未连接'}
        </div>
        {session.rationale_text && (
          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs leading-5 text-slate-300">
            {session.rationale_text}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
        <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Answered Dims</div>
        {answeredDimLabels.length > 0 ? (
          <div className="mt-3 space-y-2 text-xs text-slate-200">
            {answeredDimLabels.map((label) => (
              <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 px-3 py-2">
                {label}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 text-xs text-slate-400">尚未确认额外维度</div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
        <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Planner Trace</div>
        {latestRepair && (
          <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            repair #{latestRepair.attempt}: {(latestRepair.errors || []).join(' | ')}
          </div>
        )}
        {latestFallback && (
          <div className="mt-3 rounded-xl border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs text-blue-100">
            {latestFallback.message}
          </div>
        )}
        {latestError && (
          <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">
            {latestError.message}
          </div>
        )}
        {!latestRepair && !latestFallback && !latestError && (
          <div className="mt-3 text-xs text-slate-400">当前没有 repair / error 事件</div>
        )}
      </div>
    </div>
  )
}
