import type { ClarificationTurn } from '../../types/agent'


interface ClarificationBubbleProps {
  turn: ClarificationTurn
  answer: string
  disabled?: boolean
  onAnswerChange: (value: string) => void
  onSubmit: () => void
  onSkip: () => void
}


export function ClarificationBubble({
  turn,
  answer,
  disabled,
  onAnswerChange,
  onSubmit,
  onSkip,
}: ClarificationBubbleProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-cyan-400/80">Clarify</div>
          <div className="mt-2 text-sm leading-6 text-slate-100">{turn.question}</div>
        </div>
        <div className="rounded-full border border-slate-800 bg-slate-900 px-2 py-1 text-[11px] text-slate-400">
          {turn.dim}
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-2 md:flex-row">
        <input
          value={answer}
          onChange={(e) => onAnswerChange(e.target.value)}
          placeholder="输入你的回答"
          className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
        />
        <button
          onClick={onSubmit}
          disabled={disabled || !answer.trim()}
          className="rounded-xl bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
        >
          提交回答
        </button>
        <button
          onClick={onSkip}
          disabled={disabled}
          className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-900 disabled:opacity-50"
        >
          跳过澄清
        </button>
      </div>
    </div>
  )
}
