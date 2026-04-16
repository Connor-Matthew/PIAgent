import { useMemo } from 'react'
import { useDebugStore } from '../../stores/debugStore'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useSSE } from '../../hooks/useSSE'
import { workflowApi } from '../../services/api'
import { ExecutionTimeline } from './ExecutionTimeline'
import { AudioPlayer } from './AudioPlayer'
import type { StartInputField } from '../../types/workflow'

export function DebugDrawer() {
  const {
    isOpen, mode, isRunning, inputText, runInputs,
    finalAnswer, finalOutputs,
    toggleDrawer, setMode, setInputText, setRunInput, startRun,
  } = useDebugStore()
  const { workflowId, workflowName, nodes, toGraphJSON } = useWorkflowStore()
  const { connect } = useSSE()

  const startNode = useMemo(() => {
    return nodes.find((n) => n.data.nodeType === 'start')
  }, [nodes])

  const startInputs = useMemo<StartInputField[]>(() => {
    const config = startNode?.data.config || {}
    return (config.inputs as StartInputField[]) || []
  }, [startNode])

  if (!isOpen) return null

  const handleRun = async () => {
    if (!workflowId) return
    startRun()

    // Auto-save workflow before running
    try {
      await workflowApi.update(workflowId, {
        name: workflowName,
        graph: toGraphJSON(),
      })
    } catch (e) {
      // Continue running even if save fails
      console.warn('Auto-save failed:', e)
    }

    let payload: { input?: string; inputs?: Record<string, unknown> }
    if (startInputs.length > 0) {
      // Build inputs dict; include inputText as fallback "input" key
      const inputs: Record<string, unknown> = { ...runInputs }
      if (inputText.trim()) inputs.input = inputText.trim()
      payload = { inputs }
    } else {
      payload = { input: inputText.trim() }
    }

    const result = await workflowApi.run(workflowId, payload)
    connect(workflowId, result.run_id)
  }

  const canRun = startInputs.length > 0
    ? !isRunning && startInputs.every((f) => !f.required || (runInputs[f.name] !== undefined && runInputs[f.name] !== ''))
    : !isRunning && !!inputText.trim()

  return (
    <div className="border-t border-slate-700 bg-slate-900 shrink-0" style={{ height: '40vh' }}>
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
        {/* Input Form */}
        <div className="w-[300px] p-4 border-r border-slate-800 overflow-y-auto">
          {startInputs.length === 0 ? (
            <>
              <div className="text-xs text-slate-400 mb-2">输入文本</div>
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="请输入播客主题..."
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm text-slate-200 resize-none h-24"
              />
            </>
          ) : (
            <>
              <div className="text-xs text-slate-400 mb-2">工作流输入</div>
              <div className="space-y-3">
                {startInputs.map((field) => (
                  <label key={field.name} className="block">
                    <span className="text-xs text-slate-300 block mb-1">
                      {field.name}
                      {field.required && <span className="text-red-400 ml-1">*</span>}
                    </span>
                    {field.type === 'select' ? (
                      <select
                        value={(runInputs[field.name] as string) || (field.default as string) || ''}
                        onChange={(e) => setRunInput(field.name, e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      >
                        <option value="">请选择</option>
                        {(field.options || []).map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    ) : field.type === 'number' ? (
                      <input
                        type="number"
                        value={(runInputs[field.name] as number | string) ?? (field.default ?? '')}
                        onChange={(e) => setRunInput(field.name, e.target.value === '' ? '' : Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      />
                    ) : (
                      <input
                        type={field.type === 'file' ? 'file' : 'text'}
                        value={field.type === 'file' ? undefined : ((runInputs[field.name] as string) ?? (field.default as string) ?? '')}
                        onChange={(e) => setRunInput(field.name, e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      />
                    )}
                  </label>
                ))}
              </div>
              {/* Fallback plain input if user still wants free text */}
              <div className="mt-4 pt-3 border-t border-slate-800">
                <div className="text-xs text-slate-500 mb-1">附加输入（可选）</div>
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="额外补充文本..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-sm text-slate-200 resize-none h-16"
                />
              </div>
            </>
          )}
          <button
            onClick={handleRun}
            disabled={!canRun}
            className="w-full mt-3 bg-blue-500 text-white rounded-lg py-2 text-sm hover:bg-blue-600 disabled:opacity-50"
          >
            {isRunning ? '运行中...' : '▶ 开始运行'}
          </button>
        </div>

        {/* Timeline (detailed mode only) */}
        {mode === 'detailed' && <ExecutionTimeline />}

        {/* Final Output */}
        <div className="w-[320px] p-4 border-l border-slate-800 overflow-y-auto">
          <div className="text-xs text-slate-400 mb-3">最终输出</div>

          {finalAnswer !== null && (
            <div className="bg-slate-950 border border-slate-700 rounded-lg p-3 mb-3">
              <div className="text-xs text-slate-500 mb-1">回答内容</div>
              <div className="text-sm text-slate-200 whitespace-pre-wrap">{finalAnswer}</div>
            </div>
          )}

          {finalOutputs !== null && (
            <details className="bg-slate-950 border border-slate-700 rounded-lg mb-3 group" open={Object.keys(finalOutputs).length > 0}>
              <summary className="px-3 py-2 text-xs text-slate-400 cursor-pointer select-none hover:text-slate-300">
                结构化输出 (JSON)
              </summary>
              <pre className="px-3 pb-3 text-xs text-slate-300 overflow-x-auto">
                {JSON.stringify(finalOutputs, null, 2)}
              </pre>
            </details>
          )}

          <AudioPlayer />

          {finalAnswer === null && finalOutputs === null && !isRunning && (
            <div className="text-sm text-slate-600 text-center mt-8">等待工作流执行完成...</div>
          )}
        </div>
      </div>
    </div>
  )
}
