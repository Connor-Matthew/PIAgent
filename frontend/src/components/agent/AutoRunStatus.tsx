import type { AgentAutoRunEvent } from '../../types/agent'


interface AutoRunStatusProps {
  events: AgentAutoRunEvent[]
  isRunning: boolean
  error: string | null
}


function describeEvent(event: AgentAutoRunEvent) {
  switch (event.type) {
    case 'planning_start':
      return '开始分析用户目标'
    case 'planning_update':
      return event.text || '规划中'
    case 'planner_action':
      return `执行动作: ${event.name}`
    case 'planner_observe':
      return event.summary || `完成观察: ${event.name}`
    case 'node_added':
      return `新增节点: ${String(event.node?.data?.label || event.node?.id || 'unknown')}`
    case 'edge_added':
      return `新增连线: ${event.edge?.source} -> ${event.edge?.target}`
    case 'node_config_updated':
      return `更新节点配置: ${event.node_id}`
    case 'workflow_built':
      return `构建完成: ${event.node_count || 0} nodes / ${event.edge_count || 0} edges`
    case 'plan_ready':
      return `规划完成: ${event.recipe?.recipe || 'workflow ready'}`
    case 'planning_error':
      return event.message || '规划失败'
    default:
      return event.type
  }
}


export function AutoRunStatus({ events, isRunning, error }: AutoRunStatusProps) {
  const latestBuilt = [...events].reverse().find((event) => event.type === 'workflow_built')
  const latestReady = [...events].reverse().find((event) => event.type === 'plan_ready')
  const visibleEvents = events.slice(-8)

  if (!isRunning && !error && events.length === 0) {
    return null
  }

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs uppercase tracking-[0.18em] text-cyan-400/80">Visual Auto Run</div>
          <div
            className={`rounded-full px-2 py-1 text-[11px] ${
              isRunning
                ? 'border border-cyan-500/30 bg-cyan-500/10 text-cyan-100'
                : error
                  ? 'border border-red-500/30 bg-red-500/10 text-red-100'
                  : 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
            }`}
          >
            {isRunning ? '构建中' : error ? '失败' : '已完成'}
          </div>
        </div>
        <div className="mt-3 text-sm text-slate-100">
          {latestReady?.recipe?.recipe || '等待规划结果'}
        </div>
        <div className="mt-2 text-xs text-slate-400">
          {latestBuilt
            ? `${latestBuilt.node_count || 0} nodes / ${latestBuilt.edge_count || 0} edges`
            : '尚未构建图结构'}
        </div>
        {error && (
          <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">
            {error}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4 md:col-span-2">
        <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Build Trace</div>
        {visibleEvents.length > 0 ? (
          <div className="mt-3 space-y-2">
            {visibleEvents.map((event, index) => (
              <div
                key={`${event.type}-${index}`}
                className="rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200"
              >
                {describeEvent(event)}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 text-xs text-slate-400">等待 agent 开始搭图</div>
        )}
      </div>
    </div>
  )
}
