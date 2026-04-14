import { useDebugStore } from '../../stores/debugStore'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useSSE } from '../../hooks/useSSE'
import { workflowApi } from '../../services/api'
import { ExecutionTimeline } from './ExecutionTimeline'
import { AudioPlayer } from './AudioPlayer'

export function DebugDrawer() {
  const {
    isOpen, mode, isRunning, inputText,
    toggleDrawer, setMode, setInputText, startRun,
  } = useDebugStore()
  const { workflowId } = useWorkflowStore()
  const { connect } = useSSE()

  if (!isOpen) return null

  const handleRun = async () => {
    if (!workflowId || !inputText.trim()) return
    startRun()

    const result = await workflowApi.run(workflowId, inputText)
    connect(workflowId, result.run_id)
  }

  return (
    <div className="border-t border-slate-700 bg-slate-900" style={{ height: '40vh' }}>
      {/* Header */}
      <div className="bg-slate-800 px-5 py-3 flex justify-between items-center border-b border-slate-700">
        <div className="flex items-center gap-3">
          <span className="text-slate-100 text-sm font-semibold">调试运行</span>
          <div className="flex gap-1">
            <button
              onClick={() => setMode('simple')}
              className={`text-xs px-2.5 py-1 rounded ${mode === 'simple' ? 'bg-blue-500 text-white' : 'bg-slate-900 text-slate-400'}`}
            >
              简洁
            </button>
            <button
              onClick={() => setMode('detailed')}
              className={`text-xs px-2.5 py-1 rounded ${mode === 'detailed' ? 'bg-blue-500 text-white' : 'bg-slate-900 text-slate-400'}`}
            >
              详细
            </button>
          </div>
        </div>
        <button onClick={toggleDrawer} className="text-slate-500 hover:text-slate-300 text-lg">✕</button>
      </div>

      {/* Body */}
      <div className="flex h-[calc(100%-48px)]">
        {/* Input */}
        <div className="w-[300px] p-4 border-r border-slate-800">
          <div className="text-xs text-slate-400 mb-2">输入文本</div>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="请输入播客主题..."
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm text-slate-200 resize-none h-24"
          />
          <button
            onClick={handleRun}
            disabled={isRunning || !inputText.trim()}
            className="w-full mt-3 bg-blue-500 text-white rounded-lg py-2 text-sm hover:bg-blue-600 disabled:opacity-50"
          >
            {isRunning ? '运行中...' : '▶ 开始运行'}
          </button>
        </div>

        {/* Timeline (detailed mode only) */}
        {mode === 'detailed' && <ExecutionTimeline />}

        {/* Audio output */}
        <AudioPlayer />
      </div>
    </div>
  )
}
