import { useState } from 'react'

import { useAgentAutoRun } from '../../hooks/useAgentAutoRun'
import { useAgentSession } from '../../hooks/useAgentSession'

export function AgentPanel() {
  const [goal, setGoal] = useState('')
  const {
    autoRun,
    isAutoRunning,
  } = useAgentAutoRun()
  const {
    isBusy,
    createSession,
  } = useAgentSession()

  const handleCreateSession = () => {
    const trimmedGoal = goal.trim()
    if (!trimmedGoal) return
    void createSession(trimmedGoal).catch(() => undefined)
  }

  const handleAutoRun = () => {
    const trimmedGoal = goal.trim()
    if (!trimmedGoal) return
    void autoRun(trimmedGoal).catch(() => undefined)
  }

  return (
    <div className="shrink-0 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-4 py-3">
      <div className="mx-auto flex max-w-7xl items-center gap-3">
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="用一句话描述你想生成的工作流，比如：做一期介绍 Transformer 的播客"
          className="flex-1 min-w-0 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleCreateSession()
            }
          }}
        />
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleCreateSession}
            disabled={isBusy || isAutoRunning || !goal.trim()}
            className="rounded-lg bg-cyan-400 px-4 py-2.5 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
          >
            {isBusy ? '处理中...' : '生成草案'}
          </button>
          <button
            onClick={handleAutoRun}
            disabled={isBusy || isAutoRunning || !goal.trim()}
            className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-4 py-2.5 text-sm font-medium text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-50"
          >
            {isAutoRunning ? '可视化运行中...' : '一键搭图并运行'}
          </button>
        </div>
      </div>
    </div>
  )
}
