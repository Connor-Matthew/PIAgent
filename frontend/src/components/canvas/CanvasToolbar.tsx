import { useDebugStore } from '../../stores/debugStore'

export function CanvasToolbar() {
  const openDrawer = useDebugStore((s) => s.openDrawer)
  const isExecuting = useDebugStore((s) => s.isRunning)

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-white/90 backdrop-blur border border-black px-4 py-2 flex gap-3 items-center z-10">
      {isExecuting && (
        <div className="bg-gray-100 px-2 py-1 text-[11px] text-gray-700">
          执行中
        </div>
      )}
      <button
        onClick={openDrawer}
        className="bg-red-600 text-white text-xs px-3 py-1.5 hover:bg-red-700"
      >
        运行面板
      </button>
    </div>
  )
}
