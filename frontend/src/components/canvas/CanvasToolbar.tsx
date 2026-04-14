import { useDebugStore } from '../../stores/debugStore'

export function CanvasToolbar() {
  const toggleDrawer = useDebugStore((s) => s.toggleDrawer)

  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2 flex gap-4 items-center z-10">
      <button
        onClick={toggleDrawer}
        className="bg-blue-500 text-white text-sm px-3 py-1 rounded-md hover:bg-blue-600"
      >
        ▶ 调试
      </button>
    </div>
  )
}
