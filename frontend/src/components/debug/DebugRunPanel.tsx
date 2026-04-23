import { useMemo } from 'react'
import { useDebugStore } from '../../stores/debugStore'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useSSE } from '../../hooks/useSSE'
import { workflowApi } from '../../services/api'
import { ExecutionTimeline } from './ExecutionTimeline'
import { AudioPlayer } from './AudioPlayer'
import type { StartInputField } from '../../types/workflow'

export function DebugRunPanel() {
  const {
    mode, isRunning, inputText, runInputs,
    finalAnswer, finalOutputs,
    workflowId: activeWorkflowId,
    runId: activeRunId,
    setMode, setInputText, setRunInput, startRun, attachRun, markStopped,
  } = useDebugStore()
  const { workflowId, workflowName, nodes, toGraphJSON } = useWorkflowStore()
  const { connect, disconnect } = useSSE()

  const startNode = useMemo(() => {
    return nodes.find((n) => n.data.nodeType === 'start')
  }, [nodes])

  const startInputs = useMemo<StartInputField[]>(() => {
    const config = startNode?.data.config || {}
    const raw = config.inputs
    return Array.isArray(raw) ? (raw as StartInputField[]) : []
  }, [startNode])

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
      const inputs: Record<string, unknown> = { ...runInputs }
      if (inputText.trim()) inputs.input = inputText.trim()
      payload = { inputs }
    } else {
      payload = { input: inputText.trim() }
    }

    const result = await workflowApi.run(workflowId, payload)
    if (!useDebugStore.getState().isRunning) {
      await workflowApi.stopRun(workflowId, result.run_id).catch(() => undefined)
      return
    }
    attachRun(workflowId, result.run_id)
    connect(workflowId, result.run_id)
  }

  const handleStop = async () => {
    if (activeWorkflowId && activeRunId) {
      await workflowApi.stopRun(activeWorkflowId, activeRunId).catch(() => undefined)
    }
    disconnect()
    markStopped('已手动停止执行')
  }

  const canRun = startInputs.length > 0
    ? !isRunning && !!workflowId && startInputs.every((f) => !f.required || (runInputs[f.name] !== undefined && runInputs[f.name] !== ''))
    : !isRunning && !!workflowId && !!inputText.trim()

  return (
    <div className="h-full flex flex-col">
      {/* Input Section */}
      <div className="p-4 border-b border-gray-200 space-y-3 shrink-0">
        {startInputs.length === 0 ? (
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="请输入播客主题..."
            className="w-full bg-white border border-gray-200 p-3 text-sm text-gray-900 resize-none h-20 focus:border-black focus:outline-none"
          />
        ) : (
          <div className="space-y-2 max-h-44 overflow-y-auto">
            <div className="text-xs text-gray-500 mb-1">工作流输入</div>
            {startInputs.map((field) => (
              <label key={field.name} className="block">
                <span className="text-xs text-gray-700 block mb-1">
                  {field.name}
                  {field.required && <span className="text-red-600 ml-1">*</span>}
                </span>
                {field.type === 'select' ? (
                  <select
                    value={(runInputs[field.name] as string) || (field.default as string) || ''}
                    onChange={(e) => setRunInput(field.name, e.target.value)}
                    className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
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
                    className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                  />
                ) : (
                  <input
                    type={field.type === 'file' ? 'file' : 'text'}
                    value={field.type === 'file' ? undefined : ((runInputs[field.name] as string) ?? (field.default as string) ?? '')}
                    onChange={(e) => setRunInput(field.name, e.target.value)}
                    className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                  />
                )}
              </label>
            ))}
            <div className="pt-2 border-t border-gray-200">
              <div className="text-xs text-gray-400 mb-1">附加输入（可选）</div>
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="额外补充文本..."
                className="w-full bg-white border border-gray-200 p-2 text-sm text-gray-900 resize-none h-12 focus:border-black focus:outline-none"
              />
            </div>
          </div>
        )}
        <div className="flex gap-2">
          <button
            onClick={handleRun}
            disabled={!canRun}
            className="flex-1 bg-red-600 text-white py-2 text-sm hover:bg-red-700 disabled:opacity-50"
          >
            {isRunning ? '运行中...' : '▶ 开始运行'}
          </button>
          {isRunning && (
            <button
              onClick={() => {
                void handleStop()
              }}
              className="border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 hover:bg-red-100"
            >
              停止执行
            </button>
          )}
        </div>

        {/* Mode toggle */}
        <div className="flex gap-2">
          <button
            onClick={() => setMode('simple')}
            className={`flex-1 text-xs px-2 py-1.5 ${mode === 'simple' ? 'bg-black text-white' : 'bg-gray-100 text-gray-500'}`}
          >
            简洁
          </button>
          <button
            onClick={() => setMode('detailed')}
            className={`flex-1 text-xs px-2 py-1.5 ${mode === 'detailed' ? 'bg-black text-white' : 'bg-gray-100 text-gray-500'}`}
          >
            详细
          </button>
        </div>
      </div>

      {/* Scrollable output */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {mode === 'detailed' && <ExecutionTimeline />}

        {finalAnswer !== null && (
          <div className="bg-white border border-gray-200 p-3">
            <div className="text-xs text-gray-400 mb-1">回答内容</div>
            <div className="text-sm text-gray-900 whitespace-pre-wrap">{finalAnswer}</div>
          </div>
        )}

        {finalOutputs !== null && (
          <details className="bg-white border border-gray-200 group" open={Object.keys(finalOutputs).length > 0}>
            <summary className="px-3 py-2 text-xs text-gray-500 cursor-pointer select-none hover:text-gray-700">
              结构化输出 (JSON)
            </summary>
            <pre className="px-3 pb-3 text-xs text-gray-700 overflow-x-auto">
              {JSON.stringify(finalOutputs, null, 2)}
            </pre>
          </details>
        )}

        <AudioPlayer />

        {finalAnswer === null && finalOutputs === null && !isRunning && (
          <div className="text-sm text-gray-400 text-center mt-8">等待工作流执行完成...</div>
        )}
      </div>
    </div>
  )
}
