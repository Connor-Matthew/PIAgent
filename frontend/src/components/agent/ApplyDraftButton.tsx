interface ApplyDraftButtonProps {
  disabled?: boolean
  workflowId?: string | null
  onApply: () => void
}


export function ApplyDraftButton({ disabled, workflowId, onApply }: ApplyDraftButtonProps) {
  return (
    <button
      onClick={onApply}
      disabled={disabled}
      className="rounded-xl bg-emerald-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-300 disabled:opacity-50"
    >
      {workflowId ? '重新载入已应用工作流' : 'Apply 到工作流'}
    </button>
  )
}
