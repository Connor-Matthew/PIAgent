import { useState } from 'react'
import type { HarnessOpenQuestion } from '../../types/harness'

interface ClarificationPromptProps {
  question: HarnessOpenQuestion
  disabled?: boolean
  onSubmit: (questionId: string, answer: string) => void
}

export function ClarificationPrompt({ question, disabled, onSubmit }: ClarificationPromptProps) {
  const [answer, setAnswer] = useState('')

  const handleSubmit = () => {
    if (!answer.trim()) return
    onSubmit(question.question_id, answer.trim())
    setAnswer('')
  }

  return (
    <div className="rounded-2xl border border-cyan-500/20 bg-slate-950 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-cyan-400/80">需要澄清</div>
          <div className="mt-2 text-sm leading-6 text-slate-100">{question.prompt}</div>
        </div>
      </div>

      {question.options && question.options.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {question.options.map((opt) => (
            <button
              key={opt}
              onClick={() => onSubmit(question.question_id, opt)}
              disabled={disabled}
              className="rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 hover:border-cyan-500/40 hover:bg-slate-800 disabled:opacity-50"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-col gap-2 md:flex-row">
        <input
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="输入你的回答"
          className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSubmit()
            }
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !answer.trim()}
          className="rounded-xl bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
        >
          提交回答
        </button>
      </div>
    </div>
  )
}
