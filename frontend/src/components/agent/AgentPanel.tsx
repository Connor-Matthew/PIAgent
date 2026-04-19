import { useState } from 'react'

import { useHarnessSession } from '../../hooks/useHarnessSession'

export function AgentPanel() {
  const [goal, setGoal] = useState('')
  const {
    createSession,
    isConnecting,
    status,
  } = useHarnessSession()

  const isBusy = isConnecting || status === 'running' || status === 'awaiting_user'

  const handleCreateSession = () => {
    const trimmedGoal = goal.trim()
    if (!trimmedGoal) return
    void createSession(trimmedGoal).catch(() => undefined)
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
            disabled={isBusy || !goal.trim()}
            className="rounded-lg bg-cyan-400 px-4 py-2.5 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
          >
            {isBusy ? '生成中...' : '生成工作流'}
          </button>
        </div>
      </div>
    </div>
  )
}
