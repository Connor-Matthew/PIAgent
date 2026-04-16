import { useMemo, useState } from 'react'

import { useAgentAutoRun } from '../../hooks/useAgentAutoRun'
import { useAgentSession } from '../../hooks/useAgentSession'
import { ApplyDraftButton } from './ApplyDraftButton'
import { AutoRunStatus } from './AutoRunStatus'
import { ClarificationBubble } from './ClarificationBubble'
import { PlannerStatus } from './PlannerStatus'

export function AgentStatusPanel() {
  const [answer, setAnswer] = useState('')
  const {
    autoRunEvents,
    autoRunError,
    isAutoRunning,
  } = useAgentAutoRun()
  const {
    session,
    events,
    isBusy,
    isStreaming,
    error,
    answerSession,
    skipSession,
    applySession,
  } = useAgentSession()

  const latestQuestion = useMemo(() => {
    if (!session?.clarification_turns?.length) return null
    return session.clarification_turns[session.clarification_turns.length - 1]
  }, [session])

  const handleAnswer = () => {
    if (!answer.trim()) return
    void answerSession(answer.trim())
      .then(() => {
        setAnswer('')
      })
      .catch(() => undefined)
  }

  const handleApply = () => {
    void applySession().catch(() => undefined)
  }

  const hasContent = isAutoRunning || autoRunEvents.length > 0 || session || error

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {!hasContent && (
        <div className="text-sm text-slate-500 text-center mt-8">
          暂无 Agent 活动。在顶部输入目标并点击“生成草案”或“一键搭图并运行”。
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">
          {error}
        </div>
      )}

      <AutoRunStatus
        events={autoRunEvents}
        isRunning={isAutoRunning}
        error={autoRunError}
      />

      {session && (
        <>
          <PlannerStatus session={session} events={events} isStreaming={isStreaming} />

          {session && (session.status === 'ready' || session.status === 'applied') && (
            <div className="flex justify-end pt-1">
              <ApplyDraftButton
                disabled={isBusy || isAutoRunning}
                workflowId={session.workflow_id}
                onApply={handleApply}
              />
            </div>
          )}

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
  )
}
