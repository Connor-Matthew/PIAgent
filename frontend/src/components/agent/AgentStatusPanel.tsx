import { useHarnessStore } from '../../stores/harnessStore'
import { useHarnessSession } from '../../hooks/useHarnessSession'
import { ClarificationPrompt } from './ClarificationPrompt'
import { ApplyDraftButton } from './ApplyDraftButton'

const STATUS_LABELS: Record<string, string> = {
  idle: '等待中',
  running: '运行中',
  awaiting_user: '等待用户输入',
  ready: '草案已就绪',
  failed: '失败',
  applied: '已应用',
}

function getEventColor(type: string) {
  switch (type) {
    case 'session_start':
      return 'text-emerald-300 border-emerald-500/20 bg-emerald-500/5'
    case 'decision':
      return 'text-slate-200 border-slate-700/50 bg-slate-800/40'
    case 'tool_call':
      return 'text-violet-300 border-violet-500/20 bg-violet-500/5'
    case 'tool_result':
      return 'text-violet-300 border-violet-500/20 bg-violet-500/5'
    case 'skill_loaded':
      return 'text-cyan-300 border-cyan-500/20 bg-cyan-500/5'
    case 'graph_update':
      return 'text-blue-300 border-blue-500/20 bg-blue-500/5'
    case 'builder_error':
      return 'text-red-300 border-red-500/20 bg-red-500/5'
    case 'validator_report':
      return 'text-amber-300 border-amber-500/20 bg-amber-500/5'
    case 'awaiting_user_input':
      return 'text-cyan-300 border-cyan-500/20 bg-cyan-500/5'
    case 'user_resumed':
      return 'text-emerald-300 border-emerald-500/20 bg-emerald-500/5'
    case 'harness_ready':
      return 'text-emerald-300 border-emerald-500/20 bg-emerald-500/5'
    case 'harness_stuck':
      return 'text-red-300 border-red-500/20 bg-red-500/5'
    case 'llm_error':
      return 'text-amber-300 border-amber-500/20 bg-amber-500/5'
    case 'session_end':
      return 'text-slate-300 border-slate-700/30 bg-slate-900'
    default:
      return 'text-slate-300 border-slate-700/30 bg-slate-900'
  }
}

const DECISION_KIND_LABELS: Record<string, string> = {
  call_tool: '调用工具',
  load_skill: '加载技能',
  propose_action: '修改画布',
  ask_user: '询问用户',
  finalize: '提交草案',
}

function decisionLabel(kind?: string) {
  if (!kind) return '决定'
  return DECISION_KIND_LABELS[kind] || kind
}

function describeEvent(event: ReturnType<typeof useHarnessStore.getState>['events'][number]) {
  switch (event.type) {
    case 'session_start':
      return `会话启动: ${event.goal || ''}`
    case 'decision': {
      const label = decisionLabel(event.kind)
      const d = event.detail
      if (!d) return `决定 · ${label}`
      if (event.kind === 'call_tool' && d.tool) return `决定 · ${label}: ${d.tool}`
      if (event.kind === 'load_skill' && d.skill) return `决定 · ${label}: ${d.skill}`
      if (event.kind === 'propose_action' && d.action_kind) return `决定 · ${label}: ${d.action_kind}`
      if (event.kind === 'finalize') return `决定 · ${label}`
      if (event.kind === 'ask_user') return `决定 · ${label}`
      return `决定 · ${label}`
    }
    case 'tool_call':
      return `调用工具: ${event.tool || ''}`
    case 'tool_result':
      return event.ok === false
        ? `工具失败: ${event.tool || ''}`
        : `工具返回: ${event.tool || ''}`
    case 'skill_loaded':
      return `加载 Skill: ${event.skill || ''}`
    case 'graph_update': {
      const counts =
        event.node_count !== undefined && event.edge_count !== undefined
          ? ` · ${event.node_count} 节点 / ${event.edge_count} 边`
          : ''
      return `更新画布${counts}`
    }
    case 'builder_error':
      return `构建错误: ${event.message || ''}`
    case 'validator_report':
      return `校验报告`
    case 'awaiting_user_input':
      return `等待用户回答`
    case 'user_resumed':
      return `用户已回答`
    case 'harness_ready':
      return 'Harness 已完成'
    case 'harness_stuck':
      return `卡住: ${event.reason || ''}`
    case 'llm_error':
      return `LLM 调用失败${event.recoverable ? '（已重试）' : ''}`
    case 'session_end':
      return `会话结束: ${event.status || ''}`
    default:
      return event.type
  }
}

function formatJSON(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function EventDetail({ event }: { event: ReturnType<typeof useHarnessStore.getState>['events'][number] }) {
  if (event.type === 'decision' && event.detail) {
    const d = event.detail
    if (event.kind === 'call_tool') {
      return (
        <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-slate-300">
{`tool: ${d.tool}
args: ${formatJSON(d.args ?? {})}`}
        </pre>
      )
    }
    if (event.kind === 'propose_action' && d.action) {
      return (
        <div className="mt-1 space-y-1">
          {d.summary && (
            <div className="font-mono text-[11px] text-blue-200">{d.summary}</div>
          )}
          <pre className="max-h-40 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-slate-300">
{formatJSON(d.action)}
          </pre>
        </div>
      )
    }
    if (event.kind === 'load_skill' && d.skill) {
      return <div className="mt-1 font-mono text-[11px] text-cyan-200">{d.skill}</div>
    }
    if (event.kind === 'ask_user' && d.question) {
      return <div className="mt-1 text-[11px] opacity-80">{d.question}</div>
    }
    if (event.kind === 'finalize' && d.reason) {
      return <div className="mt-1 text-[11px] opacity-80">{d.reason}</div>
    }
  }

  if (event.type === 'tool_call' && event.args) {
    return (
      <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-slate-300">
{formatJSON(event.args)}
      </pre>
    )
  }

  if (event.type === 'graph_update') {
    return (
      <div className="mt-1 space-y-1">
        {event.summary && (
          <div className="font-mono text-[11px] text-blue-200">{event.summary}</div>
        )}
        {event.action && (
          <pre className="max-h-32 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-slate-300">
{formatJSON(event.action)}
          </pre>
        )}
      </div>
    )
  }

  if (event.type === 'skill_loaded' && event.snippet) {
    return (
      <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-cyan-100/80 whitespace-pre-wrap">
{event.snippet}
      </pre>
    )
  }

  if (event.type === 'tool_result' && event.summary) {
    return (
      <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap">
{event.summary}
      </pre>
    )
  }

  if (event.type === 'llm_error') {
    return (
      <div className="mt-1 text-[11px] opacity-80">
        {event.phase ? `[${event.phase}] ` : ''}
        {event.message}
      </div>
    )
  }

  return null
}

function EventItem({ event }: { event: ReturnType<typeof useHarnessStore.getState>['events'][number] }) {
  const header = describeEvent(event)
  const colorClass = getEventColor(event.type)

  return (
    <div className={`rounded-xl border px-3 py-2 text-xs ${colorClass}`}>
      <div className="font-medium">{header}</div>
      <EventDetail event={event} />
      {event.message && event.type !== 'builder_error' && event.type !== 'llm_error' && (
        <div className="mt-1 text-[11px] opacity-80">{event.message}</div>
      )}
      {event.findings && event.findings.length > 0 && (
        <div className="mt-1 space-y-1">
          {event.findings.map((f, i) => (
            <div key={i} className={`text-[11px] ${f.severity === 'error' ? 'text-red-300' : 'text-amber-300'}`}>
              [{f.code}] {f.message}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function AgentStatusPanel() {
  const {
    sessionId,
    status,
    events,
    error,
    openQuestion,
    goal,
    isRunning,
  } = useHarnessStore()

  const {
    resumeSession,
    applySession,
    abortSession,
    isConnecting,
  } = useHarnessSession({ autoConnect: false })

  const hasContent = sessionId || events.length > 0 || error

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {!hasContent && (
        <div className="text-sm text-slate-500 text-center mt-8">
          暂无 Agent 活动。在顶部输入目标并点击"生成工作流"。
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">
          {error}
        </div>
      )}

      {sessionId && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-400/80">Harness</div>
              <div className="mt-1 text-sm font-medium text-slate-100 truncate">{goal || '未命名目标'}</div>
            </div>
            <div className="flex items-center gap-2">
              {isRunning && (
                <button
                  onClick={() => abortSession()}
                  className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-100 hover:bg-rose-500/20"
                >
                  中止
                </button>
              )}
              <div className={`rounded-full border px-2 py-1 text-[11px] ${
                status === 'running' ? 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100' :
                status === 'awaiting_user' ? 'border-amber-500/30 bg-amber-500/10 text-amber-100' :
                status === 'ready' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100' :
                status === 'failed' ? 'border-red-500/30 bg-red-500/10 text-red-100' :
                'border-slate-700/50 bg-slate-800/60 text-slate-300'
              }`}>
                {STATUS_LABELS[status] || status}
              </div>
            </div>
          </div>

          {isConnecting && (
            <div className="mt-3 text-xs text-slate-400">正在连接 SSE...</div>
          )}
        </div>
      )}

      {openQuestion && status === 'awaiting_user' && (
        <ClarificationPrompt
          question={openQuestion}
          disabled={isConnecting}
          onSubmit={(questionId, answer) => {
            void resumeSession(questionId, answer).catch(() => undefined)
          }}
        />
      )}

      {status === 'ready' && (
        <div className="flex justify-end pt-1">
          <ApplyDraftButton
            disabled={isConnecting || isRunning}
            onApply={() => {
              void applySession().catch(() => undefined)
            }}
          />
        </div>
      )}

      {events.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Trace</div>
            <div className="text-[11px] text-slate-600">{events.length} 个事件</div>
          </div>
          <div className="mt-3 max-h-[360px] space-y-2 overflow-y-auto pr-1">
            {events.map((event, index) => (
              <EventItem key={`${event.type}-${index}`} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
