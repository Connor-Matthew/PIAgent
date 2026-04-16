import { useAutoRunStore } from '../../stores/autoRunStore'
import { useDebugStore } from '../../stores/debugStore'

export function CanvasToolbar() {
  const openDrawer = useDebugStore((s) => s.openDrawer)
  const isAutoRunning = useAutoRunStore((s) => s.isRunning)
  const autoRunError = useAutoRunStore((s) => s.error)
  const isExecuting = useDebugStore((s) => s.isRunning)

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-slate-800/90 backdrop-blur border border-slate-700 rounded-xl px-4 py-2 flex gap-3 items-center z-10 shadow-xl">
      {(isAutoRunning || isExecuting || autoRunError) && (
        <div
          className={`rounded-full px-2 py-1 text-[11px] ${
            isExecuting
              ? 'bg-sky-500/20 text-sky-100'
              : isAutoRunning
                ? 'bg-cyan-500/20 text-cyan-100'
                : 'bg-rose-500/20 text-rose-100'
          }`}
        >
          {isExecuting ? '执行中' : isAutoRunning ? '搭图中' : '出错'}
        </div>
      )}
      <button
        onClick={openDrawer}
        className="bg-blue-500 text-white text-xs px-3 py-1.5 rounded-md hover:bg-blue-600"
      >
        ▶ 运行面板
      </button>
    </div>
  )
}
