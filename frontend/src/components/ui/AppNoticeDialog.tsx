interface AppNoticeDialogProps {
  title: string
  message: string
  actionLabel?: string
  onClose: () => void
}

export function AppNoticeDialog({
  title,
  message,
  actionLabel = '我知道了',
  onClose,
}: AppNoticeDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="app-notice-dialog-title"
    >
      <div className="w-full max-w-sm border border-black bg-white p-5 shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
        <h3 id="app-notice-dialog-title" className="text-base font-semibold text-gray-900">
          {title}
        </h3>
        <p className="mt-2 text-sm leading-6 text-gray-500">{message}</p>
        <div className="mt-5 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm bg-black text-white hover:bg-gray-800"
          >
            {actionLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
