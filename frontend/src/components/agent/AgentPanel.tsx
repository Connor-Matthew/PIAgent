import { useEffect, useRef, useState } from 'react'

import { useHarnessSession } from '../../hooks/useHarnessSession'
import { useHarnessStore } from '../../stores/harnessStore'

export function AgentPanel() {
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const messages = useHarnessStore((s) => s.messages)
  const openQuestion = useHarnessStore((s) => s.openQuestion)
  const status = useHarnessStore((s) => s.status)
  const goal = useHarnessStore((s) => s.goal)

  const {
    createSession,
    resumeSession,
    continueSession,
    applySession,
    isConnecting,
  } = useHarnessSession()

  const isBusy = isConnecting || status === 'running'
  const hasSession = status !== 'idle'
  const canContinueSession = status === 'awaiting_user' || status === 'waiting' || status === 'ready'
  const canType = !isBusy && (!hasSession || canContinueSession)

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, openQuestion])

  const handleSubmit = () => {
    const trimmed = input.trim()
    if (!trimmed) return

    if (!hasSession) {
      void createSession(trimmed).catch(() => undefined)
    } else if (status === 'awaiting_user' && openQuestion) {
      void resumeSession(openQuestion.question_id, trimmed).catch(() => undefined)
    } else if (canContinueSession) {
      void continueSession(trimmed).catch(() => undefined)
    } else {
      return
    }
    setInput('')
  }

  const handleApply = async () => {
    const result = await applySession()
    if (result) {
      // Switch to config tab after apply
      // This is handled by the parent RightPanel; we just call apply
    }
  }

  return (
    <div className="flex flex-col h-full bg-slate-950/80">
      {/* Header */}
      <div className="shrink-0 px-3 py-2 border-b border-slate-800 flex items-center justify-between">
        <span className="text-xs font-medium text-slate-300">Builder Chat</span>
        {status !== 'idle' && (
          <span className={
            status === 'running' ? 'text-[10px] text-cyan-400 animate-pulse'
            : status === 'awaiting_user' ? 'text-[10px] text-amber-400'
            : status === 'waiting' ? 'text-[10px] text-slate-400'
            : status === 'ready' ? 'text-[10px] text-emerald-400'
            : status === 'failed' ? 'text-[10px] text-red-400'
            : 'text-[10px] text-slate-500'
          }>
            {status === 'running' ? '生成中...'
              : status === 'awaiting_user' ? (openQuestion ? '等待回答' : '等待输入')
              : status === 'waiting' ? '可继续'
              : status === 'ready' ? '已完成'
              : status === 'failed' ? '失败'
              : status}
          </span>
        )}
      </div>

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {messages.length === 0 && !goal && (
          <div className="text-slate-500 text-xs text-center py-6">
            描述你想构建的工作流，AI 将帮你搭建
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[90%] rounded-lg bg-cyan-400/10 border border-cyan-400/20 px-3 py-1.5 text-xs text-slate-100">
                  {msg.content}
                </div>
              </div>
            )
          }

          if (msg.role === 'agent') {
            return (
              <div key={msg.id} className="flex justify-start">
                <div className="max-w-[95%] rounded-lg bg-slate-800/60 border border-slate-700/50 px-3 py-1.5 text-xs text-slate-200 whitespace-pre-wrap leading-relaxed">
                  {msg.content || (
                    <span className="text-slate-500 italic">思考中...</span>
                  )}
                </div>
              </div>
            )
          }

          if (msg.role === 'tool_call') {
            return (
              <div key={msg.id} className="flex justify-center">
                <div className="max-w-[95%] rounded-md bg-slate-900/50 border border-slate-800 px-2 py-1 text-[10px] text-slate-400">
                  <span className="text-cyan-400/70">工具</span>{' '}
                  <span className="font-mono">{msg.tool}</span>
                  {msg.args && (
                    <details className="mt-0.5">
                      <summary className="cursor-pointer text-slate-600 text-[10px]">参数</summary>
                      <pre className="mt-0.5 text-[9px] text-slate-500 overflow-x-auto">
                        {JSON.stringify(msg.args, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            )
          }

          if (msg.role === 'tool_result') {
            return (
              <div key={msg.id} className="flex justify-center">
                <div className="max-w-[95%] rounded-md bg-slate-900/50 border border-slate-800 px-2 py-1 text-[10px] text-slate-400">
                  <span className="text-emerald-400/70">结果</span>{' '}
                  <span className="font-mono">{msg.tool}</span>
                  {msg.content && (
                    <details className="mt-0.5">
                      <summary className="cursor-pointer text-slate-600 text-[10px]">详情</summary>
                      <pre className="mt-0.5 text-[9px] text-slate-500 overflow-x-auto">
                        {msg.content.length > 200 ? msg.content.slice(0, 200) + '...' : msg.content}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            )
          }

          return null
        })}

        {/* Ask user question card */}
        {status === 'awaiting_user' && openQuestion && (
          <div className="flex justify-start">
            <div className="max-w-[95%] rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-amber-400/80 mb-1">需要澄清</div>
              <div className="text-xs text-slate-200">{openQuestion.prompt}</div>
              {openQuestion.options && openQuestion.options.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {openQuestion.options.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => {
                        if (openQuestion) {
                          void resumeSession(openQuestion.question_id, opt).catch(() => undefined)
                        }
                      }}
                      disabled={isBusy}
                      className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-200 hover:border-amber-500/40 hover:bg-slate-800 disabled:opacity-50"
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Ready state card */}
        {status === 'ready' && (
          <div className="flex justify-start">
            <div className="max-w-[95%] rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-emerald-400/80 mb-1">工作流已就绪</div>
              <div className="text-xs text-slate-200 mb-2">画布上的工作流已构建完成，可以应用或继续修改。</div>
              <div className="flex gap-2">
                <button
                  onClick={handleApply}
                  className="rounded-md bg-emerald-500/20 border border-emerald-500/30 px-3 py-1 text-[11px] text-emerald-300 hover:bg-emerald-500/30"
                >
                  应用 (Apply)
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-slate-800 px-3 py-2">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              status === 'awaiting_user' && openQuestion
                ? '回答上面的问题...'
                : status === 'waiting'
                  ? '继续补充或修改...'
                : status === 'ready'
                  ? '继续提出修改...'
                : '描述你想构建的工作流...'
            }
            disabled={!canType}
            className="flex-1 min-w-0 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400/60 disabled:opacity-50"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit()
              }
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={!canType || !input.trim()}
            className="rounded-md bg-cyan-400 px-3 py-1.5 text-xs font-medium text-slate-950 hover:bg-cyan-300 disabled:opacity-50 shrink-0"
          >
            {isBusy && status !== 'awaiting_user' ? '...' : status === 'awaiting_user' && openQuestion ? '回答' : '发送'}
          </button>
        </div>
      </div>
    </div>
  )
}
