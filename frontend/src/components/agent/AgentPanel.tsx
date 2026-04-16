import { useMemo, useState } from 'react'

import { useAgentSession } from '../../hooks/useAgentSession'
import { ApplyDraftButton } from './ApplyDraftButton'
import { ClarificationBubble } from './ClarificationBubble'
import { PlannerStatus } from './PlannerStatus'


export function AgentPanel() {
  const [goal, setGoal] = useState('')
  const [answer, setAnswer] = useState('')
  const {
    session,
    events,
    isBusy,
    isStreaming,
    error,
    createSession,
    answerSession,
    skipSession,
    applySession,
  } = useAgentSession()

  const latestQuestion = useMemo(() => {
    if (!session?.clarification_turns?.length) return null
    return session.clarification_turns[session.clarification_turns.length - 1]
  }, [session])

  const handleCreateSession = async () => {
    const trimmedGoal = goal.trim()
    if (!trimmedGoal) return
    setAnswer('')
    try {
      await createSession(trimmedGoal)
    } catch {}
  }

  const handleAnswer = async () => {
    if (!answer.trim()) return
    try {
      await answerSession(answer.trim())
      setAnswer('')
    } catch {}
  }

  const handleApply = async () => {
    try {
      await applySession()
    } catch {}
  }

  return (
    <div className="shrink-0 border-b border-slate-800 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.16),_transparent_35%),linear-gradient(180deg,#020617_0%,#020617_100%)] px-4 py-4">
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="flex-1">
            <div className="text-xs uppercase tracking-[0.24em] text-cyan-400/80">Agent Mode</div>
            <div className="mt-2 text-sm text-slate-300">
              先澄清，再生成一张可编辑的 workflow 草案。
            </div>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="用一句话描述你想生成的工作流，比如：做一期介绍 Transformer 的播客"
              className="mt-3 h-24 w-full rounded-2xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCreateSession}
              disabled={isBusy || !goal.trim()}
              className="rounded-2xl bg-cyan-400 px-5 py-3 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
            >
              {isBusy ? '处理中...' : '生成草案'}
            </button>
            {session && (session.status === 'ready' || session.status === 'applied') && (
              <ApplyDraftButton
                disabled={isBusy}
                workflowId={session.workflow_id}
                onApply={handleApply}
              />
            )}
          </div>
        </div>

        {error && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        )}

        {session && (
          <>
            <PlannerStatus session={session} events={events} isStreaming={isStreaming} />

            {latestQuestion && session.status === 'clarifying' && (
              <ClarificationBubble
                turn={latestQuestion}
                answer={answer}
                disabled={isBusy}
                onAnswerChange={setAnswer}
                onSubmit={handleAnswer}
                onSkip={() => {
                  void skipSession().catch(() => undefined)
                }}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
