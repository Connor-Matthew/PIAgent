import { AppNoticeDialog } from '../ui/AppNoticeDialog'

interface ConfirmDialogProps {
  mode: 'confirm'
  workflowName: string
  isDeleting: boolean
  onCancel: () => void
  onConfirm: () => void
}

interface ErrorDialogProps {
  mode: 'error'
  errorMessage: string
  onClose: () => void
}

type WorkflowDeleteDialogProps = ConfirmDialogProps | ErrorDialogProps

export function WorkflowDeleteDialog(props: WorkflowDeleteDialogProps) {
  const isConfirm = props.mode === 'confirm'

  if (!isConfirm) {
    return (
      <AppNoticeDialog
        title="删除失败"
        message={props.errorMessage}
        onClose={props.onClose}
      />
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="workflow-delete-dialog-title"
    >
      <div className="w-full max-w-sm border border-black bg-white p-5 shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
        <h3
          id="workflow-delete-dialog-title"
          className="text-base font-semibold text-gray-900"
        >
          确认删除
        </h3>

        <p className="mt-2 text-sm leading-6 text-gray-500">
          确认删除工作流 <span className="font-medium text-gray-900">"{props.workflowName}"</span>？
          此操作不可撤销。
        </p>

        <div className="mt-5 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={props.onCancel}
            disabled={props.isDeleting}
            className="px-4 py-2 text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={props.onConfirm}
            disabled={props.isDeleting}
            className="px-4 py-2 text-sm bg-red-600 text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {props.isDeleting ? '删除中...' : '删除'}
          </button>
        </div>
      </div>
    </div>
  )
}
